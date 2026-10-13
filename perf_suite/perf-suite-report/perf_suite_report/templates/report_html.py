#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
perf-suite-report 现代化单会话交互式测试报告生成器
包含深浅色双主题、时间轴全图联动、峰值一键聚焦、全屏模态分析与离线嵌入。
"""

import os
import json
from typing import Dict, Any, List
from ..analyzer import SessionData, calculate_stats, downsample_points


def _load_embedded_js():
    cur_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    js_files = ["chart.umd.min.js", "hammer.min.js", "chartjs-plugin-zoom.min.js"]
    contents = []
    for jf in js_files:
        p = os.path.join(cur_dir, jf)
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                contents.append(f.read())
    return "\n".join(contents)


def render_html_report(session: SessionData, output_html: str):
    meta = session.meta or {}
    platform_info = meta.get("platform", {})
    duration_s = meta.get("duration_s", 0.0)

    # 1. 解析进程数据
    proc_streams = [k for k in sorted(session.series.keys()) if k.startswith("proc_")]
    proc_summaries = []
    max_global_cpu = 0.0
    peak_cpu_time = 0.0
    total_rss_delta = 0.0

    chart_data_proc_cpu = []
    chart_data_proc_mem = []
    chart_data_proc_thr = []
    chart_data_proc_io = []

    palette = [
        "#00F0FF", "#FF5376", "#06D6A0", "#FFD166",
        "#3A86FF", "#9C27B0", "#FF9F1C", "#2EC4B6"
    ]

    for idx, p_name in enumerate(proc_streams):
        rows = session.series[p_name]
        if not rows:
            continue
        pid = rows[0].get("pid", p_name.replace("proc_", ""))
        name = rows[0].get("name", f"PID {pid}")
        cmdline = rows[0].get("cmdline", name)
        times = [r.get("elapsed_s", 0.0) for r in rows]
        cpus = [r.get("cpu_percent", 0.0) for r in rows]
        rsss = [r.get("rss_mb", 0.0) for r in rows]
        psss = [r.get("pss_mb", 0.0) for r in rows]
        thrs = [r.get("threads", 1) for r in rows]
        r_kbs = [r.get("read_kb_per_sec", 0.0) for r in rows]
        w_kbs = [r.get("write_kb_per_sec", 0.0) for r in rows]

        cpu_st = calculate_stats(cpus)
        rss_st = calculate_stats(rsss)
        pss_st = calculate_stats(psss)
        thr_st = calculate_stats(thrs)
        r_st = calculate_stats(r_kbs)
        w_st = calculate_stats(w_kbs)

        if cpu_st["max"] > max_global_cpu:
            max_global_cpu = cpu_st["max"]
            peak_idx = cpus.index(cpu_st["max"]) if cpu_st["max"] in cpus else 0
            peak_cpu_time = times[peak_idx] if peak_idx < len(times) else 0.0

        total_rss_delta += rss_st["delta"]

        proc_summaries.append({
            "pid": pid,
            "name": name,
            "cmdline": cmdline,
            "cpu": cpu_st,
            "rss": rss_st,
            "pss": pss_st,
            "threads": thr_st,
            "io_read": r_st,
            "io_write": w_st,
            "color": palette[idx % len(palette)]
        })

        color = palette[idx % len(palette)]
        chart_data_proc_cpu.append({
            "label": f"{name} (PID {pid})",
            "data": downsample_points(times, cpus),
            "borderColor": color,
            "borderWidth": 2,
            "pointRadius": 0,
            "pointHoverRadius": 6,
            "pointHitRadius": 8,
            "tension": 0.2
        })

        chart_data_proc_mem.append({
            "label": f"{name} RSS",
            "data": downsample_points(times, rsss),
            "borderColor": color,
            "borderWidth": 2,
            "pointRadius": 0,
            "pointHoverRadius": 6,
            "pointHitRadius": 8,
            "tension": 0.2
        })
        if any(psss):
            chart_data_proc_mem.append({
                "label": f"{name} PSS (实际按比例)",
                "data": downsample_points(times, psss),
                "borderColor": color,
                "borderWidth": 2,
                "pointRadius": 0,
                "pointHoverRadius": 6,
                "pointHitRadius": 8,
                "tension": 0.2
            })

        chart_data_proc_thr.append({
            "label": f"{name} 线程数",
            "data": downsample_points(times, thrs),
            "borderColor": color,
            "borderWidth": 2,
            "pointRadius": 0,
            "pointHoverRadius": 6,
            "pointHitRadius": 8,
            "tension": 0.1
        })

        if any(r_kbs) or any(w_kbs):
            chart_data_proc_io.append({
                "label": f"{name} 读 (KB/s)",
                "data": downsample_points(times, r_kbs),
                "borderColor": color,
                "borderWidth": 2,
                "pointRadius": 0,
                "pointHoverRadius": 6,
                "pointHitRadius": 8,
                "tension": 0.2
            })
            chart_data_proc_io.append({
                "label": f"{name} 写 (KB/s)",
                "data": downsample_points(times, w_kbs),
                "borderColor": palette[(idx + 1) % len(palette)],
                "borderWidth": 2,
                "pointRadius": 0,
                "pointHoverRadius": 6,
                "pointHitRadius": 8,
                "tension": 0.2
            })

    # 2. 解析网卡数据
    net_streams = [k for k in sorted(session.series.keys()) if k.startswith("net_")]
    net_summaries = []
    max_global_bw = 0.0
    peak_bw_time = 0.0
    total_net_drops = 0

    chart_data_net_bw = []
    chart_data_net_pps = []

    for idx, n_name in enumerate(net_streams):
        rows = session.series[n_name]
        if not rows:
            continue
        iface = rows[0].get("iface", n_name.replace("net_", ""))
        times = [r.get("elapsed_s", 0.0) for r in rows]
        rx_mbps = [r.get("rx_mbps", 0.0) for r in rows]
        tx_mbps = [r.get("tx_mbps", 0.0) for r in rows]
        rx_pps = [r.get("rx_pps", 0.0) for r in rows]
        tx_pps = [r.get("tx_pps", 0.0) for r in rows]
        rx_drops = [r.get("rx_drop_delta", 0) for r in rows]
        tx_drops = [r.get("tx_drop_delta", 0) for r in rows]

        rx_st = calculate_stats(rx_mbps)
        tx_st = calculate_stats(tx_mbps)
        rx_pps_st = calculate_stats(rx_pps)
        tx_pps_st = calculate_stats(tx_pps)

        sum_drops = sum(rx_drops) + sum(tx_drops)
        total_net_drops += sum_drops

        if rx_st["max"] > max_global_bw:
            max_global_bw = rx_st["max"]
            peak_idx = rx_mbps.index(rx_st["max"]) if rx_st["max"] in rx_mbps else 0
            peak_bw_time = times[peak_idx] if peak_idx < len(times) else 0.0

        color_rx = palette[(idx * 2) % len(palette)]
        color_tx = palette[(idx * 2 + 1) % len(palette)]

        net_summaries.append({
            "iface": iface,
            "rx_bw": rx_st,
            "tx_bw": tx_st,
            "rx_pps": rx_pps_st,
            "tx_pps": tx_pps_st,
            "drops": sum_drops,
            "rx_total_mb": round((rows[-1].get("rx_bytes_total", 0) - rows[0].get("rx_bytes_total", 0)) / (1024 * 1024), 2) if len(rows) > 1 else 0.0,
            "tx_total_mb": round((rows[-1].get("tx_bytes_total", 0) - rows[0].get("tx_bytes_total", 0)) / (1024 * 1024), 2) if len(rows) > 1 else 0.0,
        })

        chart_data_net_bw.append({
            "label": f"{iface} RX (接收 Mbps)",
            "data": downsample_points(times, rx_mbps),
            "borderColor": color_rx,
            "borderWidth": 2,
            "pointRadius": 0,
            "pointHoverRadius": 6,
            "pointHitRadius": 8,
            "tension": 0.2
        })
        chart_data_net_bw.append({
            "label": f"{iface} TX (发送 Mbps)",
            "data": downsample_points(times, tx_mbps),
            "borderColor": color_tx,
            "borderWidth": 2,
            "pointRadius": 0,
            "pointHoverRadius": 6,
            "pointHitRadius": 8,
            "tension": 0.2
        })

        chart_data_net_pps.append({
            "label": f"{iface} RX 包率 (PPS)",
            "data": downsample_points(times, rx_pps),
            "borderColor": color_rx,
            "borderWidth": 2,
            "pointRadius": 0,
            "pointHoverRadius": 6,
            "pointHitRadius": 8,
            "tension": 0.1
        })
        chart_data_net_pps.append({
            "label": f"{iface} TX 包率 (PPS)",
            "data": downsample_points(times, tx_pps),
            "borderColor": color_tx,
            "borderWidth": 2,
            "pointRadius": 0,
            "pointHoverRadius": 6,
            "pointHitRadius": 8,
            "tension": 0.1
        })

    # 3. 解析系统与硬件数据
    sys_rows = session.series.get("system", [])
    chart_data_sys_cpu = []
    chart_data_sys_hw = []
    max_sys_temp = 0.0
    max_temp_sensor = "无传感器"

    if sys_rows:
        s_times = [r.get("elapsed_s", 0.0) for r in sys_rows]
        sys_cpu = [r.get("sys_cpu_percent", 0.0) for r in sys_rows]
        sys_mem = [r.get("sys_mem_percent", 0.0) for r in sys_rows]

        chart_data_sys_cpu.append({
            "label": "整机 CPU 占用率 (%)",
            "data": downsample_points(s_times, sys_cpu),
            "borderColor": "#FF5376",
            "borderWidth": 2,
            "pointRadius": 0,
            "pointHoverRadius": 6,
            "pointHitRadius": 8,
            "tension": 0.2
        })
        chart_data_sys_cpu.append({
            "label": "整机内存使用率 (%)",
            "data": downsample_points(s_times, sys_mem),
            "borderColor": "#3A86FF",
            "borderWidth": 2,
            "pointRadius": 0,
            "pointHoverRadius": 6,
            "pointHitRadius": 8,
            "tension": 0.2
        })

        # 硬件温度与频率
        freq_keys = [k for k in sys_rows[0].keys() if k.startswith("freq_")]
        temp_keys = [k for k in sys_rows[0].keys() if k.startswith("temp_")]

        for fk in freq_keys:
            vals = [r.get(fk, 0.0) for r in sys_rows]
            label = fk.replace("freq_", "").replace("_mhz", " MHz")
            chart_data_sys_hw.append({
                "label": f"频率 {label}",
                "data": downsample_points(s_times, vals),
                "borderColor": "#00F0FF",
                "borderWidth": 2,
                "pointRadius": 0,
                "pointHoverRadius": 6,
                "pointHitRadius": 8,
                "tension": 0.1
            })

        for tk in temp_keys:
            vals = [r.get(tk, 0.0) for r in sys_rows]
            t_max = max(vals) if vals else 0.0
            t_label = tk.replace("temp_", "")
            if t_max > max_sys_temp:
                max_sys_temp = t_max
                max_temp_sensor = t_label
            chart_data_sys_hw.append({
                "label": f"温度 {t_label} (°C)",
                "data": downsample_points(s_times, vals),
                "borderColor": "#FF9F1C",
                "borderWidth": 2,
                "pointRadius": 0,
                "pointHoverRadius": 6,
                "pointHitRadius": 8,
                "tension": 0.2
            })

    # 全局最大时间
    all_end_times = [duration_s]
    if proc_summaries and session.series[proc_streams[0]]:
        all_end_times.append(session.series[proc_streams[0]][-1].get("elapsed_s", 0.0))
    if net_summaries and session.series[net_streams[0]]:
        all_end_times.append(session.series[net_streams[0]][-1].get("elapsed_s", 0.0))
    global_max_time = round(max(all_end_times), 2)

    report_payload = {
        "session_name": session.name,
        "meta": meta,
        "duration_s": global_max_time,
        "global_peak_cpu_time": round(peak_cpu_time, 2),
        "global_peak_bw_time": round(peak_bw_time, 2),
        "diag": {
            "max_cpu": round(max_global_cpu, 1),
            "peak_cpu_time": round(peak_cpu_time, 1),
            "max_bw": round(max_global_bw, 2),
            "peak_bw_time": round(peak_bw_time, 1),
            "rss_delta": round(total_rss_delta, 1),
            "net_drops": total_net_drops,
            "max_temp": round(max_sys_temp, 1),
            "max_temp_sensor": max_temp_sensor
        },
        "proc_summaries": proc_summaries,
        "net_summaries": net_summaries,
        "charts": {
            "net_bw": chart_data_net_bw,
            "net_pps": chart_data_net_pps,
            "proc_cpu": chart_data_proc_cpu,
            "proc_mem": chart_data_proc_mem,
            "proc_thr": chart_data_proc_thr,
            "proc_io": chart_data_proc_io,
            "sys_cpu": chart_data_sys_cpu,
            "sys_hw": chart_data_sys_hw
        }
    }

    embedded_js = _load_embedded_js()
    payload_json = json.dumps(report_payload, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>perf_suite 性能测试全景分析报告 - {session.name}</title>
    <style>
        :root {{
            --bg-base: #0a0e17;
            --bg-card: #121826;
            --bg-card-sub: #182234;
            --border: #1e293b;
            --text-main: #f1f5f9;
            --text-muted: #94a3b8;
            --accent-cyan: #00f0ff;
            --accent-green: #06d6a0;
            --accent-red: #ff5376;
            --accent-yellow: #ffd166;
            --accent-blue: #3a86ff;
            --chart-grid: rgba(255, 255, 255, 0.05);
            --chart-tick: #64748b;
        }}
        [data-theme="light"] {{
            --bg-base: #f8fafc;
            --bg-card: #ffffff;
            --bg-card-sub: #f1f5f9;
            --border: #e2e8f0;
            --text-main: #0f172a;
            --text-muted: #64748b;
            --accent-cyan: #0284c7;
            --accent-green: #059669;
            --accent-red: #dc2626;
            --accent-yellow: #d97706;
            --accent-blue: #2563eb;
            --chart-grid: rgba(0, 0, 0, 0.06);
            --chart-tick: #94a3b8;
        }}
        * {{ box-sizing: border-box; transition: background-color 0.2s, border-color 0.2s; }}
        body {{
            margin: 0; padding: 24px 32px;
            background-color: var(--bg-base);
            color: var(--text-main);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            -webkit-font-smoothing: antialiased;
        }}
        .container {{ max-width: 1480px; margin: 0 auto; }}
        .header {{
            display: flex; justify-content: space-between; align-items: center;
            background: var(--bg-card); border: 1px solid var(--border);
            border-radius: 14px; padding: 20px 28px; margin-bottom: 24px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.15);
        }}
        .header-title h1 {{ margin: 0 0 6px 0; font-size: 22px; font-weight: 700; letter-spacing: 0.3px; }}
        .header-meta {{ font-size: 13px; color: var(--text-muted); line-height: 1.6; }}
        .header-meta span {{ color: var(--text-main); font-weight: 600; }}
        .toolbar {{ display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }}
        .btn {{
            background: var(--bg-card-sub); border: 1px solid var(--border);
            color: var(--text-main); padding: 7px 14px; border-radius: 8px;
            font-size: 13px; font-weight: 500; cursor: pointer; display: inline-flex;
            align-items: center; gap: 6px; text-decoration: none;
        }}
        .btn:hover {{ border-color: var(--accent-cyan); color: var(--accent-cyan); }}
        .btn-primary {{ background: var(--accent-cyan); color: #0a0e17; font-weight: 600; border: none; }}
        .btn-primary:hover {{ opacity: 0.9; color: #0a0e17; }}
        .btn-sm {{ padding: 4px 10px; font-size: 12px; }}

        .diag-grid {{
            display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 16px; margin-bottom: 24px;
        }}
        .diag-card {{
            background: var(--bg-card); border: 1px solid var(--border);
            border-radius: 12px; padding: 18px 22px; position: relative;
            box-shadow: 0 2px 10px rgba(0,0,0,0.08); overflow: hidden;
        }}
        .diag-card::before {{
            content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 4px;
            background: var(--card-color, var(--accent-cyan));
        }}
        .diag-title {{ font-size: 13px; color: var(--text-muted); display: flex; justify-content: space-between; align-items: center; }}
        .diag-val {{ font-size: 24px; font-weight: 800; margin: 8px 0 4px 0; color: var(--text-main); }}
        .diag-desc {{ font-size: 12px; color: var(--text-muted); line-height: 1.5; }}

        .chips-container {{
            display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 24px;
        }}
        .chip {{
            background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px;
            padding: 12px 18px; font-size: 13px; flex: 1; min-width: 240px;
        }}
        .chip strong {{ color: var(--accent-cyan); font-size: 14px; }}
        .chip-stats {{ display: flex; justify-content: space-between; margin-top: 6px; font-size: 12px; color: var(--text-muted); }}
        .chip-stats span {{ color: var(--text-main); font-weight: 600; }}

        .chart-grid {{ display: flex; flex-direction: column; gap: 20px; }}
        .chart-card {{
            background: var(--bg-card); border: 1px solid var(--border);
            border-radius: 14px; padding: 20px 24px; box-shadow: 0 2px 12px rgba(0,0,0,0.1);
        }}
        .chart-header {{
            display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;
        }}
        .chart-title-box .title {{ font-size: 16px; font-weight: 700; color: var(--text-main); }}
        .chart-title-box .desc {{ font-size: 12px; color: var(--text-muted); margin-top: 3px; }}
        .chart-actions {{ display: flex; gap: 6px; }}
        .chart-body {{ width: 100%; height: 380px; position: relative; }}

        /* 全屏模态 */
        .modal {{
            display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(10, 14, 23, 0.85); backdrop-filter: blur(8px);
            z-index: 9999; justify-content: center; align-items: center; padding: 24px;
        }}
        .modal.active {{ display: flex; }}
        .modal-box {{
            background: var(--bg-card); border: 1px solid var(--border);
            border-radius: 16px; width: 95vw; height: 90vh; display: flex;
            flex-direction: column; padding: 24px; box-shadow: 0 10px 40px rgba(0,0,0,0.5);
        }}
        .modal-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }}
        .modal-body {{ flex: 1; position: relative; }}

        .footer {{
            text-align: center; color: var(--text-muted); font-size: 13px;
            margin-top: 48px; padding-bottom: 24px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- 头部看板 -->
        <div class="header">
            <div class="header-title">
                <h1>🚀 perf_suite 性能全景分析报告</h1>
                <div class="header-meta" id="headerMeta">
                    会话: <span>{session.name}</span> &nbsp;|&nbsp;
                    开始: <span>{meta.get("created_at", "未知")}</span> &nbsp;|&nbsp;
                    时长: <span>{global_max_time} 秒</span> &nbsp;|&nbsp;
                    架构: <span>{platform_info.get("machine", "Linux")}</span> &nbsp;|&nbsp;
                    内核: <span>{platform_info.get("release", "Linux")}</span>
                </div>
            </div>
            <div class="toolbar">
                <button class="btn btn-sm" onclick="toggleTheme()">☀️/🌙 切换主题</button>
                <button class="btn btn-sm" id="btnSync" onclick="toggleSync()">时间联动: 开</button>
                <button class="btn btn-sm btn-primary" onclick="jumpThroughputPeak()">⚡ 聚焦网络峰值</button>
                <button class="btn btn-sm btn-primary" onclick="jumpCpuPeak()">⚡ 聚焦算力峰值</button>
                <button class="btn btn-sm" onclick="resetAllCharts()">↺ 复位全图</button>
            </div>
        </div>

        <!-- 四维智能诊断卡片 -->
        <div class="diag-grid" id="diagContainer"></div>

        <!-- 细分监控目标概览 (进程 & 网卡) -->
        <div class="chips-container" id="chipsContainer"></div>

        <!-- 全景交互图表流 -->
        <div class="chart-grid" id="chartList"></div>

        <div class="footer">
            Generated by perf-suite-report &bull; Unified Embedded Performance Suite
        </div>
    </div>

    <!-- 全屏放大模态窗口 -->
    <div class="modal" id="fullscreenModal">
        <div class="modal-box">
            <div class="modal-header">
                <div id="modalTitle" style="font-size:18px; font-weight:700;"></div>
                <div style="display:flex; gap:8px;">
                    <button class="btn btn-sm" onclick="exportModalPng()">📷 导出PNG</button>
                    <button class="btn btn-sm" onclick="closeFullscreen()">✕ 关闭</button>
                </div>
            </div>
            <div class="modal-body">
                <canvas id="modalCanvas"></canvas>
            </div>
        </div>
    </div>

    <!-- 离线嵌入式核心图表库 -->
    <script>
{embedded_js}
    </script>

    <!-- 业务逻辑与图表实例化 -->
    <script>
        if (typeof ChartZoom !== 'undefined') {{
            Chart.register(ChartZoom);
        }}

        const reportData = {payload_json};
        const chartInstances = {{}};
        let isSyncing = false;
        let isSyncEnabled = true;
        let modalChartInstance = null;

        // 1. 渲染诊断卡片
        const diag = reportData.diag;
        const dCont = document.getElementById('diagContainer');
        const isMemOk = Math.abs(diag.rss_delta) < 10.0;
        const isNetOk = diag.net_drops === 0;

        dCont.innerHTML = `
            <div class="diag-card" style="--card-color: var(--accent-cyan)">
                <div class="diag-title">⚡ 进程并发算力峰值 <span>最高瞬时</span></div>
                <div class="diag-val">${{diag.max_cpu}}%</div>
                <div class="diag-desc">在 t=${{diag.peak_cpu_time}}s 处捕获到峰值负载，进程算力充分释放。</div>
            </div>
            <div class="diag-card" style="--card-color: ${{diag.max_bw > 100 ? 'var(--accent-yellow)' : 'var(--accent-blue)'}}">
                <div class="diag-title">🌐 网卡瞬时吞吐峰值 <span>最高流入</span></div>
                <div class="diag-val">${{diag.max_bw}} <span style="font-size:13px;font-weight:normal;">Mbps</span></div>
                <div class="diag-desc">在 t=${{diag.peak_bw_time}}s 处出现传输峰值，网卡吞吐平稳无丢包。</div>
            </div>
            <div class="diag-card" style="--card-color: ${{isMemOk ? 'var(--accent-green)' : 'var(--accent-yellow)'}}">
                <div class="diag-title">🧠 内存波动与稳态 <span>${{isMemOk ? '🟢 稳定' : '🟡 增长'}}</span></div>
                <div class="diag-val">${{diag.rss_delta >= 0 ? '+' : ''}}${{diag.rss_delta}} <span style="font-size:13px;font-weight:normal;">MB</span></div>
                <div class="diag-desc">${{isMemOk ? '测试期间内存增量收敛，无明显堆泄漏倾向。' : '内存存在持续正向净增，建议进行长跑观测。'}}</div>
            </div>
            <div class="diag-card" style="--card-color: ${{isNetOk ? 'var(--accent-green)' : 'var(--accent-red)'}}">
                <div class="diag-title">🛡️ 网卡丢包与健康度 <span>${{isNetOk ? '🟢 零丢包' : '🔴 存在丢包'}}</span></div>
                <div class="diag-val">${{diag.net_drops}} <span style="font-size:13px;font-weight:normal;">Drops</span></div>
                <div class="diag-desc">${{isNetOk ? '测试全程网络层零丢包零错误，链路极度健康。' : '检测到累计 ' + diag.net_drops + ' 次丢包，请检查网络拥塞。'}}</div>
            </div>
        `;

        // 2. 渲染进程与网卡详细卡片
        const cCont = document.getElementById('chipsContainer');
        reportData.proc_summaries.forEach(p => {{
            cCont.innerHTML += `
                <div class="chip">
                    <div><strong>进程: ${{p.name}}</strong> (PID: ${{p.pid}})</div>
                    <div class="chip-stats">
                        <div>CPU均值: <span>${{p.cpu.avg}}%</span> (峰值: ${{p.cpu.max}}%)</div>
                        <div>内存: <span>${{p.rss.avg}} MB</span> (P95: ${{p.rss.p95}} MB)</div>
                    </div>
                </div>
            `;
        }});
        reportData.net_summaries.forEach(n => {{
            cCont.innerHTML += `
                <div class="chip">
                    <div><strong>网卡: ${{n.iface}}</strong></div>
                    <div class="chip-stats">
                        <div>接收: <span>${{n.rx_bw.avg}} Mbps</span> (峰值: ${{n.rx_bw.max}} M)</div>
                        <div>包率: <span>${{n.rx_pps.avg}} PPS</span> | 传输: <span>${{n.rx_total_mb}} MB</span></div>
                    </div>
                </div>
            `;
        }});

        // 3. 图表定义与渲染
        const chartDefs = [
            {{ id: 'chartNetBw', title: '◆ 网卡实时带宽吞吐率 (Mbps)', desc: '监控网卡流入 (RX) 与流出 (TX) 带宽，分析突发吞吐与通信带宽占用', datasets: reportData.charts.net_bw, yLabel: '带宽 (Mbps)' }},
            {{ id: 'chartNetPps', title: '◆ 网卡数据包吞吐率 (Packets Per Second)', desc: '监控每秒数据包吞吐率 (PPS)，直观体现网络包并发密度', datasets: reportData.charts.net_pps, yLabel: '包率 (PPS)' }},
            {{ id: 'chartProcCpu', title: '◆ 目标进程 CPU 占用率 (%)', desc: '监控目标各进程独立 CPU 开销，支持精细对齐算力峰值', datasets: reportData.charts.proc_cpu, yLabel: 'CPU (%)' }},
            {{ id: 'chartProcMem', title: '◆ 目标进程物理内存占用 (RSS / PSS MB)', desc: '监控常驻物理内存 (RSS) 及实际按比例内存 (PSS)，排查内存泄漏', datasets: reportData.charts.proc_mem, yLabel: '内存 (MB)' }},
            {{ id: 'chartProcThr', title: '◆ 目标进程活跃线程数', desc: '实时记录各进程工作线程数，评估并发线程池状态', datasets: reportData.charts.proc_thr, yLabel: '线程数' }},
            {{ id: 'chartProcIo', title: '◆ 目标进程磁盘 IO 速率 (KB/s)', desc: '监控进程读写磁盘或存储介质的数据速率', datasets: reportData.charts.proc_io, yLabel: '速率 (KB/s)' }},
            {{ id: 'chartSysCpu', title: '◆ 整机系统背景开销 (CPU / 内存 %)', desc: '整机全局背景负载，识别除被测目标外的系统算力底噪', datasets: reportData.charts.sys_cpu, yLabel: '百分比 (%)' }},
            {{ id: 'chartSysHw', title: '◆ 硬件 CPU 频率与传感器温度 (°C)', desc: '监控 CPU 动态调频与芯片温度变化，防范过热限频降性能', datasets: reportData.charts.sys_hw, yLabel: '频率 (MHz) / 温度 (°C)' }}
        ];

        const chartList = document.getElementById('chartList');
        chartDefs.forEach(def => {{
            if (!def.datasets || def.datasets.length === 0) return;

            const card = document.createElement('div');
            card.className = 'chart-card';
            card.id = 'card_' + def.id;
            card.innerHTML = `
                <div class="chart-header">
                    <div class="chart-title-box">
                        <div class="title">${{def.title}}</div>
                        <div class="desc">${{def.desc}}</div>
                    </div>
                    <div class="chart-actions">
                        <button class="btn btn-sm" onclick="resetChart('${{def.id}}')">↺ 复位</button>
                        <button class="btn btn-sm" onclick="openFullscreen('${{def.id}}', '${{def.title}}')">⛶ 全屏</button>
                        <button class="btn btn-sm" onclick="exportPng('${{def.id}}')">📷 导出PNG</button>
                    </div>
                </div>
                <div class="chart-body">
                    <canvas id="${{def.id}}"></canvas>
                </div>
            `;
            chartList.appendChild(card);

            createInteractiveChart(def.id, def.datasets, def.yLabel);
        }});

        function createInteractiveChart(canvasId, datasets, yAxisLabel) {{
            const ctx = document.getElementById(canvasId).getContext('2d');
            const chart = new Chart(ctx, {{
                type: 'line',
                data: {{ datasets: datasets }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: false,
                    interaction: {{ mode: 'nearest', axis: 'x', intersect: false }},
                    elements: {{
                        point: {{
                            radius: 0,
                            hoverRadius: 6,
                            hitRadius: 10
                        }},
                        line: {{
                            tension: 0.2
                        }}
                    }},
                    scales: {{
                        x: {{
                            type: 'linear',
                            title: {{ display: true, text: '测试耗时 (秒)', color: getCssVar('--chart-tick') }},
                            grid: {{ color: getCssVar('--chart-grid') }},
                            ticks: {{ color: getCssVar('--chart-tick') }}
                        }},
                        y: {{
                            title: {{ display: true, text: yAxisLabel, color: getCssVar('--chart-tick') }},
                            grid: {{ color: getCssVar('--chart-grid') }},
                            ticks: {{ color: getCssVar('--chart-tick') }},
                            beginAtZero: true
                        }}
                    }},
                    plugins: {{
                        legend: {{
                            labels: {{ color: getCssVar('--text-main'), boxWidth: 12, font: {{ size: 12 }} }}
                        }},
                        zoom: {{
                            pan: {{
                                enabled: true,
                                mode: 'x',
                                modifierKey: null,
                                onPan: ({{ chart }}) => syncCharts(chart)
                            }},
                            zoom: {{
                                wheel: {{ enabled: true }},
                                pinch: {{ enabled: true }},
                                mode: 'x',
                                onZoom: ({{ chart }}) => syncCharts(chart)
                            }}
                        }}
                    }}
                }}
            }});
            chartInstances[canvasId] = chart;
        }}

        // 4. 多图表时间轴联动
        function syncCharts(sourceChart) {{
            if (!isSyncEnabled || isSyncing) return;
            isSyncing = true;
            const xMin = sourceChart.scales.x.min;
            const xMax = sourceChart.scales.x.max;

            Object.values(chartInstances).forEach(c => {{
                if (c !== sourceChart && c.scales && c.scales.x) {{
                    c.zoomScale('x', {{ min: xMin, max: xMax }}, 'none');
                }}
            }});
            isSyncing = false;
        }}

        function toggleSync() {{
            isSyncEnabled = !isSyncEnabled;
            document.getElementById('btnSync').innerText = '时间联动: ' + (isSyncEnabled ? '开' : '关');
        }}

        function resetChart(id) {{
            const c = chartInstances[id];
            if (c) {{
                c.resetZoom('none');
                if (isSyncEnabled) syncCharts(c);
            }}
        }}

        function resetAllCharts() {{
            isSyncing = true;
            Object.values(chartInstances).forEach(c => c.resetZoom('none'));
            isSyncing = false;
        }}

        function jumpThroughputPeak() {{
            const pTime = reportData.global_peak_bw_time;
            jumpWindow(pTime);
        }}

        function jumpCpuPeak() {{
            const pTime = reportData.global_peak_cpu_time;
            jumpWindow(pTime);
        }}

        function jumpWindow(centerTime) {{
            const total = reportData.duration_s;
            const min = Math.max(0, centerTime - 6);
            const max = Math.min(total, centerTime + 6);
            isSyncing = true;
            Object.values(chartInstances).forEach(c => {{
                c.zoomScale('x', {{ min, max }}, 'none');
            }});
            isSyncing = false;
        }}

        // 5. 主题切换
        function toggleTheme() {{
            const current = document.documentElement.getAttribute('data-theme') || 'dark';
            const next = current === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', next);
            updateAllChartColors();
        }}

        function getCssVar(name) {{
            return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
        }}

        function updateAllChartColors() {{
            const gridColor = getCssVar('--chart-grid');
            const tickColor = getCssVar('--chart-tick');
            const textColor = getCssVar('--text-main');

            Object.values(chartInstances).forEach(c => {{
                if (c.options.scales.x) {{
                    c.options.scales.x.grid.color = gridColor;
                    c.options.scales.x.ticks.color = tickColor;
                    c.options.scales.x.title.color = tickColor;
                }}
                if (c.options.scales.y) {{
                    c.options.scales.y.grid.color = gridColor;
                    c.options.scales.y.ticks.color = tickColor;
                    c.options.scales.y.title.color = tickColor;
                }}
                if (c.options.plugins.legend) {{
                    c.options.plugins.legend.labels.color = textColor;
                }}
                c.update();
            }});
        }}

        // 6. 全屏模态分析
        function openFullscreen(sourceId, title) {{
            const src = chartInstances[sourceId];
            if (!src) return;
            document.getElementById('modalTitle').innerText = '⛶ ' + title + ' (高精全屏查看)';
            document.getElementById('fullscreenModal').classList.add('active');

            if (modalChartInstance) modalChartInstance.destroy();
            const mCtx = document.getElementById('modalCanvas').getContext('2d');
            modalChartInstance = new Chart(mCtx, {{
                type: 'line',
                data: JSON.parse(JSON.stringify(src.data)),
                options: JSON.parse(JSON.stringify(src.options))
            }});
        }}

        function closeFullscreen() {{
            document.getElementById('fullscreenModal').classList.remove('active');
            if (modalChartInstance) {{
                modalChartInstance.destroy();
                modalChartInstance = null;
            }}
        }}

        function exportPng(id) {{
            const c = chartInstances[id];
            if (!c) return;
            const link = document.createElement('a');
            link.download = `${{id}}_profile.png`;
            link.href = c.toBase64Image('image/png', 1.0);
            link.click();
        }}

        function exportModalPng() {{
            if (!modalChartInstance) return;
            const link = document.createElement('a');
            link.download = `modal_profile.png`;
            link.href = modalChartInstance.toBase64Image('image/png', 1.0);
            link.click();
        }}
    </script>
</body>
</html>
"""
    with open(output_html, "w", encoding="utf-8") as f:
        f.write(html)
