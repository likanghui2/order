# 9G Web 当前框架原生迁移设计

## 背景与目标

旧项目的 `flight_9Gweb` 包含搜索、循环押位、正式预订、独立支付、订单详情和库存验位，依赖旧任务模型、旧内部航班模型、`CurlHttpUtil`、旧错误体系和库存 Redis 聚合。

本次把 9G Web 原生接入当前项目，使用当前任务协议、Pydantic 模型、`CurlCffiTls`、代理解析和错误类型。对外提供 `9GWEB` 的 `search`、`verify`、`shamBooking`、`booking` 和 `orderDetail`。当前框架没有独立支付任务，因此支付作为 `booking` 的可选阶段执行。

## 范围

本次包含：

- Web 搜索和验价。
- 每次仅生成一个 PNR、最多五名成人的 Web 押位。
- 正式预订、可选行李和可选信用卡支付。
- 订单详情和电子票状态解析。
- Web 专用 Parser、Script、Service、Celery 入口、Worker 镜像和测试。
- 每个任务入口的本地 `if __name__ == "__main__":` 请求示例。

本次不包含：

- 独立 `pay` 任务协议。
- 旧库存聚合响应和库存验位协议。
- 单任务循环创建多个 PNR。
- App/Web 会话或 OAuth token 共享。
- 对当前公共任务模型和 `TaskTypeEnum` 的扩展。

## 架构

Web 与 App 共用 `flights/sunphuquocairways_9g` 航司包和稳定产品配置，但拥有独立的 Parser、Script 和 Service：

- `config.py`：增加 Web API、OAuth、币种国家码、Incapsula、hCaptcha 和支付常量。
- `flight_common/web_flight_parser.py`：Web 搜索响应转换为当前航班模型。
- `flight_common/web_order_parser.py`：Web itinerary、baggage 和订单状态转换为当前订单模型。
- `script/web_script.py`：TLS、OAuth、验证码、搜索、购物车、旅客、联系人、建单、行李、支付和查单 HTTP 请求。
- `service/web_service.py`：业务数据转换、单 PNR 建单、行李、支付和订单详情编排。
- `task/9Gweb/search.py`：当前 `search/verify` 任务入口。
- `task/9Gweb/sham_booking.py`：当前单 PNR `shamBooking` 入口。
- `task/9Gweb/booking.py`：当前 `booking` 入口，包含可选支付。
- `task/9Gweb/order_detail.py`：当前 `orderDetail` 入口。
- `Dockerfile` 和 `start.sh`：启动上述四类模块对应的五种队列。

App 现有代码和接口保持不变。

## 配置与认证

Web 支持 `VND`、`USD`、`KRW`、`TWD`、`HKD`、`THB`、`SGD` 和 `CNY`。币种映射成 Web OAuth 所需国家码，不支持的币种抛出 `DATA_VALIDATION_FAILED`。

生产会话初始化顺序为：

1. 使用任务 `ext.proxy` 初始化 `CurlCffiTls`。
2. 使用当前 `DanLiCaptchaUtil` 和相同代理求解 Web Incapsula token。
3. 使用币种国家码、Incapsula token 和 Web OAuth client credentials 获取 Bearer token。
4. 会话内为每个请求生成稳定 session UUID 和递增 `ama-client-ref`。

订单详情同样使用上述认证路径，不保留旧代码的独立硬编码初始化分支。

## 航班模型映射

- 每个 Web itinerary 转换为一个 `FlightJourneyModel`。
- 每个 Web flight dictionary 项转换为 `FlightSegmentModel`，包含真实承运人、航班号、起降时间、航站楼、经停和航段索引。
- 每个可售价格转换为 `FlightBundleModel`。
- 购物车所需的 `airBoundIds` 按顺序写入 `fare_key`，多个 ID 使用 `^` 分隔。
- `fareFamilyCode` 写入 `code`，官网品牌写入 `product_tag`，订座舱位组合写入 `cabin`。
- 余座取各航段最低值；售罄套餐不返回。
- 成人和儿童基础票价、税费及币种写入 `FlightBundlePriceModel`。
- 免费行李转换为当前 `FlightSsrInfoModel`；不能可靠映射的数据保存在 `ext`。

空结果、无可售套餐或官网 `NO FLIGHTS FOUND` 转换为 `NO_FLIGHT_DATA`。

## 搜索与验价

搜索入口从当前 `RequestSearchTaskDataModel` 构建单程或往返 Web 请求，支持成人、儿童、币种和首个优惠码。搜索 Service 可以由 `MachineCache` 短期复用，但币种变化时必须重新获取 OAuth token。

`verify` 继续使用当前 `task_decorator` 的统一航班号筛选和响应协议，不单独实现第二套任务。

## 单 PNR 押位

