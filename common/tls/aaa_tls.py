import http.cookies
import json
import random
from collections.abc import Mapping, Sequence
from typing import Any, Optional
from urllib.parse import parse_qsl, urlsplit, urlunsplit

import requests

from common.decorators.http_log_decorator import http_log_decorator
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.proxy_Info_model import ProxyInfoModel
from common.model.response_info_model import ResponseInfoModel
from common.tls.__tls_abstract import TlsAbstract


class AaaTls(TlsAbstract):
    """通过 AAA 远端服务执行带指定浏览器指纹的目标 HTTP 请求。"""

    TLS_PROXY_URL = "http://127.0.0.1:24800"

    def __init__(
        self,
        api_url: str,
        api_key: str,
        impersonates: Sequence[str] = ("chrome136aaa", "chrome131aaa"),
        proxy_user_agent: str = "X-Chrome",
        client_id: str = "Chrome|133_SA",
        auth_manage_cookie: bool = False,
    ):
        super().__init__()
        if auth_manage_cookie:
            raise ServiceError(
                ServiceStateEnum.DATA_VALIDATION_FAILED,
                "AAA TLS不支持auth_manage_cookie=True",
            )
        if not str(api_url or "").strip():
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "AAA TLS API URL")
        if not str(api_key or "").strip():
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "AAA TLS API Key")
        if not impersonates:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "AAA TLS impersonates")

        self._api_url = api_url
        self._api_key = api_key
        self._impersonates = tuple(impersonates)
        self._proxy_user_agent = proxy_user_agent
        self._client_id = client_id
        self._real_proxy_url: Optional[str] = None

    def initialize(self, proxy_info_data: Optional[ProxyInfoModel], **kwargs):
        if proxy_info_data:
            self.set_proxy_info_data(proxy_info_data.model_copy(deep=True))
            if proxy_info_data.format and "{sessId}" in proxy_info_data.format:
                self.generate_sess_id()
            proxy_url = self.get_proxy_data().get_proxy_info_to_string()
            self._real_proxy_url = (
                proxy_url
                if proxy_url.lower().startswith(("http://", "https://", "socks"))
                else f"{kwargs.get('proxy_type', 'http')}://{proxy_url}"
            )
        else:
            self._real_proxy_url = None
        self.set_session(requests.Session())

    def close(self):
        session = self.get_session()
        if session:
            session.close()
        self.set_session(None)

    def cookie_update(self, cookie_data):
        if not cookie_data:
            return
        if isinstance(cookie_data, Mapping):
            self.get_cookie_dict().update({
                str(key): str(value) for key, value in cookie_data.items()
            })
            return
        if isinstance(cookie_data, (list, tuple)):
            cookie_data = ";".join(str(value) for value in cookie_data)
        cookie_obj = http.cookies.SimpleCookie(str(cookie_data))
        for key in cookie_obj:
            self.get_cookie_dict()[cookie_obj[key].key] = cookie_obj[key].value

    @http_log_decorator()
    def get(
        self,
        url: str,
        headers: dict[str, Any],
        timeout: int = 60,
        **keywords,
    ) -> ResponseInfoModel:
        return self.request(
            method="GET",
            url=url,
            headers=headers,
            timeout=timeout,
            **keywords,
        )

    @http_log_decorator()
    def post(
        self,
        url: str,
        headers: dict[str, Any],
        data=None,
        timeout: int = 60,
        **keywords,
    ) -> ResponseInfoModel:
        return self.request(
            method="POST",
            url=url,
            headers=headers,
            data=data,
            timeout=timeout,
            **keywords,
        )

    @http_log_decorator()
    def put(self, url: str, headers: dict[str, Any], data=None,
            timeout: int = 60, **keywords) -> ResponseInfoModel:
        return self.request(
            method="PUT", url=url, headers=headers, data=data,
            timeout=timeout, **keywords,
        )

    @http_log_decorator()
    def patch(self, url: str, headers: dict[str, Any], data=None,
              timeout: int = 60, **keywords) -> ResponseInfoModel:
        return self.request(
            method="PATCH", url=url, headers=headers, data=data,
            timeout=timeout, **keywords,
        )

    @http_log_decorator()
    def delete(self, url: str, headers: dict[str, Any], data=None,
               timeout: int = 60, **keywords) -> ResponseInfoModel:
        return self.request(
            method="DELETE", url=url, headers=headers, data=data,
            timeout=timeout, **keywords,
        )

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, Any],
        data=None,
        timeout: int = 60,
        **keywords,
    ) -> ResponseInfoModel:
        if self.get_session() is None:
            self.initialize(None)

        json_data = keywords.pop("json", None)
        if data is not None and json_data is not None:
            raise ServiceError(
                ServiceStateEnum.DATA_VALIDATION_FAILED,
                "AAA TLS请求不能同时传data和json",
            )

        parsed_url = urlsplit(url)
        if parsed_url.fragment:
            raise ServiceError(
                ServiceStateEnum.DATA_VALIDATION_FAILED,
                "AAA TLS请求URL不能包含fragment",
            )
        target_url = urlunsplit((parsed_url.scheme, parsed_url.netloc, parsed_url.path, "", ""))
        params = self._merge_params(
            parse_qsl(parsed_url.query, keep_blank_values=True),
            keywords.pop("params", None),
        )

        use_headers = dict(headers or {})
        if any(str(key).lower() == "cookie" for key in use_headers):
            raise ServiceError(
                ServiceStateEnum.DATA_VALIDATION_FAILED,
                "AAA TLS Cookie必须通过cookies参数传入",
            )

        use_json_body = json_data is not None
        json_payload = json_data
        if json_payload is None and data is not None and self._is_json_content_type(use_headers):
            use_json_body = True
            if isinstance(data, (str, bytes, bytearray)):
                try:
                    json_payload = json.loads(data)
                except (TypeError, ValueError, UnicodeDecodeError):
                    raise ServiceError(
                        ServiceStateEnum.DATA_VALIDATION_FAILED,
                        "AAA TLS JSON请求体",
                    ) from None
            else:
                json_payload = data
            data = None

        use_cookies = dict(self.get_cookie_dict())
        explicit_cookies = keywords.pop("cookies", None)
        if explicit_cookies:
            use_cookies.update(explicit_cookies)

        proxy_headers = {
            "X-User-Agent": self._proxy_user_agent,
            "X-C-Id": self._client_id,
        }
        proxy_headers.update(keywords.pop("proxy_headers", None) or {})
        if self._real_proxy_url:
            proxy_headers["X-AAA-Proxy"] = self._real_proxy_url

        allow_redirects = keywords.pop(
            "allow_redirects",
            keywords.pop("auth_redirect", False),
        )
        request_data = {
            "timeout": timeout,
            "proxies": {
                "http": self.TLS_PROXY_URL,
                "https": self.TLS_PROXY_URL,
            },
            "proxy_headers": proxy_headers,
            "method": str(method).upper(),
            "url": target_url,
            "impersonate": keywords.pop("impersonate", None) or random.choice(self._impersonates),
            "headers": use_headers,
            "cookies": use_cookies,
            "read_bytes": bool(keywords.pop("read_bytes", False)),
            "allow_redirects": bool(allow_redirects),
        }
        if keywords:
            unexpected = ",".join(sorted(keywords))
            raise ServiceError(
                ServiceStateEnum.DATA_VALIDATION_FAILED,
                f"AAA TLS不支持参数[{unexpected}]",
            )
        if params is not None:
            request_data["params"] = params
        if use_json_body:
            request_data["json_body"] = json_payload
        elif data is not None:
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            request_data["data"] = data

        try:
            response = self.get_session().post(
                self._api_url,
                json=request_data,
                headers={"apiKey": self._api_key},
                timeout=timeout + 15,
            )
            response_json = response.json()
        except requests.Timeout:
            raise ServiceError(ServiceStateEnum.HTTP_TIMEOUT, timeout) from None
        except (requests.RequestException, TypeError, ValueError):
            raise ServiceError(ServiceStateEnum.HTTP_EXCEPTION) from None

        return self._parse_response(response_json, target_url)

    def _parse_response(self, response: Any, target_url: str) -> ResponseInfoModel:
        if not isinstance(response, dict) or "status_code" not in response:
            raise ServiceError(ServiceStateEnum.API_RESPONSE_EXCEPTION)
        try:
            status = int(response["status_code"])
        except (TypeError, ValueError):
            raise ServiceError(ServiceStateEnum.API_RESPONSE_EXCEPTION) from None
        if status == 0:
            raise ServiceError(ServiceStateEnum.HTTP_TIMEOUT, 0)
        headers = response.get("headers") or {}
        cookies = response.get("cookies") or {}
        if not isinstance(headers, dict) or not isinstance(cookies, dict):
            raise ServiceError(ServiceStateEnum.API_RESPONSE_EXCEPTION)
        self.cookie_update(cookies)
        text = response.get("text")
        if text is None:
            text = ""
        elif not isinstance(text, str):
            text = str(text)
        self._raise_risk_error(status, text)
        return ResponseInfoModel(
            data_bytes=text.encode("utf-8"),
            status=status,
            headers={str(key): str(value) for key, value in headers.items()},
            url=str(response.get("url") or target_url),
        )

    @staticmethod
    def _merge_params(url_params: list[tuple[str, str]], params) -> Optional[dict]:
        merged = {}

        def add_value(key, value):
            key = str(key)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
                for item in value:
                    add_value(key, item)
                return
            merged.setdefault(key, []).append(value)

        for key, value in url_params:
            add_value(key, value)
        if params is not None:
            if isinstance(params, str):
                items = parse_qsl(params.lstrip("?"), keep_blank_values=True)
            elif isinstance(params, Mapping):
                items = params.items()
            elif isinstance(params, Sequence):
                items = params
            else:
                raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "AAA TLS params")
            for item in items:
                if (
                    not isinstance(item, Sequence)
                    or isinstance(item, (str, bytes, bytearray))
                    or len(item) != 2
                ):
                    raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "AAA TLS params")
                add_value(item[0], item[1])
        if not merged:
            return None
        return {
            key: values[0] if len(values) == 1 else values
            for key, values in merged.items()
        }

    @staticmethod
    def _is_json_content_type(headers: dict) -> bool:
        content_type = next(
            (
                str(value) for key, value in headers.items()
                if str(key).lower() == "content-type"
            ),
            "",
        )
        media_type = content_type.split(";", 1)[0].strip().lower()
        return media_type == "application/json" or media_type.endswith("+json")

    @staticmethod
    def _raise_risk_error(status: int, text: str):
        if status == 428 and "verify_url" in text:
            raise ServiceError(ServiceStateEnum.AKM_RISK_CHECK_FAILED)
        if status == 403 and "Access Denied" in text:
            raise ServiceError(ServiceStateEnum.AKM_RISK_CHECK_FAILED)
        if status == 403 and (
            "Just a moment" in text or "Attention Required" in text
        ):
            raise ServiceError(ServiceStateEnum.CLOUD_FLARE_CHECK_FAILURE)
        if status == 403 and "_Incapsula_Resource" in text:
            raise ServiceError(ServiceStateEnum.INCAPSULA_CHECK_FAILURE)
        if status == 403 and "appId" in text:
            raise ServiceError(ServiceStateEnum.PX_CHECK_FAILURE)


AaaTlsHttpUtil = AaaTls
AAATls = AaaTls
