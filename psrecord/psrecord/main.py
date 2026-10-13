# Copyright (c) 2013, Thomas P. Robitaille
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

import argparse
import json
import os
import platform
import sys
import time

children = []

# Characters that mean a command has to be run through a shell rather than
# being split into arguments and executed directly
SHELL_CHARS = "|&;<>()$`\\\"'*?[]{}~#\n"


def get_percent(process):
    return process.cpu_percent()


def get_memory(process):
    return process.memory_info()


def all_children(pr):
    global children

    try:
        children_of_pr = pr.children(recursive=True)
    except Exception:  # pragma: no cover
        return children

    for child in children_of_pr:
        if child not in children:
            children.append(child)

    return children


def read_pss_mb(pid):
    # Read PSS from /proc/<pid>/smaps_rollup (much cheaper than parsing smaps)
    try:
        with open(f"/proc/{pid}/smaps_rollup") as f:
            for line in f:
                if line.startswith("Pss:"):
                    return int(line.split()[1]) / 1024.0
    except OSError:
        return None
    return None


def probe_capabilities(pid):
    # Probe once at startup which metrics are available on this kernel
    # (similar to atop probing /proc/1/io). Avoids crashing on kernels
    # built without e.g. CONFIG_TASK_IO_ACCOUNTING.
    import psutil

    caps = {}
    try:
        pr = psutil.Process(pid)
    except psutil.Error:
        pr = None

    caps["io"] = False
    if pr is not None and hasattr(pr, "io_counters"):
        try:
            pr.io_counters()
            caps["io"] = True
        except Exception:
            caps["io"] = False

    caps["pss"] = os.path.exists("/proc/self/smaps_rollup")

    caps["fds"] = False
    if pr is not None and hasattr(pr, "num_fds"):
        try:
            pr.num_fds()
            caps["fds"] = True
        except Exception:
            caps["fds"] = False

    caps["threads"] = pr is not None and hasattr(pr, "num_threads")
    caps["ctx_switches"] = pr is not None and hasattr(pr, "num_ctx_switches")

    try:
        caps["sensors_temperatures"] = bool(psutil.sensors_temperatures())
    except Exception:
        caps["sensors_temperatures"] = False
    caps["thermal_zones"] = os.path.isdir("/sys/class/thermal")

    return caps


class ProcessTracker:
    """Tracks a single target process (optionally including its children)."""

    def __init__(self, pid, include_children=False, include_io=False, caps=None):
        import psutil

        self.pid = pid
        self.include_children = include_children
        self.include_io = include_io and caps.get("io", False)
        self.caps = caps or {}
        self.process = psutil.Process(pid)
        self.name = self.process.name()
        try:
            self.cmdline = " ".join(self.process.cmdline())
        except Exception:
            self.cmdline = ""
        self.dead_at = None
        # Prime cpu_percent (first call always returns 0.0)
        try:
            self.process.cpu_percent()
        except Exception:
            pass

    @property
    def alive(self):
        return self.dead_at is None

    def check_alive(self):
        import psutil

        try:
            status = self.process.status()
        except psutil.NoSuchProcess:
            self.dead_at = time.time()
            return False
        if status in [psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD]:
            self.dead_at = time.time()
            return False
        return True

    def sample(self):
        # Returns a dict of metrics, aggregating children if requested
        s = {
            "cpu": 0.0,
            "mem_real": 0.0,
            "mem_virtual": 0.0,
            "pss": 0.0,
            "threads": 0,
            "fds": 0,
            "ctx_voluntary": 0,
            "ctx_involuntary": 0,
            "n_proc": 0,
        }
        if self.include_io:
            s["read_count"] = 0
            s["write_count"] = 0
            s["read_bytes"] = 0
            s["write_bytes"] = 0

        processes = [self.process]
        if self.include_children:
            processes = processes + all_children(self.process)

        for pr in processes:
            try:
                s["cpu"] += get_percent(pr)
                mem = get_memory(pr)
                s["mem_real"] += mem.rss / 1024.0**2
                s["mem_virtual"] += mem.vms / 1024.0**2
                if self.caps.get("pss"):
                    pss = read_pss_mb(pr.pid)
                    if pss is not None:
                        s["pss"] += pss
                if self.caps.get("threads"):
                    s["threads"] += pr.num_threads()
                if self.caps.get("fds"):
                    try:
                        s["fds"] += pr.num_fds()
                    except Exception:
                        pass
                if self.caps.get("ctx_switches"):
                    ctx = pr.num_ctx_switches()
                    s["ctx_voluntary"] += ctx.voluntary
                    s["ctx_involuntary"] += ctx.involuntary
                if self.include_io:
                    counters = pr.io_counters()
                    s["read_count"] += counters.read_count
                    s["write_count"] += counters.write_count
                    s["read_bytes"] += counters.read_bytes
                    s["write_bytes"] += counters.write_bytes
                s["n_proc"] += 1
            except Exception:
                continue

        if not self.caps.get("pss"):
            s["pss"] = None

        return s


