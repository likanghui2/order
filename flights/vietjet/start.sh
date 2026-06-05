#!/bin/bash

# 1. 提取相同的 Celery 启动参数
COMMON_ARGS="worker -P threads --concurrency=$CONCURRENCY --without-heartbeat --without-gossip --without-mingle --task-events"

# 2. 根据 SOURCE 判断 Celery app。
if [ "$SOURCE" == "AGENT" ]; then
  APP_PREFIX="VJagent"
  DEFAULT_QUEUE_PREFIXES="VJagent,VZagent"
elif [ "$SOURCE" == "VZWEB" ] || [ "$SOURCE" == "VZ" ]; then
  APP_PREFIX="VZweb"
  DEFAULT_QUEUE_PREFIXES="VZweb"
else
  APP_PREFIX="VJweb"
  DEFAULT_QUEUE_PREFIXES="VJweb"
fi

# 3. 队列前缀可通过 QUEUE_PREFIX/QUEUE_PREFIXES 覆盖。
QUEUE_PREFIXES="${QUEUE_PREFIXES:-${QUEUE_PREFIX:-$DEFAULT_QUEUE_PREFIXES}}"

build_queues() {
  local suffix="$1"
  local queues=""
  local prefix

  IFS=',' read -ra prefixes <<< "$QUEUE_PREFIXES"
  for prefix in "${prefixes[@]}"; do
    if [ -z "$queues" ]; then
      queues="${prefix}-${suffix}"
    else
      queues="${queues},${prefix}-${suffix}"
    fi
  done

  echo "$queues"
}

# 4. 根据 TASK_TYPE 执行对应的 Celery worker
case "$TASK_TYPE" in
  "search" | "verify")
    exec celery -A task.${APP_PREFIX}.search $COMMON_ARGS -Q "$(build_queues "$TASK_TYPE")"
    ;;
  "booking")
    exec celery -A task.${APP_PREFIX}.booking $COMMON_ARGS -Q "$(build_queues "booking")"
    ;;
  "orderDetail")
    exec celery -A task.${APP_PREFIX}.order_detail $COMMON_ARGS -Q "$(build_queues "orderDetail")"
    ;;
  "shamBooking")
    exec celery -A task.${APP_PREFIX}.sham_booking $COMMON_ARGS -Q "$(build_queues "shamBooking")"
    ;;
  *)
    echo "Unknown task: $TASK_TYPE"
    exit 1
    ;;
esac
