#!/bin/bash
# 构建 psrecord / psrecord-report 两个 deb 安装包（纯 Python, Architecture: all）
# 用法: ./packaging/build_debs.sh  (在仓库根目录执行, 产物输出到 dist/)
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

# 采集器（板端使用）
build_deb psrecord 1.5.0-1 psrecord psrecord psrecord.main \
    "python3 (>= 3.8), python3-psutil" "" \
    "多进程性能记录工具(采集器): CPU/内存(PSS)/线程/FD/IO/整机背景指标采样落盘"

# 可视化报告（PC端使用）
build_deb psrecord-report 1.0.0-1 psrecord-report/psrecord_report psrecord-report psrecord_report.report \
    "python3 (>= 3.8)" "" \
    "psrecord 会话可视化报告生成器: 现代化交互式HTML分析报告/平滑缩放/时间轴联动/双主题/均值/P95/跨会话对比"

ls -la $OUT/*.deb
