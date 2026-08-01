# 当前项目公共核心提示词

你正在维护 `rakdFlightLocalShamBooking`，这是从 `/Users/a1234/Desktop/rakdFlightScript` 独立出来的本地押位运行项目。目标不是重建主仓，也不是改造完整机票系统，而是在尽量不破坏现有本地工作台和 copied 业务链路的前提下，完成最小有效修改。

这个项目的核心形态是：

- 本地 FastAPI + 静态页面工作台。
- 任务保存到本地 SQLite：`local_sham_booking.db`。
- 本地 runner 扫描到期任务，直接调用 `task.<source>.sham_booking.main(payload)`。
- Source 通过 `task/*/sham_booking.py` 动态发现，不再手工维护映射表。
- 押位执行结果、attempt 记录、PNR 摘要和 source 代理配置都写回 SQLite。
- `flights/*`、`common/*`、`task/*` 中有大量从主仓 copy 出来的业务代码，修改时要优先保持兼容。

## 常驻原则

始终按下面顺序做决策：

1. 与当前项目本地运行目标一致。
2. 与当前项目已有 API、SQLite、runner、前端页面交互一致。
3. 与当前 source 的 `task/<source>/sham_booking.py` 既有实现一致。
4. 与 copied 主仓业务代码风格一致。
5. 最后才考虑自己的默认写法。

不要为了“更通用”或“更优雅”扩大改动面。这个仓库的价值在于本地可控、快速录入、可追踪执行结果，而不是抽象成一套新的通用任务平台。

## 项目边界

当前项目不是原始主仓。默认不要改 `/Users/a1234/Desktop/rakdFlightScript` 或其他仓库，除非用户明确要求。

当前项目也不是生产队列系统。它已经取消 RabbitMQ/Celery 队列投递机制，运行方式是本地线程或线程池直接执行 sham booking task。保留 Celery 相关装饰器和 copied 结构通常是为了兼容旧 task 入口，不要因为本地运行而贸然删除。

## 默认工作流

开始修改前，先把范围收敛下来：

- 看仓库状态：`git status --short`
- 看项目说明：`README.md`、`PRODUCT.md`
- 涉及 API 或任务格式：读 `app/api.py`
- 涉及调度、并发、执行结果：读 `app/runner.py`、`app/store.py`
- 涉及 source 展示或动态发现：读 `app/source_registry.py`
- 涉及代理：读 `app/proxy_context.py` 和 `source_proxy_configs` 相关代码
- 涉及页面交互：读 `static/index.html`、`static/app.js`、`static/styles.css`
- 涉及具体航司押位：读对应 `task/<source>/sham_booking.py`，必要时再看同 source 的 `search.py`、`booking.py` 和 `flights/<airline>/*`

如果用户说“当前项目”，默认指 `/Users/a1234/Desktop/rakdFlightLocalShamBooking`。

## 重点目录

- `app/api.py`：FastAPI 路由、任务创建/导入、PNR 查询、source 代理配置、表格导入解析。
- `app/runner.py`：本地执行器、并发控制、source task 加载、线程级代理切换、结果解析。
- `app/store.py`：SQLite 表结构、任务状态、attempt、PNR 记录、父子任务、source 代理持久化。
- `app/source_registry.py`：扫描 `task/*/sham_booking.py` 并生成 source 列表。
- `static/*`：本地工作台 UI。
- `task/*/sham_booking.py`：各 source 押位入口，runner 会调用 `main(payload)`。
- `flights/*`：航司业务 service/script/config，主要来自主仓 copy。
- `common/*`：模型、装饰器、枚举、TLS、工具类，主要来自主仓 copy。
- `tools/sqlite_maintenance.py`：SQLite 检查、恢复、重建。
- `run-local-sham.sh`：本地启动脚本。

## 修改边界

能在 `app/*`、`static/*`、目标 `task/<source>/*` 或 `tools/*` 内解决的问题，不要先改 `common/*` 或 `flights/*`。

只有在以下情况才考虑改 copied 公共层：

- 当前 source 的押位链路无法正确运行。
- 错误明确来自 copied 模型、工具、decorator 或 service。
- 不改公共层会导致本地 runner/API 无法兼容现有 task。
- 用户明确要求同步修某个航司底层链路。

