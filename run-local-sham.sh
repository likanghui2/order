#!/bin/bash
set -e

cd "$(dirname "$0")"
export PYTHONPATH="${PYTHONPATH:-$(pwd)}"

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8018}"
PYTHON_BIN="${PYTHON_BIN:-$(pwd)/.venv/bin/python}"
RELOAD="${RELOAD:-1}"
RELOAD_DIRS="${RELOAD_DIRS:-app,static,task}"

if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3 || command -v python)"
fi

if ! "$PYTHON_BIN" -m uvicorn --version >/dev/null 2>&1; then
  echo "缺少本地服务依赖，请先执行："
  echo "  cd $(pwd)"
  echo "  $PYTHON_BIN -m pip install -r requirements-local.txt"
  exit 1
fi

UVICORN_ARGS=(app.api:app --host "$HOST" --port "$PORT")

if [ "$RELOAD" != "0" ] && [ "$RELOAD" != "false" ] && [ "$RELOAD" != "FALSE" ]; then
  UVICORN_ARGS+=(--reload)
  IFS=',' read -ra RELOAD_DIR_LIST <<< "$RELOAD_DIRS"
  for reload_dir in "${RELOAD_DIR_LIST[@]}"; do
    reload_dir="$(echo "$reload_dir" | xargs)"
    if [ -n "$reload_dir" ]; then
      UVICORN_ARGS+=(--reload-dir "$reload_dir")
    fi
  done
fi

exec "$PYTHON_BIN" -m uvicorn "${UVICORN_ARGS[@]}" "$@"
