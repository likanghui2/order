import base64
import hashlib
import hmac
import time
from typing import Any, Callable, Optional

import requests


DEFAULT_TIMEOUT_SECONDS = 8


class DingTalkNotificationError(RuntimeError):
    pass


def send_text_notification(
    webhook_url: str,
    content: str,
    *,
    secret: str = "",
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    post: Optional[Callable[..., Any]] = None,
    timestamp_ms: Optional[int] = None,
) -> dict[str, Any]:
    url = str(webhook_url or "").strip()
    if not url.startswith(("https://", "http://")):
        raise DingTalkNotificationError("钉钉 Webhook 地址无效")
    if not str(content or "").strip():
        raise DingTalkNotificationError("钉钉通知内容不能为空")

    params: dict[str, Any] = {}
    secret_value = str(secret or "").strip()
    if secret_value:
        timestamp = int(timestamp_ms if timestamp_ms is not None else time.time() * 1000)
        string_to_sign = f"{timestamp}\n{secret_value}".encode("utf-8")
        digest = hmac.new(secret_value.encode("utf-8"), string_to_sign, hashlib.sha256).digest()
        params = {
            "timestamp": timestamp,
            "sign": base64.b64encode(digest).decode("utf-8"),
        }

    sender = post or requests.post
    try:
        response = sender(
            url,
            params=params or None,
            json={"msgtype": "text", "text": {"content": str(content)}},
            timeout=timeout_seconds,
        )
    except Exception as exc:
        raise DingTalkNotificationError(f"钉钉通知请求失败：{exc}") from exc

    status_code = int(getattr(response, "status_code", 0) or 0)
    try:
        data = response.json()
    except Exception:
        data = {}
    error_code = _safe_int(data.get("errcode")) if isinstance(data, dict) else None
    if status_code < 200 or status_code >= 300:
        raise DingTalkNotificationError(f"钉钉通知 HTTP {status_code}")
    if error_code not in (None, 0):
        error_message = str(data.get("errmsg") or "未知错误")
        raise DingTalkNotificationError(f"钉钉通知失败：{error_message}（{error_code}）")
    return {
        "sent": True,
        "statusCode": status_code,
        "errorCode": error_code or 0,
        "message": str(data.get("errmsg") or "ok") if isinstance(data, dict) else "ok",
    }


def build_downgrade_match_message(
    *,
    task_id: str,
    source: str,
    task_data: dict[str, Any],
    match: dict[str, Any],
    matched_at: Optional[float] = None,
) -> str:
    occurred_at = time.strftime(
        "%Y-%m-%d %H:%M:%S",
        time.localtime(matched_at if matched_at is not None else time.time()),
    )
    dep_date = _format_date(task_data.get("depDate"))
    target = str(match.get("targetPriceDisplay") or task_data.get("targetPrice") or "-").strip()
    actual = str(match.get("priceDisplay") or match.get("price") or "-").strip()
    currency = str(task_data.get("currencyCode") or "").strip()
    currency_suffix = f" {currency}" if currency else ""
    return "\n".join(
        [
            "【刷降舱命中】",
            f"数据源：{source or '-'}",
            f"航线：{task_data.get('depAirport') or '-'} → {task_data.get('arrAirport') or '-'}",
            f"日期：{dep_date}",
            f"航班：{match.get('flightNumber') or task_data.get('flightNumber') or '-'}",
            f"目标价格：{target or '-'}{currency_suffix}",
            f"命中价格：{actual}{currency_suffix}",
            f"命中时间：{occurred_at}",
            f"任务 ID：{task_id}",
        ]
    )


def _format_date(value: Any) -> str:
    raw = str(value or "").replace("-", "").replace("/", "").strip()
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    return str(value or "-")


def _safe_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
