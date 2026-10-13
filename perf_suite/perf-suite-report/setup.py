#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from setuptools import setup, find_packages

setup(
    name="perf-suite-report",
    version="0.1.0",
    description="perf-suite 会话可视化与对比报告生成工具（PC端）",
    author="zsxc",
    packages=find_packages(),
    package_data={
        "perf_suite_report": ["*.js"],
    },
    include_package_data=True,
    install_requires=[],
    entry_points={
        "console_scripts": [
            "perf-suite-report=perf_suite_report.cli:main",
        ],
    },
    python_requires=">=3.8",
)
