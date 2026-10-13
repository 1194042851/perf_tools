from setuptools import setup, find_packages

setup(
    name="psrecord",
    version="1.5.0",
    description="Python package to record activity from processes",
    packages=find_packages(),
    install_requires=["psutil>=5.6"],
    entry_points={
        "console_scripts": [
            "psrecord=psrecord.main:main",
        ],
    },
)
