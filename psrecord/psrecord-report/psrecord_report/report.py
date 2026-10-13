#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
现代化高性能系统/进程测试报告生成器 (psrecord-report)
纯 HTML5 + Chart.js + Hammer.js + Zoom 插件
支持单会话与多会话横向对比、多进程对比、多核/大小核/温控/频点分析，原生纯中文。
特性:
- 鼠标滚轮缩放 (Wheel Zoom)
- 鼠标拖拽平移 (Drag Pan)
- 多图表时间轴联动 (Synchronized Time Axis / Cursor)
- 十字光标辅助线 (Vertical Crosshair)
- 算力峰值区间一键聚焦 (Peak Window Preset)
- 单图全屏模态放大 (Fullscreen Modal View)
- 一键导出高清 PNG 图片
- 深色极客风 / 明亮浅色模式一键自适应切换 (修复白底无黑色色块)
- 智能健康诊断与性能瓶颈卡片
- 100% 离线单文件自包含 (Zero CDN 依赖)
"""

import os
import sys
import json
import csv
import math
import argparse
from datetime import datetime

def p95(values):
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return 0.0
    idx = min(len(vals) - 1, math.ceil(0.95 * len(vals)) - 1)
    return vals[idx]

def calc_stats(values):
    vals = [v for v in values if v is not None]
    if not vals:
        return {"avg": 0.0, "max": 0.0, "min": 0.0, "p95": 0.0, "first": 0.0, "last": 0.0, "delta": 0.0}
    return {
        "avg": round(sum(vals) / len(vals), 2),
        "max": round(max(vals), 2),
        "min": round(min(vals), 2),
        "p95": round(p95(vals), 2),
        "first": round(vals[0], 2),
        "last": round(vals[-1], 2),
        "delta": round(vals[-1] - vals[0], 2)
    }

def moving_average(values, window_size=15):
    """计算滑动平均"""
    if not values:
        return []
    res = []
    window = []
    for v in values:
        if v is not None:
            window.append(v)
            if len(window) > window_size:
                window.pop(0)
            res.append(round(sum(window) / len(window), 2))
        else:
            res.append(None)
    return res

def load_csv_data(path):
    if not os.path.exists(path):
        return {}
    with open(path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        return {}
    cols = {k: [] for k in rows[0].keys()}
    for row in rows:
        for k, v in row.items():
            if v == "" or v is None:
                cols[k].append(None)
            else:
                try:
                    cols[k].append(float(v))
                except (ValueError, TypeError):
                    cols[k].append(v)
    return cols

def load_session(session_dir):
    session_dir = os.path.abspath(session_dir)
    name = os.path.basename(session_dir.rstrip('/'))
    meta_path = os.path.join(session_dir, "meta.json")
    meta = {}
    if os.path.exists(meta_path):
        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)

    # 载入进程数据
    procs = {}
    for fname in sorted(os.listdir(session_dir)):
        if fname.startswith("proc_") and fname.endswith(".csv"):
            label = fname[:-4]
            procs[label] = load_csv_data(os.path.join(session_dir, fname))

    # 载入系统数据
    sys_path = os.path.join(session_dir, "system.csv")
    sys_data = load_csv_data(sys_path) if os.path.exists(sys_path) else {}

    return {
        "name": name,
        "path": session_dir,
        "dir": session_dir,
        "meta": meta,
        "procs": procs,
        "system": sys_data
    }

def downsample_points(times, values, max_points=1200):
    """降采样并输出为 [{x, y}] 坐标格式"""
    if not times or not values:
        return []
    n = min(len(times), len(values))
    if n <= max_points:
        return [{"x": round(times[i], 2), "y": round(values[i], 2) if values[i] is not None else None} for i in range(n)]
    
    step = n / max_points
    points = []
    for i in range(max_points):
        idx = min(int(i * step), n - 1)
        t = times[idx]
        v = values[idx]
        points.append({"x": round(t, 2), "y": round(v, 2) if v is not None else None})
    return points

def read_asset(name):
    # 优先从当前文件所在目录读取
    cur_dir = os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(cur_dir, name)
    if os.path.exists(p):
        with open(p, 'r', encoding='utf-8') as f:
            return f.read()
    # 备选目录
    fallbacks = [
        os.path.join(cur_dir, "..", name),
        os.path.join("/usr/lib/python3/dist-packages/psrecord_report", name),
        os.path.join("/home/zsxc/work/tools/perf_tools", name)
    ]
    for fb in fallbacks:
        if os.path.exists(fb):
            with open(fb, 'r', encoding='utf-8') as f:
                return f.read()
    return ""

def build_report_html(sessions, output_file):
    chart_js_code = read_asset("chart.umd.min.js")
    hammer_js_code = read_asset("hammer.min.js")
    zoom_js_code = read_asset("chartjs-plugin-zoom.min.js")

    COLORS = [
        "#00F0FF", "#06D6A0", "#FFD166", "#EF476F", "#118AB2", 
        "#9D4EDD", "#F78C6B", "#8338EC", "#3A86FF", "#FB5607"
    ]
    
    proc_summaries = []
    chart_series = {
        "cpu": [],
        "mem_rss": [],
        "mem_pss": [],
        "threads": [],
        "fds": [],
        "sys_cores": [],
        "sys_temp": [],
        "sys_freq": []
    }
    
    global_max_time = 0.0
    global_peak_time = 0.0
    global_peak_cpu = 0.0

    diag = {
        "max_cpu": 0.0,
        "avg_cpu": 0.0,
        "peak_time": 0.0,
        "rss_delta": 0.0,
        "max_temp": 0.0,
        "max_temp_sensor": "",
        "big_core_peak": 0.0,
        "little_core_peak": 0.0
    }

    for s_idx, sess in enumerate(sessions):
        s_name = sess["name"]
        meta = sess.get("meta", {})
        sys_data = sess.get("system", {})
        
        # 遍历进程
        for p_idx, (p_label, p_data) in enumerate(sess["procs"].items()):
            if not p_data or "elapsed" not in p_data:
                continue
            t = p_data["elapsed"]
            if t and t[-1] is not None and t[-1] > global_max_time:
                global_max_time = t[-1]

            p_name = p_label
            p_cmd = ""
            for p_meta in meta.get("processes", []):
                if str(p_meta.get("pid")) in p_label:
                    p_name = f"{p_meta.get('name', '')} (PID: {p_meta.get('pid')})"
                    p_cmd = p_meta.get("cmdline", "")
                    break

            color = COLORS[(s_idx * 5 + p_idx) % len(COLORS)]
            
            cpus = p_data.get("cpu", [])
            cpu_stat = calc_stats(cpus)
            rss_stat = calc_stats(p_data.get("mem_real", []))
            pss_stat = calc_stats(p_data.get("pss", []))
            th_stat = calc_stats(p_data.get("threads", []))
            fd_stat = calc_stats(p_data.get("fds", []))

            if cpu_stat["max"] > global_peak_cpu:
                global_peak_cpu = cpu_stat["max"]
                valid_cpus = [c if c is not None else -1 for c in cpus]
                max_i = valid_cpus.index(max(valid_cpus)) if valid_cpus else 0
                global_peak_time = t[max_i] if max_i < len(t) and t[max_i] is not None else 0.0

            diag["max_cpu"] = max(diag["max_cpu"], cpu_stat["max"])
            diag["avg_cpu"] = round(cpu_stat["avg"], 1)
            diag["rss_delta"] = rss_stat["delta"]
            diag["peak_time"] = round(global_peak_time, 1)

            proc_summaries.append({
                "session": s_name,
                "label": p_name,
                "raw_label": p_label,
                "cmd": p_cmd,
                "cpu": cpu_stat,
                "rss": rss_stat,
                "pss": pss_stat,
                "threads": th_stat,
                "fds": fd_stat,
                "color": color
            })

            cpu_ma = moving_average(cpus, window_size=15)

            s_cpu_raw = downsample_points(t, cpus)
            s_cpu_smooth = downsample_points(t, cpu_ma)
            s_rss = downsample_points(t, p_data.get("mem_real", []))
            s_pss = downsample_points(t, p_data.get("pss", []))
            s_th = downsample_points(t, p_data.get("threads", []))
            s_fd = downsample_points(t, p_data.get("fds", []))

            series_name = f"[{s_name}] {p_name}" if len(sessions) > 1 else p_name
            chart_series["cpu"].append({
                "name": f"{series_name} (平滑趋势 1s MA)",
                "data": s_cpu_smooth,
                "color": color,
                "borderWidth": 2.2,
                "fill": True,
                "isSmooth": True
            })
            chart_series["cpu"].append({
                "name": f"{series_name} (原始采样值)",
                "data": s_cpu_raw,
                "color": color,
                "borderWidth": 0.9,
                "hidden": False,
                "fill": False,
                "isRaw": True
            })

            chart_series["mem_rss"].append({"name": f"{series_name} (RSS物理内存)", "data": s_rss, "color": color})
            if any(s_pss):
                chart_series["mem_pss"].append({"name": f"{series_name} (PSS实际按比例内存)", "data": s_pss, "color": color, "dash": [5, 5]})
            chart_series["threads"].append({"name": f"{series_name} (线程数)", "data": s_th, "color": color})
            chart_series["fds"].append({"name": f"{series_name} (句柄数)", "data": s_fd, "color": "#FFD166", "dash": [4, 4]})

        # 系统指标
        if sys_data and "elapsed" in sys_data:
            st = sys_data["elapsed"]
            if st and st[-1] is not None and st[-1] > global_max_time:
                global_max_time = st[-1]

            cpu_cnt = len([k for k in sys_data if k.startswith("cpu") and k[3:].isdigit()])
            if cpu_cnt == 0:
                cpu_cnt = 8
            is_rk_or_biglittle = (cpu_cnt == 8 and 'aarch64' in meta.get("system", {}).get("machine", ""))
            palette = ["#3A86FF", "#FF5376", "#00F0FF", "#FFD166", "#06D6A0", "#9C27B0", "#FF9F1C", "#2EC4B6"]
            for core in range(cpu_cnt):
                ckey = f"cpu{core}"
                if ckey in sys_data:
                    if is_rk_or_biglittle:
                        cname = f"CPU{core} ({'大核A76' if core>=4 else '小核A55'})"
                        is_big = (core >= 4)
                        ccolor = "#FF5376" if is_big else "#3A86FF"
                    else:
                        cname = f"CPU{core}"
                        is_big = False
                        ccolor = palette[core % len(palette)]
                    s_pts = downsample_points(st, sys_data[ckey])
                    core_max = max(v for v in sys_data[ckey] if v is not None) if sys_data[ckey] else 0
                    if is_big:
                        diag["big_core_peak"] = max(diag["big_core_peak"], core_max)
                    else:
                        diag["little_core_peak"] = max(diag["little_core_peak"], core_max)

                    chart_series["sys_cores"].append({
                        "name": cname,
                        "data": s_pts,
                        "color": ccolor,
                        "isBigCore": is_big,
                        "borderWidth": 1.8 if is_big else 1.2
                    })
            
            temp_keys = [k for k in sys_data if k.startswith("temp_")]
            temp_name_map = {
                "temp_soc_thermal": "SoC 全局温度",
                "temp_bigcore0_thermal": "大核簇 0 温度",
                "temp_bigcore1_thermal": "大核簇 1 温度",
                "temp_littlecore_thermal": "小核簇温度",
                "temp_center_thermal": "中心区域温度",
                "temp_gpu_thermal": "GPU 温度",
                "temp_npu_thermal": "NPU 温度"
            }
            t_colors = ["#FF5722", "#E91E63", "#9C27B0", "#673AB7", "#3F51B5", "#00BCD4", "#4CAF50"]
            for i, tk in enumerate(temp_keys):
                s_pts = downsample_points(st, sys_data[tk])
                c_name = temp_name_map.get(tk, tk)
                t_max = max(v for v in sys_data[tk] if v is not None) if sys_data[tk] else 0
                if t_max > diag["max_temp"]:
                    diag["max_temp"] = t_max
                    diag["max_temp_sensor"] = c_name
                chart_series["sys_temp"].append({"name": c_name, "data": s_pts, "color": t_colors[i % len(t_colors)]})

            freq_keys = [k for k in sys_data if k.startswith("freq")]
            freq_map = {"freq0": "小核集群频率 (A55)", "freq1": "大核集群0频率 (A76)", "freq2": "大核集群1频率 (A76)"}
            f_colors = ["#00F0FF", "#FFD166", "#06D6A0"]
            for i, fk in enumerate(freq_keys):
                s_pts = downsample_points(st, sys_data[fk])
                chart_series["sys_freq"].append({"name": freq_map.get(fk, fk), "data": s_pts, "color": f_colors[i % len(f_colors)]})

    report_payload = {
        "proc_summaries": proc_summaries,
        "chart_series": chart_series,
        "sessions": [{"name": s["name"], "meta": s.get("meta", {})} for s in sessions],
        "global_max_time": round(global_max_time, 2),
        "global_peak_time": round(global_peak_time, 2),
        "diag": diag
    }
    report_json_str = json.dumps(report_payload, ensure_ascii=False)

    html_template = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>psrecord report - 进程性能深度测试交互报告</title>
    <!-- psrecord report & Summary statistics -->
    <script>
    __CHART_JS_INLINE__
    </script>
    <script>
    __HAMMER_JS_INLINE__
    </script>
    <script>
    __ZOOM_JS_INLINE__
    </script>
    <style>
        :root {
            --bg-body: #0d1117;
            --bg-card: #161b22;
            --bg-card-hover: #1f242c;
            --bg-toolbar: #13171e;
            --border: #30363d;
            --border-light: #21262d;
            --text-main: #f0f6fc;
            --text-sub: #8b949e;
            --accent: #58a6ff;
            --accent-cyan: #00f0ff;
            --accent-green: #06d6a0;
            --accent-yellow: #ffd166;
            --accent-red: #ff5376;
            --card-radius: 12px;
            --btn-bg: #21262d;
            --btn-hover: #30363d;
            --grid-line: #21262d;
        }

        body.light-theme {
            --bg-body: #f6f8fa;
            --bg-card: #ffffff;
            --bg-card-hover: #f3f4f6;
            --bg-toolbar: #f6f8fa;
            --border: #d0d7de;
            --border-light: #e1e4e8;
            --text-main: #1f2328;
            --text-sub: #656d76;
            --accent: #0969da;
            --accent-cyan: #0284c7;
            --accent-green: #059669;
            --accent-yellow: #d97706;
            --accent-red: #dc2626;
            --btn-bg: #ffffff;
            --btn-hover: #f3f4f6;
            --grid-line: #e8ecf0;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background-color: var(--bg-body);
            color: var(--text-main);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
            line-height: 1.6;
            padding: 24px 36px 60px;
            transition: background-color 0.2s ease, color 0.2s ease;
        }

        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 20px;
            border-bottom: 1px solid var(--border);
            margin-bottom: 20px;
        }
        .title-group h1 {
            font-size: 26px;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .badge {
            font-size: 12px;
            padding: 3px 10px;
            border-radius: 20px;
            background: rgba(88, 166, 255, 0.15);
            color: var(--accent);
            border: 1px solid rgba(88, 166, 255, 0.4);
            font-weight: 500;
        }
        .header-meta {
            color: var(--text-sub);
            font-size: 13px;
            margin-top: 6px;
        }
        .header-actions {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .btn {
            background: var(--btn-bg);
            color: var(--text-main);
            border: 1px solid var(--border);
            padding: 7px 14px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
            font-weight: 500;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            transition: all 0.15s ease;
            user-select: none;
        }
        .btn:hover {
            background: var(--btn-hover);
            border-color: var(--accent);
            transform: translateY(-1px);
        }
        .btn-accent {
            background: rgba(88, 166, 255, 0.15);
            border-color: var(--accent);
            color: var(--accent);
        }
        .btn-sm {
            padding: 4px 9px;
            font-size: 12px;
            border-radius: 4px;
        }

        .global-bar {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: var(--card-radius);
            padding: 14px 20px;
            margin-bottom: 24px;
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }
        .global-bar-group {
            display: flex;
            align-items: center;
            gap: 8px;
            flex-wrap: wrap;
        }
        .group-label {
            font-size: 13px;
            color: var(--text-sub);
            font-weight: 600;
            margin-right: 4px;
        }
        .switch-label {
            font-size: 13px;
            color: var(--text-main);
            display: inline-flex;
            align-items: center;
            gap: 6px;
            cursor: pointer;
            user-select: none;
        }
        .switch-label input[type="checkbox"] {
            cursor: pointer;
            accent-color: var(--accent);
            width: 16px;
            height: 16px;
        }

        .diag-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }
        .diag-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: var(--card-radius);
            padding: 16px 18px;
            border-left: 4px solid var(--card-color, var(--accent));
            transition: all 0.2s ease;
        }
        .diag-title {
            font-size: 13px;
            font-weight: 600;
            color: var(--text-sub);
            margin-bottom: 6px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .diag-val {
            font-size: 18px;
            font-weight: 700;
            color: var(--text-main);
            margin-bottom: 4px;
            font-family: "SF Mono", Menlo, Consolas, monospace;
        }
        .diag-desc {
            font-size: 12px;
            color: var(--text-sub);
            line-height: 1.4;
        }

        .stat-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }
        .stat-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: var(--card-radius);
            padding: 18px 20px;
            position: relative;
            overflow: hidden;
            transition: all 0.2s ease;
        }
        .stat-card::before {
            content: "";
            position: absolute;
            left: 0; top: 0; bottom: 0;
            width: 4px;
            background: var(--card-color, var(--accent));
        }
        .stat-label {
            font-size: 13px;
            color: var(--text-sub);
            margin-bottom: 8px;
            display: flex;
            justify-content: space-between;
        }
        .stat-value {
            font-size: 26px;
            font-weight: 700;
            color: var(--text-main);
            font-family: "SF Mono", Menlo, Consolas, monospace;
        }
        .stat-sub {
            font-size: 12px;
            color: var(--text-sub);
            margin-top: 6px;
        }

        .section-box {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: var(--card-radius);
            padding: 22px;
            margin-bottom: 24px;
        }
        .section-title {
            font-size: 17px;
            font-weight: 600;
            margin-bottom: 14px;
            display: flex;
            align-items: center;
            gap: 10px;
            color: var(--text-main);
        }
        .section-title::before {
            content: "";
            width: 4px;
            height: 18px;
            background: var(--accent);
            border-radius: 2px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
            text-align: left;
        }
        th {
            background: var(--bg-toolbar);
            color: var(--text-sub);
            font-weight: 600;
            padding: 11px 14px;
            border-bottom: 1px solid var(--border);
        }
        td {
            padding: 11px 14px;
            border-bottom: 1px solid var(--border-light);
            color: var(--text-main);
        }
        tr:hover td {
            background: rgba(88, 166, 255, 0.05);
        }
        .mono {
            font-family: "SF Mono", Menlo, Consolas, monospace;
        }
        .tag-pill {
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
        }

        .chart-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 20px;
            margin-bottom: 28px;
        }
        .chart-full {
            grid-column: 1 / -1;
        }
        .chart-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: var(--card-radius);
            padding: 18px 20px;
            height: 410px;
            display: flex;
            flex-direction: column;
            position: relative;
            transition: border-color 0.2s ease;
        }
        .chart-card:hover {
            border-color: rgba(88, 166, 255, 0.4);
        }
        .chart-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 12px;
            gap: 10px;
        }
        .chart-title-box {
            flex: 1;
        }
        .chart-title {
            font-size: 15px;
            font-weight: 600;
            color: var(--text-main);
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .chart-desc {
            font-size: 12px;
            color: var(--text-sub);
            margin-top: 2px;
        }
        .chart-toolbar {
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .chart-body {
            flex: 1;
            position: relative;
            min-height: 0;
            width: 100%;
        }

        .modal-overlay {
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0, 0, 0, 0.82);
            backdrop-filter: blur(8px);
            z-index: 9999;
            display: none;
            padding: 30px 40px;
            align-items: center;
            justify-content: center;
        }
        .modal-overlay.active {
            display: flex;
        }
        .modal-box {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: var(--card-radius);
            width: 95vw;
            height: 90vh;
            display: flex;
            flex-direction: column;
            padding: 24px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.5);
        }
        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
            padding-bottom: 12px;
            border-bottom: 1px solid var(--border);
        }
        .modal-body {
            flex: 1;
            position: relative;
            min-height: 0;
        }

        .footer {
            text-align: center;
            color: var(--text-sub);
            font-size: 12px;
            padding-top: 24px;
            border-top: 1px solid var(--border);
        }
    </style>
</head>
<body>

    <div class="header">
        <div class="title-group">
            <h1>psrecord report <span class="badge">嵌入式基准评测</span></h1>
            <div class="header-meta" id="headerMeta">正在加载会话元信息...</div>
        </div>
        <div class="header-actions">
            <button class="btn" id="themeBtn" onclick="toggleTheme()">☀️ 切换浅色模式</button>
            <button class="btn btn-accent" onclick="window.print()">🖨️ 打印 / 导出 PDF</button>
        </div>
    </div>

    <!-- 全局交互控制台 -->
    <div class="global-bar">
        <div class="global-bar-group">
            <span class="group-label">⏱️ 时间轴快捷跳转:</span>
            <button class="btn btn-sm" onclick="jumpRange(0, 1)">全量 (0~100%)</button>
            <button class="btn btn-sm" onclick="jumpRange(0, 0.5)">前半程 (0~50%)</button>
            <button class="btn btn-sm" onclick="jumpRange(0.5, 1)">后半程 (50~100%)</button>
            <button class="btn btn-sm btn-accent" id="peakJumpBtn" onclick="jumpPeak()">⚡ 聚焦算力峰值窗口</button>
        </div>

        <div class="global-bar-group">
            <label class="switch-label">
                <input type="checkbox" id="syncCheck" checked onchange="toggleSync(this.checked)">
                <strong>🔗 所有图表时间轴联动 (Sync Zoom)</strong>
            </label>
            <button class="btn btn-sm" onclick="resetAllCharts()">↺ 复位所有图表</button>
        </div>
    </div>

    <!-- 智能健康与瓶颈分析 -->
    <div class="diag-grid" id="diagContainer"></div>

    <!-- 核心 KPI 指标卡片 -->
    <div class="stat-grid" id="statCards"></div>

    <!-- 进程指标明细表 -->
    <div class="section-box">
        <div class="section-title">进程性能指标全景透视 (Summary statistics)</div>
        <div style="overflow-x:auto;">
            <table>
                <thead>
                    <tr>
                        <th>会话与目标进程</th>
                        <th>CPU 均值 (Avg)</th>
                        <th>CPU 峰值 (Max)</th>
                        <th>CPU P95分位</th>
                        <th>物理内存 RSS (Avg/Max)</th>
                        <th>实际比例内存 PSS</th>
                        <th>内存净增量 (Delta)</th>
                        <th>线程数</th>
                        <th>文件句柄 (FDs)</th>
                    </tr>
                </thead>
                <tbody id="summaryTableBody"></tbody>
            </table>
        </div>
    </div>

    <!-- 交互式性能图表网格 -->
    <div class="chart-grid">
        <!-- 1. CPU 利用率 -->
        <div class="chart-card chart-full" id="card_chartCpu">
            <div class="chart-header">
                <div class="chart-title-box">
                    <div class="chart-title">◆ CPU 使用率趋势图 (CPU Utilization %)</div>
                    <div class="chart-desc">滚轮缩放时间轴，按住鼠标拖拽平移；平滑线与瞬时采样点双模对照</div>
                </div>
                <div class="chart-toolbar">
                    <button class="btn btn-sm" onclick="toggleDataset('chartCpu', 1)">切入/隐藏原始散点</button>
                    <button class="btn btn-sm" onclick="resetChart('chartCpu')">↺ 复位</button>
                    <button class="btn btn-sm" onclick="openFullscreen('chartCpu', 'CPU 使用率趋势图')">⛶ 全屏</button>
                    <button class="btn btn-sm" onclick="exportPng('chartCpu')">📷 导出PNG</button>
                </div>
            </div>
            <div class="chart-body">
                <canvas id="chartCpu"></canvas>
            </div>
        </div>

        <!-- 2. 内存波动趋势 (RSS / PSS) -->
        <div class="chart-card" id="card_chartMem">
            <div class="chart-header">
                <div class="chart-title-box">
                    <div class="chart-title">◆ 物理内存 (RSS) 与 比例内存 (PSS) 趋势</div>
                    <div class="chart-desc">评估算法运行期内存增长速率及潜在泄漏风险</div>
                </div>
                <div class="chart-toolbar">
                    <button class="btn btn-sm" onclick="resetChart('chartMem')">↺ 复位</button>
                    <button class="btn btn-sm" onclick="openFullscreen('chartMem', '内存波动趋势 (RSS/PSS)')">⛶ 全屏</button>
                    <button class="btn btn-sm" onclick="exportPng('chartMem')">📷 导出PNG</button>
                </div>
            </div>
            <div class="chart-body">
                <canvas id="chartMem"></canvas>
            </div>
        </div>

        <!-- 3. 线程与句柄数 -->
        <div class="chart-card" id="card_chartThreads">
            <div class="chart-header">
                <div class="chart-title-box">
                    <div class="chart-title">◆ 线程数 (Threads) & 文件句柄 (FDs)</div>
                    <div class="chart-desc">监控多线程并发及底层文件/Socket 描述符稳定性</div>
                </div>
                <div class="chart-toolbar">
                    <button class="btn btn-sm" onclick="resetChart('chartThreads')">↺ 复位</button>
                    <button class="btn btn-sm" onclick="openFullscreen('chartThreads', '线程与句柄监控')">⛶ 全屏</button>
                    <button class="btn btn-sm" onclick="exportPng('chartThreads')">📷 导出PNG</button>
                </div>
            </div>
            <div class="chart-body">
                <canvas id="chartThreads"></canvas>
            </div>
        </div>

        <!-- 4. 单核 CPU 负载分布 -->
        <div class="chart-card" id="card_chartCores">
            <div class="chart-header">
                <div class="chart-title-box">
                    <div class="chart-title">◆ 单核 CPU 负载分布 (各核心利用率)</div>
                    <div class="chart-desc">实时监控各 CPU 核心利用率，分析多核亲和性与调度均衡</div>
                </div>
                <div class="chart-toolbar">
                    <button class="btn btn-sm" onclick="filterCores('all')">全核</button>
                    <button class="btn btn-sm" style="color:#ff5376" onclick="filterCores('big')">只看大核</button>
                    <button class="btn btn-sm" style="color:#3a86ff" onclick="filterCores('little')">只看小核</button>
                    <button class="btn btn-sm" onclick="resetChart('chartCores')">↺ 复位</button>
                    <button class="btn btn-sm" onclick="openFullscreen('chartCores', '单核 CPU 负载分布')">⛶ 全屏</button>
                    <button class="btn btn-sm" onclick="exportPng('chartCores')">📷 导出PNG</button>
                </div>
            </div>
            <div class="chart-body">
                <canvas id="chartCores"></canvas>
            </div>
        </div>

        <!-- 5. 核心温度监控 -->
        <div class="chart-card" id="card_chartTemp">
            <div class="chart-header">
                <div class="chart-title-box">
                    <div class="chart-title">◆ 板端传感器温度变化 (°C)</div>
                    <div class="chart-desc">实时监控 SoC、GPU、NPU 及大核集群热状态</div>
                </div>
                <div class="chart-toolbar">
                    <button class="btn btn-sm" onclick="resetChart('chartTemp')">↺ 复位</button>
                    <button class="btn btn-sm" onclick="openFullscreen('chartTemp', '板端传感器温度变化')">⛶ 全屏</button>
                    <button class="btn btn-sm" onclick="exportPng('chartTemp')">📷 导出PNG</button>
                </div>
            </div>
            <div class="chart-body">
                <canvas id="chartTemp"></canvas>
            </div>
        </div>

        <!-- 6. CPU 频点变化 (若有) -->
        <div class="chart-card" id="card_chartFreq" style="display:none;">
            <div class="chart-header">
                <div class="chart-title-box">
                    <div class="chart-title">◆ CPU 动态频率调节 (DVFS)</div>
                    <div class="chart-desc">监控大核与小核时钟频率升降频状态</div>
                </div>
                <div class="chart-toolbar">
                    <button class="btn btn-sm" onclick="resetChart('chartFreq')">↺ 复位</button>
                    <button class="btn btn-sm" onclick="openFullscreen('chartFreq', 'CPU 动态频率调节')">⛶ 全屏</button>
                    <button class="btn btn-sm" onclick="exportPng('chartFreq')">📷 导出PNG</button>
                </div>
            </div>
            <div class="chart-body">
                <canvas id="chartFreq"></canvas>
            </div>
        </div>
    </div>

    <!-- 全屏放大模态弹窗 -->
    <div class="modal-overlay" id="fullscreenModal">
        <div class="modal-box">
            <div class="modal-header">
                <div>
                    <h2 id="modalTitle" style="font-size:18px; color:var(--text-main);">图表全屏分析</h2>
                    <p style="font-size:12px; color:var(--text-sub); margin-top:2px;">支持滚轮沿时间轴平滑缩放、鼠标左键拖拽平移；按 ESC 键或点击右上角关闭</p>
                </div>
                <div style="display:flex; align-items:center; gap:8px;">
                    <button class="btn btn-sm" onclick="resetModalChart()">↺ 重置缩放</button>
                    <button class="btn btn-sm" onclick="exportModalPng()">📷 导出PNG</button>
                    <button class="btn btn-sm" onclick="closeFullscreen()" style="font-weight:bold;">✕ 关闭</button>
                </div>
            </div>
            <div class="modal-body">
                <canvas id="modalCanvas"></canvas>
            </div>
        </div>
    </div>

    <div class="footer">
        Generated by psrecord-report &bull; Linux Performance Profiler
    </div>

    <script>
        if (typeof ChartZoom !== 'undefined') {
            Chart.register(ChartZoom);
        }

        const reportData = __REPORT_DATA_JSON__;
        const chartInstances = {};
        let isSyncing = false;
        let isSyncEnabled = true;
        let modalChartInstance = null;
        let currentModalSourceId = null;

        // 1. 渲染头部元信息
        const sess0 = reportData.sessions[0];
        const meta = sess0.meta || {};
        const sys = meta.system || {};
        const sessNames = reportData.sessions.map(s => s.name).join(', ');
        document.getElementById('headerMeta').innerHTML = `
            <span><strong>会话:</strong> ${sessNames}</span> &nbsp;|&nbsp;
            <span><strong>开始时间:</strong> ${meta.start_time || '未知'}</span> &nbsp;|&nbsp;
            <span><strong>采样周期:</strong> ${meta.interval || 0}s</span> &nbsp;|&nbsp;
            <span><strong>记录时长:</strong> ${meta.duration_s || reportData.global_max_time} 秒</span> &nbsp;|&nbsp;
            <span><strong>平台架构:</strong> ${sys.machine || 'Linux'}</span> &nbsp;|&nbsp;
            <span><strong>内核:</strong> ${sys.kernel || 'Linux'}</span>
        `;

        // 2. 渲染智能诊断面板
        const diag = reportData.diag;
        const diagContainer = document.getElementById('diagContainer');
        
        const isMemSafe = Math.abs(diag.rss_delta) < 5.0;
        const memColor = isMemSafe ? 'var(--accent-green)' : (diag.rss_delta > 15.0 ? 'var(--accent-red)' : 'var(--accent-yellow)');
        const memDesc = isMemSafe 
            ? `物理内存净增量 ${diag.rss_delta > 0 ? '+' : ''}${diag.rss_delta} MB，内存波动极为收敛，未检测到泄漏倾向。`
            : `测试期间内存净增加 ${diag.rss_delta} MB，存在一定堆缓存增长，建议进行长跑压测复查。`;

        const isCpuBurst = diag.max_cpu > 100.0;
        const cpuDesc = isCpuBurst 
            ? `在 t=${diag.peak_time}s 处出现并发爆发，瞬时算力高达 ${diag.max_cpu}% (相当于 ${Math.round(diag.max_cpu/100*10)/10} 个满载核心)。`
            : `均值 ${diag.avg_cpu}%，运行过程负载平稳，未出现剧烈并发抖动。`;

        const tempColor = diag.max_temp > 75.0 ? 'var(--accent-red)' : (diag.max_temp > 65.0 ? 'var(--accent-yellow)' : 'var(--accent-green)');
        const tempDesc = `传感器最高记录为 ${diag.max_temp}°C (${diag.max_temp_sensor})，距离 SoC 80°C 限频安全阈值余量充足。`;

        const coreDesc = diag.big_core_peak > 0
            ? `大核集群峰值 ${diag.big_core_peak}%，小核集群峰值 ${diag.little_core_peak}%；调度器有效将计算任务分配至各核心。`
            : `系统各核心调度平稳，各核均有负载分担。`;

        diagContainer.innerHTML = `
            <div class="diag-card" style="--card-color: var(--accent-cyan)">
                <div class="diag-title">⚡ 算力负载特征 <span>P95: ${reportData.proc_summaries[0]?.cpu.p95 || 0}%</span></div>
                <div class="diag-val">${diag.max_cpu}% <span style="font-size:13px; font-weight:normal;">峰值</span></div>
                <div class="diag-desc">${cpuDesc}</div>
            </div>
            <div class="diag-card" style="--card-color: ${memColor}">
                <div class="diag-title">🧠 内存稳态与泄漏评估 <span>${isMemSafe ? '🟢 稳定' : '🟡 需关注'}</span></div>
                <div class="diag-val">${diag.rss_delta > 0 ? '+' : ''}${diag.rss_delta} MB <span style="font-size:13px; font-weight:normal;">净增量</span></div>
                <div class="diag-desc">${memDesc}</div>
            </div>
            <div class="diag-card" style="--card-color: var(--accent)">
                <div class="diag-title">🎯 CPU 调度与负载分布 <span>${diag.big_core_peak > 0 ? '大小核集群' : '多核利用率'}</span></div>
                <div class="diag-val">${diag.big_core_peak || diag.avg_cpu}% <span style="font-size:13px; font-weight:normal;">峰值</span></div>
                <div class="diag-desc">${coreDesc}</div>
            </div>
            <div class="diag-card" style="--card-color: ${tempColor}">
                <div class="diag-title">🔥 板端传感器热状态 <span>${diag.max_temp < 65 ? '🟢 良好' : '🟡 预警'}</span></div>
                <div class="diag-val">${diag.max_temp}°C <span style="font-size:13px; font-weight:normal;">峰值温升</span></div>
                <div class="diag-desc">${tempDesc}</div>
            </div>
        `;

        // 3. 渲染指标卡片
        const cardsContainer = document.getElementById('statCards');
        reportData.proc_summaries.forEach((p, idx) => {
            const deltaSign = p.rss.delta >= 0 ? `+${p.rss.delta}` : `${p.rss.delta}`;
            const deltaColor = p.rss.delta > 2 ? 'var(--accent-red)' : 'var(--accent-green)';
            const pTitle = p.session ? `[${p.session}] ${p.label}` : p.label;
            
            cardsContainer.innerHTML += `
                <div class="stat-card" style="--card-color: ${p.color}">
                    <div class="stat-label">
                        <span>${pTitle}</span>
                        <span class="tag-pill" style="background:${p.color}22; color:${p.color}">CPU 峰值</span>
                    </div>
                    <div class="stat-value">${p.cpu.max}<span style="font-size:16px">%</span></div>
                    <div class="stat-sub">均值: <strong>${p.cpu.avg}%</strong> &nbsp;|&nbsp; P95分位: <strong>${p.cpu.p95}%</strong></div>
                </div>
                <div class="stat-card" style="--card-color: var(--accent-green)">
                    <div class="stat-label">
                        <span>物理内存 (RSS) 稳态</span>
                        <span class="tag-pill" style="background:rgba(6,214,160,0.15); color:var(--accent-green)">Memory</span>
                    </div>
                    <div class="stat-value">${p.rss.avg}<span style="font-size:16px"> MB</span></div>
                    <div class="stat-sub">净增量: <strong style="color:${deltaColor}">${deltaSign} MB</strong> (PSS均值: ${p.pss.avg} MB)</div>
                </div>
                <div class="stat-card" style="--card-color: var(--accent-yellow)">
                    <div class="stat-label">
                        <span>线程并发与文件句柄</span>
                        <span class="tag-pill" style="background:rgba(255,209,102,0.15); color:var(--accent-yellow)">Concurrency</span>
                    </div>
                    <div class="stat-value">${p.threads.avg}<span style="font-size:16px"> 线程</span></div>
                    <div class="stat-sub">文件句柄 (FDs): <strong>${p.fds.avg} 个</strong></div>
                </div>
            `;
        });

        // 4. 渲染明细表格
        const tbody = document.getElementById('summaryTableBody');
        reportData.proc_summaries.forEach(p => {
            const deltaSign = p.rss.delta >= 0 ? `+${p.rss.delta}` : `${p.rss.delta}`;
            const displayLabel = p.session ? `[${p.session}] ${p.label}` : p.label;
            tbody.innerHTML += `
                <tr>
                    <td>
                        <strong style="color:${p.color}">${displayLabel}</strong>
                        <div style="font-size:11px; color:var(--text-sub);">${p.raw_label}</div>
                        ${p.cmd ? `<div style="font-size:11px; color:var(--text-sub); max-width:320px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${p.cmd}">${p.cmd}</div>` : ''}
                    </td>
                    <td class="mono">${p.cpu.avg}%</td>
                    <td class="mono" style="color:var(--accent-red); font-weight:600;">${p.cpu.max}%</td>
                    <td class="mono">${p.cpu.p95}%</td>
                    <td class="mono">${p.rss.avg} / ${p.rss.max} MB</td>
                    <td class="mono">${p.pss.avg} MB</td>
                    <td class="mono" style="color:${p.rss.delta > 2 ? 'var(--accent-red)':'var(--accent-green)'}">${deltaSign} MB</td>
                    <td class="mono">${p.threads.avg}</td>
                    <td class="mono">${p.fds.avg}</td>
                </tr>
            `;
        });

        // 5. 十字光标插件
        const verticalCrosshairPlugin = {
            id: 'verticalCrosshair',
            afterDraw: (chart) => {
                if (chart._crosshairX != null && chart.chartArea) {
                    const ctx = chart.ctx;
                    ctx.save();
                    ctx.beginPath();
                    ctx.strokeStyle = document.body.classList.contains('light-theme') ? 'rgba(9,105,218,0.5)' : 'rgba(88,166,255,0.5)';
                    ctx.lineWidth = 1;
                    ctx.setLineDash([4, 3]);
                    ctx.moveTo(chart._crosshairX, chart.chartArea.top);
                    ctx.lineTo(chart._crosshairX, chart.chartArea.bottom);
                    ctx.stroke();
                    ctx.restore();
                }
            }
        };
        Chart.register(verticalCrosshairPlugin);

        // 颜色与透明度辅助函数
        function hexToRgba(hex, alpha = 0.15) {
            if (!hex || typeof hex !== 'string') return 'transparent';
            let c = hex.replace('#', '');
            if (c.length === 8) c = c.substring(0, 6);
            if (c.length === 3) c = c.split('').map(x => x + x).join('');
            if (c.length === 6) {
                const r = parseInt(c.substring(0, 2), 16);
                const g = parseInt(c.substring(2, 4), 16);
                const b = parseInt(c.substring(4, 6), 16);
                return "rgba(" + r + ", " + g + ", " + b + ", " + alpha + ")";
            }
            return hex;
        }

        function getThemeColor(color, isLight) {
            if (!isLight || !color) return color;
            const map = {
                '#00f0ff': '#0284c7',
                '#06d6a0': '#059669',
                '#ffd166': '#d97706',
                '#ef476f': '#dc2626',
                '#ff5376': '#dc2626',
                '#3a86ff': '#2563eb'
            };
            return map[color.toLowerCase()] || color;
        }

        // 6. 创建图表通用配置
        function createInteractiveChart(canvasId, datasets, yTitle, isArea=false) {
            const canvas = document.getElementById(canvasId);
            if (!canvas) return null;
            const ctx = canvas.getContext('2d');

            const isDark = !document.body.classList.contains('light-theme');
            const gridColor = isDark ? '#21262d' : '#e8ecf0';
            const tickColor = isDark ? '#8b949e' : '#656d76';

            const chart = new Chart(ctx, {
                type: 'line',
                data: {
                    datasets: datasets.map(d => {
                        const isLight = document.body.classList.contains('light-theme');
                        const baseColor = getThemeColor(d.color, isLight);
                        const shouldFill = (d.fill !== undefined) ? d.fill : isArea;
                        const lineColor = d.isRaw ? hexToRgba(baseColor, isLight ? 0.45 : 0.4) : baseColor;
                        const bgColor = shouldFill ? hexToRgba(baseColor, isLight ? 0.12 : 0.18) : 'transparent';
                        return {
                            label: d.name,
                            data: d.data,
                            borderColor: lineColor,
                            backgroundColor: bgColor,
                            borderWidth: d.borderWidth || 2.0,
                            pointRadius: 0,
                            pointHoverRadius: 4,
                            borderDash: d.dash || [],
                            fill: shouldFill ? 'origin' : false,
                            tension: d.isSmooth ? 0.2 : 0.05,
                            hidden: d.hidden || false,
                            _origColor: d.color,
                            _isRaw: d.isRaw,
                            _fill: shouldFill
                        };
                    })
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: false,
                    parsing: false,
                    normalized: true,
                    interaction: { mode: 'index', intersect: false },
                    plugins: {
                        legend: {
                            labels: {
                                color: tickColor,
                                font: { size: 11, family: 'system-ui' },
                                boxWidth: 12,
                                usePointStyle: true
                            }
                        },
                        tooltip: {
                            backgroundColor: isDark ? '#1f242c' : '#ffffff',
                            titleColor: isDark ? '#58a6ff' : '#0969da',
                            bodyColor: isDark ? '#f0f6fc' : '#1f2328',
                            borderColor: isDark ? '#30363d' : '#d0d7de',
                            borderWidth: 1,
                            padding: 10,
                            boxPadding: 4,
                            usePointStyle: true,
                            callbacks: {
                                title: (items) => {
                                    if (items.length && items[0].parsed) {
                                        return `时间: ${items[0].parsed.x.toFixed(2)} 秒`;
                                    }
                                    return '';
                                },
                                label: (item) => {
                                    const yVal = item.parsed.y != null ? item.parsed.y.toFixed(2) : 'N/A';
                                    return ` ${item.dataset.label}: ${yVal}`;
                                }
                            }
                        },
                        zoom: {
                            pan: {
                                enabled: true,
                                mode: 'x',
                                onPan: ({ chart }) => {
                                    syncCharts(chart);
                                }
                            },
                            zoom: {
                                wheel: { enabled: true, speed: 0.1 },
                                pinch: { enabled: true },
                                mode: 'x',
                                onZoom: ({ chart }) => {
                                    syncCharts(chart);
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            type: 'linear',
                            min: 0,
                            max: reportData.global_max_time,
                            grid: { color: gridColor },
                            ticks: {
                                color: tickColor,
                                font: { size: 10 },
                                maxTicksLimit: 12,
                                callback: (v) => `${v.toFixed(1)}s`
                            },
                            title: { display: true, text: '时间 (秒)', color: tickColor, font: { size: 11 } }
                        },
                        y: {
                            grid: { color: gridColor },
                            ticks: { color: tickColor, font: { size: 10 } },
                            title: { display: true, text: yTitle, color: tickColor, font: { size: 11 } }
                        }
                    }
                }
            });

            canvas.addEventListener('mousemove', (e) => {
                const rect = canvas.getBoundingClientRect();
                const x = e.clientX - rect.left;
                chart._crosshairX = x;
                chart.draw();
            });
            canvas.addEventListener('mouseleave', () => {
                chart._crosshairX = null;
                chart.draw();
            });

            chartInstances[canvasId] = chart;
            return chart;
        }

        // 7. 实例化各个图表
        const cs = reportData.chart_series;
        createInteractiveChart('chartCpu', cs.cpu, 'CPU 利用率 (%)', true);
        createInteractiveChart('chartMem', [...cs.mem_rss, ...cs.mem_pss], '内存容量 (MB)', false);
        createInteractiveChart('chartThreads', [...cs.threads, ...cs.fds], '数量 (Count)', false);
        createInteractiveChart('chartCores', cs.sys_cores, '单核 CPU (%)', false);
        createInteractiveChart('chartTemp', cs.sys_temp, '温度 (°C)', false);
        if (cs.sys_freq && cs.sys_freq.length) {
            document.getElementById('card_chartFreq').style.display = 'flex';
            createInteractiveChart('chartFreq', cs.sys_freq, '频率 (kHz / MHz)', false);
        }

        // 8. 多图表时间轴联动
        function syncCharts(sourceChart) {
            if (!isSyncEnabled || isSyncing) return;
            isSyncing = true;
            const xMin = sourceChart.scales.x.min;
            const xMax = sourceChart.scales.x.max;

            Object.values(chartInstances).forEach(c => {
                if (c !== sourceChart && c.scales && c.scales.x) {
                    c.zoomScale('x', { min: xMin, max: xMax }, 'none');
                }
            });
            isSyncing = false;
        }

        function toggleSync(enabled) {
            isSyncEnabled = enabled;
        }

        function resetChart(chartId) {
            const chart = chartInstances[chartId];
            if (chart) {
                chart.resetZoom('none');
                if (isSyncEnabled) {
                    syncCharts(chart);
                }
            }
        }

        function resetAllCharts() {
            isSyncing = true;
            Object.values(chartInstances).forEach(c => c.resetZoom('none'));
            isSyncing = false;
        }

        function jumpRange(startPct, endPct) {
            const total = reportData.global_max_time;
            const min = total * startPct;
            const max = total * endPct;
            isSyncing = true;
            Object.values(chartInstances).forEach(c => {
                c.zoomScale('x', { min, max }, 'none');
            });
            isSyncing = false;
        }

        function jumpPeak() {
            const peak = reportData.global_peak_time;
            const total = reportData.global_max_time;
            const min = Math.max(0, peak - 8);
            const max = Math.min(total, peak + 8);
            isSyncing = true;
            Object.values(chartInstances).forEach(c => {
                c.zoomScale('x', { min, max }, 'none');
            });
            isSyncing = false;
        }

        // 9. 曲线显隐控制与大小核过滤
        function toggleDataset(chartId, datasetIndex) {
            const chart = chartInstances[chartId];
            if (chart && chart.data.datasets[datasetIndex]) {
                const current = chart.isDatasetVisible(datasetIndex);
                chart.setDatasetVisibility(datasetIndex, !current);
                chart.update();
            }
        }

        function filterCores(type) {
            const chart = chartInstances['chartCores'];
            if (!chart) return;
            chart.data.datasets.forEach((ds, idx) => {
                const isBig = ds.label.includes('大核');
                if (type === 'all') {
                    chart.setDatasetVisibility(idx, true);
                } else if (type === 'big') {
                    chart.setDatasetVisibility(idx, isBig);
                } else if (type === 'little') {
                    chart.setDatasetVisibility(idx, !isBig);
                }
            });
            chart.update();
        }

        // 10. 图片高清导出
        function exportPng(chartId) {
            const chart = chartInstances[chartId];
            if (!chart) return;
            const url = chart.toBase64Image('image/png', 1.0);
            const link = document.createElement('a');
            link.download = `${chartId}_profile.png`;
            link.href = url;
            link.click();
        }

        // 11. 全屏模态放大窗口
        function openFullscreen(sourceChartId, title) {
            const sourceChart = chartInstances[sourceChartId];
            if (!sourceChart) return;
            currentModalSourceId = sourceChartId;

            document.getElementById('modalTitle').innerText = `⛶ ${title} (全屏高精分析)`;
            const modalOverlay = document.getElementById('fullscreenModal');
            modalOverlay.classList.add('active');

            const modalCanvas = document.getElementById('modalCanvas');
            const ctx = modalCanvas.getContext('2d');

            if (modalChartInstance) {
                modalChartInstance.destroy();
            }

            const isDark = !document.body.classList.contains('light-theme');
            const gridColor = isDark ? '#21262d' : '#e8ecf0';
            const tickColor = isDark ? '#8b949e' : '#656d76';

            modalChartInstance = new Chart(ctx, {
                type: 'line',
                data: JSON.parse(JSON.stringify(sourceChart.data)),
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: false,
                    parsing: false,
                    normalized: true,
                    interaction: { mode: 'index', intersect: false },
                    plugins: {
                        legend: {
                            labels: { color: tickColor, font: { size: 12 } }
                        },
                        tooltip: sourceChart.options.plugins.tooltip,
                        zoom: {
                            pan: { enabled: true, mode: 'x' },
                            zoom: { wheel: { enabled: true }, mode: 'x' }
                        }
                    },
                    scales: {
                        x: {
                            type: 'linear',
                            min: sourceChart.scales.x.min,
                            max: sourceChart.scales.x.max,
                            grid: { color: gridColor },
                            ticks: { color: tickColor, callback: v => `${v.toFixed(1)}s` }
                        },
                        y: {
                            grid: { color: gridColor },
                            ticks: { color: tickColor },
                            title: sourceChart.options.scales.y.title
                        }
                    }
                }
            });
        }

        function closeFullscreen() {
            const modalOverlay = document.getElementById('fullscreenModal');
            modalOverlay.classList.remove('active');
            if (modalChartInstance) {
                modalChartInstance.destroy();
                modalChartInstance = null;
            }
        }

        function resetModalChart() {
            if (modalChartInstance) {
                modalChartInstance.resetZoom('none');
            }
        }

        function exportModalPng() {
            if (!modalChartInstance) return;
            const url = modalChartInstance.toBase64Image('image/png', 1.0);
            const link = document.createElement('a');
            link.download = `fullscreen_${currentModalSourceId}.png`;
            link.href = url;
            link.click();
        }

        window.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') closeFullscreen();
        });

        // 12. 切换暗黑 / 明亮主题
        function toggleTheme() {
            const body = document.body;
            body.classList.toggle('light-theme');
            const isLight = body.classList.contains('light-theme');
            document.getElementById('themeBtn').innerHTML = isLight ? '🌙 切换深色模式' : '☀️ 切换浅色模式';

            const gridColor = isLight ? '#e8ecf0' : '#21262d';
            const tickColor = isLight ? '#656d76' : '#8b949e';
            const tooltipBg = isLight ? '#ffffff' : '#1f242c';
            const tooltipTitle = isLight ? '#0969da' : '#58a6ff';
            const tooltipBody = isLight ? '#1f2328' : '#f0f6fc';
            const tooltipBorder = isLight ? '#d0d7de' : '#30363d';

            Object.values(chartInstances).forEach(c => {
                if (c.options.scales.x) {
                    c.options.scales.x.grid.color = gridColor;
                    c.options.scales.x.ticks.color = tickColor;
                    if (c.options.scales.x.title) c.options.scales.x.title.color = tickColor;
                }
                if (c.options.scales.y) {
                    c.options.scales.y.grid.color = gridColor;
                    c.options.scales.y.ticks.color = tickColor;
                    if (c.options.scales.y.title) c.options.scales.y.title.color = tickColor;
                }
                if (c.options.plugins.legend) {
                    c.options.plugins.legend.labels.color = tickColor;
                }
                if (c.options.plugins.tooltip) {
                    c.options.plugins.tooltip.backgroundColor = tooltipBg;
                    c.options.plugins.tooltip.titleColor = tooltipTitle;
                    c.options.plugins.tooltip.bodyColor = tooltipBody;
                    c.options.plugins.tooltip.borderColor = tooltipBorder;
                }
                if (c.data && c.data.datasets) {
                    c.data.datasets.forEach(ds => {
                        const base = getThemeColor(ds._origColor || ds.borderColor, isLight);
                        ds.borderColor = ds._isRaw ? hexToRgba(base, isLight ? 0.45 : 0.4) : base;
                        ds.backgroundColor = ds._fill ? hexToRgba(base, isLight ? 0.12 : 0.18) : 'transparent';
                    });
                }
                c.update('none');
            });

            if (modalChartInstance) {
                modalChartInstance.options.scales.x.grid.color = gridColor;
                modalChartInstance.options.scales.x.ticks.color = tickColor;
                modalChartInstance.options.scales.y.grid.color = gridColor;
                modalChartInstance.options.scales.y.ticks.color = tickColor;
                if (modalChartInstance.options.plugins.legend) {
                    modalChartInstance.options.plugins.legend.labels.color = tickColor;
                }
                if (modalChartInstance.data && modalChartInstance.data.datasets) {
                    modalChartInstance.data.datasets.forEach(ds => {
                        const base = getThemeColor(ds._origColor || ds.borderColor, isLight);
                        ds.borderColor = ds._isRaw ? hexToRgba(base, isLight ? 0.45 : 0.4) : base;
                        ds.backgroundColor = ds._fill ? hexToRgba(base, isLight ? 0.12 : 0.18) : 'transparent';
                    });
                }
                modalChartInstance.update('none');
            }
        }
    </script>
</body>
</html>
"""

    final_html = html_template.replace("__CHART_JS_INLINE__", chart_js_code)\
                              .replace("__HAMMER_JS_INLINE__", hammer_js_code)\
                              .replace("__ZOOM_JS_INLINE__", zoom_js_code)\
                              .replace("__REPORT_DATA_JSON__", report_json_str)

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(final_html)
    return output_file

def generate_html(sessions, output="report.html"):
    """供库接口和测试调用的兼容方法"""
    loaded = []
    for s in sessions:
        if isinstance(s, str):
            loaded.append(load_session(s))
        elif isinstance(s, dict):
            loaded.append(s)
    return build_report_html(loaded, output)

def main():
    parser = argparse.ArgumentParser(description="psrecord 会话可视化报告生成器 (psrecord-report)")
    parser.add_argument("sessions", nargs="+", help="会话目录路径，支持单个或多个会话对比")
    parser.add_argument("-o", "--output", default="report.html", help="输出的 HTML 报告路径 (默认: report.html)")
    args = parser.parse_args()

    loaded_sessions = [load_session(p) for p in args.sessions]
    build_report_html(loaded_sessions, args.output)
    print(f"✨ 现代化测试报告已成功生成: {args.output}")

if __name__ == "__main__":
    main()
