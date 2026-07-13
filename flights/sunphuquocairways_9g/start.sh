#!/bin/bash

set -e

: "${CONCURRENCY:=1}"

PREFIX="9GAPP"
COMMON_ARGS=(
  worker
  -P threads
  --concurrency="${CONCURRENCY}"
  --without-heartbeat
  --without-gossip
  --without-mingle
  --task-events
)

case "$TASK_TYPE" in
  "search" | "verify")
    exec celery -A task.9Gapp.search "${COMMON_ARGS[@]}" -Q "${PREFIX}-${TASK_TYPE}"
    ;;
  "shamBooking")
    exec celery -A task.9Gapp.sham_booking "${COMMON_ARGS[@]}" -Q "${PREFIX}-shamBooking"
    ;;
  *)
    echo "Unknown task: ${TASK_TYPE}"
    exit 1
    ;;
esac
