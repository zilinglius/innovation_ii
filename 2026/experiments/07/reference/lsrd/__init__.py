"""
lsrd —— Lab 2 的链路状态路由守护进程（协议 LSR-lite v1）。

模块分工（与指导书第三节的骨架说明一致）：

  loop.py       事件循环：一个 select() 同时等套接字与定时器            【给定】
  transport.py  每接口一个 UDP 套接字、广播 / 单播、JSON 编解码与校验     【给定】
  sysnet.py     读接口、写内核路由表、订阅内核链路事件                  【给定，watch_links 留作进阶任务】
  neighbor.py   Hello 的生成与处理、邻居表与状态机（R1、R2）             【学生实现】
  lsdb.py       LSA、LSDB、泛洪规则（R3–R6、R9）                        【学生实现】
  spf.py        Dijkstra、首跳提取、前缀表、ECMP（R7）                   【学生实现】
  router.py     把上面几块接起来：事件 → 动作；R8 的路由安装             【给定】
  cli.py        lsrd show neighbors | lsdb | routes | stats              【给定】
"""

__version__ = "1.0"
