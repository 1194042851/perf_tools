import os
import json
import csv
import platform
import time
from typing import Dict, Any, List

class SessionManager:
    def __init__(self, output_dir: str):
        self.output_dir = os.path.abspath(output_dir)
        os.makedirs(self.output_dir, exist_ok=True)
        self.meta: Dict[str, Any] = {
            "version": "0.1.0",
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "platform": {
                "system": platform.system(),
                "node": platform.node(),
                "release": platform.release(),
                "machine": platform.machine(),
            },
            "capabilities": {},
            "streams": [],
            "start_time": 0.0,
            "end_time": 0.0,
            "duration_s": 0.0,
        }
        self.file_handles: Dict[str, Any] = {}
        self.csv_writers: Dict[str, csv.DictWriter] = {}

    def set_capabilities(self, caps: Dict[str, Any]):
        self.meta["capabilities"] = caps

    def write_rows(self, rows: List[Dict[str, Any]]):
        for row in rows:
            stream = row.get("stream", "default")
            if stream not in self.csv_writers:
                filepath = os.path.join(self.output_dir, f"{stream}.csv")
                f = open(filepath, "w", newline="", encoding="utf-8")
                self.file_handles[stream] = f
                # 表头排除内部流标识
                fieldnames = [k for k in row.keys() if k != "stream"]
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                self.csv_writers[stream] = writer
                if stream not in self.meta["streams"]:
                    self.meta["streams"].append(stream)

            writer = self.csv_writers[stream]
            clean_row = {k: v for k, v in row.items() if k != "stream"}
            writer.writerow(clean_row)

    def flush(self):
        for f in self.file_handles.values():
            f.flush()

    def finish(self, start_time: float, end_time: float):
        self.meta["start_time"] = round(start_time, 3)
        self.meta["end_time"] = round(end_time, 3)
        self.meta["duration_s"] = round(end_time - start_time, 3)

        for f in self.file_handles.values():
            try:
                f.close()
            except Exception:
                pass

        meta_path = os.path.join(self.output_dir, "meta.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(self.meta, f, indent=2, ensure_ascii=False)
