import os
import json
import csv
import math
from typing import Dict, Any, List

def calculate_stats(values: List[float]) -> Dict[str, float]:
    if not values:
        return {"avg": 0.0, "max": 0.0, "min": 0.0, "p95": 0.0}
    clean_vals = sorted(values)
    avg_v = sum(clean_vals) / len(clean_vals)
    max_v = clean_vals[-1]
    min_v = clean_vals[0]
    idx_p95 = int(math.ceil(len(clean_vals) * 0.95)) - 1
    p95_v = clean_vals[max(0, min(idx_p95, len(clean_vals) - 1))]
    return {
        "avg": round(avg_v, 2),
        "max": round(max_v, 2),
        "min": round(min_v, 2),
        "p95": round(p95_v, 2),
    }

class SessionData:
    def __init__(self, session_dir: str):
        self.session_dir = os.path.abspath(session_dir)
        self.meta: Dict[str, Any] = {}
        self.series: Dict[str, List[Dict[str, Any]]] = {}
        self.load()

    def load(self):
        meta_path = os.path.join(self.session_dir, "meta.json")
        if os.path.exists(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                self.meta = json.load(f)

        for filename in os.listdir(self.session_dir):
            if filename.endswith(".csv"):
                stream_name = filename[:-4]
                filepath = os.path.join(self.session_dir, filename)
                rows = []
                with open(filepath, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for r in reader:
                        # 转换数值类型
                        converted = {}
                        for k, v in r.items():
                            try:
                                if "." in v:
                                    converted[k] = float(v)
                                else:
                                    converted[k] = int(v)
                            except ValueError:
                                converted[k] = v
                        rows.append(converted)
                self.series[stream_name] = rows

    def get_summary_stats(self) -> Dict[str, Any]:
        stats = {}
        for stream, rows in self.series.items():
            if not rows:
                continue
            stream_stats = {}
            # 自动提取所有数值列
            sample_keys = [k for k, v in rows[0].items() if isinstance(v, (int, float)) and k not in ("timestamp", "elapsed_s", "pid")]
            for k in sample_keys:
                vals = [r[k] for r in rows if k in r and isinstance(r[k], (int, float))]
                stream_stats[k] = calculate_stats(vals)
            stats[stream] = stream_stats
        return stats
