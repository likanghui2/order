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
    exec celery -A task.9Gweb.search:CELERY_APP "${COMMON_ARGS[@]}" -Q "${PREFIX}-${TASK_TYPE}"
    ;;
  "shamBooking")
    exec celery -A task.9Gweb.sham_booking:CELERY_APP "${COMMON_ARGS[@]}" -Q "9GWEB-shamBooking"
    ;;
  "booking")
    exec celery -A task.9Gweb.booking:CELERY_APP "${COMMON_ARGS[@]}" -Q "9GWEB-booking"
    ;;
  "orderDetail")
    exec celery -A task.9Gweb.order_detail:CELERY_APP "${COMMON_ARGS[@]}" -Q "9GWEB-orderDetail"
    ;;
  *)
    echo "Unknown task: ${TASK_TYPE}"
    exit 1
    ;;
esac
