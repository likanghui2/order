#!/bin/bash
set -e

cd "$(dirname "$0")"
export PYTHONPATH="${PYTHONPATH:-$(pwd)}"

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8018}"
PYTHON_BIN="${PYTHON_BIN:-$(pwd)/.venv/bin/python}"

if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3 || command -v python)"
fi

if ! "$PYTHON_BIN" -m uvicorn --version >/dev/null 2>&1; then
  echo "缺少本地服务依赖，请先执行："
  echo "  cd $(pwd)"
  echo "  $PYTHON_BIN -m pip install -r requirements-local.txt"
  exit 1
fi

exec "$PYTHON_BIN" -m uvicorn app.api:app --host "$HOST" --port "$PORT" "$@"
