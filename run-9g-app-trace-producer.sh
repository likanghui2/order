#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
exec .venv/bin/python tools/nine_g_app_trace_token_producer.py "$@"
