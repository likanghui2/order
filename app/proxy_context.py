import threading
from typing import Any

from common.model.proxy_Info_model import ProxyInfoModel


class ThreadLocalProxyProvider:
    def __init__(self, default_proxy: ProxyInfoModel):
        object.__setattr__(self, "_default_proxy", default_proxy.model_copy(deep=True))
        object.__setattr__(self, "_local", threading.local())

    def set_current(self, proxy: ProxyInfoModel) -> None:
        self._local.current = proxy

    def clear_current(self) -> None:
        if hasattr(self._local, "current"):
            del self._local.current

    def current(self) -> ProxyInfoModel:
        proxy = getattr(self._local, "current", None)
        return proxy if proxy is not None else self._default_proxy

    def default_copy(self) -> ProxyInfoModel:
        return self._default_proxy.model_copy(deep=True)

    def model_copy(self, *args: Any, **kwargs: Any) -> ProxyInfoModel:
        return self.current().model_copy(*args, **kwargs)

    def get_proxy_info_to_string(self) -> str:
        return self.current().get_proxy_info_to_string()

    def generate_sess_id(self) -> None:
        self.current().generate_sess_id()

    def __getattr__(self, name: str) -> Any:
        return getattr(self.current(), name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            object.__setattr__(self, name, value)
        else:
            setattr(self.current(), name, value)

    def __bool__(self) -> bool:
        return bool(self.current())


def ensure_thread_local_proxy_provider(proxy: Any) -> ThreadLocalProxyProvider:
    if isinstance(proxy, ThreadLocalProxyProvider):
        return proxy
    return ThreadLocalProxyProvider(proxy)