PROC_CSV_FIELDS = [
    "cpu",
    "mem_real",
    "mem_virtual",
    "pss",
    "threads",
    "fds",
    "ctx_voluntary",
    "ctx_involuntary",
    "n_proc",
]
PROC_CSV_IO_FIELDS = ["read_count", "write_count", "read_bytes", "write_bytes"]


def sample_system(caps):
    import psutil

    s = {}
    percpu = psutil.cpu_percent(percpu=True)
    s["cpu_total"] = sum(percpu) / len(percpu) if percpu else 0.0
    for i, v in enumerate(percpu):
        s[f"cpu{i}"] = v
    vm = psutil.virtual_memory()
    s["mem_used_mb"] = vm.used / 1024.0**2
    s["mem_percent"] = vm.percent
    try:
        for i, f in enumerate(psutil.cpu_freq(percpu=True) or []):
            s[f"freq{i}"] = f.current
    except Exception:
        pass
    # Temperatures: prefer psutil sensors, fall back to thermal_zone files
    temps = {}
    if caps.get("sensors_temperatures"):
        try:
            for chip, entries in psutil.sensors_temperatures().items():
                for entry in entries:
                    label = entry.label or chip
                    temps[f"temp_{label}"] = entry.current
        except Exception:
            temps = {}
    if not temps and caps.get("thermal_zones"):
        base = "/sys/class/thermal"
        try:
            for zone in sorted(os.listdir(base)):
                if not zone.startswith("thermal_zone"):
                    continue
                try:
                    with open(os.path.join(base, zone, "type")) as f:
                        label = f.read().strip()
                    with open(os.path.join(base, zone, "temp")) as f:
                        temps[f"temp_{label}"] = int(f.read().strip()) / 1000.0
                except (OSError, ValueError):
                    continue
        except OSError:
            pass
    s.update(temps)
    try:
        dio = psutil.disk_io_counters()
        if dio is not None:
            s["disk_read_bytes"] = dio.read_bytes
            s["disk_write_bytes"] = dio.write_bytes
    except Exception:
        pass
    return s


def _safe_name(name):
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in name)[:40]


