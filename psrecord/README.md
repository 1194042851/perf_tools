# perf_tools - 进程性能监控与测试报告工具

专为 Linux 及嵌入式开发板设计的轻量级进程性能监控与交互式测试报告工具。
- **采集端 (`psrecord`)**：目标机 / 板端极低开销记录 CPU、内存 (RSS/PSS)、线程、句柄及多核/温度等数据。
- **报告端 (`psrecord-report`)**：PC 端一键生成单文件交互式 HTML 测试报告，支持高精缩放联动与多测试对比。

---

## 一、安装

### 1. 目标机 / 板端安装采集器
```bash
# 将 dist/psrecord_1.5.0-1_all.deb 拷贝到目标机执行：
sudo dpkg -i psrecord_1.5.0-1_all.deb
```
> 若提示缺少 psutil，执行 `sudo apt install -y python3-psutil` 即可。

### 2. PC 端安装报告生成器
```bash
sudo dpkg -i psrecord/dist/psrecord-report_1.0.0-1_all.deb
```
> 也可以直接在本地使用源码：`pip install -e psrecord/psrecord-report`。

---

## 二、使用方法

### 1. 目标机 / 板端：记录进程性能数据

#### ① 监控正在运行的进程（指定 PID）
```bash
# 监控 PID 1234，每 0.05 秒采一次，包含子进程，保存到 session_test 目录
psrecord 1234 --interval 0.05 --include-children --output-dir ./session_test
```
按 `Ctrl+C` 结束采集，数据自动落盘保存。

#### ② 同时监控多个进程
```bash
# 同时监控 PID 1234 和 5678
psrecord 1234,5678 --interval 0.1 --output-dir ./session_multi
```

#### ③ 监控启动命令的全生命周期
```bash
# 拉起测试命令并一直录制到它运行退出
psrecord "python3 run_test.py" --interval 0.1 --output-dir ./session_cmd
```

#### 常用采集参数速查

| 参数 | 说明 |
|---|---|
| `<PID>` 或 `"<cmd>"` | 目标 PID（多个用逗号隔开）或待执行的命令 |
| `--output-dir <DIR>` | **会话落盘目录**（生成 CSV 与 meta.json 数据） |
| `--interval <秒>` | 采样间隔（推荐 `0.05` 或 `0.1`） |
| `--duration <秒>` | 自动记录指定秒数后停止退出 |
| `--include-children` | **递归包含所有子进程**（多进程/ROS 强烈推荐开启） |
| `--include-io` | 记录磁盘 I/O 速率（读写字节数） |

---

### 2. PC 端：生成交互式测试报告

把采集生成的会话目录拷贝回 PC 后执行：

#### ① 生成单次测试分析报告
```bash
psrecord-report ./session_test -o report.html
```

#### ② 生成多次测试横向对比报告（性能回归对比）
```bash
psrecord-report ./session_v1 ./session_v2 -o compare.html
```
双击生成的 `.html` 文件即可在任意浏览器直接查看。

---

## 三、重新构建安装包

若修改了源码需要重新生成 deb 安装包：
```bash
cd psrecord && ./packaging/build_debs.sh
# 产物自动输出在 psrecord/dist/ 目录下
```
