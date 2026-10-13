#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
perf-suite-report 通用跨会话 (A/B) 对比分析与报告生成引擎
支持任意多会话横向对比：多网卡带宽/PPS、多进程 CPU/RSS/线程、整机负载，自动计算相对首个会话的变化基准。
"""

import os
import json
import math
from typing import List, Dict, Any
from .analyzer import SessionData, calculate_stats
import plotly.graph_objects as go

DEFAULT_PALETTE = [
    "#2563EB", "#DC2626", "#059669", "#D97706",
    "#7C3AED", "#DB2777", "#0891B2", "#4B5563"
]


def build_comparison_report(session_dirs: List[str], output_html: str):
    sessions = [SessionData(s) for s in session_dirs]
    session_names = [os.path.basename(os.path.abspath(s)) for s in session_dirs]

    figures = []

    # 1. 网卡对比 (若存在 net_ 流)
    all_net_ifaces = set()
    for sess in sessions:
        for k in sess.series.keys():
            if k.startswith("net_"):
                all_net_ifaces.add(k[4:])

    for iface in sorted(all_net_ifaces):
        # 1.1 RX 带宽对比
        fig_rx = go.Figure()
        has_rx_data = False
        for idx, (s_name, sess) in enumerate(zip(session_names, sessions)):
            stream_key = f"net_{iface}"
            if stream_key in sess.series and sess.series[stream_key]:
                rows = [r for r in sess.series[stream_key] if r["elapsed_s"] >= 0]
                color = DEFAULT_PALETTE[idx % len(DEFAULT_PALETTE)]
                fig_rx.add_trace(go.Scatter(
                    x=[r["elapsed_s"] for r in rows],
                    y=[r.get("rx_mbps", 0.0) for r in rows],
                    mode="lines",
                    name=f"[{s_name}] {iface} RX",
                    line=dict(color=color, width=2)
                ))
                has_rx_data = True

        if has_rx_data:
            fig_rx.update_layout(
                title=f"网卡 <code>{iface}</code> 接收带宽跨会话对比 (RX Mbps)",
                xaxis_title="测试持续时间 (秒)",
                yaxis_title="接收带宽 (Mbps)",
                template="plotly_white",
                hovermode="x unified"
            )
            figures.append({
                "id": f"chart_cmp_net_rx_{iface}",
                "title": f"网卡 {iface} 接收带宽对比 (Mbps)",
                "fig": fig_rx
            })

        # 1.2 RX PPS 对比
        fig_pps = go.Figure()
        has_pps_data = False
        for idx, (s_name, sess) in enumerate(zip(session_names, sessions)):
            stream_key = f"net_{iface}"
            if stream_key in sess.series and sess.series[stream_key]:
                rows = [r for r in sess.series[stream_key] if r["elapsed_s"] >= 0]
                color = DEFAULT_PALETTE[idx % len(DEFAULT_PALETTE)]
                fig_pps.add_trace(go.Scatter(
                    x=[r["elapsed_s"] for r in rows],
                    y=[r.get("rx_pps", 0.0) for r in rows],
                    mode="lines",
                    name=f"[{s_name}] {iface} PPS",
                    line=dict(color=color, width=2)
                ))
                has_pps_data = True

        if has_pps_data:
            fig_pps.update_layout(
                title=f"网卡 <code>{iface}</code> 接收包吞吐率对比 (RX Packets Per Second)",
                xaxis_title="测试持续时间 (秒)",
                yaxis_title="包吞吐率 (PPS)",
                template="plotly_white",
                hovermode="x unified"
            )
            figures.append({
                "id": f"chart_cmp_net_pps_{iface}",
                "title": f"网卡 {iface} 包吞吐率对比 (PPS)",
                "fig": fig_pps
            })

    # 2. 进程 CPU 与 内存 对比
    fig_proc_cpu = go.Figure()
    fig_proc_mem = go.Figure()
    has_proc_cpu = False
    has_proc_mem = False

    for s_idx, (s_name, sess) in enumerate(zip(session_names, sessions)):
        proc_streams = [k for k in sess.series.keys() if k.startswith("proc_")]
        for p_idx, p_stream in enumerate(proc_streams):
            rows = sess.series[p_stream]
            if not rows:
                continue
            p_name = rows[0].get("name", p_stream)
            color = DEFAULT_PALETTE[(s_idx * 3 + p_idx) % len(DEFAULT_PALETTE)]
            line_dash = "solid" if s_idx == 0 else ("dash" if s_idx == 1 else "dot")

            fig_proc_cpu.add_trace(go.Scatter(
                x=[r["elapsed_s"] for r in rows],
                y=[r.get("cpu_percent", 0.0) for r in rows],
                mode="lines",
                name=f"[{s_name}] {p_name} ({p_stream})",
                line=dict(color=color, width=2, dash=line_dash)
            ))
            has_proc_cpu = True

            fig_proc_mem.add_trace(go.Scatter(
                x=[r["elapsed_s"] for r in rows],
                y=[r.get("rss_mb", 0.0) for r in rows],
                mode="lines",
                name=f"[{s_name}] {p_name} ({p_stream})",
                line=dict(color=color, width=2, dash=line_dash)
            ))
            has_proc_mem = True

    if has_proc_cpu:
        fig_proc_cpu.update_layout(
            title="多会话目标进程 CPU 占用率对比 (%)",
            xaxis_title="测试持续时间 (秒)",
            yaxis_title="CPU (%)",
            template="plotly_white",
            hovermode="x unified"
        )
        figures.append({"id": "chart_cmp_proc_cpu", "title": "进程 CPU 占用对比 (%)", "fig": fig_proc_cpu})

    if has_proc_mem:
        fig_proc_mem.update_layout(
            title="多会话目标进程物理内存对比 (RSS MB)",
            xaxis_title="测试持续时间 (秒)",
            yaxis_title="内存 (MB)",
            template="plotly_white",
            hovermode="x unified"
        )
        figures.append({"id": "chart_cmp_proc_mem", "title": "进程物理内存对比 (RSS MB)", "fig": fig_proc_mem})

    # 3. 整机系统背景 CPU 对比
    fig_sys_cpu = go.Figure()
    has_sys_data = False
    for idx, (s_name, sess) in enumerate(zip(session_names, sessions)):
        if "system" in sess.series and sess.series["system"]:
            rows = sess.series["system"]
            color = DEFAULT_PALETTE[idx % len(DEFAULT_PALETTE)]
            fig_sys_cpu.add_trace(go.Scatter(
                x=[r["elapsed_s"] for r in rows],
                y=[r.get("sys_cpu_percent", 0.0) for r in rows],
                mode="lines",
                name=f"[{s_name}] 整机 CPU",
                line=dict(color=color, width=2)
            ))
            has_sys_data = True

    if has_sys_data:
        fig_sys_cpu.update_layout(
            title="多会话整机 CPU 占用率对比 (%)",
            xaxis_title="测试持续时间 (秒)",
            yaxis_title="整机 CPU (%)",
            template="plotly_white",
            hovermode="x unified"
        )
        figures.append({"id": "chart_cmp_sys_cpu", "title": "整机 CPU 对比 (%)", "fig": fig_sys_cpu})

    # 4. 构造通用汇总统计表
    # 以第一个会话作为 Baseline 计算变化率
    baseline_stats = sessions[0].get_summary_stats() if sessions else {}

    table_rows = []
    for s_idx, (s_name, sess) in enumerate(zip(session_names, sessions)):
        stats = sess.get_summary_stats()
        for stream, metrics in sorted(stats.items()):
            for m_name, s_val in sorted(metrics.items()):
                # 仅展示重要指标
                if m_name not in ("rx_mbps", "tx_mbps", "rx_pps", "cpu_percent", "rss_mb", "sys_cpu_percent", "sys_mem_percent", "threads"):
                    continue

                avg_val = s_val.get("avg", 0.0)
                p95_val = s_val.get("p95", 0.0)
                max_val = s_val.get("max", 0.0)

                # 变化率计算 (相对第一个 Session)
                diff_str = "-"
                if s_idx == 0:
                    diff_str = "<span style='color:#64748b;'>基准 (Baseline)</span>"
                else:
                    base_m = baseline_stats.get(stream, {}).get(m_name, {}).get("avg")
                    if base_m and base_m > 0:
                        diff = ((avg_val - base_m) / base_m) * 100.0
                        if abs(diff) < 0.1:
                            diff_str = "<span style='color:#64748b;'>持平 (0%)</span>"
                        elif diff > 0:
                            diff_str = f"<span style='color:#DC2626;font-weight:bold;'>↑ +{diff:.1f}%</span>"
                        else:
                            diff_str = f"<span style='color:#059669;font-weight:bold;'>↓ {diff:.1f}%</span>"

                table_rows.append(f"""
                <tr>
                    <td><strong>{s_name}</strong></td>
                    <td><code>{stream}</code></td>
                    <td><strong>{m_name}</strong></td>
                    <td>{avg_val}</td>
                    <td><span style="color:#2563EB;font-weight:bold;">{p95_val}</span></td>
                    <td><span style="color:#DC2626;font-weight:bold;">{max_val}</span></td>
                    <td>{diff_str}</td>
                </tr>
                """)

    chart_divs = []
    chart_scripts = []
    for f_info in figures:
        cid = f_info["id"]
        fig = f_info["fig"]
        chart_divs.append(f'<div id="{cid}" style="width:100%;min-height:430px;margin-bottom:30px;"></div>')
        json_spec = fig.to_json()
        chart_scripts.append(f"""
        (function() {{
            var spec = {json_spec};
            Plotly.newPlot('{cid}', spec.data, spec.layout, {{responsive: true}});
        }})();
        """)

    sess_labels = ", ".join(f"<code>{n}</code>" for n in session_names)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>perf_suite A/B 跨会话对比报告</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; background: #f8fafc; padding: 24px; color: #0f172a; margin: 0; }}
        .container {{ max-width: 1320px; margin: 0 auto; }}
        .header {{ background: #ffffff; border-radius: 12px; padding: 24px 32px; margin-bottom: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); border: 1px solid #e2e8f0; }}
        .header h1 {{ margin: 0 0 8px 0; font-size: 24px; color: #0f172a; }}
        .header p {{ margin: 0; color: #64748b; font-size: 14px; line-height: 1.6; }}
        .card {{ background: #ffffff; border-radius: 12px; padding: 24px 32px; margin-bottom: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); border: 1px solid #e2e8f0; }}
        h2 {{ font-size: 18px; color: #1e293b; margin-top: 0; padding-bottom: 12px; border-bottom: 1px solid #e2e8f0; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 14px; margin-top: 14px; }}
        th, td {{ padding: 12px 14px; border-bottom: 1px solid #e2e8f0; text-align: left; }}
        th {{ background: #f1f5f9; font-weight: 600; color: #475569; }}
        tr:hover {{ background: #f8fafc; }}
        code {{ background: #f1f5f9; padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 13px; color: #0f172a; }}
        .footer {{ text-align: center; color: #94a3b8; font-size: 13px; margin-top: 40px; padding-bottom: 20px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>⚖️ perf_suite 跨会话 (A/B) 综合对比评测报告</h1>
            <p><strong>对比会话清单 ({len(session_names)} 组):</strong> {sess_labels} &nbsp;|&nbsp; <strong>对比基准:</strong> <code>{session_names[0]}</code></p>
        </div>

        <div class="card">
            <h2>📊 核心指标跨会话对比表 (含基准相对变化)</h2>
            <table>
                <thead>
                    <tr>
                        <th>会话名称</th>
                        <th>数据流 (Stream)</th>
                        <th>监控指标项</th>
                        <th>平均值 (Avg)</th>
                        <th>95分位数 (P95)</th>
                        <th>峰值 (Max)</th>
                        <th>相对基准会话变化</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(table_rows)}
                </tbody>
            </table>
        </div>

        <div class="card">
            <h2>📈 多维度全景可视化对比图表</h2>
            {''.join(chart_divs)}
        </div>

        <div class="footer">
            Generated by perf-suite-report &bull; Unified Embedded Performance Suite
        </div>
    </div>
    <script>{''.join(chart_scripts)}</script>
</body>
</html>
"""
    with open(output_html, "w", encoding="utf-8") as f:
        f.write(html)