如果只是页面展示、任务入库、任务调度、PNR 提取、表格导入、source 列表、代理配置或 SQLite 维护，不要顺手改航司业务代码。

## 本地任务协议

本地任务推荐使用完整外层协议：

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

保持字段命名兼容现有模型：

- API 入参常见 camelCase：`taskId`、`taskType`、`taskData`、`intervalSeconds`、`maxRuns`、`firstRunAt`、`passengerRange`。
- SQLite 内部常见 snake_case：`task_id`、`task_type`、`task_data`、`interval_seconds`。
- `source` 统一走 `normalize_source()`，展示和入库默认大写。
- 新增 source 时优先增加 `task/<source>/sham_booking.py`，让 `source_registry.py` 动态发现。

不要新增一份静态 source 映射表，除非用户明确要求。

## 任务与 runner 规范

`LocalRunner` 的核心契约是：

1. 从 `TaskStore.acquire_due_tasks()` 获取到期且非父任务的 ACTIVE 任务。
2. 拼出 payload：`taskId/source/taskType/taskData`。
3. 通过 `module_for_source(source)` import `task.<source>.sham_booking`。
4. 调用模块里的 `main(payload)`。
5. 把返回值解析成 dict，并写入 attempts、tasks、pnr_records。

修改 runner 时要特别注意：

- `LOCAL_SHAM_CONCURRENCY=0` 表示不限制并发。
- 有限并发走 `ThreadPoolExecutor`，无限并发走 daemon thread。
- 每次启动会 `reset_stale_in_flight(older_than_seconds=0)`，避免上次异常退出遗留 in-flight。
- `_task_cache` 会缓存 source 对应的 `main`。
- source 代理通过线程本地 provider 注入 `GlobalVariable.PROXY_INFO_DATA`，不要用全局变量硬切造成线程串代理。
- 不要让父任务被实际执行；父任务只用于分组展示和级联控制。

## SQLite 与状态规范

SQLite 是本地工作台的事实状态源。涉及表结构时优先做向后兼容迁移：

- 新字段通过 `_ensure_*_columns()` 增量添加。
- 不要轻易删除或重建用户现有库。
- 不要修改 `local_sham_booking.db` 的真实数据来“测试”，除非用户明确允许。
- 修改查询时注意 `limit/offset`、排序、父子任务展开和已有字段兼容。

任务状态只使用现有语义：

- `ACTIVE`：会被 runner 扫描执行。
- `PAUSED`：暂停执行。
- `STOPPED`：停止，不再调度。
- `in_flight`：表示已被 runner 领取，执行完成后必须回落为 false。

父子任务规则：

- `passengerRange` 如 `1-4` 会创建一个父任务和多个子任务。
- 父任务 `is_parent=True`，`next_run_at=None`，不直接执行。
- 子任务会把人数写入 `taskData.ext.passengerCount`。
- pause/resume/stop/run-now/delete 都要级联到子任务。

## PNR 记录规范

PNR 摘要由 `TaskStore.finish_attempt()` 从成功结果中提取，并写入 `pnr_records`。

保留这些兼容点：

- 只有 `status == 200` 才提取 PNR。
- PNR 优先从 `data.pnr` 取，其次从顶层 `pnr` 取。
- 舱位、币种、乘机人、人数、有效期都要容忍缺失。
- 有效期优先看 `taskData.ext.pnrValidMinutes`、`pnrValidityMinutes`、`pnrValidMinute`。
- `rawResult` 保存原始结果，方便页面追溯。

如果新增某个航司结果结构的适配，尽量只扩展提取候选字段，不要破坏已有通用提取。

## 表格导入规范

表格导入由 `app/api.py` 解析，支持 `.xlsx`、`.xlsm`、`.xls`、`.csv`、`.tsv`、`.txt`。

修改时注意：

- 单次预览限制 `MAX_TABLE_IMPORT_ROWS = 1001`。
- 单行列数限制 `MAX_TABLE_IMPORT_COLUMNS = 50`。
- Excel 依赖是 `openpyxl` 和 `xlrd`，新增依赖要同步三个 requirements 文件。
- 文本编码依次尝试 `utf-8-sig`、`gb18030`、`big5`、`latin-1`。
- 日期要兼容 `YYYY-MM-DD` 和 `YYYYMMDD` 这类现有输入。
- 页面预览和最终创建任务的字段语义必须保持一致。

