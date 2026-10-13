#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
perf-suite-report 现代化多会话 (A/B) 跨会话对比分析与报告生成引擎
内嵌 Chart.js 离线图表，支持深浅双主题、全图联动、基准变化率指标卡表与高清导出。
"""

import os
import json
from typing import List, Dict, Any
from .analyzer import SessionData, calculate_stats, downsample_points


def _load_embedded_js():
    cur_dir = os.path.dirname(os.path.abspath(__file__))
    js_files = ["chart.umd.min.js", "hammer.min.js", "chartjs-plugin-zoom.min.js"]
    contents = []
    for jf in js_files:
        p = os.path.join(cur_dir, jf)
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                contents.append(f.read())
    return "\n".join(contents)


def build_comparison_report(session_dirs: List[str], output_html: str):
    sessions = [SessionData(s) for s in session_dirs]
    session_names = [os.path.basename(os.path.abspath(s)) for s in session_dirs]

    palette = [
        "#00F0FF", "#FF5376", "#06D6A0", "#FFD166",
        "#3A86FF", "#9C27B0", "#FF9F1C", "#2EC4B6"
    ]

    # 1. 网卡对比数据
    all_net_ifaces = set()
    for sess in sessions:
        for k in sess.series.keys():
            if k.startswith("net_"):
                all_net_ifaces.add(k[4:])

    chart_cmp_rx_bw = []
    chart_cmp_rx_pps = []

    for iface in sorted(all_net_ifaces):
        for idx, (s_name, sess) in enumerate(zip(session_names, sessions)):
            stream_key = f"net_{iface}"
            if stream_key in sess.series and sess.series[stream_key]:
                rows = sess.series[stream_key]
                times = [r.get("elapsed_s", 0.0) for r in rows]
                rx_mbps = [r.get("rx_mbps", 0.0) for r in rows]
                rx_pps = [r.get("rx_pps", 0.0) for r in rows]
                color = palette[idx % len(palette)]

                chart_cmp_rx_bw.append({
                    "label": f"[{s_name}] {iface} RX (Mbps)",
                    "data": downsample_points(times, rx_mbps),
                    "borderColor": color,
                    "borderWidth": 2,
                    "pointRadius": 0,
                    "pointHoverRadius": 6,
                    "pointHitRadius": 8,
                    "tension": 0.2
                })

                chart_cmp_rx_pps.append({
                    "label": f"[{s_name}] {iface} PPS",
                    "data": downsample_points(times, rx_pps),
                    "borderColor": color,
                    "borderWidth": 2,
                    "pointRadius": 0,
                    "pointHoverRadius": 6,
                    "pointHitRadius": 8,
                    "tension": 0.1
                })

    # 2. 进程 CPU 与 内存对比
    chart_cmp_proc_cpu = []
    chart_cmp_proc_mem = []

    for s_idx, (s_name, sess) in enumerate(zip(session_names, sessions)):
        proc_streams = [k for k in sorted(sess.series.keys()) if k.startswith("proc_")]
        for p_idx, p_stream in enumerate(proc_streams):
            rows = sess.series[p_stream]
            if not rows:
                continue
            p_name = rows[0].get("name", p_stream)
            times = [r.get("elapsed_s", 0.0) for r in rows]
            cpus = [r.get("cpu_percent", 0.0) for r in rows]
            rsss = [r.get("rss_mb", 0.0) for r in rows]
            color = palette[(s_idx * 3 + p_idx) % len(palette)]

            chart_cmp_proc_cpu.append({
                "label": f"[{s_name}] {p_name} CPU (%)",
                "data": downsample_points(times, cpus),
                "borderColor": color,
                "borderWidth": 2,
                "pointRadius": 0,
                "pointHoverRadius": 6,
                "pointHitRadius": 8,
                "tension": 0.2
            })

            chart_cmp_proc_mem.append({
                "label": f"[{s_name}] {p_name} RSS (MB)",
                "data": downsample_points(times, rsss),
                "borderColor": color,
                "borderWidth": 2,
                "pointRadius": 0,
                "pointHoverRadius": 6,
                "pointHitRadius": 8,
                "tension": 0.2
            })

    # 3. 整机系统 CPU 对比
    chart_cmp_sys_cpu = []
    for idx, (s_name, sess) in enumerate(zip(session_names, sessions)):
        if "system" in sess.series and sess.series["system"]:
            rows = sess.series["system"]
            times = [r.get("elapsed_s", 0.0) for r in rows]
            sys_cpu = [r.get("sys_cpu_percent", 0.0) for r in rows]
            color = palette[idx % len(palette)]

            chart_cmp_sys_cpu.append({
                "label": f"[{s_name}] 整机 CPU (%)",
                "data": downsample_points(times, sys_cpu),
                "borderColor": color,
                "borderWidth": 2,
                "pointRadius": 0,
                "pointHoverRadius": 6,
                "pointHitRadius": 8,
                "tension": 0.2
            })

    # 4. 汇总统计表格构造 (以第一个会话为 Baseline)
    baseline_stats = sessions[0].get_summary_stats() if sessions else {}
    table_rows = []

    for s_idx, (s_name, sess) in enumerate(zip(session_names, sessions)):
        stats = sess.get_summary_stats()
        for stream, metrics in sorted(stats.items()):
            for m_name, s_val in sorted(metrics.items()):
                if m_name not in ("rx_mbps", "tx_mbps", "rx_pps", "cpu_percent", "rss_mb", "sys_cpu_percent", "threads"):
                    continue

                avg_val = s_val.get("avg", 0.0)
                p95_val = s_val.get("p95", 0.0)
                max_val = s_val.get("max", 0.0)

                diff_str = "-"
                if s_idx == 0:
                    diff_str = "<span style='color:var(--text-muted);'>基准 (Baseline)</span>"
                else:
                    base_m = baseline_stats.get(stream, {}).get(m_name, {}).get("avg")
                    if base_m and base_m > 0:
                        diff = ((avg_val - base_m) / base_m) * 100.0
                        if abs(diff) < 0.1:
                            diff_str = "<span style='color:var(--text-muted);'>持平 (0%)</span>"
                        elif diff > 0:
                            diff_str = f"<span style='color:var(--accent-red);font-weight:bold;'>↑ +{diff:.1f}%</span>"
                        else:
                            diff_str = f"<span style='color:var(--accent-green);font-weight:bold;'>↓ {diff:.1f}%</span>"

                table_rows.append(f"""
                <tr>
                    <td><strong>{s_name}</strong></td>
                    <td><code>{stream}</code></td>
                    <td><strong>{m_name}</strong></td>
                    <td>{avg_val}</td>
                    <td><span style="color:var(--accent-blue);font-weight:bold;">{p95_val}</span></td>
                    <td><span style="color:var(--accent-red);font-weight:bold;">{max_val}</span></td>
                    <td>{diff_str}</td>
                </tr>
                """)

    report_payload = {
        "session_names": session_names,
        "charts": {
            "net_rx_bw": chart_cmp_rx_bw,
            "net_rx_pps": chart_cmp_rx_pps,
            "proc_cpu": chart_cmp_proc_cpu,
            "proc_mem": chart_cmp_proc_mem,
            "sys_cpu": chart_cmp_sys_cpu
        }
    }

    embedded_js = _load_embedded_js()
    payload_json = json.dumps(report_payload, ensure_ascii=False)
    sess_badges = " ".join(f"<span class='badge'><code>{n}</code></span>" for n in session_names)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>perf_suite A/B 跨会话对比分析报告</title>
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
        .header-title h1 {{ margin: 0 0 6px 0; font-size: 22px; font-weight: 700; }}
        .header-meta {{ font-size: 13px; color: var(--text-muted); }}
        .badge {{ background: var(--bg-card-sub); padding: 3px 8px; border-radius: 6px; border: 1px solid var(--border); }}
        .toolbar {{ display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }}
        .btn {{
            background: var(--bg-card-sub); border: 1px solid var(--border);
            color: var(--text-main); padding: 7px 14px; border-radius: 8px;
            font-size: 13px; font-weight: 500; cursor: pointer; display: inline-flex;
            align-items: center; gap: 6px;
        }}
        .btn:hover {{ border-color: var(--accent-cyan); color: var(--accent-cyan); }}
        .btn-sm {{ padding: 4px 10px; font-size: 12px; }}

        .card {{
            background: var(--bg-card); border: 1px solid var(--border);
            border-radius: 14px; padding: 20px 24px; margin-bottom: 24px;
            box-shadow: 0 2px 12px rgba(0,0,0,0.1);
        }}
        .card h2 {{ font-size: 16px; font-weight: 700; margin: 0 0 16px 0; color: var(--text-main); }}

        table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
        th, td {{ padding: 12px 14px; border-bottom: 1px solid var(--border); text-align: left; }}
        th {{ background: var(--bg-card-sub); color: var(--text-muted); font-weight: 600; }}
        tr:hover {{ background: var(--bg-card-sub); }}
        code {{ background: var(--bg-card-sub); padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 12px; color: var(--accent-cyan); }}

        .chart-card {{
            background: var(--bg-card); border: 1px solid var(--border);
            border-radius: 14px; padding: 20px 24px; margin-bottom: 20px;
        }}
        .chart-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }}
        .chart-title-box .title {{ font-size: 16px; font-weight: 700; color: var(--text-main); }}
        .chart-title-box .desc {{ font-size: 12px; color: var(--text-muted); margin-top: 3px; }}
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
            flex-direction: column; padding: 24px;
        }}
        .modal-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }}
        .modal-body {{ flex: 1; position: relative; }}

        .footer {{ text-align: center; color: var(--text-muted); font-size: 13px; margin-top: 48px; padding-bottom: 24px; }}
    </style>
</head>
<body>
    <div class="container">
        <!-- 头部看板 -->
        <div class="header">
            <div class="header-title">
                <h1>⚖️ perf_suite 跨会话 (A/B) 综合对比评测报告</h1>
                <div class="header-meta">
                    对比会话 ({len(session_names)} 组): {sess_badges} &nbsp;|&nbsp;
                    基准会话: <code>{session_names[0]}</code>
                </div>
            </div>
            <div class="toolbar">
                <button class="btn btn-sm" onclick="toggleTheme()">☀️/🌙 切换主题</button>
                <button class="btn btn-sm" id="btnSync" onclick="toggleSync()">时间联动: 开</button>
                <button class="btn btn-sm" onclick="resetAllCharts()">↺ 复位全图</button>
            </div>
        </div>

        <!-- 核心指标跨会话对比表 -->
        <div class="card">
            <h2>📊 核心指标跨会话对比表 (相对基准会话变化率)</h2>
            <table>
                <thead>
                    <tr>
                        <th>会话名称</th>
                        <th>数据流 (Stream)</th>
                        <th>监控指标项</th>
                        <th>平均值 (Avg)</th>
                        <th>95分位数 (P95)</th>
                        <th>峰值 (Max)</th>
                        <th>相对基准变化</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(table_rows)}
                </tbody>
            </table>
        </div>

        <!-- 对比图表集 -->
        <div id="chartList"></div>

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

    <!-- 图表渲染与交互逻辑 -->
    <script>
        if (typeof ChartZoom !== 'undefined') {{
            Chart.register(ChartZoom);
        }}

        const reportData = {payload_json};
        const chartInstances = {{}};
        let isSyncing = false;
        let isSyncEnabled = true;
        let modalChartInstance = null;

        const chartDefs = [
            {{ id: 'cmpNetRxBw', title: '◆ 跨会话网卡接收带宽对比 (RX Mbps)', desc: '对比各会话网卡流量吞吐率，验证网络优化与压缩效果', datasets: reportData.charts.net_rx_bw, yLabel: '接收带宽 (Mbps)' }},
            {{ id: 'cmpNetRxPps', title: '◆ 跨会话网卡包吞吐率对比 (PPS)', desc: '对比各会话网络包处理密度', datasets: reportData.charts.net_rx_pps, yLabel: '包吞吐率 (PPS)' }},
            {{ id: 'cmpProcCpu', title: '◆ 跨会话目标进程 CPU 占用率对比 (%)', desc: '对比各版本算法或程序进程 CPU 开销', datasets: reportData.charts.proc_cpu, yLabel: 'CPU (%)' }},
            {{ id: 'cmpProcMem', title: '◆ 跨会话目标进程物理内存对比 (RSS MB)', desc: '对比各版本程序物理内存占用与缓存水平', datasets: reportData.charts.proc_mem, yLabel: '内存 (MB)' }},
            {{ id: 'cmpSysCpu', title: '◆ 跨会话整机 CPU 负载对比 (%)', desc: '对比整机全局背景算力开销', datasets: reportData.charts.sys_cpu, yLabel: '整机 CPU (%)' }}
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
                    <div style="display:flex; gap:6px;">
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
                            labels: {{ color: getCssVar('--text-main'), boxWidth: 14, font: {{ size: 12 }} }}
                        }},
                        zoom: {{
                            pan: {{
                                enabled: true,
                                mode: 'x',
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
            link.download = `modal_cmp_profile.png`;
            link.href = modalChartInstance.toBase64Image('image/png', 1.0);
            link.click();
        }}
    </script>
</body>
</html>
"""
    with open(output_html, "w", encoding="utf-8") as f:
        f.write(html)
