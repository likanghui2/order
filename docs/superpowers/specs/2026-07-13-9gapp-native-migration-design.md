# 9G App 当前框架原生迁移设计

## 背景与目标

旧框架的 9G App 押位入口位于
`/Users/a1234/Desktop/kySpiderNew/branches/dev/task/flight_9Gapp/press_cabin/main.py`。
旧入口依赖旧版内部模型、HTTP 工具、错误枚举和库存聚合响应，并在单次任务中最多循环创建五个 PNR。

本次迁移把 9G App 的搜索和押位完整接入当前项目，并只使用当前项目的任务协议、Pydantic 模型、TLS 客户端、代理解析、错误体系和目录约定。迁移后的押位任务每次只创建一个 PNR，一次最多占五个座位。

## 范围

本次包含：

- 9G App 搜索和验价任务入口。
- 9G App 押位任务入口。
- 9G App HTTP Script、业务 Service、航班解析器和配置。
- `9GAPP` Celery Worker 的 Dockerfile 和启动脚本。
- 搜索解析、币种配置、请求构造、舱位筛选和押位编排的单元测试。

本次不包含：

- 旧 Web 流程。
- 未被 App 搜索或押位调用的旧订单详情解析器。
- Redis 库存聚合和旧 `press_cabin` 响应模型。
- 单次任务循环创建多个 PNR。
- 对当前公共任务模型的扩展。

## 代码结构

新增以下模块：

- `flights/sunphuquocairways_9g/config.py`：API 地址、User-Agent、签名凭据、Incapsula 参数、币种上下文、产品名称和建单等待时间。
- `flights/sunphuquocairways_9g/flight_common/app_flight_parser.py`：把 9G 搜索响应转换为当前航班模型。
- `flights/sunphuquocairways_9g/script/app_script.py`：负责 HMAC 签名、TLS 请求、Incapsula token、搜索、创建订单和 Hold 请求。
- `flights/sunphuquocairways_9g/service/app_service.py`：负责币种校验、乘客和联系人转换、响应解析以及建单业务编排。
- `task/9Gapp/search.py`：接入当前 `search` 和 `verify` 任务协议。
- `task/9Gapp/sham_booking.py`：接入当前 `shamBooking` 任务协议并创建单个 PNR。
- `flights/sunphuquocairways_9g/Dockerfile` 和 `start.sh`：启动 `9GAPP` 对应队列。

公共代码只在现有接口不足以表达 9G 行为时修改；本设计不需要新增公共模型。

## 模型映射

9G 响应映射到当前模型时遵循以下规则：

- 每个 `list_trip` 转换为一个 `FlightJourneyModel`。
- 每个 `list_itinerary` 转换为一个 `FlightSegmentModel`，支持直飞和多航段行程。
- `trip_id` 写入 `FlightBundleModel.fare_key`，供创建订单使用。
- `journey_key` 使用稳定的行程标识；优先使用接口行程 ID，无行程 ID 时由航段标识组成。
- `fare_family_code` 等 9G 专有数据写入 `FlightBundleModel.ext`。
- 舱位、产品名、余座、成人和儿童票价转换到当前 `FlightBundleModel`、`FlightBundlePriceModel` 和 `FlightSsrInfoModel`。
- 不确定余座时沿用旧接口语义，返回默认上限 9；明确售罄的套餐不返回。
- 9G 航班号统一规范为带 `9G` 前缀的四位数字形式。

## 搜索流程

1. 从任务的 `ext.proxy` 构建 `ProxyInfoModel`。
2. 初始化 `CurlCffiTls` 会话。
3. 根据币种选择 Office ID 和语言；不支持的币种返回明确的当前框架业务错误。
4. 把当前任务的出发地、目的地、出发日期、返程日期、成人、儿童和优惠码转换成 9G 请求。
5. 对请求体进行紧凑 JSON 序列化，并按 9G 规则生成 HMAC 请求头。
6. 解析返回数据并交给当前 `task_decorator` 完成统一响应和回调。

