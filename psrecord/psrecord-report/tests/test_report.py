import csv
import json
import os
import subprocess
import sys

from psrecord_report import generate_html, load_session


def make_session(path, pid=1234, name="demo", samples=5, io_cap=False):
    os.makedirs(path, exist_ok=True)
    meta = {
        "start_epoch": 1700000000.0,
        "start_time": "2026-10-13 12:00:00",
        "duration_s": samples * 0.5,
        "interval": 0.5,
        "capabilities": {"io": io_cap, "pss": True, "threads": True, "fds": True},
        "system": {"machine": "aarch64", "kernel": "5.10.160", "cpu_count": 8},
        "processes": [{"pid": pid, "name": name, "cmdline": "demo --run"}],
    }
    with open(os.path.join(path, "meta.json"), "w") as f:
        json.dump(meta, f)
    with open(os.path.join(path, f"proc_{pid}_{name}.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["elapsed", "epoch", "cpu", "mem_real", "mem_virtual", "pss",
                    "threads", "fds", "ctx_voluntary", "ctx_involuntary", "n_proc"])
        for i in range(samples):
            w.writerow([i * 0.5, 1700000000.0 + i * 0.5, 10.0 + i, 100.0 + i,
                        200.0, 90.0 + i, 4, 32, 100 + i, 50 + i, 1])
    with open(os.path.join(path, "system.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["elapsed", "epoch", "cpu_total", "cpu0", "mem_percent", "freq0"])
        for i in range(samples):
            w.writerow([i * 0.5, 1700000000.0 + i * 0.5, 5.0, 3.0, 20.0, 1800.0])
    return path


class TestReport:
    def test_load_session(self, tmpdir):
        session_dir = make_session(tmpdir.join("s1").strpath)
        session = load_session(session_dir)
        assert session["meta"]["processes"][0]["pid"] == 1234
        assert "proc_1234_demo" in session["procs"]
        assert "cpu_total" in session["system"]
        assert len(session["procs"]["proc_1234_demo"]["cpu"]) == 5

    def test_generate_html(self, tmpdir):
        session_dir = make_session(tmpdir.join("s1").strpath)
        out = tmpdir.join("report.html").strpath
        generate_html([load_session(session_dir)], out)
        content = open(out).read()
        assert "psrecord report" in content
        assert "Summary statistics" in content
        assert "proc_1234_demo" in content

    def test_compare_two_sessions(self, tmpdir):
        s1 = load_session(make_session(tmpdir.join("before").strpath))
        s2 = load_session(make_session(tmpdir.join("after").strpath, pid=1234, name="demo"))
        out = tmpdir.join("compare.html").strpath
        generate_html([s1, s2], out)
        content = open(out).read()
        assert "before" in content and "after" in content

    def test_cli(self, tmpdir):
        session_dir = make_session(tmpdir.join("s1").strpath)
        out = tmpdir.join("cli.html").strpath
        r = subprocess.run(
            [sys.executable, "-m", "psrecord_report.report", session_dir, "-o", out],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, r.stderr
        assert os.path.exists(out)
