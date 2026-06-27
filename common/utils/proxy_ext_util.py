from typing import Any, Optional

from common.model.proxy_Info_model import ProxyInfoModel


def proxy_info_from_ext(ext: Optional[dict[str, Any]]) -> ProxyInfoModel:
    proxy_data = ext.get("proxy") if isinstance(ext, dict) else None
    if isinstance(proxy_data, ProxyInfoModel):
        return proxy_data.model_copy(deep=True)
    if not isinstance(proxy_data, dict):
        raise ValueError("缺少 ext.proxy 代理参数")

    host = _clean(proxy_data.get("host"))
    port = proxy_data.get("port")
    if not host or port is None:
        raise ValueError("ext.proxy 缺少 host/port")
    format_value = _clean(proxy_data.get("format"))
    if not format_value:
        raise ValueError("ext.proxy 缺少 format")

    session_time = proxy_data.get("sessionTime") or proxy_data.get("session_time")
    sess_id = proxy_data.get("sessId") or proxy_data.get("sess_id")
    return ProxyInfoModel(
        host=host,
        port=int(port),
        username=_clean(proxy_data.get("username")) or None,
        password=_clean(proxy_data.get("password")) or None,
        region=_clean(proxy_data.get("region")) or None,
        sess_id=_clean(sess_id) or None,
        session_time=int(session_time) if session_time else None,
        format=format_value,
    )


def _clean(value: Any) -> str:
    return str(value).strip() if value is not None else ""
