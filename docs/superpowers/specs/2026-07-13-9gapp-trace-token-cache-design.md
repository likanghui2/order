# 9G App Trace Token 缓存设计

## 目标

为 9G App 的 `trace_id` 增加一个全局 Redis ZSET Token 池。查询接口产出的 Token 写入池中，等待 120 秒后才能被下单流程领取；Token 领取即删除，并在同一次 `create_order + hold_booking` 流程中复用。

该能力只服务 `9GAPP`，与 VJ Web Session 缓存没有代码或运行时依赖。

## 明确约束

- Redis 成员只保存 `trace_id` Token 字符串，不保存 JSON、航线、代理、设备信息或任务信息。
- Token 不按航线分池，所有 9G App 查询写入同一个全局池。
- Token 生成后等待 120 秒才可领取。
- Token 就绪后的可领取窗口为 20 分钟。
- Token 从生成到最终失效的总时间为 22 分钟。
- Token 领取与删除必须是原子操作，不能被两个任务重复领取。
- 一个 Token 只对应一次下单流程，但该流程内的 `create_order` 和 `hold_booking` 使用同一个 Token。
- 下单流程只能从 Redis 池领取 Token，不回退到 `AppScript` 实例中由当前查询留下的旧值。

## 数据结构

Redis Key：

```text
9g:app:trace:v1
```

使用 ZSET：

- member：原始 `trace_id` Token 字符串。
- score：`ready_at` Unix 时间戳，即 Token 写入时间加 120 秒。
- 失效时间由 `ready_at + 1200` 秒推导，不写入 member。

因此 Redis 业务数据本身只有 Token；就绪和失效判断只使用 ZSET score。

## 组件边界

新增 `NineGAppTraceCache`，负责以下操作：

1. `save(token)`：校验非空 Token，清理已失效成员，以 `now + 120` 为 score 写入 ZSET，并刷新 Key 的兜底 TTL。
2. `pop_ready()`：通过 Lua 脚本清理已失效成员，取出一个 score 不晚于当前时间的 Token，原子删除后返回。
3. `stats()`：仅用于测试或诊断时统计 warming、ready 数量，不进入下单协议。

缓存类接收可注入的 Redis 连接和时钟，生产环境使用当前项目的 Redis 配置，测试使用内存替身或受控 Redis 替身。

## 数据流

### 查询生产 Token

1. 9G App 查询请求正常发送。
2. 查询响应通过现有业务校验。
3. 从响应读取 `trace_id`。
4. 将非空 `trace_id` 写入 ZSET，score 为当前时间加 120 秒。
5. 查询继续返回原有航班结果，不把缓存结构暴露给任务响应。

若响应缺少 `trace_id` 或 Redis 写入失败，查询任务返回明确错误，避免系统表面查询成功但 Token 池持续断粮。

### 下单消费 Token

1. `create_order` 开始前调用 `pop_ready()`。
2. Lua 脚本删除超过 20 分钟可用窗口的成员。
3. Lua 脚本选择一个已经等待满 120 秒的 Token。
4. 选中的 Token 在同一 Lua 调用内从 ZSET 删除并返回。
5. `AppScript` 将 Token 写入当前实例的 `trace_id`，`create_order` 请求头携带 `Spa-Trace-Id`。
6. 随后的 `hold_booking` 沿用该实例上的同一个 Token。
7. 流程结束后不归还 Token。

若池中没有已就绪 Token，下单在发送上游请求前失败，并返回“9GAPP暂无可用trace_id”业务错误。

## 原子领取规则

Lua 脚本在一次 Redis 调用内完成：

1. 计算 `expired_before = now - 1200`。
2. 删除 score 不大于 `expired_before` 的成员。
3. 从 `(expired_before, now]` 范围按 score 升序取一个成员。
4. 找到后执行 `ZREM` 并返回 Token；找不到则返回空值。

该范围同时保证 Token 已等待满 120 秒且尚未超过 20 分钟可用窗口。

## 错误与安全

- 空 Token 不写入缓存。
- Redis 异常转换为当前框架的 `ServiceError`，不使用本地内存降级，避免多进程重复消费。
- 日志只记录缓存数量、动作和错误，不输出完整 Token。
- HTTP 日志现有敏感字段脱敏继续生效；`Spa-Trace-Id` 不应写入明文日志。
- 不新增对 VJ Session Server 的调用，也不在其 Redis Key 空间中写入 9G 数据。

## 测试范围

- 查询响应产生的 `trace_id` 被写入缓存。
- 缓存 member 只有 Token 字符串。
- Token 在 119 秒时不可领取，在 120 秒时可领取。
- Token 就绪后 20 分钟内可领取，超过窗口会被清理。
- 并发领取语义下，同一 Token 只返回一次。
- `create_order` 从缓存领取 Token，并与 `hold_booking` 复用。
- 缓存为空时不会发送创建订单请求。
- Redis 写入/读取异常映射为明确的当前框架错误。
- 现有 9G App 搜索、单 PNR 押位和 9G Web 流程保持通过。

## 非目标

- 不缓存完整查询响应、航班、代理、设备 ID 或乘客数据。
- 不按航线或币种拆分 Token 池。
- 不增加独立 FastAPI Token 服务。
- 不复用、修改或依赖 `tools/vj_web_session_server.py`。
- 不改变每个押位任务只创建一个 PNR、最多五人的既有规则。
