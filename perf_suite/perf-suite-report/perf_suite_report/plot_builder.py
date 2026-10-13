import plotly.graph_objects as go
from plotly.subplots import make_subplots
from typing import Dict, Any, List
from .analyzer import SessionData

COLOR_PALETTE = [
    "#2563EB", "#DC2626", "#059669", "#D97706", 
    "#7C3AED", "#DB2777", "#4B5563", "#0891B2"
]

def build_process_figures(session: SessionData) -> List[Dict[str, Any]]:
    figures = []
    proc_streams = [s for s in session.series.keys() if s.startswith("proc_")]
    if not proc_streams:
        return figures

    # 1. CPU 对比图
    fig_cpu = go.Figure()
    for idx, s in enumerate(proc_streams):
        rows = session.series[s]
        if not rows:
            continue
        name = rows[0].get("name", s)
        color = COLOR_PALETTE[idx % len(COLOR_PALETTE)]
        times = [r["elapsed_s"] for r in rows]
        cpus = [r["cpu_percent"] for r in rows]
        # 主曲线
        fig_cpu.add_trace(go.Scatter(
            x=times, y=cpus, mode="lines", name=f"{name} ({s})",
            line=dict(color=color, width=2)
        ))
    fig_cpu.update_layout(
        title="进程 CPU 使用率对比 (%)",
        xaxis_title="测试耗时 (秒)",
        yaxis_title="CPU (%)",
        template="plotly_white",
        hovermode="x unified"
    )
    figures.append({"id": "chart_proc_cpu", "title": "多进程 CPU 对比", "fig": fig_cpu})

    # 2. 内存 (RSS) 对比图
    fig_mem = go.Figure()
    for idx, s in enumerate(proc_streams):
        rows = session.series[s]
        if not rows:
            continue
        name = rows[0].get("name", s)
        color = COLOR_PALETTE[idx % len(COLOR_PALETTE)]
        times = [r["elapsed_s"] for r in rows]
        rss = [r["rss_mb"] for r in rows]
        fig_mem.add_trace(go.Scatter(
            x=times, y=rss, mode="lines", name=f"{name} RSS",
            line=dict(color=color, width=2)
        ))
    fig_mem.update_layout(
        title="进程物理内存对比 (RSS MB)",
        xaxis_title="测试耗时 (秒)",
        yaxis_title="内存 (MB)",
        template="plotly_white",
        hovermode="x unified"
    )
    figures.append({"id": "chart_proc_mem", "title": "多进程物理内存对比", "fig": fig_mem})

    # 3. 线程数对比图
    fig_thr = go.Figure()
    for idx, s in enumerate(proc_streams):
        rows = session.series[s]
        if not rows:
            continue
        name = rows[0].get("name", s)
        color = COLOR_PALETTE[idx % len(COLOR_PALETTE)]
        times = [r["elapsed_s"] for r in rows]
        thrs = [r.get("threads", 1) for r in rows]
        fig_thr.add_trace(go.Scatter(
            x=times, y=thrs, mode="lines", name=f"{name} 线程数",
            line=dict(color=color, width=2)
        ))
    fig_thr.update_layout(
        title="进程活跃线程数变化",
        xaxis_title="测试耗时 (秒)",
        yaxis_title="线程数",
        template="plotly_white",
        hovermode="x unified"
    )
    figures.append({"id": "chart_proc_threads", "title": "线程数变化", "fig": fig_thr})

    return figures

