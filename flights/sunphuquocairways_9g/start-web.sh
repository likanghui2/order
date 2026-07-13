#!/bin/bash

set -e

: "${CONCURRENCY:=1}"

PREFIX="9GWEB"
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
    exec celery -A task.9Gweb.search "${COMMON_ARGS[@]}" -Q "${PREFIX}-${TASK_TYPE}"
    ;;
  "shamBooking")
    exec celery -A task.9Gweb.sham_booking "${COMMON_ARGS[@]}" -Q "9GWEB-shamBooking"
    ;;
  "booking")
    exec celery -A task.9Gweb.booking "${COMMON_ARGS[@]}" -Q "9GWEB-booking"
    ;;
  "orderDetail")
    exec celery -A task.9Gweb.order_detail "${COMMON_ARGS[@]}" -Q "9GWEB-orderDetail"
    ;;
  *)
    echo "Unknown task: ${TASK_TYPE}"
    exit 1
    ;;
esac
