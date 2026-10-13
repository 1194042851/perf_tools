#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
perf-suite: 嵌入式多进程与网卡统一性能记录工具（采集端）
极低开销，仅依赖 python3-psutil，采样落盘多流 CSV 与 meta.json
"""

import argparse
import sys
import os
import subprocess
import time
from typing import List

from .core.session import SessionManager
from .core.runner import Runner
from .collectors.process import ProcessCollector
from .collectors.network import NetworkCollector
from .collectors.system import SystemCollector


def cmd_record(args):
    pids = []
    child_process = None

    if args.pid:
        for p_str in args.pid.split(","):
            if p_str.strip():
                try:
                    pids.append(int(p_str.strip()))
                except ValueError:
                    print(f"[ERROR] 无效的 PID: {p_str}")
                    sys.exit(1)

    if args.command:
        print(f"[INFO] 正在启动被监控进程: {args.command}")
        child_process = subprocess.Popen(args.command, shell=True)
        pids.append(child_process.pid)

    output_dir = args.output
    if not output_dir:
        timestamp_str = time.strftime("%Y%m%d_%H%M%S")
        output_dir = f"session_{timestamp_str}"

    session = SessionManager(output_dir)
    collectors = []

    if pids:
        print(f"[INFO] 注册进程监控目标 PID: {pids}")
        p_col = ProcessCollector(
            pids=pids,
            include_children=args.include_children,
            include_io=args.include_io
        )
        collectors.append(p_col)

    if args.iface:
        ifaces = [i.strip() for i in args.iface.split(",") if i.strip()]
        print(f"[INFO] 注册网卡监控目标: {ifaces}")
        n_col = NetworkCollector(ifaces=ifaces)
        collectors.append(n_col)

    if not args.no_system:
        s_col = SystemCollector(
            sample_thermal=not args.no_thermal,
            sample_freq=not args.no_freq
        )
        collectors.append(s_col)

    if not collectors:
        print("[ERROR] 未指定任何监控目标！请至少指定 --pid, --command 或 --iface")
        sys.exit(1)

    runner = Runner(
        collectors=collectors,
        session=session,
        interval=args.interval,
        duration=args.duration
    )

    try:
        runner.run()
    finally:
        if child_process is not None:
            try:
                child_process.terminate()
            except Exception:
                pass


def cmd_report_hint(args):
    print("[TIP] 报告生成工具已解耦为独立的 'perf-suite-report' 组件。")
    print("      请在 PC 端安装并执行: perf-suite-report " + " ".join(args.session_dirs or []))
    try:
        from perf_suite_report.cli import main as report_main
        print("[INFO] 本地已检测到 perf-suite-report 组件，正在为您直接启动生成报告...")
        report_main()
    except ImportError:
        pass


def add_record_arguments(parser):
    parser.add_argument("--pid", type=str, help="监控的目标 PID 列表，逗号分隔，如 '1234,5678'")
    parser.add_argument("--command", type=str, help="直接启动并监控的目标命令行")
    parser.add_argument("--iface", type=str, help="监控的网卡名称列表，逗号分隔，如 'eth0,lo' 或 'all'")
    parser.add_argument("--interval", type=float, default=1.0, help="采样间隔 (秒)，默认 1.0")
    parser.add_argument("--duration", type=float, default=None, help="最大记录时长 (秒)，默认无限制持续记录")
    parser.add_argument("--output", "-o", type=str, default=None, help="指定 Session 输出目录")
    parser.add_argument("--include-children", action="store_true", help="聚合统计子进程资源")
    parser.add_argument("--include-io", action="store_true", help="采集进程级 IO 统计 (内核不支持将自动安全降级)")
    parser.add_argument("--no-system", action="store_true", help="不采集整机与系统背景指标")
    parser.add_argument("--no-thermal", action="store_true", help="不采集温度传感器")
    parser.add_argument("--no-freq", action="store_true", help="不采集 CPU 频率")


def main():
    parser = argparse.ArgumentParser(
        prog="perf-suite",
        description="嵌入式/Linux 多进程与网卡统一性能记录工具（采集端）\n"
                    "支持多进程(CPU/PSS/线程/IO)与多网卡(Mbps/PPS/丢包)同步采样落盘。",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(dest="subcommand", help="子命令 (record / report)")

    p_rec = subparsers.add_parser("record", help="开始记录性能数据")
    add_record_arguments(p_rec)
    p_rec.set_defaults(func=cmd_record)

    p_rep = subparsers.add_parser("report", help="生成报告提示或跳转")
    p_rep.add_argument("session_dirs", nargs="*", type=str, help="待分析的 session 目录")
    p_rep.add_argument("--output", "-o", type=str, default=None)
    p_rep.set_defaults(func=cmd_report_hint)

    # 兼容直接传参 (不带 record 子命令直接运行)
    if len(sys.argv) > 1 and sys.argv[1] not in ("record", "report", "-h", "--help"):
        add_record_arguments(parser)
        args = parser.parse_args()
        cmd_record(args)
        return

    if len(sys.argv) < 2:
        parser.print_help()
        sys.exit(1)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
