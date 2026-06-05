#!/bin/bash

if [ "$TASK_TYPE" == "search" ] || [ "$TASK_TYPE" == "verify" ]; then
    exec celery -A task.SLweb.search worker -Q SLweb-$TASK_TYPE --concurrency=$CONCURRENCY -P threads --without-heartbeat --without-gossip --without-mingle --task-events
elif [ "$TASK_TYPE" == "KeyStore" ]; then
    exec celery -A flights.hkexpress.flynasKeyStoreTask.main worker -Q flynas$TASK_TYPE -P $TASK_EXECUTE_TYPE --concurrency=$CONCURRENCY -E
elif [ "$TASK_TYPE" == "booking" ]; then
    exec celery -A task.SLweb.booking worker -Q SLweb-booking -P threads --concurrency=$CONCURRENCY -E
elif [ "$TASK_TYPE" == "orderDetail" ]; then
    exec celery -A task.SLweb.order_detail worker -Q SLweb-orderDetail -P threads --concurrency=$CONCURRENCY -E
  elif [ "$TASK_TYPE" == "shamBooking" ]; then
    exec celery -A task.SLweb.sham_booking worker -Q SLweb-shamBooking -P threads --concurrency=$CONCURRENCY --without-heartbeat --without-gossip --without-mingle --task-events

else
    echo "Unknown task: $TASK_TYPE"
    exit 1
fi
