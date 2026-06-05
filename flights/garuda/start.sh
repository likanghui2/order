#!/bin/bash


if [ "$TASK_TYPE" == "search" ] || [ "$TASK_TYPE" == "verify" ]; then
    exec celery -A task.GAweb.search worker -Q GAweb-$TASK_TYPE --concurrency=$CONCURRENCY -P threads --without-heartbeat --without-gossip --without-mingle --task-events
elif [ "$TASK_TYPE" == "shamBooking" ]; then
    exec celery -A task.GAweb.sham_booking worker -Q GAweb-shamBooking -P threads --concurrency=$CONCURRENCY --without-heartbeat --without-gossip --without-mingle --task-events
elif [ "$TASK_TYPE" == "orderDetail" ]; then
    exec celery -A task.GAweb.order_detail worker -Q GAweb-orderDetail -P threads --concurrency=$CONCURRENCY --without-heartbeat --without-gossip --without-mingle --task-events
else
    echo "Unknown task: $TASK_TYPE"
    exit 1
fi
