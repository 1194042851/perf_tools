# perf_tools

Linux 及嵌入式开发板性能分析、基准测试与系统调优工具集。

## 工具列表

- **[psrecord](./psrecord/)**：轻量级多进程性能记录与交互式 HTML 测试报告套件
  - **采集端 (`psrecord`)**：板端/目标机极低开销记录 CPU、内存 (RSS/PSS)、线程、句柄及多核/温度等数据。
  - **报告端 (`psrecord-report`)**：PC 端一键生成单文件交互式 HTML 测试报告，支持高精缩放联动与多测试对比。
  - **使用方法**：详见 [`psrecord/README.md`](./psrecord/README.md)。
