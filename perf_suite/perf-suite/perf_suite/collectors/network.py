import time
import psutil
from typing import Dict, Any, List
from .base import BaseCollector

class NetworkCollector(BaseCollector):
    def __init__(self, ifaces: List[str]):
        self.requested_ifaces = [i.strip() for i in ifaces if i.strip()]
        self.active_ifaces: List[str] = []
        self.last_stats: Dict[str, Dict[str, Any]] = {}
        self._init_ifaces()

    def _init_ifaces(self):
        all_stats = psutil.net_io_counters(pernic=True)
        if "all" in self.requested_ifaces:
            self.active_ifaces = list(all_stats.keys())
        else:
            self.active_ifaces = [i for i in self.requested_ifaces if i in all_stats]

    def probe(self) -> Dict[str, Any]:
        return {
            "monitored_ifaces": self.active_ifaces,
            "supported": len(self.active_ifaces) > 0
        }

    def collect(self, now: float, elapsed: float) -> List[Dict[str, Any]]:
        results = []
        current_stats = psutil.net_io_counters(pernic=True)

        for iface in self.active_ifaces:
            if iface not in current_stats:
                continue

            stat = current_stats[iface]
            last = self.last_stats.get(iface)

            rx_mbps = 0.0
            tx_mbps = 0.0
            rx_pps = 0.0
            tx_pps = 0.0
            rx_drop_delta = 0
            tx_drop_delta = 0
            rx_err_delta = 0
            tx_err_delta = 0

            if last is not None:
                dt = now - last["time"]
                if dt > 0.0001:
                    delta_rx_bytes = max(0, stat.bytes_recv - last["bytes_recv"])
                    delta_tx_bytes = max(0, stat.bytes_sent - last["bytes_sent"])
                    delta_rx_pkts = max(0, stat.packets_recv - last["packets_recv"])
                    delta_tx_pkts = max(0, stat.packets_sent - last["packets_sent"])

                    # 速率计算：Bytes * 8 / (dt * 1e6) = Mbps
                    rx_mbps = round((delta_rx_bytes * 8.0) / (dt * 1_000_000.0), 3)
                    tx_mbps = round((delta_tx_bytes * 8.0) / (dt * 1_000_000.0), 3)
                    rx_pps = round(delta_rx_pkts / dt, 1)
                    tx_pps = round(delta_tx_pkts / dt, 1)

                    rx_drop_delta = max(0, stat.dropin - last["dropin"])
                    tx_drop_delta = max(0, stat.dropout - last["dropout"])
                    rx_err_delta = max(0, stat.errin - last["errin"])
                    tx_err_delta = max(0, stat.errout - last["errout"])

            self.last_stats[iface] = {
                "time": now,
                "bytes_recv": stat.bytes_recv,
                "bytes_sent": stat.bytes_sent,
                "packets_recv": stat.packets_recv,
                "packets_sent": stat.packets_sent,
                "dropin": stat.dropin,
                "dropout": stat.dropout,
                "errin": stat.errin,
                "errout": stat.errout,
            }

            row = {
                "stream": f"net_{iface}",
                "timestamp": round(now, 3),
                "elapsed_s": round(elapsed, 3),
                "iface": iface,
                "rx_mbps": rx_mbps,
                "tx_mbps": tx_mbps,
                "rx_pps": rx_pps,
                "tx_pps": tx_pps,
                "rx_bytes_total": stat.bytes_recv,
                "tx_bytes_total": stat.bytes_sent,
                "rx_drop_delta": rx_drop_delta,
                "tx_drop_delta": tx_drop_delta,
                "rx_err_delta": rx_err_delta,
                "tx_err_delta": tx_err_delta,
            }
            results.append(row)

        return results

    def get_stream_names(self) -> List[str]:
        return [f"net_{iface}" for iface in self.active_ifaces]
