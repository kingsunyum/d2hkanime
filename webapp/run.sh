#!/usr/bin/env bash
# 启动动画下载前端（WSL 内）
# 用法: ./run.sh          默认 0.0.0.0:8770
#       PORT=9000 ./run.sh
cd "$(dirname "$0")" || exit 1
export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-8770}"
echo "动画下载前端 → http://localhost:${PORT}"
exec python3 app.py