def main():
    parser = argparse.ArgumentParser(
        prog="psrecord",
        description="多进程与系统性能记录工具（增强版）：支持单/多进程 CPU、内存(RSS/PSS)、线程数、"
                    "句柄数(FD)、整机背景指标（各核CPU/频率/温度）的采样与落盘。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n"
               "  psrecord 1234 --duration 10                     # 监控单个进程10秒（终端实时打印）\n"
               "  psrecord 1234 --log out.csv --log-format csv    # 记录单进程到CSV文件\n"
               "  psrecord --pid 1234,5678 --output-dir session1  # 同时监控多个进程并记录会话\n"
               "  psrecord \"sleep 5\" --output-dir session2       # 启动命令并全程监控记录\n"
               "  psrecord-report session1 -o report.html         # 生成交互式HTML可视化报告\n",
    )

    parser.add_argument(
        "process_id_or_command",
        type=str,
        nargs="?",
        metavar="PID或命令",
        help="要监控的目标进程PID或要启动并监控的命令（如 1234 或 \"sleep 10\"）。",
    )

    parser.add_argument(
        "--pid",
        type=str,
        action="append",
        default=[],
        metavar="PID列表",
        help="要同时监控的目标进程PID，支持逗号分隔或多次指定，例如: --pid 1234,5678 或 --pid 1234 --pid 5678。",
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        metavar="DIR",
        help="会话输出目录（包含各进程独立CSV、整机背景system.csv及meta.json元数据）。"
             "监控多进程时如果不指定，将自动生成形如 session_YYYYMMDD_HHMMSS 的目录。",
    )

    parser.add_argument(
        "--duration",
        type=float,
        metavar="秒",
        help="持续记录时长（单位: 秒）。若不指定则持续记录直至目标进程退出或按 Ctrl+C 中断。",
    )

    parser.add_argument(
        "--interval",
        type=float,
        metavar="秒",
        help="采样时间间隔（单位: 秒，例如 0.5、1.0）。若不指定则以最高速率尽可能密集采样。",
    )

    parser.add_argument(
        "--include-children",
        action="store_true",
        help="统计时包含目标进程的所有子进程（多进程模式下每个目标进程独立聚合其子进程）。",
    )

    parser.add_argument(
        "--include-io",
        action="store_true",
        help="采集目标进程的读写 IO 计数及字节数。内核未开启 CONFIG_TASK_IO_ACCOUNTING 时将自动探测并安全跳过，绝不崩溃。",
    )

    parser.add_argument(
        "--no-system",
        action="store_true",
        help="在会话模式下不采集整机背景指标（整机背景默认包含各核CPU利用率、内存、大小核频率、各温区温度、磁盘总IO）。",
    )

    parser.add_argument(
        "--log",
        type=str,
        metavar="FILE",
        help="【单进程模式】输出统计数据到文件。若未指定 --log 和 --plot 则默认打印到标准输出。",
    )

    parser.add_argument(
        "--log-format",
        type=str,
        default="plain",
        choices=["plain", "csv"],
        help='【单进程模式】日志输出格式，可选 "plain"（纯文本对齐）或 "csv"（逗号分隔，默认: plain）。',
    )

    parser.add_argument(
        "--plot",
        type=str,
        metavar="FILE",
        help="【单进程模式】录制结束后绘制简单的静态折线图并保存为图片（如 plot.png）。",
    )

    args = parser.parse_args()

    include_children = args.include_children

    # Collect all target pids
    pids = []
    for item in args.pid:
        for part in item.split(","):
            part = part.strip()
            if part:
                pids.append(int(part))

    sprocess = None
    if args.process_id_or_command is not None:
        try:
            pids.append(int(args.process_id_or_command))
            print(f"Attaching to process {pids[-1]}")
        except ValueError:
            import shlex
            import subprocess

            command = args.process_id_or_command
            print(f"Starting up command '{command}' and attaching to process")
            if sys.platform == "win32":
                sprocess = subprocess.Popen(command)
            elif any(char in command for char in SHELL_CHARS):
                # Running the command through a shell means the monitored process
                # is the shell itself, since modern shells no longer exec single
                # commands in-place, so child processes have to be included for
                # the statistics to be meaningful.
                sprocess = subprocess.Popen(command, shell=True)
                if not include_children:
                    print("Command requires a shell, including child processes in statistics")
                    include_children = True
            else:
                sprocess = subprocess.Popen(shlex.split(command))
            pids.append(sprocess.pid)

    if not pids:
        parser.error("no process specified (use a positional PID/command or --pid)")

    if len(set(pids)) != len(pids):
        parser.error(f"duplicate process ids: {pids}")

    if len(pids) > 1 and (args.log or args.plot):
        parser.error("--log and --plot only support a single process, use --output-dir instead")

    output_dir = args.output_dir
    if output_dir is None and len(pids) > 1:
        output_dir = time.strftime("session_%Y%m%d_%H%M%S")
        print(f"No --output-dir given, recording session to {output_dir}")

    monitor(
        pids,
        logfile=args.log,
        plot=args.plot,
        session_dir=output_dir,
        duration=args.duration,
        interval=args.interval,
        include_children=include_children,
        include_io=args.include_io,
        log_format=args.log_format,
        include_system=not args.no_system,
    )

    if sprocess is not None:
        sprocess.kill()


