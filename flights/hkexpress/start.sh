#!/bin/bash


if [ "$TASK_TYPE" == "search" ] || [ "$TASK_TYPE" == "verify" ]; then
    exec celery -A task.UOapp.search worker -Q UOapp-$TASK_TYPE --concurrency=$CONCURRENCY -P threads --without-heartbeat --without-gossip --without-mingle --task-events
elif [ "$TASK_TYPE" == "KeyStore" ]; then
    exec celery -A flights.hkexpress.flynasKeyStoreTask.main worker -Q flynas$TASK_TYPE -P $TASK_EXECUTE_TYPE --concurrency=$CONCURRENCY --without-heartbeat --without-gossip --without-mingle --task-events
elif [ "$TASK_TYPE" == "booking" ]; then
    exec celery -A task.UOapp.booking worker -Q UOapp-booking -P threads --concurrency=$CONCURRENCY --without-heartbeat --without-gossip --without-mingle --task-events
elif [ "$TASK_TYPE" == "orderDetail" ]; then
    exec celery -A task.UOapp.order_detail worker -Q UOapp-orderDetail -P threads --concurrency=$CONCURRENCY --without-heartbeat --without-gossip --without-mingle --task-events
elif [ "$TASK_TYPE" == "shamBooking" ]; then
    exec celery -A task.UOapp.sham_booking worker -Q UOapp-shamBooking -P threads --concurrency=$CONCURRENCY --without-heartbeat --without-gossip --without-mingle --task-events
else
    echo "Unknown task: $TASK_TYPE"
    exit 1
fi
