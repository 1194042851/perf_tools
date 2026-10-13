from abc import ABC, abstractmethod
from typing import Dict, Any, List

class BaseCollector(ABC):
    """指标采集器抽象基类"""

    @abstractmethod
    def probe(self) -> Dict[str, Any]:
        """初始化前能力探测，返回该采集器支持的特性能力字典"""
        pass

    @abstractmethod
    def collect(self, now: float, elapsed: float) -> List[Dict[str, Any]]:
        """每个 tick 采集一次，返回行数据列表（支持单采样产出多行或多个目标）"""
        pass

    @abstractmethod
    def get_stream_names(self) -> List[str]:
        """返回此采集器输出的流标识（对应不同输出文件名，如 proc_1234, net_eth0）"""
        pass
