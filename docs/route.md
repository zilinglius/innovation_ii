# Linux `ip route` 使用与配置总结

`ip route` 用于查看和管理 Linux 的路由表。

---

## 1. 查看路由表
```bash
ip route show
# 或简写
ip r
```
示例：
```
default via 192.168.1.1 dev eth0 proto dhcp metric 100
192.168.1.0/24 dev eth0 proto kernel scope link src 192.168.1.10
```

---

## 2. 添加路由
```bash
# 添加直连路由
ip route add 172.16.0.0/16 dev eth1

# 添加下一跳路由
ip route add 10.0.0.0/24 via 192.168.1.1

# 添加默认路由
ip route add default via 192.168.1.1
```

---

## 3. 删除路由
```bash
ip route del 10.0.0.0/24
ip route del default
```

---

## 4. 修改路由
```bash
ip route change default via 192.168.1.254
```

---

## 5. metric（路由优先级）
- **metric 数值越小，优先级越高**。
- 常用于多网关或多路径环境。

### 添加带 metric 的路由
```bash
ip route add default via 192.168.1.1 metric 100
ip route add default via 192.168.1.2 metric 200
```

### 修改已有路由的 metric
```bash
ip route change default via 192.168.1.1 metric 50
```

### 删除再添加（通用做法）
```bash
ip route del default via 192.168.1.1
ip route add default via 192.168.1.1 metric 50
```

---

## 6. 高级用法
- **指定源地址**
  ```bash
  ip route add 10.0.0.0/24 via 192.168.1.1 src 192.168.1.20
  ```

- **多路径负载均衡**
  ```bash
  ip route add default \
    nexthop via 192.168.1.1 dev eth0 weight 1 \
    nexthop via 192.168.1.2 dev eth1 weight 1
  ```

---

## 7. 双网关场景示例

### 场景说明
- **eth0** → 连接外网（Internet，网关 192.168.1.1）  
- **eth1** → 连接内网（Intranet，网关 10.0.0.1）  
- 默认走 **外网 eth0**，访问 `10.0.0.0/8` 内网地址走 **eth1**。

### 配置示例
```bash
# 默认外网路由
ip route add default via 192.168.1.1 dev eth0 metric 100

# 内网专用路由
ip route add 10.0.0.0/8 via 10.0.0.1 dev eth1 metric 50
```

### 查看结果
```bash
ip route show
```
示例：
```
default via 192.168.1.1 dev eth0 proto static metric 100
10.0.0.0/8 via 10.0.0.1 dev eth1 proto static metric 50
192.168.1.0/24 dev eth0 proto kernel scope link src 192.168.1.100
10.0.0.0/24 dev eth1 proto kernel scope link src 10.0.0.100
```

---

## 8. 双默认路由策略

### 主备路由（metric 控制优先级）
```bash
ip route add default via 192.168.1.1 dev eth0 metric 100
ip route add default via 192.168.1.2 dev eth1 metric 200
```

### 负载均衡（多路径）
```bash
ip route add default \
    nexthop via 192.168.1.1 dev eth0 weight 1 \
    nexthop via 192.168.1.2 dev eth1 weight 1
```

---

## 9. 注意事项
- `ip route` 添加的路由默认是 **临时的**，重启后会消失。
- 要永久生效，需要写入系统网络配置文件：
  - **Ubuntu (netplan)** → `/etc/netplan/*.yaml`
  - **Debian/Ubuntu (旧版)** → `/etc/network/interfaces`
  - **CentOS/RHEL** → `/etc/sysconfig/network-scripts/`

