"""检查易混淆的抓包口径：同 IP 不同 VNI、SYN 重传与真实包数。"""
import importlib.util
from pathlib import Path
import socket
import struct
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("measure", Path(__file__).parents[1] / "measure.py")
measure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(measure)


def ipv4(payload, protocol, source="192.168.10.11", destination="192.168.10.12"):
    return struct.pack("!BBHHHBBH4s4s", 0x45, 0, 20 + len(payload), 0, 0,
                       64, protocol, 0, socket.inet_aton(source), socket.inet_aton(destination)) + payload


def tcp(flags, payload=b"", seq=17):
    return struct.pack("!HHIIBBHHH", 40001, 5201, seq, 0, 0x50, flags, 1000, 0, 0) + payload


def ethernet(payload, ethertype=0x800):
    return bytes(12) + struct.pack("!H", ethertype) + payload


def vxlan(inner, vni=100, source_port=45000):
    payload = b"\x08\0\0\0" + vni.to_bytes(3, "big") + b"\0" + inner
    udp = struct.pack("!HHHH", source_port, 4789, 8 + len(payload), 0) + payload
    return ethernet(ipv4(udp, 17, "10.0.1.1", "10.0.3.1"))


def write_capture(path, frames):
    with path.open("wb") as out:
        out.write(struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 262144, 1))
        for frame in frames:
            out.write(struct.pack("<IIII", 1, 0, len(frame), len(frame)) + frame)


class CaptureTests(unittest.TestCase):
    def test_vni_and_inner_flow_separate_data_from_noise(self):
        syn = vxlan(ethernet(ipv4(tcp(2), 6)))
        data = vxlan(ethernet(ipv4(tcp(24, b"abc"), 6)))
        frames = [syn, syn, data, data,
                  vxlan(ethernet(ipv4(tcp(24, b"other tenant"), 6)), vni=200),
                  vxlan(ethernet(bytes(28), 0x806))]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "r1-r5.pcap"
            write_capture(path, frames)
            result = measure.classify([path], [measure.parse_flow("t1a:t3a:40001:5201")], "vxlan")
        self.assertEqual(result["captured_packets"], 6)
        self.assertEqual(result["unmatched_packets"], 2)
        flow = result["flows"][0]
        self.assertEqual(flow["syn_observations"], 1)
        self.assertEqual(flow["syn_paths"], ["r1-r5"])
        self.assertEqual(flow["groups"], [{"interface": "r1-r5", "outer_source_port": 45000,
                                        "packets": 4, "data_packets": 2,
                                        "tcp_payload_bytes_with_retransmissions": 6}])

    def test_truncated_capture_is_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.pcap"
            write_capture(path, [ethernet(ipv4(tcp(2), 6))])
            path.write_bytes(path.read_bytes()[:-1])
            with self.assertRaisesRegex(ValueError, "记录不完整"):
                list(measure.packets(path))

    def test_fragment_is_not_misread_as_tcp_header(self):
        packet = bytearray(ipv4(tcp(2), 6))
        packet[6:8] = b"\0\x01"
        self.assertIsNone(measure.decode_ipv4(packet))


if __name__ == "__main__":
    unittest.main()
