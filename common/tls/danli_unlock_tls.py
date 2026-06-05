import http.cookies
import time
import traceback
from typing import Any, Optional, Union

import requests

from common.decorators.http_log_decorator import http_log_decorator
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.proxy_Info_model import ProxyInfoModel
from common.model.response_info_model import ResponseInfoModel
from common.tls.__tls_abstract import TlsAbstract
from common.utils.log_util import LogUtil


class DanliUnlockTls(TlsAbstract):
    def __init__(self, appid_key: str, site: str, auth_manage_cookie: bool = False):
        super().__init__()
        self.__appid_key = appid_key
        self.__site = site
        self.__auth_manage_cookie = auth_manage_cookie
        self.__proxy = ""
        self.__log = LogUtil("DanliUnlockTls")

    def initialize(self, proxy_info_data: Optional[ProxyInfoModel], **kwargs):
        if proxy_info_data:
            self.set_proxy_info_data(proxy_info_data)
            if proxy_info_data.format and proxy_info_data.format.find('{sessId}') != -1:
                self.generate_sess_id()
            proxy = self.get_proxy_data().get_proxy_info_to_string()
            self.__proxy = proxy if proxy.startswith("http") else f"http://{proxy}"
        else:
            self.__proxy = ""

        session = requests.Session()
        session.verify = False
        self.set_session(session)

    def close(self):
        session = self.get_session()
        if session:
            session.close()

    def cookie_update(self, cookie_data: Union[str, dict, list]):
        if isinstance(cookie_data, dict):
            self.get_cookie_dict().update(cookie_data)
            return

        if isinstance(cookie_data, list):
            cookie_data = ";".join(cookie_data)

        if not cookie_data:
            return

        cookie_obj_data = http.cookies.SimpleCookie(cookie_data)
        for key in cookie_obj_data:
            self.get_cookie_dict()[cookie_obj_data[key].key] = cookie_obj_data[key].value

    def add_cookie_string(self, cookie_data: str):
        self.cookie_update(cookie_data)

    def clear_cookies(self):
        self.get_cookie_dict().clear()

    @http_log_decorator()
    def get(self, url: str, headers: dict[str, Any], timeout: int = 60, **keywords) -> ResponseInfoModel:
        return self._execute_request(method="GET", url=url, headers=headers, timeout=timeout, data={})

    @http_log_decorator()
    def post(self,
             url: str,
             headers: dict[str, Any],
             data: Union[dict, str, bytes, None] = None,
             timeout: int = 60,
             **keywords) -> ResponseInfoModel:
        return self._execute_request(method="POST", url=url, headers=headers, data=data, timeout=timeout)

    def _execute_request(self, method: str, **keywords) -> ResponseInfoModel:
        start_time = time.time()
        try:
            headers = keywords.get('headers') or {}
            self._add_headers_cookie(headers)
            headers.update({
                "api-url": keywords['url'],
                "api-key": self.__appid_key,
                "api-proxy": self.__proxy,
            })

            response = self.get_session().request(
                url=f"http://site.zjdanli.com/unlock/{self.__site}",
                method=method,
                headers=headers,
                json=self._build_json_body(keywords.get('data')),
                timeout=(keywords.get('timeout') or 60) + 10,
            )
            if response.status_code == 729:
                self.__log.error('第三方并发限制')
                time.sleep(1)
                response = self.get_session().request(
                    url=f"http://site.zjdanli.com/unlock/{self.__site}",
                    method=method,
                    headers=headers,
                    json=self._build_json_body(keywords.get('data')),
                    timeout=(keywords.get('timeout') or 60) + 10,
                )
            response_data = self._response_to_data(response=response, url=keywords['url'])
            if response.headers.get('set-cookie'):
                self._update_response_cookie(response.headers['set-cookie'])
            return response_data
        except ServiceError:
            raise
        except Exception:
            self.__log.error(traceback.format_exc())
            if "timeout" in traceback.format_exc().lower():
                raise ServiceError(ServiceStateEnum.HTTP_TIMEOUT, time.time() - start_time)
            raise ServiceError(ServiceStateEnum.HTTP_EXCEPTION)

    @staticmethod
    def _build_json_body(data):
        if data is None:
            return None
        if isinstance(data, bytes):
            return data.decode('utf-8')
        if isinstance(data, str):
            return data
        return data

    def _add_headers_cookie(self, headers: dict):
        if self.__auth_manage_cookie:
            return
        if 'Cookie' not in headers and 'cookie' not in headers:
            headers['Cookie'] = self.get_cookie_str()

    def _update_response_cookie(self, cookies: str):
        if self.__auth_manage_cookie:
            return

        cookie_dict = self._parse_cookie_string(cookies)
        for key, value in cookie_dict.items():
            if key in ["_abck", "bm_sz"]:
                continue
            self.get_cookie_dict()[key] = value

    @staticmethod
    def _parse_cookie_string(cookie_str: str) -> dict:
        cookie_dict = {}
        exclude_keys = {'domain', 'path', 'expires', 'max-age', 'httponly', 'secure', 'samesite'}

        for part in cookie_str.split(', '):
            main_pair = part.split(';')[0]
            if '=' not in main_pair:
                continue
            key, val = main_pair.split('=', 1)
            key = key.strip()
            if key.lower() not in exclude_keys:
                cookie_dict[key] = val.strip()

        return cookie_dict

    @staticmethod
    def _headers_to_dict(headers) -> dict:
        return {key: value for key, value in headers.items()}

    def _response_to_data(self, response: requests.Response, url: str) -> ResponseInfoModel:
        text = response.text
        if "akm风控拦截" in text:
            raise ServiceError(ServiceStateEnum.AKM_RISK_CHECK_FAILED)
        if response.status_code == 428 and "verify_url" in text:
            raise ServiceError(ServiceStateEnum.AKM_RISK_CHECK_FAILED)
        if response.status_code == 403 and "Access Denied" in text:
            raise ServiceError(ServiceStateEnum.AKM_RISK_CHECK_FAILED)
        if response.status_code == 403 and ("Just a moment" in text or "Attention Required" in text):
            raise ServiceError(ServiceStateEnum.CLOUD_FLARE_CHECK_FAILURE)

        return ResponseInfoModel(
            data_bytes=response.content,
            status=response.status_code,
            headers=self._headers_to_dict(response.headers),
            url=url,
        )
