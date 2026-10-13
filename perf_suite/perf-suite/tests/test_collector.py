#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import unittest
import os
import shutil
import tempfile
import psutil
from perf_suite.collectors.network import NetworkCollector
from perf_suite.collectors.process import ProcessCollector
from perf_suite.collectors.system import SystemCollector
from perf_suite.core.session import SessionManager


class TestCollectorUnit(unittest.TestCase):
    def test_session_writer_and_reader(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            sess = SessionManager(tmp_dir)
            sess.set_capabilities({"mock": True})
            row = {"stream": "test_st", "timestamp": 100.0, "elapsed_s": 0.0, "val": 42.5}
            sess.write_rows([row])
            sess.finish(100.0, 105.0)

            self.assertTrue(os.path.exists(os.path.join(tmp_dir, "meta.json")))
            self.assertTrue(os.path.exists(os.path.join(tmp_dir, "test_st.csv")))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_network_collector(self):
        col = NetworkCollector(ifaces=["lo"])
        probe = col.probe()
        self.assertIn("monitored_ifaces", probe)
        data = col.collect(now=10.0, elapsed=0.0)
        self.assertIsInstance(data, list)

    def test_process_collector(self):
        cur_pid = os.getpid()
        col = ProcessCollector(pids=[cur_pid])
        probe = col.probe()
        self.assertIn("monitored_pids", probe)
        data = col.collect(now=10.0, elapsed=0.0)
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)
        self.assertEqual(data[0]["pid"], cur_pid)


if __name__ == "__main__":
    unittest.main()
