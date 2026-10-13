#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from setuptools import setup, find_packages

setup(
    name="perf-suite",
    version="0.1.0",
    description="嵌入式/Linux 多进程与网卡统一性能记录工具（采集端）",
    author="zsxc",
    packages=find_packages(),
    install_requires=[
        "psutil>=5.8.0",
    ],
    entry_points={
        "console_scripts": [
            "perf-suite=perf_suite.cli:main",
        ],
    },
    python_requires=">=3.8",
)