## 前端修改规范

这个页面是给运营人员高频使用的本地命令台，不是营销页。

改 UI 时遵守 `PRODUCT.md`：

- 保持任务、PNR、日志、筛选、动作紧密可见。
- 优先密集但清晰的信息布局。
- 控件状态要稳定，表格列宽和按钮不要因内容变化乱跳。
- 状态、错误、风险操作要明确可扫。
- 目标 WCAG AA 对比度，支持键盘操作和低动态偏好。

不要增加 landing page、hero、装饰性大卡片或会遮挡高频操作的动效。

## Source 押位链路规范

修改 `task/<source>/sham_booking.py` 时，优先沿用该 source 现有风格。

常见要求：

- 入口保持 `main(payload)` 可被本地 runner 调用。
- 继续兼容 `@task_decorator(LOG)` 和 copied 主仓模型。
- `taskType` 默认是 `shamBooking`。
- 查询、验舱、押位、PNR 生成/回填的顺序要一眼可见。
- `ext.passengerCount` 是本地父子任务拆分后的乘机人数来源之一。
- `bookingConfig.currencyCode` 是币种来源。
- `depDate` 在不同 source 中可能是 `YYYYMMDD` 或转成 `YYYY-MM-DD` 后传 service，按当前 source 保持一致。

不要为了本地测试把真实押位核心步骤全部 mock 掉，除非用户明确要做 dry-run 或演示模式。

## 代理规范

source 代理配置保存在 SQLite 的 `source_proxy_configs`。

修改代理相关逻辑时：

- API 负责校验和规范化 host、port、username、password、region、sessionTime、format。
- runner 执行前通过 `_source_proxy(source)` 设置线程当前代理。
- 未启用或未配置时使用默认代理副本。
- 启用但缺 host/port 时应明确报错。
- 支持完整代理 URL、`host:port` 和分字段配置。
- 不要用单个全局代理对象在多个线程间来回改字段。

## 依赖与启动

安装依赖：

```bash
cd /Users/a1234/Desktop/rakdFlightLocalShamBooking
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-local.txt
```

启动本地页面：

```bash
/bin/bash /Users/a1234/Desktop/rakdFlightLocalShamBooking/run-local-sham.sh
```

默认地址：

```text
http://0.0.0.0:8018
```

新增 Python 依赖时同步更新：

- `requirements-local.txt`
- `requirements.txt`
- `requirements-py313.txt`

## 高风险动作

押位、生单、下单、扣款、出票、真实支付、生产代理配置都属于高风险动作。

在用户没有明确要求真实运行前：

- 只做静态代码修改、局部函数验证、API 结构验证或页面验证。
- 不主动执行会访问真实航司并生成 PNR 的任务。
- 不主动调用真实支付、扣款或出票接口。
- 不主动清空、重建或批量改写现有 SQLite 数据。

如果必须跑真实 source task，要在输出里明确说明跑了什么、是否可能生成 PNR、有没有支付/扣款/出票。

## 验证要求

每次修改后，按风险选择最小但有效的验证：

- 文档修改：检查 Markdown 内容是否已落到目标文件。
- Python 修改：至少跑 `python -m py_compile ...` 覆盖改动文件。
- API/runner/store 修改：优先补一个小范围函数级验证，或用 TestClient/临时 SQLite 验证本次行为。
- 表格导入修改：用最小样例验证对应格式解析。
- 前端修改：启动本地服务后用浏览器或接口检查页面可用，必要时截图确认。
- SQLite 维护工具修改：用临时数据库验证，不要直接拿真实 `local_sham_booking.db` 做破坏性测试。

不能跑真实链路时，明确说明没有跑真实押位链路。

## 输出要求

完成修改后，优先按下面顺序输出结论：

1. 改了什么。
2. 改在哪些文件。
3. 做了什么验证。
4. 哪些真实链路没有跑。
5. 如果有风险或后续注意点，单独说明。

先讲结论，再讲依据。涉及押位、支付、扣款、出票时，必须明确说明是否实际执行。
