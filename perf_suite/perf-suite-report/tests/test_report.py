#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import unittest
import os
import shutil
import tempfile
import json
import csv
from perf_suite_report.analyzer import calculate_stats, SessionData
from perf_suite_report.templates.report_html import render_html_report
from perf_suite_report.comparator import build_comparison_report


class TestReportUnit(unittest.TestCase):
    def test_calculate_stats(self):
        vals = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
        stats = calculate_stats(vals)
        self.assertEqual(stats["min"], 10.0)
        self.assertEqual(stats["max"], 100.0)
        self.assertEqual(stats["avg"], 55.0)
        self.assertGreaterEqual(stats["p95"], 90.0)

    def _create_mock_session(self, root_dir, name="session_test"):
        s_dir = os.path.join(root_dir, name)
        os.makedirs(s_dir, exist_ok=True)
        meta = {
            "version": "0.1.0",
            "created_at": "2026-10-13 12:00:00",
            "platform": {"system": "Linux", "node": "host", "release": "5.10", "machine": "aarch64"},
            "duration_s": 5.0
        }
        with open(os.path.join(s_dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f)

        # 进程 CSV
        with open(os.path.join(s_dir, "proc_100.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["timestamp", "elapsed_s", "pid", "name", "cpu_percent", "rss_mb", "threads"])
            w.writerow([10.0, 0.0, 100, "test_app", 15.0, 50.0, 4])
            w.writerow([11.0, 1.0, 100, "test_app", 25.0, 52.0, 4])

        # 网卡 CSV
        with open(os.path.join(s_dir, "net_eth0.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["timestamp", "elapsed_s", "iface", "rx_mbps", "tx_mbps", "rx_pps", "tx_pps"])
            w.writerow([10.0, 0.0, "eth0", 12.5, 5.0, 100.0, 50.0])
            w.writerow([11.0, 1.0, "eth0", 18.0, 7.5, 150.0, 70.0])

        return s_dir

    def test_single_session_report(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            s_dir = self._create_mock_session(tmp_dir)
            data = SessionData(s_dir)
            out_html = os.path.join(tmp_dir, "report.html")
            render_html_report(data, out_html)
            self.assertTrue(os.path.exists(out_html))
            with open(out_html, "r", encoding="utf-8") as f:
                html = f.read()
            self.assertIn("perf_suite 性能全景分析报告", html)
            self.assertIn("test_app", html)
            self.assertIn("ChartZoom", html)
            self.assertIn("data-theme", html)
            self.assertIn('"pointRadius": 0', html)
            self.assertIn('"pointHoverRadius": 6', html)
            # 确认自定义数据集不含虚线配置 (Chart.js 内部代码除外)
            data_payload = html.split("const reportData = ")[1].split(";\n        const chartInstances")[0]
            self.assertNotIn("borderDash", data_payload)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_comparison_report(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            s1 = self._create_mock_session(tmp_dir, "session_v1")
            s2 = self._create_mock_session(tmp_dir, "session_v2")
            out_html = os.path.join(tmp_dir, "cmp.html")
            build_comparison_report([s1, s2], out_html)
            self.assertTrue(os.path.exists(out_html))
            with open(out_html, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("perf_suite 跨会话 (A/B) 综合对比评测报告", content)
            self.assertIn("session_v1", content)
            self.assertIn("session_v2", content)
            self.assertIn("ChartZoom", content)
            self.assertIn("data-theme", content)
            self.assertIn('"pointRadius": 0', content)
            self.assertIn('"pointHoverRadius": 6', content)
            cmp_payload = content.split("const reportData = ")[1].split(";\n        const chartInstances")[0]
            self.assertNotIn("borderDash", cmp_payload)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
