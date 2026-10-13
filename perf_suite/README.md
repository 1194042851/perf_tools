# perf_suite - 多进程与网卡统一性能监控套件

专为 Linux 及嵌入式开发板设计的轻量级多进程与网卡联合性能监控与测试报告工具。
- **采集端 (`perf-suite`)**：目标机 / 板端极低开销同步记录多进程（CPU/PSS/线程/IO）、多网卡（吞吐/PPS/丢包）及整机背景指标。
- **报告端 (`perf-suite-report`)**：PC 端生成自包含交互式 HTML 测试报告，支持单会话全景分析与 A/B 跨会话横向对比。

---

## 一、安装

### 1. 目标机 / 板端安装采集器
```bash
sudo dpkg -i dist/perf-suite_0.1.0-1_all.deb
```
> 若提示缺少依赖，执行 `sudo apt install -y python3-psutil` 即可。

### 2. PC 端安装报告生成器
```bash
sudo dpkg -i dist/perf-suite-report_0.1.0-1_all.deb
```
> 也可以直接在本地使用源码：`pip install -e perf-suite-report`。推荐安装 Plotly：`pip install plotly` 或 `sudo apt install python3-plotly`。

---

## 二、使用方法

### 1. 目标机 / 板端：记录性能数据

#### ① 监控指定进程与网卡
```bash
# 监控 PID 1024, 1025，网卡 eth0, lo，每 0.5 秒采一次，保存到 session_test 目录
perf-suite record --pid 1024,1025 --iface eth0,lo --interval 0.5 -o ./session_test
```
按 `Ctrl+C` 结束采集，数据自动落盘。

#### ② 监控启动命令的全生命周期
```bash
# 拉起待测程序并全程监控该进程及其子进程
perf-suite record --command "./my_app" --iface eth0 --include-children -o ./session_cmd
```

#### 常用采集参数速查

| 参数 | 说明 |
|---|---|
| `--pid <PIDS>` | 监控的目标 PID 列表，逗号分隔（如 `1024,1025`） |
| `--command "<cmd>"` | 直接启动并监控目标命令 |
| `--iface <IFACES>` | 监控的网卡名称列表，逗号分隔（如 `eth0,lo` 或 `all`） |
| `-o, --output <DIR>` | **会话落盘目录**（生成各流 CSV 与 meta.json 数据） |
| `--interval <秒>` | 采样间隔（推荐 `0.1` ~ `1.0`，默认 `1.0`） |
| `--duration <秒>` | 自动记录指定秒数后退出 |
| `--include-children` | 递归聚合统计所有子进程资源 |
| `--include-io` | 采集进程级 IO 速率（若内核无相关特性将自动安全降级） |
| `--no-system` | 不采集整机背景指标 |

---

### 2. PC 端：生成测试报告

把采集生成的会话目录拷贝回 PC 后执行：

#### ① 生成单会话分析报告
```bash
perf-suite-report ./session_test -o report.html
```

#### ② 生成多次测试 (A/B) 跨会话横向对比报告
```bash
perf-suite-report ./session_baseline ./session_optimized -o comparison_report.html
```
双击生成的 `.html` 文件即可在任意浏览器直接查看交互式图表与数据对比表。

---

## 三、重新构建安装包

若修改了源码需要重新生成 deb 安装包：
```bash
./packaging/build_debs.sh
# 产物自动输出在 dist/ 目录下
```
