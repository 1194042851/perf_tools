import os
import psutil
from typing import Dict, Any, List, Optional
from .base import BaseCollector

class ProcessCollector(BaseCollector):
    def __init__(self, pids: List[int], include_children: bool = False, include_io: bool = False):
        self.target_pids = list(set(pids))
        self.include_children = include_children
        self.request_io = include_io
        self.has_io_accounting = False
        self.has_smaps_rollup = False
        self.proc_map: Dict[int, psutil.Process] = {}
        self.meta_info: Dict[int, Dict[str, Any]] = {}
        self.dead_pids: set = set()
        self._init_processes()

    def _init_processes(self):
        for pid in self.target_pids:
            try:
                p = psutil.Process(pid)
                self.proc_map[pid] = p
                name = p.name()
                try:
                    cmd = " ".join(p.cmdline())
                except Exception:
                    cmd = name
                self.meta_info[pid] = {
                    "name": name,
                    "cmdline": cmd,
                    "create_time": p.create_time()
                }
                # 预热 cpu_percent
                p.cpu_percent()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                self.dead_pids.add(pid)

    def probe(self) -> Dict[str, Any]:
        # 探测 1: 进程 IO 统计能力 (解决缺少 CONFIG_TASK_IO_ACCOUNTING 导致 io_counters 崩溃)
        self.has_io_accounting = False
        if self.proc_map:
            sample_proc = next(iter(self.proc_map.values()))
            if hasattr(sample_proc, "io_counters"):
                try:
                    sample_proc.io_counters()
                    self.has_io_accounting = True
                except Exception:
                    self.has_io_accounting = False
            else:
                self.has_io_accounting = False

        # 探测 2: smaps_rollup (PSS 内存)
        self.has_smaps_rollup = os.path.exists(f"/proc/{os.getpid()}/smaps_rollup")

        return {
            "task_io_accounting": self.has_io_accounting,
            "smaps_rollup_pss": self.has_smaps_rollup,
            "monitored_pids": list(self.proc_map.keys())
        }

    def _read_pss(self, pid: int) -> float:
        if not self.has_smaps_rollup:
            return 0.0
        try:
            with open(f"/proc/{pid}/smaps_rollup", "r") as f:
                for line in f:
                    if line.startswith("Pss:"):
                        # Pss:        1234 kB
                        parts = line.split()
                        return round(float(parts[1]) / 1024.0, 2)
        except Exception:
            pass
        return 0.0

    def collect(self, now: float, elapsed: float) -> List[Dict[str, Any]]:
        results = []
        for pid, p in list(self.proc_map.items()):
            if pid in self.dead_pids:
                continue

            try:
                # 状态检查
                status = p.status()
                if status in (psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD):
                    self.dead_pids.add(pid)
                    continue

                cpu_pct = p.cpu_percent()
                mem = p.memory_info()
                rss_mb = round(mem.rss / (1024.0 ** 2), 2)
                vms_mb = round(mem.vms / (1024.0 ** 2), 2)
                pss_mb = self._read_pss(pid)

                # 线程数
                threads = p.num_threads()

                # 上下文切换
                vol_ctx, invol_ctx = 0, 0
                try:
                    ctx = p.num_ctx_switches()
                    vol_ctx = ctx.voluntary
                    invol_ctx = ctx.involuntary
                except Exception:
                    pass

                # IO 统计 (受保护)
                read_bytes, write_bytes = 0, 0
                read_count, write_count = 0, 0
                if self.request_io and self.has_io_accounting:
                    try:
                        io = p.io_counters()
                        read_bytes = io.read_bytes
                        write_bytes = io.write_bytes
                        read_count = io.read_count
                        write_count = io.write_count
                    except Exception:
                        pass

                # 处理子进程聚合
                if self.include_children:
                    try:
                        for child in p.children(recursive=True):
                            try:
                                cpu_pct += child.cpu_percent()
                                c_mem = child.memory_info()
                                rss_mb += round(c_mem.rss / (1024.0 ** 2), 2)
                                vms_mb += round(c_mem.vms / (1024.0 ** 2), 2)
                                threads += child.num_threads()
                                if self.request_io and self.has_io_accounting:
                                    c_io = child.io_counters()
                                    read_bytes += c_io.read_bytes
                                    write_bytes += c_io.write_bytes
                            except Exception:
                                continue
                    except Exception:
                        pass

                row = {
                    "stream": f"proc_{pid}",
                    "timestamp": round(now, 3),
                    "elapsed_s": round(elapsed, 3),
                    "pid": pid,
                    "name": self.meta_info[pid]["name"],
                    "cpu_percent": round(cpu_pct, 1),
                    "rss_mb": round(rss_mb, 2),
                    "vms_mb": round(vms_mb, 2),
                    "pss_mb": round(pss_mb, 2),
                    "threads": threads,
                    "voluntary_ctx": vol_ctx,
                    "involuntary_ctx": invol_ctx,
                }
                if self.request_io and self.has_io_accounting:
                    row["read_bytes"] = read_bytes
                    row["write_bytes"] = write_bytes
                    row["read_count"] = read_count
                    row["write_count"] = write_count

                results.append(row)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                self.dead_pids.add(pid)
                continue

        return results

    def get_stream_names(self) -> List[str]:
        return [f"proc_{pid}" for pid in self.target_pids]

    def all_dead(self) -> bool:
        return len(self.dead_pids) >= len(self.target_pids)
