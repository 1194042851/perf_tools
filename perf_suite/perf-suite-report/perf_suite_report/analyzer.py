#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
perf-suite-report 数据解析与统计引擎
负责解析 Session 目录（meta.json 与多流 CSV），执行高精度聚合、降采样以及生成智能诊断指标。
"""

import os
import json
import csv
import math
from typing import Dict, Any, List, Optional


def calculate_stats(values: List[float]) -> Dict[str, float]:
    clean_vals = [v for v in values if v is not None and not math.isnan(v)]
    if not clean_vals:
        return {"avg": 0.0, "max": 0.0, "min": 0.0, "p95": 0.0, "delta": 0.0}
    clean_sorted = sorted(clean_vals)
    avg_v = sum(clean_sorted) / len(clean_sorted)
    max_v = clean_sorted[-1]
    min_v = clean_sorted[0]
    idx_p95 = int(math.ceil(len(clean_sorted) * 0.95)) - 1
    p95_v = clean_sorted[max(0, min(idx_p95, len(clean_sorted) - 1))]
    delta_v = clean_vals[-1] - clean_vals[0] if len(clean_vals) > 1 else 0.0
    return {
        "avg": round(avg_v, 2),
        "max": round(max_v, 2),
        "min": round(min_v, 2),
        "p95": round(p95_v, 2),
        "delta": round(delta_v, 2),
    }


def downsample_points(times: List[float], values: List[float], max_points: int = 1500) -> List[Dict[str, float]]:
    n = len(times)
    if n == 0:
        return []
    if n <= max_points:
        return [{"x": round(times[i], 2), "y": round(values[i], 2) if values[i] is not None else 0.0} for i in range(n)]

    step = n / max_points
    sampled = []
    sampled.append({"x": round(times[0], 2), "y": round(values[0], 2) if values[0] is not None else 0.0})

    for i in range(1, max_points - 1):
        idx = int(i * step)
        if idx >= n:
            break
        v = values[idx]
        sampled.append({"x": round(times[idx], 2), "y": round(v, 2) if v is not None else 0.0})

    sampled.append({"x": round(times[-1], 2), "y": round(values[-1], 2) if values[-1] is not None else 0.0})
    return sampled


class SessionData:
    def __init__(self, session_dir: str):
        self.session_dir = os.path.abspath(session_dir)
        self.name = os.path.basename(self.session_dir)
        self.meta: Dict[str, Any] = {}
        self.series: Dict[str, List[Dict[str, Any]]] = {}
        self.load()

    def load(self):
        meta_path = os.path.join(self.session_dir, "meta.json")
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    self.meta = json.load(f)
            except Exception:
                pass

        if not os.path.isdir(self.session_dir):
            return

        for filename in sorted(os.listdir(self.session_dir)):
            if filename.endswith(".csv"):
                stream_name = filename[:-4]
                filepath = os.path.join(self.session_dir, filename)
                rows = []
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        reader = csv.DictReader(f)
                        for r in reader:
                            converted = {}
                            for k, v in r.items():
                                if v is None or v == "":
                                    converted[k] = None
                                    continue
                                try:
                                    if "." in v:
                                        converted[k] = float(v)
                                    else:
                                        converted[k] = int(v)
                                except ValueError:
                                    converted[k] = v
                            rows.append(converted)
                except Exception:
                    pass
                self.series[stream_name] = rows

    def get_summary_stats(self) -> Dict[str, Any]:
        stats = {}
        for stream, rows in self.series.items():
            if not rows:
                continue
            stream_stats = {}
            sample_keys = [k for k, v in rows[0].items() if isinstance(v, (int, float)) and k not in ("timestamp", "elapsed_s", "pid")]
            for k in sample_keys:
                vals = [r[k] for r in rows if k in r and isinstance(r[k], (int, float))]
                stream_stats[k] = calculate_stats(vals)
            stats[stream] = stream_stats
        return stats
