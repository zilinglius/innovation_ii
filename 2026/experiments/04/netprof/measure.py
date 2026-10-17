"""在实验床上执行一次测量（TODO 5）。需要 root 与实验床，不能离线测试。"""

import json
import subprocess
import time  # noqa: F401  TODO 5 可能用到

from . import parse, sysrun  # noqa: F401  TODO 5 会用到 parse


def ping(src, dst_ip, count, interval):
    """在 src 中 ping dst_ip，返回完整输出文本。有丢失时 ping 的退出码为 1，这里仍返回输出。"""
    args = ["ping", "-c", str(count), "-i", str(interval), "-W", "1", dst_ip]
    return sysrun.run_in(src, args, timeout=count * interval + 15).stdout


def iperf3_once(src, dst, dst_ip, seconds, omit, port=5201):
    """一次独立的吞吐测量：dst 起一次性服务端，src 作客户端发送 seconds 秒（另加 omit 秒预热）。

    返回 iperf3 -J 的 JSON（dict）。iperf3 自身出错时 JSON 里带 error 字段，由 parse_iperf3 处理；
    这里只在没有任何 JSON 输出（例如超时）时抛出 RuntimeError。
    """
    args = ["iperf3", "-c", dst_ip, "-p", str(port), "-t", str(seconds), "-O", str(omit), "-J"]
    with sysrun.iperf3_server(dst, port):
        try:
            result = sysrun.run_in(src, args, timeout=seconds + omit + 20)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"iperf3 {src}→{dst} 超时") from exc
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"iperf3 {src}→{dst} 没有输出 JSON：{result.stderr.strip()[:200]}") from exc


def throughput_runs(src, dst, dst_ip, seconds, omit, repeats, save=None, pause=0.3):
    """TODO 5　对一个有向主机对做 repeats 次独立的吞吐测量。

    每次调用 iperf3_once()（每次一个新的一次性服务端、一条新连接），再用 parse.parse_iperf3() 取出结果；
    save 不为 None 时，对每次拿到的原始 JSON 调用 save(第几次, report)，用于留存证据。
    返回 (runs, errors)：runs 是成功测量的 parse_iperf3 结果列表，errors 是失败原因（字符串）列表。

    要考虑：
    - 某一次失败（服务端没起来、连接被拒、超时、parse_iperf3 抛出 ValueError）时，把原因记进 errors 并继续，
      不要让整张画像因为一对主机中断；
    - 两次测量之间留 pause 秒，避免上一条连接的余波与下一次重叠；
    - 同一时刻只做这一项测量（第 06 讲 5.3 节）——调用者保证这一点，这里不要开线程。
    """
    raise NotImplementedError("TODO 5：throughput_runs")
