#!/bin/bash

# 信号处理函数
function handle_signal {
    echo "Received signal, stopping..."
    # 在此处添加任何清理工作
    exit 0
}

# 捕获 SIGTERM 和 SIGINT 信号
trap handle_signal SIGTERM SIGINT

if [ "$TASK_TYPE" == "search" ] || [ "$TASK_TYPE" == "verify" ]; then
    exec celery -A task.NKapp.search worker -Q NKapp-$TASK_TYPE --concurrency=$CONCURRENCY -P threads --without-heartbeat --without-gossip --without-mingle --task-events
elif [ "$TASK_TYPE" == "KeyStore" ]; then
    exec celery -A flights.hkexpress.flynasKeyStoreTask.main worker -Q flynas$TASK_TYPE -P $TASK_EXECUTE_TYPE --concurrency=$CONCURRENCY -E
elif [ "$TASK_TYPE" == "booking" ]; then
    exec celery -A task.NKapp.booking worker -Q NKapp-booking -P threads --concurrency=$CONCURRENCY -E
elif [ "$TASK_TYPE" == "orderDetail" ]; then
    exec celery -A task.NKapp.order_detail worker -Q NKapp-orderDetail -P threads --concurrency=$CONCURRENCY -E
else
    echo "Unknown task: $TASK_TYPE"
    exit 1
fi
