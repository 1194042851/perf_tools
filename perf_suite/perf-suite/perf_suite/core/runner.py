import time
import signal
import sys
from typing import List
from .session import SessionManager
from ..collectors.base import BaseCollector
from ..collectors.process import ProcessCollector

class Runner:
    def __init__(self, collectors: List[BaseCollector], session: SessionManager, interval: float = 1.0, duration: float = None):
        self.collectors = collectors
        self.session = session
        self.interval = max(0.1, interval)
        self.duration = duration
        self._running = True
        self._setup_signals()

    def _setup_signals(self):
        def _handler(signum, frame):
            print("\n[INFO] 接收到中断信号，正在安全结束记录并刷新数据...")
            self._running = False
        signal.signal(signal.SIGINT, _handler)
        signal.signal(signal.SIGTERM, _handler)

    def run(self):
        # 1. 运行能力探测
        all_caps = {}
        for c in self.collectors:
            name = c.__class__.__name__
            all_caps[name] = c.probe()
        self.session.set_capabilities(all_caps)

        start_time = time.time()
        print(f"[INFO] 开始记录 (采样间隔: {self.interval}s, 预期时长: {self.duration or '持续直至中断'}s)")

        try:
            while self._running:
                now = time.time()
                elapsed = now - start_time

                if self.duration is not None and elapsed >= self.duration:
                    print(f"[INFO] 达到预定时长 {self.duration}s，记录完成。")
                    break

                # 检查进程收集器是否所有目标均已退出
                all_procs_dead = False
                for c in self.collectors:
                    if isinstance(c, ProcessCollector):
                        if c.all_dead():
                            all_procs_dead = True
                if all_procs_dead:
                    print("[INFO] 所有监控目标进程均已退出，结束记录。")
                    break

                batch_rows = []
                for c in self.collectors:
                    batch_rows.extend(c.collect(now, elapsed))

                if batch_rows:
                    self.session.write_rows(batch_rows)
                    self.session.flush()

                # 精确定时休眠
                loop_elapsed = time.time() - now
                sleep_time = max(0.01, self.interval - loop_elapsed)
                time.sleep(sleep_time)

        finally:
            end_time = time.time()
            self.session.finish(start_time, end_time)
            print(f"[INFO] 记录已落盘完成，Session 路径: {self.session.output_dir}")