def build_network_figures(session: SessionData) -> List[Dict[str, Any]]:
    figures = []
    net_streams = [s for s in session.series.keys() if s.startswith("net_")]
    if not net_streams:
        return figures

    # 1. 网络带宽吞吐 (Mbps) 对比图
    fig_bw = go.Figure()
    for idx, s in enumerate(net_streams):
        rows = session.series[s]
        if not rows:
            continue
        iface = rows[0].get("iface", s)
        color_rx = COLOR_PALETTE[(idx * 2) % len(COLOR_PALETTE)]
        color_tx = COLOR_PALETTE[(idx * 2 + 1) % len(COLOR_PALETTE)]
        times = [r["elapsed_s"] for r in rows]
        rx_mbps = [r.get("rx_mbps", 0.0) for r in rows]
        tx_mbps = [r.get("tx_mbps", 0.0) for r in rows]

        fig_bw.add_trace(go.Scatter(
            x=times, y=rx_mbps, mode="lines", name=f"{iface} RX (流入 Mbps)",
            line=dict(color=color_rx, width=2)
        ))
        fig_bw.add_trace(go.Scatter(
            x=times, y=tx_mbps, mode="lines", name=f"{iface} TX (流出 Mbps)",
            line=dict(color=color_tx, width=2, dash="dash")
        ))
    fig_bw.update_layout(
        title="网卡实时带宽吞吐率 (Mbps)",
        xaxis_title="测试耗时 (秒)",
        yaxis_title="带宽 (Mbps)",
        template="plotly_white",
        hovermode="x unified"
    )
    figures.append({"id": "chart_net_bandwidth", "title": "网卡带宽吞吐率", "fig": fig_bw})

    # 2. PPS 对比图
    fig_pps = go.Figure()
    for idx, s in enumerate(net_streams):
        rows = session.series[s]
        if not rows:
            continue
        iface = rows[0].get("iface", s)
        times = [r["elapsed_s"] for r in rows]
        rx_pps = [r.get("rx_pps", 0.0) for r in rows]
        tx_pps = [r.get("tx_pps", 0.0) for r in rows]
        fig_pps.add_trace(go.Scatter(
            x=times, y=rx_pps, mode="lines", name=f"{iface} RX 包率 (PPS)"
        ))
        fig_pps.add_trace(go.Scatter(
            x=times, y=tx_pps, mode="lines", name=f"{iface} TX 包率 (PPS)",
            line=dict(dash="dot")
        ))
    fig_pps.update_layout(
        title="网卡包吞吐率 (Packets Per Second)",
        xaxis_title="测试耗时 (秒)",
        yaxis_title="PPS",
        template="plotly_white",
        hovermode="x unified"
    )
    figures.append({"id": "chart_net_pps", "title": "网卡包吞吐率 (PPS)", "fig": fig_pps})

    return figures

def build_system_figures(session: SessionData) -> List[Dict[str, Any]]:
    figures = []
    if "system" not in session.series or not session.series["system"]:
        return figures

    rows = session.series["system"]
    times = [r["elapsed_s"] for r in rows]

    # 系统 CPU & 内存占用
    fig_sys = go.Figure()
    fig_sys.add_trace(go.Scatter(
        x=times, y=[r.get("sys_cpu_percent", 0.0) for r in rows],
        mode="lines", name="整机 CPU (%)", line=dict(color="#DC2626", width=2)
    ))
    fig_sys.add_trace(go.Scatter(
        x=times, y=[r.get("sys_mem_percent", 0.0) for r in rows],
        mode="lines", name="整机内存使用率 (%)", line=dict(color="#2563EB", width=2)
    ))
    fig_sys.update_layout(
        title="整机背景开销 (CPU / 内存 %)",
        xaxis_title="测试耗时 (秒)",
        yaxis_title="占用率 (%)",
        template="plotly_white",
        hovermode="x unified"
    )
    figures.append({"id": "chart_sys_overview", "title": "整机背景开销", "fig": fig_sys})

    # RK3588 频率与温度
    freq_keys = [k for k in rows[0].keys() if k.startswith("freq_")]
    temp_keys = [k for k in rows[0].keys() if k.startswith("temp_")]

    if freq_keys or temp_keys:
        fig_hw = make_subplots(specs=[[{"secondary_y": True}]])
        for fk in freq_keys:
            fig_hw.add_trace(go.Scatter(
                x=times, y=[r.get(fk, 0.0) for r in rows],
                mode="lines", name=f"频率: {fk.replace('freq_', '').replace('_mhz', '')} (MHz)"
            ), secondary_y=False)
        for tk in temp_keys:
            fig_hw.add_trace(go.Scatter(
                x=times, y=[r.get(tk, 0.0) for r in rows],
                mode="lines", name=f"温度: {tk.replace('temp_', '')} (℃)",
                line=dict(dash="dot")
            ), secondary_y=True)

        fig_hw.update_layout(
            title="系统硬件状态 (CPU 频率 & 传感器温度)",
            xaxis_title="测试耗时 (秒)",
            template="plotly_white",
            hovermode="x unified"
        )
        fig_hw.update_yaxes(title_text="CPU 频率 (MHz)", secondary_y=False)
        fig_hw.update_yaxes(title_text="温度 (℃)", secondary_y=True)
        figures.append({"id": "chart_sys_hw", "title": "硬件频率与温度", "fig": fig_hw})

    return figures