def monitor(
    pid,
    logfile=None,
    plot=None,
    session_dir=None,
    duration=None,
    interval=None,
    include_children=False,
    include_io=False,
    log_format="plain",
    include_system=True,
):
    # We import psutil here so that the module can be imported even if psutil
    # is not present (for example if accessing the version)
    import psutil

    if isinstance(pid, int):
        pids = [pid]
    else:
        pids = list(pid)

    if len(pids) > 1 and (logfile is not None or plot is not None):
        raise ValueError("logfile/plot only support a single process, use session_dir")

    caps = probe_capabilities(pids[0])

    if include_io and not caps["io"]:
        print(
            "WARNING: per-process I/O stats are not available on this kernel "
            "(CONFIG_TASK_IO_ACCOUNTING is not set); continuing without I/O metrics"
        )

    trackers = [ProcessTracker(p, include_children, include_io, caps) for p in pids]

    # Record start time
    start_time = time.time()

    f = None
    if logfile is None and plot is None and session_dir is None:
        f = sys.stdout
        logfile = "<stdout>"
    elif logfile is not None:
        f = open(logfile, "w")

    if logfile:
        if log_format == "plain":
            f.write(
                "# {:12s} {:12s} {:12s} {:12s}".format(
                    "Elapsed time".center(12),
                    "CPU (%)".center(12),
                    "Real (MB)".center(12),
                    "Virtual (MB)".center(12),
                ),
            )
            if include_io and caps["io"]:
                f.write(
                    " {:12s} {:12s} {:12s} {:12s}".format(
                        "Read count".center(12),
                        "Write count".center(12),
                        "Read bytes".center(12),
                        "Write bytes".center(12),
                    )
                )
        elif log_format == "csv":
            f.write("elapsed_time,nproc,cpu,mem_real,mem_virtual")
            if include_io and caps["io"]:
                f.write(",read_count,write_count,read_bytes,write_bytes")
        else:
            raise ValueError(
                f"Unknown log format: '{log_format}', should be either 'plain' or 'csv'"
            )
        f.write("\n")

    # Session output: one CSV per process plus system.csv and meta.json
    proc_files = {}
    system_f = None
    system_header_written = False
    session_dir_created = None
    if session_dir is not None:
        session_dir_created = session_dir
        os.makedirs(session_dir, exist_ok=True)
        for tracker in trackers:
            path = os.path.join(
                session_dir, f"proc_{tracker.pid}_{_safe_name(tracker.name)}.csv"
            )
            pf = open(path, "w")
            fields = list(PROC_CSV_FIELDS)
            if tracker.include_io:
                fields += PROC_CSV_IO_FIELDS
            pf.write("elapsed,epoch," + ",".join(fields) + "\n")
            pf.flush()
            proc_files[tracker.pid] = (pf, fields)
        if include_system:
            system_f = open(os.path.join(session_dir, "system.csv"), "w")
        # Prime per-cpu cpu_percent so first recorded sample is meaningful
        psutil.cpu_percent(percpu=True)

    meta = {
        "start_epoch": start_time,
        "start_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start_time)),
        "interval": interval,
        "include_children": include_children,
        "capabilities": caps,
        "system": {
            "machine": platform.machine(),
            "kernel": platform.release(),
            "platform": platform.platform(),
            "cpu_count": psutil.cpu_count(),
            "psutil_version": psutil.__version__,
        },
        "processes": [
            {"pid": t.pid, "name": t.name, "cmdline": t.cmdline} for t in trackers
        ],
    }

    log = {}
    log["times"] = []
    log["cpu"] = []
    log["mem_real"] = []
    log["mem_virtual"] = []

    if include_io and caps["io"]:
        log["read_count"] = []
        log["write_count"] = []
        log["read_bytes"] = []
        log["write_bytes"] = []

    try:
        # Start main event loop
        while True:
            # Find current time
            current_time = time.time()
            elapsed_time = current_time - start_time

            # Check if we have reached the maximum time
            if duration is not None and elapsed_time > duration:
                break

            samples = {}
            all_dead = True
            for tracker in trackers:
                if not tracker.alive:
                    continue
                if not tracker.check_alive():
                    print(
                        f"Process {tracker.pid} ({tracker.name}) finished "
                        f"({elapsed_time:.2f} seconds)"
                    )
                    # Single-process legacy behaviour: stop recording
                    if len(trackers) == 1:
                        break
                    continue
                all_dead = False
                samples[tracker.pid] = tracker.sample()

            if not trackers[0].alive and len(trackers) == 1:
                break
            if len(trackers) > 1 and all_dead:
                print(f"All processes finished ({elapsed_time:.2f} seconds)")
                break

            # Write session CSVs
            for tracker in trackers:
                if tracker.pid not in proc_files:
                    continue
                pf, fields = proc_files[tracker.pid]
                s = samples.get(tracker.pid)
                if s is None:
                    values = [""] * len(fields)
                else:
                    values = []
                    for field in fields:
                        v = s.get(field)
                        values.append("" if v is None else str(v))
                pf.write(f"{elapsed_time:.3f},{current_time:.3f}," + ",".join(values) + "\n")
                pf.flush()

            if system_f is not None:
                sys_sample = sample_system(caps)
                if not system_header_written:
                    system_f.write("elapsed,epoch," + ",".join(sys_sample.keys()) + "\n")
                    system_header_written = True
                system_f.write(
                    f"{elapsed_time:.3f},{current_time:.3f},"
                    + ",".join(str(v) for v in sys_sample.values())
                    + "\n"
                )
                system_f.flush()

            # Legacy single-process logfile/stdout output
            if logfile and len(trackers) == 1:
                s = samples.get(trackers[0].pid)
                if s is not None:
                    if log_format == "plain":
                        f.write(
                            f"{elapsed_time:12.3f} {s['cpu']:12.3f}"
                            f" {s['mem_real']:12.3f} {s['mem_virtual']:12.3f}"
                        )
                        if include_io and caps["io"]:
                            f.write(
                                f" {s['read_count']:12d} {s['write_count']:12d}"
                                f" {s['read_bytes']:12d} {s['write_bytes']:12d}"
                            )
                    elif log_format == "csv":
                        f.write(
                            f"{elapsed_time},{s['n_proc']},{s['cpu']},{s['mem_real']},{s['mem_virtual']}"
                        )
                        if include_io and caps["io"]:
                            f.write(
                                f",{s['read_count']},{s['write_count']},{s['read_bytes']},{s['write_bytes']}"
                            )
                    f.write("\n")
                    f.flush()

            if interval is not None:
                time.sleep(interval)

            # If plotting, record the values
            if plot and len(trackers) == 1:
                s = samples.get(trackers[0].pid)
                if s is not None:
                    log["times"].append(elapsed_time)
                    log["cpu"].append(s["cpu"])
                    log["mem_real"].append(s["mem_real"])
                    log["mem_virtual"].append(s["mem_virtual"])
                    if include_io and caps["io"]:
                        log["read_count"].append(s["read_count"])
                        log["write_count"].append(s["write_count"])
                        log["read_bytes"].append(s["read_bytes"])
                        log["write_bytes"].append(s["write_bytes"])

    except KeyboardInterrupt:  # pragma: no cover
        pass
    finally:
        # close the logfile, if it's not stdout
        if logfile and logfile != "<stdout>":
            f.close()
        for pf, _ in proc_files.values():
            pf.close()
        if system_f is not None:
            system_f.close()
        if session_dir_created is not None:
            end_time = time.time()
            meta["end_epoch"] = end_time
            meta["end_time"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(end_time))
            meta["duration_s"] = round(end_time - start_time, 3)
            for entry, tracker in zip(meta["processes"], trackers):
                if tracker.dead_at is not None:
                    entry["dead_at_epoch"] = tracker.dead_at
            with open(os.path.join(session_dir_created, "meta.json"), "w") as mf:
                json.dump(meta, mf, indent=2)
            print(f"Session written to {session_dir_created}")

    if plot and log["times"]:
        # Use non-interactive backend, to enable operation on headless machines
        # We import matplotlib here so that the module can be imported even if
        # matplotlib is not present and the plotting option is unset
        import matplotlib.pyplot as plt

        with plt.rc_context({"backend": "Agg"}):
            fig = plt.figure()
            ax = fig.add_subplot(1, 1, 1)

            ax.plot(log["times"], log["cpu"], "-", lw=1, color="r")

            ax.set_ylabel("CPU (%)", color="r")
            ax.set_xlabel("time (s)")
            ax.set_ylim(0.0, max(log["cpu"]) * 1.2)

            ax2 = ax.twinx()

            ax2.plot(log["times"], log["mem_real"], "-", lw=1, color="b")
            ax2.set_ylim(0.0, max(log["mem_real"]) * 1.2)

            ax2.set_ylabel("Real Memory (MB)", color="b")

            ax.grid()

            fig.savefig(plot, bbox_inches="tight")
