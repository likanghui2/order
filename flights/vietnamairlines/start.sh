#!/bin/bash

COMMON_ARGS="worker -P threads --concurrency=$CONCURRENCY --without-heartbeat --without-gossip --without-mingle --task-events"

case "$TASK_TYPE" in
  "search" | "verify")
    exec celery -A task.VNweb.search $COMMON_ARGS -Q "VNweb-${TASK_TYPE}"
    ;;
  "shamBooking")
    exec celery -A task.VNweb.sham_booking $COMMON_ARGS -Q "VNweb-shamBooking"
    ;;
  *)
    echo "Unknown task: $TASK_TYPE"
    exit 1
    ;;
esac
