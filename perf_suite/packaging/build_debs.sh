#!/bin/bash
# 构建 perf-suite / perf-suite-report 两个 deb 安装包（纯 Python, Architecture: all）
# 用法: ./packaging/build_debs.sh  (在 perf_suite 目录下执行, 产物输出到 dist/)
set -e
cd "$(dirname "$0")/.."
OUT=dist
mkdir -p $OUT

build_deb() {
    local pkg_name=$1 version=$2 src_pkg=$3 bin_name=$4 bin_module=$5 depends=$6 recommends=$7 desc_cn=$8
    local stage=$(mktemp -d)
    mkdir -p $stage/DEBIAN $stage/usr/lib/python3/dist-packages $stage/usr/bin

    cp -r $src_pkg $stage/usr/lib/python3/dist-packages/
    find $stage -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
    find $stage -name "*.pyc" -delete

    cat > $stage/usr/bin/$bin_name << LAUNCHER
#!/usr/bin/python3
import sys
from $bin_module import main
if __name__ == "__main__":
    main()
else:
    sys.exit(main())
LAUNCHER
    chmod 755 $stage/usr/bin/$bin_name

    {
        echo "Package: $pkg_name"
        echo "Version: $version"
        echo "Section: utils"
        echo "Priority: optional"
        echo "Architecture: all"
        echo "Maintainer: perf_tools"
        echo "Depends: $depends"
        [ -n "$recommends" ] && echo "Recommends: $recommends"
        echo "Description: $desc_cn"
    } > $stage/DEBIAN/control

    dpkg-deb --build --root-owner-group $stage $OUT/${pkg_name}_${version}_all.deb
    rm -rf $stage
    echo "built: $OUT/${pkg_name}_${version}_all.deb"
}

# 1. 采集器 (板端使用)
build_deb perf-suite 0.1.0-1 perf-suite/perf_suite perf-suite perf_suite.cli \
    "python3 (>= 3.8), python3-psutil" "" \
    "多进程与网卡统一性能记录工具(采集端): CPU/PSS/IO/网卡吞吐/PPS/整机背景指标采样落盘"

# 2. 可视化报告 (PC端使用)
build_deb perf-suite-report 0.1.0-1 perf-suite-report/perf_suite_report perf-suite-report perf_suite_report.cli \
    "python3 (>= 3.8)" "python3-plotly" \
    "perf-suite 会话可视化与对比报告生成工具(PC端): 单会话全景交互式报告与A/B多会话横向对比"

ls -la $OUT/*.deb
