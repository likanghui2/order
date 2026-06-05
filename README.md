# Local Sham Booking Runner

这是从 `/Users/a1234/Desktop/rakdFlightScript` 独立出来的本地押位项目。原项目不改动，这个目录只保留本地运行需要的 copied 业务代码。

当前版本取消 RabbitMQ/Celery 队列投递机制，改成：

- 图形化页面录入或导入押位任务。
- 任务保存到本地 SQLite：`local_sham_booking.db`。
- 本地线程池扫描到期任务，直接调用 `task.<source>.sham_booking.main(payload)`。
- 执行结果、日志摘要和最近返回写回 SQLite，页面自动刷新查看。

## 安装依赖

```bash
cd /Users/a1234/Desktop/rakdFlightLocalShamBooking
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-local.txt
```

新增 Python 依赖时，同步更新：

- `requirements-local.txt`
- `requirements.txt`
- `requirements-py313.txt`

## 启动页面

```bash
/bin/bash /Users/a1234/Desktop/rakdFlightLocalShamBooking/run-local-sham.sh
```

默认地址：

```text
http://0.0.0.0:8018
```

可用环境变量：

```bash
HOST=0.0.0.0
PORT=8018
LOCAL_SHAM_DB=/Users/a1234/Desktop/rakdFlightLocalShamBooking/local_sham_booking.db
LOCAL_SHAM_CONCURRENCY=0
LOCAL_SHAM_POLL_INTERVAL=0.5
PYTHON_BIN=/Users/a1234/Desktop/rakdFlightLocalShamBooking/.venv/bin/python
```

`LOCAL_SHAM_CONCURRENCY=0` 表示不限制本地并发；设置为 `3`、`5` 等正整数时，才会限制同时执行数量。

## 页面使用

- 顶部填写 source、出发地、目的地、日期、航班号、舱位、查询延迟、预计延迟、人数、PNR有效期后点击“添加任务”。
- 人数默认 `1-1`；填写 `1-4` 会生成 1 个主任务和 4 个子任务，子任务分别携带 `1`、`2`、`3`、`4` 人的任务参数。
- 任务会立即写入 SQLite，到期后本机直接执行。
- “开始”会把任务设为立即执行；“停止”会暂停轮询；“复制”会把任务参数回填到上方表单；“删除”会清理任务和执行记录。
- 点击任务行后，底部 Log 区会显示成功/失败次数、数据库文件、最近返回和执行记录。
- “高级配置 / JSON 导入”可以生成单任务 JSON 或批量导入任务。
- “配置管理 / 数据源代理”可以为每个 source 配置独立代理；未启用或未配置时使用环境变量里的默认代理。

## 任务格式

JSON 可以是数组、`{"tasks": [...]}`，或 `{taskId: payload}`。

每个任务推荐使用完整外层协议：

```json
{
  "taskId": "local-5j-ceb-hkg-5j236",
  "source": "5JWEB",
  "taskType": "shamBooking",
  "intervalSeconds": 10,
  "passengerRange": "1-1",
  "taskData": {
    "depAirport": "CEB",
    "arrAirport": "HKG",
    "depDate": "20260529",
    "flightNumber": "5J236",
    "cabin": "",
    "bookingConfig": {
      "bookRate": 10,
      "currencyCode": "PHP"
    },
    "ext": {
      "pnrValidMinutes": 30
    },
    "callbackData": {
      "callData": "",
      "callUrl": ""
    }
  }
}
```

当前内置 source 映射：`5JWEB`、`7CWEB`、`GAWEB`、`KRWEB`、`ODWEB`、`SLWEB`、`TGWEB`、`UOAPP`、`VJWEB`、`VNWEB`、`VZWEB`。