1. 创建独立 Web Service 并完成认证。
2. 用一名成人搜索目标航线和日期。
3. 精确匹配当前任务的航班号、舱位和可选 `ext.productTag`。
4. 最终人数为可用座位数和五的较小值；没有余座时返回 `NO_AVAILABLE_CABIN`。
5. 用最终人数重新搜索并重新验证同一航班、舱位和产品。
6. 生成当前框架虚拟成人和联系人。
7. 创建一个购物车，更新所有旅客和联系人。
8. 仅调用一次 Purchase Order；如果接口明确返回 hCaptcha 挑战，先求解再重新提交尚未执行的建单请求。
9. 返回一个 `ResponseOrderInfoModel`，状态为 `HOLD`。

押位不添加付费行李、不执行支付、不缓存库存会话，也不创建第二个 PNR。

## 正式预订

1. 根据请求乘客类型计算成人和儿童人数并重新搜索。
2. 精确校验航班号、起降时间、产品、余座和可选价格阈值。
3. 创建购物车并写入所有乘客和联系人。
4. 调用一次 Purchase Order，并取得 PNR、旅客 ID、航班 ID、币种和订单金额。
5. 根据乘客 `ssr.baggage` 获取服务目录并添加请求行李。没有请求行李时跳过。
6. `paymentInfo.type == "NO_PAY"` 时返回 `HOLD`。
7. 其他支付类型仅接受当前支持的 Visa/Mastercard 卡数据：查询 payment method、加载支付页、初始化 3DS、用 `CardinalcommerceUtil` 完成指纹、提交卡数据并查询 payment records。
8. 支付成功后最多轮询五次 itinerary；将电子票号写入 `PassengerInfoModel.ticket_number`，订单状态设为 `OPEN_FOR_USE`。

价格阈值校验发生在 Purchase Order 之前。支付提交后任何未知结果都返回异常，不自动再次提交支付。

## 订单详情

订单详情入口使用当前 `RequestOrderDetailTaskModel` 的 PNR 和姓氏查询 itinerary 与 baggage，并构建 `ResponseOrderInfoModel`：

- 有电子票号：`OPEN_FOR_USE`。
- 未出票且订单仍处于有效 Hold：`HOLD`。
- 官网明确取消：`CANCEL`。
- 无法识别：`UNKNOWN`。

解析结果包含 PNR、订单号、乘客、联系人、航段、唯一套餐、总金额、币种和票号。缺失非关键展示字段时使用当前模型默认值；缺少 PNR、乘客或核心金额时返回 `DATA_VALIDATION_FAILED`。

## 重试与错误安全

- TLS 初始化、Incapsula、OAuth、搜索和只读订单详情允许有限重试并重建认证上下文。
- 创建购物车可以在明确未创建成功时重新请求，但任务层不进行盲重试。
- Purchase Order、添加付费行李、3DS 提交和支付提交不做通用自动重试。
- hCaptcha 只在官网明确返回挑战且 Purchase Order 尚未执行时求解一次并重交。
- HTTP 状态转换为 `HTTP_RESPONSE_STATE_NOT_SATISFY`。
- 非 JSON、缺少购物车 ID、PNR、payment method ID、action token 或票号转换为 `DATA_VALIDATION_FAILED`。
- Incapsula/hCaptcha 求解失败转换为当前验证码或 API 错误，终止当前任务。

## 本地示例与 Worker

四个任务文件都包含完整、受 `__main__` 保护的本地示例。示例代理和卡信息只使用明显占位值，不提交真实敏感数据。

Worker 使用 Python 3.13 和当前 `requirements-py313.txt`，支持：

- `9GWEB-search`
- `9GWEB-verify`
- `9GWEB-shamBooking`
- `9GWEB-booking`
- `9GWEB-orderDetail`

## 测试策略

所有自动测试都注入 TLS、验证码和 3DS 假对象，不访问官网、代理、验证码或支付服务：

- Web 币种与 OAuth 请求。
- Incapsula token 和请求头。
- 单程、往返、成人、儿童、优惠码请求体。
- 直飞、多航段、套餐、余座、票价和行李解析。
- 购物车、旅客、联系人和单次 Purchase Order。
- 押位两次搜索、最多五人和只创建一个 PNR。
- 正式预订的 NO_PAY、行李和支付成功分支。
- 不安全操作遇到异常时不重试。
- 订单详情的 HOLD、OPEN_FOR_USE、CANCEL 和 UNKNOWN 状态。
- `9GWEB` 四个任务模块的注册、本地示例和 Worker Shell 语法。
- 全量测试确保现有 `9GAPP` 行为无回归。

## 验收标准

- 当前注册逻辑可以发现 `9GWEB` 的搜索、押位、预订和订单详情模块。
- 搜索输出符合当前航班模型。
- 押位一次最多五人且只创建一个 PNR。
- 正式预订能返回 HOLD，或在支付成功后返回 OPEN_FOR_USE 与票号。
- 订单详情符合当前订单响应模型。
- 新代码不导入旧 `common.models`、`CurlHttpUtil`、库存模型或库存 Redis 工具。
- 新增和现有测试全部通过，主工作区原有未提交修改不被覆盖。
