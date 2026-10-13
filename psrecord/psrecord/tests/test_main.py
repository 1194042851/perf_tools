import csv
import os
import subprocess
import sys

import psutil
import pytest

from ..main import all_children, main, monitor

TEST_CODE = """
import subprocess
p = subprocess.Popen('sleep 5'.split())
p.wait()
"""


def test_all_children(tmpdir):
    filename = tmpdir.join("test.py").strpath

    with open(filename, "w") as f:
        f.write(TEST_CODE)

    p = subprocess.Popen(f"{sys.executable} {filename}".split())

    import time

    time.sleep(1)

    pr = psutil.Process(p.pid)
    children = all_children(pr)
    assert len(children) > 0
    p.kill()


class TestMonitor:
    def setup_method(self, method):
        self.p = subprocess.Popen("sleep 10", shell=True)

    def teardown_method(self, method):
        self.p.kill()

    def test_simple(self):
        monitor(self.p.pid, duration=3)

    def test_simple_with_interval(self):
        monitor(self.p.pid, duration=3, interval=0.1)

    def test_with_children(self, tmpdir):
        # Test with current process since it has a subprocess (self.p)
        monitor(os.getpid(), duration=3, include_children=True)

    def test_logfile(self, tmpdir):
        filename = tmpdir.join("test_logfile").strpath
        monitor(self.p.pid, logfile=filename, duration=3)
        assert os.path.exists(filename)
        assert len(open(filename).readlines()) > 0

    def test_logfile_csv(self, tmpdir):
        filename = tmpdir.join("test_logfile.csv").strpath
        monitor(self.p.pid, logfile=filename, duration=3, log_format="csv")
        assert os.path.exists(filename)
        assert len(open(filename).readlines()) > 0
        with open(filename) as csvfile:
            data = csv.reader(csvfile)
            assert next(data) == ["elapsed_time", "nproc", "cpu", "mem_real", "mem_virtual"]

    def test_plot(self, tmpdir):
        pytest.importorskip("matplotlib")
        filename = tmpdir.join("test_plot.png").strpath
        monitor(self.p.pid, plot=filename, duration=3)
        assert os.path.exists(filename)

    def test_main(self):
        sys.argv = [
            "psrecord",
            "--duration=3",
            f'"{sys.executable}" -c "import time; time.sleep(10)"',
        ]
        main()

    def test_main_by_id(self):
        sys.argv = ["psrecord", "--duration=3", str(os.getpid())]
        main()

    @pytest.mark.skipif(sys.platform == "darwin", reason="Functionality not supported on MacOS")
    def test_io(self, tmpdir):
        monitor(os.getpid(), duration=3, include_io=True)


MEMORY_CODE = """
x = [0] * 20_000_000
import time
time.sleep(10)
"""


def max_logged_memory(filename):
    with open(filename) as f:
        rows = [line.split() for line in f.readlines()[1:]]
    return max(float(row[2]) for row in rows)


@pytest.mark.skipif(sys.platform == "win32", reason="Test relies on POSIX commands")
class TestLaunchedCommand:
    # When psrecord launches the command itself, the logged statistics
    # should be those of the command, not of an intermediate shell

    def setup_method(self, method):
        self.original_argv = sys.argv

    def teardown_method(self, method):
        sys.argv = self.original_argv

    def test_simple_command(self, tmpdir):
        script = tmpdir.join("memory.py").strpath
        with open(script, "w") as f:
            f.write(MEMORY_CODE)
        logfile = tmpdir.join("log.txt").strpath
        sys.argv = [
            "psrecord",
            f"{sys.executable} {script}",
            "--log",
            logfile,
            "--duration=3",
            "--interval=0.2",
        ]
        main()
        assert max_logged_memory(logfile) > 100

    def test_command_with_shell_syntax(self, tmpdir):
        script = tmpdir.join("memory.py").strpath
        with open(script, "w") as f:
            f.write(MEMORY_CODE)
        logfile = tmpdir.join("log.txt").strpath
        sys.argv = [
            "psrecord",
            f"sleep 0 && {sys.executable} {script}",
            "--log",
            logfile,
            "--duration=3",
            "--interval=0.2",
        ]
        main()
        assert max_logged_memory(logfile) > 100


class TestNewFeatures:
    def test_probe_capabilities(self):
        from ..main import probe_capabilities

        caps = probe_capabilities(os.getpid())
        assert isinstance(caps, dict)
        assert "io" in caps
        assert "pss" in caps
        assert "threads" in caps
        assert "fds" in caps

    def test_multi_pid_session(self, tmpdir):
        p1 = subprocess.Popen("sleep 10", shell=True)
        p2 = subprocess.Popen("sleep 10", shell=True)
        try:
            out_dir = tmpdir.join("session_test").strpath
            sys.argv = [
                "psrecord",
                f"--pid={p1.pid},{p2.pid}",
                f"--output-dir={out_dir}",
                "--duration=2",
                "--interval=0.2",
            ]
            main()
            assert os.path.isdir(out_dir)
            assert os.path.exists(os.path.join(out_dir, "meta.json"))
            assert os.path.exists(os.path.join(out_dir, "system.csv"))
            csvs = [f for f in os.listdir(out_dir) if f.startswith("proc_")]
            assert len(csvs) == 2
            # Check meta.json structure
            import json

            import json
            with open(os.path.join(out_dir, "meta.json")) as f:
                meta = json.load(f)
            assert len(meta["processes"]) == 2
            assert "capabilities" in meta
        finally:
            p1.kill()
            p2.kill()

    def test_io_unsupported_does_not_crash(self, tmpdir, monkeypatch):
        import psrecord
        import sys
        mod = sys.modules["psrecord.main"]

        orig_probe = mod.probe_capabilities

        def fake_probe(pid):
            c = orig_probe(pid)
            c["io"] = False
            return c

        monkeypatch.setattr(mod, "probe_capabilities", fake_probe)
        out_dir = tmpdir.join("session_io").strpath
        p = subprocess.Popen("sleep 5", shell=True)
        try:
            monitor(p.pid, session_dir=out_dir, duration=1.5, interval=0.2, include_io=True)
            assert os.path.isdir(out_dir)
            import json
            with open(os.path.join(out_dir, "meta.json")) as f:
                meta = json.load(f)
            assert meta["capabilities"]["io"] is False
        finally:
            p.kill()

