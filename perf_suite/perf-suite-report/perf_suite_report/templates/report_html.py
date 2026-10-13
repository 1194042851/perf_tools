from typing import Dict, Any, List
import json

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>perf_suite 性能测试报告</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background-color: #f8fafc;
            color: #1e293b;
            margin: 0;
            padding: 24px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        .header {
            background: #ffffff;
            padding: 24px;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            margin-bottom: 24px;
        }
        .header h1 {
            margin: 0 0 12px 0;
            font-size: 24px;
            color: #0f172a;
        }
        .meta-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 12px;
            font-size: 14px;
            color: #475569;
        }
        .card {
            background: #ffffff;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 24px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        .card h2 {
            margin-top: 0;
            font-size: 18px;
            border-bottom: 1px solid #e2e8f0;
            padding-bottom: 12px;
            color: #334155;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
            margin-top: 12px;
        }
        th, td {
            text-align: left;
            padding: 10px 12px;
            border-bottom: 1px solid #e2e8f0;
        }
        th {
            background-color: #f1f5f9;
            color: #475569;
            font-weight: 600;
        }
        tr:hover {
            background-color: #f8fafc;
        }
        .chart-box {
            width: 100%;
            min-height: 420px;
            margin-bottom: 16px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 perf_suite 性能测试报告</h1>
            <div class="meta-grid">
                <div><strong>测试时长:</strong> {{ duration_s }} 秒</div>
                <div><strong>记录开始时间:</strong> {{ created_at }}</div>
                <div><strong>主机平台:</strong> {{ platform_node }} ({{ platform_machine }})</div>
                <div><strong>内核版本:</strong> {{ platform_release }}</div>
            </div>
        </div>

        <div class="card">
            <h2>📊 指标汇总统计 (均值 / P95 / 峰值)</h2>
            <table>
                <thead>
                    <tr>
                        <th>流标识 / 进程</th>
                        <th>统计指标</th>
                        <th>平均值 (Avg)</th>
                        <th>95分位数 (P95)</th>
                        <th>峰值 (Max)</th>
                        <th>最小值 (Min)</th>
                    </tr>
                </thead>
                <tbody>
                    {{ table_rows }}
                </tbody>
            </table>
        </div>

        <div class="card">
            <h2>📈 详细时序图表</h2>
            {{ chart_divs }}
        </div>
    </div>

    <script>
        {{ chart_scripts }}
    </script>
</body>
</html>
"""

def render_html_report(meta: Dict[str, Any], stats: Dict[str, Any], figures: List[Dict[str, Any]]) -> str:
    # 构造表格行
    table_rows = []
    for stream, metrics in stats.items():
        for m_name, s_val in metrics.items():
            table_rows.append(f"""
            <tr>
                <td><strong>{stream}</strong></td>
                <td>{m_name}</td>
                <td>{s_val.get('avg', '-')}</td>
                <td><span style="color:#2563EB;font-weight:bold;">{s_val.get('p95', '-')}</span></td>
                <td><span style="color:#DC2626;font-weight:bold;">{s_val.get('max', '-')}</span></td>
                <td>{s_val.get('min', '-')}</td>
            </tr>
            """)

    chart_divs = []
    chart_scripts = []

    for f_info in figures:
        cid = f_info["id"]
        fig = f_info["fig"]
        chart_divs.append(f'<div id="{cid}" class="chart-box"></div>')
        json_spec = fig.to_json()
        chart_scripts.append(f"""
        (function() {{
            var spec = {json_spec};
            Plotly.newPlot('{cid}', spec.data, spec.layout, {{responsive: true}});
        }})();
        """)

    plat = meta.get("platform", {})
    html = HTML_TEMPLATE
    html = html.replace("{{ duration_s }}", str(meta.get("duration_s", "-")))
    html = html.replace("{{ created_at }}", str(meta.get("created_at", "-")))
    html = html.replace("{{ platform_node }}", str(plat.get("node", "-")))
    html = html.replace("{{ platform_machine }}", str(plat.get("machine", "-")))
    html = html.replace("{{ platform_release }}", str(plat.get("release", "-")))
    html = html.replace("{{ table_rows }}", "".join(table_rows))
    html = html.replace("{{ chart_divs }}", "\n".join(chart_divs))
    html = html.replace("{{ chart_scripts }}", "\n".join(chart_scripts))
    return html
