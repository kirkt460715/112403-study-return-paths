#!/usr/bin/env python3
"""参与路径分析工具入口（无第三方依赖，Python 3.9+）。"""

import sys

from pathway_tool.cli import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
