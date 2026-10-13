from setuptools import setup, find_packages

setup(
    name="psrecord-report",
    version="1.0.0",
    description="psrecord 性能测试报告生成器（现代化交互式可视化工具）",
    packages=find_packages(),
    package_data={"psrecord_report": ["*.min.js", "*.js"]},
    include_package_data=True,
    install_requires=[],
    entry_points={
        "console_scripts": [
            "psrecord-report=psrecord_report.report:main",
        ],
    },
)
