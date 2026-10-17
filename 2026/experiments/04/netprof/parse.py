"""解析测量工具的输出（TODO 1、2）。只处理文本与 JSON，不运行命令，可以离线测试。"""

import re  # noqa: F401  解析文本时可能用到


def parse_ping(text):
    """TODO 1　从 iputils ping 的完整输出中取出样本。

    输入：ping 打印的全部文本（不要加 -q，否则没有逐个样本）。
    返回：{"samples": [往返时间, 单位 ms, 按 icmp_seq 从小到大], "sent": 发出数, "received": 收到数}

    - 样本来自形如 "64 bytes from 10.0.3.11: icmp_seq=3 ttl=62 time=0.155 ms" 的行；
    - sent、received 来自摘要行 "40 packets transmitted, 38 received, ..."；同一行还可能有
      "+1 errors"、"+2 duplicates" 等字段，不要被它们干扰；
    - 重复回复（行尾带 "(DUP!)"）不是新的样本：同一个 icmp_seq 只保留第一次；
    - 全部丢失时 samples 为空列表、received 为 0；
    - 找不到摘要行（命令没跑完或输出被截断）时抛出 ValueError。
    """
    raise NotImplementedError("TODO 1：parse_ping")


def parse_iperf3(report):
    """TODO 2　从一次 iperf3 -J 的结果中取出体检单需要的字段。

    输入：iperf3 -J 的输出，已用 json.loads 解析成 dict。
    返回：{"mbps": 接收端速率, "sender_mbps": 发送端速率, "retransmits": 发送端重传段数,
           "cpu_host": 本端（客户端）CPU 占用 %, "cpu_remote": 对端（服务端）CPU 占用 %}

    - 速率单位为 Mbit/s（10^6 bit/s）；体检单取接收端 end.sum_received，理由见第 06 讲 3.3 节；
    - 发送端在 end.sum_sent，重传数也在这里；
    - CPU 占用在 end.cpu_utilization_percent 的 host_total、remote_total；
    - iperf3 失败时 JSON 顶层带 "error" 字段，此时抛出 ValueError，消息中带上 error 的原文。
    """
    raise NotImplementedError("TODO 2：parse_iperf3")