搜索支持当前协议的单程和往返请求。押位任务沿用当前 `RequestShamBookingTaskDataModel`，因此只处理单程订单。

## 押位流程

1. 初始化独立的 9G App Service 会话。
2. 用一名成人实时搜索目标日期和航线。
3. 使用 `FlightUtil.number_filter` 精确匹配任务航班号；结果不是唯一航班时返回 `NO_AVAILABLE_FLIGHT_NUMBER`。
4. 按任务 `cabin` 精确匹配舱位；当 `ext.productTag` 存在时同时匹配产品品牌。
5. 最终占位人数为可用座位数和 5 的较小值；没有余座时返回 `NO_AVAILABLE_CABIN`。
6. 按最终人数重新实时搜索，并重新匹配同一航班、舱位和品牌，防止使用过期报价。
7. 生成当前框架的虚拟成人乘客和联系人。
8. 使用重新搜索得到的 `fare_key` 创建订单。创建前获取新的 Incapsula `x-d-token`；旧流程中的固定等待时间迁入配置并默认保持 30 秒。
9. 从创建订单响应取得 `booking_id`，调用 Hold 接口取得 PNR。
10. 填充一个 `ResponseOrderInfoModel`，包括订单号、PNR、`HOLD` 状态、乘客、联系人、唯一行程和套餐、币种及所有乘客总价。

任务不会重试创建第二个 PNR，也不会返回旧库存列表。

## 错误处理与重试

- 非 200 HTTP 响应转换为当前 `HTTP_RESPONSE_STATE_NOT_SATISFY` 或语义更明确的业务错误。
- 空 JSON、缺少 `booking_id`、缺少 PNR 和缺少币种等情况转换为 `DATA_VALIDATION_FAILED`。
- 官网明确返回无航班时转换为 `NO_FLIGHT_DATA`。
- 售罄、舱位或产品不匹配时分别使用当前 `NO_AVAILABLE_CABIN` 或 `NO_AVAILABLE_BUNDLE`。
- TLS 超时和 Curl 异常沿用 `CurlCffiTls` 的错误映射。
- 只对搜索阶段的可恢复 HTTP 错误重建会话并有限重试；创建订单和 Hold 不做不安全的自动重试，以避免重复 PNR。
- Incapsula 求解失败直接终止当前建单，避免在 token 状态未知时提交订单。

## 测试策略

测试全部使用模拟响应，不访问 9G 官网或验证码服务：

- 币种上下文：支持币种映射和不支持币种错误。
- HMAC：固定时间和 nonce 后验证签名字符串及请求头。
- 搜索请求：单程、往返、人数和优惠码序列化。
- 航班解析：直飞、多航段、售罄过滤、余座、票价、舱位、产品名和建单键。
- 舱位选择：指定舱位、指定产品、无匹配套餐和无余座。
- 押位成功：验证先查一人、再查最终人数、只调用一次创建订单和一次 Hold，并正确计算总价。
- 押位失败：航班不唯一、二次搜索余座不足、缺少 `booking_id`、缺少 PNR。
- 任务注册：`source_registry` 能发现 `9GAPP` 的搜索与押位模块。

完成后运行相关 Pytest、模块导入检查和当前仓库已有的适用测试。实时官网联调依赖有效代理和 Incapsula 服务，不作为离线测试通过的前提。

## 验收标准

- `source=9GAPP` 的 `search`、`verify` 和 `shamBooking` 能被当前任务注册逻辑发现。
- 搜索输出完全符合当前 `ResponseSearchInfoModel` 使用的航班模型。
- 押位任务最多占五个座位且只创建一个 PNR。
- 押位成功响应符合当前 `ResponseOrderInfoModel`，订单状态为 `HOLD`。
- 迁移代码不导入旧项目的 `common.models`、`CurlHttpUtil`、旧任务模型或库存工具。
- 离线单元测试通过，且不覆盖当前工作区中与本任务无关的用户修改。
