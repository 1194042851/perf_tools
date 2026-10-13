import os
import glob
import psutil
from typing import Dict, Any, List
from .base import BaseCollector

class SystemCollector(BaseCollector):
    def __init__(self, sample_thermal: bool = True, sample_freq: bool = True):
        self.sample_thermal = sample_thermal
        self.sample_freq = sample_freq
        self.thermal_paths: Dict[str, str] = {}
        self.policy_paths: Dict[str, str] = {}
        self._init_hardware_nodes()

    def _init_hardware_nodes(self):
        # 寻找 thermal zones
        if self.sample_thermal:
            for tz in sorted(glob.glob("/sys/class/thermal/thermal_zone*")):
                name = os.path.basename(tz)
                type_path = os.path.join(tz, "type")
                tz_type = name
                if os.path.exists(type_path):
                    try:
                        with open(type_path, "r") as f:
                            tz_type = f.read().strip()
                    except Exception:
                        pass
                temp_path = os.path.join(tz, "temp")
                if os.path.exists(temp_path):
                    # 识别 key: soc, cpu 等
                    self.thermal_paths[f"temp_{tz_type}"] = temp_path

        # 寻找 cpufreq policies (RK3588 通常是 policy0 [A55], policy4 [A76], policy6 [A76])
        if self.sample_freq:
            for pol in sorted(glob.glob("/sys/devices/system/cpu/cpufreq/policy*")):
                name = os.path.basename(pol)
                cur_freq = os.path.join(pol, "scaling_cur_freq")
                if os.path.exists(cur_freq):
                    self.policy_paths[f"freq_{name}_mhz"] = cur_freq

    def probe(self) -> Dict[str, Any]:
        return {
            "thermal_sensors": list(self.thermal_paths.keys()),
            "cpufreq_policies": list(self.policy_paths.keys()),
            "cpu_count": psutil.cpu_count(logical=True)
        }

    def collect(self, now: float, elapsed: float) -> List[Dict[str, Any]]:
        # 整机 CPU
        sys_cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()

        row = {
            "stream": "system",
            "timestamp": round(now, 3),
            "elapsed_s": round(elapsed, 3),
            "sys_cpu_percent": round(sys_cpu, 1),
            "sys_mem_percent": round(mem.percent, 1),
            "sys_mem_used_mb": round(mem.used / (1024.0 ** 2), 1),
            "sys_mem_avail_mb": round(mem.available / (1024.0 ** 2), 1),
        }

        # 读频率
        for key, path in self.policy_paths.items():
            try:
                with open(path, "r") as f:
                    val_khz = int(f.read().strip())
                    row[key] = round(val_khz / 1000.0, 1)
            except Exception:
                row[key] = 0.0

        # 读温度
        for key, path in self.thermal_paths.items():
            try:
                with open(path, "r") as f:
                    val_mc = int(f.read().strip())
                    row[key] = round(val_mc / 1000.0, 1)
            except Exception:
                row[key] = 0.0

        return [row]

    def get_stream_names(self) -> List[str]:
        return ["system"]
