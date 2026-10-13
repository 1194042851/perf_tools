# perf_tools

Linux 及嵌入式开发板性能分析、基准测试与系统调优工具集。

## 工具列表

- **[psrecord](./psrecord/)**：轻量级进程性能监控与交互式 HTML 测试报告套件
  - **采集端 (`psrecord`)**：板端/目标机极低开销记录进程 CPU、内存 (RSS/PSS)、线程、句柄及多核/温度等数据。
  - **报告端 (`psrecord-report`)**：PC 端一键生成单文件交互式 HTML 测试报告，支持高精缩放联动与多测试对比。
  - **使用方法**：详见 [`psrecord/README.md`](./psrecord/README.md)。

- **[perf_suite](./perf_suite/)**：多进程与多网卡联合性能监控套件
  - **采集端 (`perf-suite`)**：目标机/板端同步高精度采样多进程（CPU/PSS/IO）与多网卡（吞吐/PPS/丢包）及系统硬件指标。
  - **报告端 (`perf-suite-report`)**：PC 端生成全景可视化 HTML 报告与 A/B 跨会话横向对比报告。
  - **使用方法**：详见 [`perf_suite/README.md`](./perf_suite/README.md)。
