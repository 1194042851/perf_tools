#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
perf-suite-report: 嵌入式/Linux 性能会话可视化测试报告生成器
支持单会话全景交互式报告与多会话 A/B 横向对比报告生成。
"""

import argparse
import sys
import os
from typing import List

from .analyzer import SessionData
from .plot_builder import build_process_figures, build_network_figures, build_system_figures
from .templates.report_html import render_html_report
from .comparator import build_comparison_report


def main():
    parser = argparse.ArgumentParser(
        prog="perf-suite-report",
        description="perf-suite 性能会话可视化测试报告生成器\n"
                    "支持单会话全景交互式报告生成，以及多次测试 (A/B) 跨会话横向对比报告。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n"
               "  perf-suite-report ./session_test -o report.html\n"
               "  perf-suite-report ./session_v1 ./session_v2 -o comparison.html\n"
    )

    parser.add_argument(
        "session_dirs",
        nargs="+",
        type=str,
        help="待分析的一个或多个 session 目录路径"
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        help="输出的 HTML 报告文件路径 (默认为 report.html 或 comparison_report.html)"
    )

    args = parser.parse_args()

    session_dirs = args.session_dirs
    for s in session_dirs:
        if not os.path.isdir(s):
            print(f"[ERROR] Session 目录不存在或不是有效目录: {s}")
            sys.exit(1)

    if len(session_dirs) == 1:
        s_dir = session_dirs[0]
        output_html = args.output or os.path.join(s_dir, "report.html")
        print(f"[INFO] 正在分析单会话性能数据: {s_dir}")
        data = SessionData(s_dir)
        render_html_report(data, output_html)
        print(f"[INFO] 单会话性能测试报告生成成功: {output_html}")
    else:
        output_html = args.output or "comparison_report.html"
        print(f"[INFO] 正在生成跨会话 (A/B) 对比分析报告: {session_dirs}")
        build_comparison_report(session_dirs, output_html)
        print(f"[INFO] 跨会话对比报告生成成功: {output_html}")


if __name__ == "__main__":
    main()
