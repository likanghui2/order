# Local Sham Booking Runner

这是从 `/Users/a1234/Desktop/rakdFlightScript` 独立出来的本地押位项目。原项目不改动，这个目录只保留本地运行需要的 copied 业务代码。

当前版本取消 RabbitMQ/Celery 队列投递机制，改成：

- 图形化页面录入或通过表格文件导入押位任务。
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
LOCAL_SHAM_LOG_TO_FILE=1
VJ_WEB_SESSION_CACHE_ENABLED=1
VJ_WEB_SESSION_READY_SECONDS=120
VJ_WEB_SESSION_CACHE_TTL_SECONDS=300
VJ_WEB_SESSION_CACHE_MAX_SIZE=80
PYTHON_BIN=/Users/a1234/Desktop/rakdFlightLocalShamBooking/.venv/bin/python
RELOAD=1
RELOAD_DIRS=app,static,task
```

`LOCAL_SHAM_CONCURRENCY=0` 表示不限制本地并发；设置为 `3`、`5` 等正整数时，才会限制同时执行数量。
`RELOAD=1` 表示开启热更新，默认监听 `app`、`static` 和 `task`；如需关闭，用 `RELOAD=0 /bin/bash run-local-sham.sh`。
`LOCAL_SHAM_LOG_TO_FILE=1` 会把本地服务 stdout/stderr 追加写入 `logs/local-sham.log`，供 Grafana Loki 采集；如需关闭，用 `LOCAL_SHAM_LOG_TO_FILE=0`。

## VietJet Web Session 预热

VJWEB session 池独立于主押位链路。预热进程会提前调用 VietJet `get-session`，把 `sessionId`、`requestId`、`sessionExpIn` 和设备绑定参数写入 Redis；代理不写入缓存、不在进程间传输。主框架不自动消费缓存，需要时调用接口取 ready session。

```bash
.venv/bin/python tools/vj_session_cache_warmer.py
```

航线和数量直接改脚本顶部配置：

```python
SOURCE = "VJWEB"
ROUTES = []
TARGET_SIZE = 10
INTERVAL_SECONDS = 2
RUN_ONCE = False
```

`ROUTES = []` 时会从本地 SQLite 的任务里读取航线；想固定航线时再改成 `["SGN-CAN"]` 这种形式。

取 session 接口：

```text
GET /api/vj-web-session?depAirport=SGN&arrAirport=CAN
```

取不到 ready session 时接口直接返回 404，并带上当前池子的 `ready/warming/expired` 统计。

常用参数：

- `VJ_WEB_SESSION_READY_SECONDS=120`：session 预热多久后接口可取。
- `VJ_WEB_SESSION_CACHE_TTL_SECONDS=300`：航司未返回 `sessionExpIn` 时的兜底保留时间；正常优先使用 `sessionExpIn` 作为过期时间。
- `VJ_WEB_SESSION_CACHE_MAX_SIZE=80`：每条航线最多缓存多少个。
- `VJ_WEB_SESSION_CACHE_ENABLED=0`：关闭 session 池读写。

## 技术日志排查

技术排查独立使用 Grafana Loki，不和业务页面混在一起。先启动业务服务，让日志写入 `logs/local-sham.log`，再启动日志栈：

```bash
/bin/bash /Users/a1234/Desktop/rakdFlightLocalShamBooking/run-loki-logs.sh
```

启动前需要先打开 Docker Desktop。

默认地址：

```text
http://localhost:3000/d/sl-booking-logs
```

Grafana 已预置 Loki 数据源和 `SL Booking 技术日志` Dashboard。常用 LogQL：

```logql
{job="sl-booking"} | json
{job="sl-booking"} | json | level="ERROR"
{job="sl-booking"} | json | taskId="VJAPP-SGN-CAN-VJ3908-20260729-24704"
{job="sl-booking"} | json | executionTaskId="VJAPP-SGN-CAN-VJ3908-20260729-24704-RUN0001"
```

## SQLite 损坏处理

如果日志出现 `sqlite3.DatabaseError: database disk image is malformed`，先停止本地服务，再处理数据库文件。

```bash
python tools/sqlite_maintenance.py --db local_sham_booking.db --check
python tools/sqlite_maintenance.py --db local_sham_booking.db --recover
```

`--recover` 会先备份原库，再尽量把可读的 `tasks`、`attempts`、`pnr_records`、`source_proxy_configs` 迁到新库。如果恢复失败或不需要保留旧任务，可以备份后重建空库：

```bash
python tools/sqlite_maintenance.py --db local_sham_booking.db --rebuild-empty
```

## 页面使用

- 顶部填写 source、出发地、目的地、日期、航班号、舱位、查询延迟、预计延迟、人数、PNR有效期后点击“添加任务”。
- 人数默认 `1-1`；填写 `1-4` 会生成 1 个主任务和 4 个子任务，子任务分别携带 `1`、`2`、`3`、`4` 人的任务参数。
- 任务会立即写入 SQLite，到期后本机直接执行。
- “开始”会把任务设为立即执行；“停止”会暂停轮询；“复制”会把任务参数回填到上方表单；“删除”会清理任务和执行记录。
- 点击任务行后，底部 Log 区会显示成功/失败次数、数据库文件、最近返回和执行记录。
- “表格导入”支持上传 `.xlsx`、`.xlsm`、`.xls`、`.csv`、`.tsv`、`.txt` 文件，解析预览有效行后按行创建任务。
- Source 会自动读取 `task/*/sham_booking.py`，新增数据源时增加对应目录和 `sham_booking.py` 即可，例如 `task/XXweb/sham_booking.py` 会显示为 `XXWEB`。
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

当前 source 不再手工维护映射表，会按 `task` 目录动态发现支持押位的 source。
