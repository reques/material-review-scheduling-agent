#!/bin/sh
# 重新生成 examples/（调用 Python 脚本，输出为 CLI 真实运行结果）。
set -e
cd "$(dirname "$0")/.."
python3 scripts/generate_examples.py
