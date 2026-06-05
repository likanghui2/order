#!/bin/bash
set -e

if [ "$SOURCE" = "WEB" ]; then
    if [ "$TASK_TYPE" = "search" ] || [ "$TASK_TYPE" = "verify" ]; then
        exec celery -A task.ODweb.search worker \
            -Q ODweb-$TASK_TYPE \
            --concurrency="$CONCURRENCY" \
            -P threads \
            --without-heartbeat --without-gossip --without-mingle \
            --task-events

    elif [ "$TASK_TYPE" = "booking" ]; then
        exec celery -A task.ODweb.booking worker \
            -Q ODweb-booking \
            --concurrency="$CONCURRENCY" \
            -P threads \
            --without-heartbeat --without-gossip --without-mingle \
            --task-events

    elif [ "$TASK_TYPE" = "orderDetail" ]; then
        exec celery -A task.ODweb.order_detail worker \
            -Q ODweb-orderDetail \
            --concurrency="$CONCURRENCY" \
            -P threads \
            --without-heartbeat --without-gossip --without-mingle \
            --task-events

    elif [ "$TASK_TYPE" = "shamBooking" ]; then
        exec celery -A task.ODweb.sham_booking worker \
            -Q ODweb-shamBooking \
            --concurrency="$CONCURRENCY" \
            -P threads \
            --without-heartbeat --without-gossip --without-mingle \
            --task-events

    else
        echo "Unknown task type: $TASK_TYPE"
        exit 1
    fi
else
    if [ "$TASK_TYPE" = "search" ] || [ "$TASK_TYPE" = "verify" ]; then
        exec celery -A task.ODapi.search worker \
            -Q ODapi-$TASK_TYPE \
            --concurrency="$CONCURRENCY" \
            -P threads \
            --without-heartbeat --without-gossip --without-mingle \
            --task-events

    elif [ "$TASK_TYPE" = "booking" ]; then
        exec celery -A task.ODapi.booking worker \
            -Q ODapi-booking \
            --concurrency="$CONCURRENCY" \
            -P threads \
            --without-heartbeat --without-gossip --without-mingle \
            --task-events
  elif [ "$TASK_TYPE" = "cancel_order" ]; then
        exec celery -A task.ODapi.cancel_order worker \
            -Q ODapi-cancelOrder \
            --concurrency="$CONCURRENCY" \
            -P threads \
            --without-heartbeat --without-gossip --without-mingle \
            --task-events
    else
        echo "Unknown task type: $TASK_TYPE"
        exit 1
    fi
fi