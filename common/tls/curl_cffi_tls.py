import http.cookies
import json
from typing import Any, Optional, Union

import curl_cffi
from curl_cffi import CurlError
from requests import Timeout

from .__tls_abstract import TlsAbstract
from ..decorators.http_log_decorator import http_log_decorator
from ..errors.service_error import ServiceError, ServiceStateEnum
from ..model.proxy_Info_model import ProxyInfoModel

from ..model.response_info_model import ResponseInfoModel


class CurlCffiTls(TlsAbstract):

    def initialize(self, proxy_info_data: Optional[ProxyInfoModel], **kwargs):

        session = curl_cffi.Session(verify=False, **kwargs)

        if proxy_info_data:
            self.set_proxy_info_data(proxy_info_data)
            if proxy_info_data.format.find('{sessId}') != -1:
                self.generate_sess_id()
            session.proxies = {
                'http': self.get_proxy_data().get_proxy_info_to_string(),
                'https': self.get_proxy_data().get_proxy_info_to_string()
            }
        self.set_session(session)

    def set_proxy_info_str(self, proxy_data: str):
        self.get_session().proxies = {
            'http': proxy_data,
            'https': proxy_data
        }

    def get_ip(self):
        return self.get_session().get('https://ipinfo.io/ip').text

    def cookie_update(self, cookie_data: [str, dict]):
        """

        :param cookie_data:
        :return:
        """
        if type(cookie_data) == dict:
            t = self.get_cookie_dict()
            for k, v in cookie_data.items():
                t[k] = v
        elif type(cookie_data) == str:
            cookie_obj_data = http.cookies.SimpleCookie(cookie_data)
            t = self.get_cookie_dict()
            for x in cookie_obj_data:
                t[cookie_obj_data[x].key] = cookie_obj_data[x].value

    @http_log_decorator()
    def get(self, url: str, headers: dict[str, Any], timeout: int = 60, **keywords) -> ResponseInfoModel:
        return self._execute_request(method="GET", url=url, headers=headers, timeout=timeout, **keywords)

    @http_log_decorator()
    def post(self, url: str, headers: dict[str, Any], data: Union[dict, str, bytes, None] = None, timeout: int = 60,
             **keywords) -> ResponseInfoModel:
        return self._execute_request(method="POST", url=url, headers=headers, data=data, timeout=timeout, **keywords)

    @http_log_decorator()
    def put(self, url: str, headers: dict[str, Any], data: Union[dict, str, bytes, None] = None, timeout: int = 60,
             **keywords) -> ResponseInfoModel:
        return self._execute_request(method="PUT", url=url, headers=headers, data=data, timeout=timeout, **keywords)
    @http_log_decorator()
    def patch(self, url: str, headers: dict[str, Any], data: Union[dict, str, bytes, None] = None, timeout: int = 60,
              **keywords) -> ResponseInfoModel:
        return self._execute_request(method="PATCH", url=url, headers=headers, data=data, timeout=timeout, **keywords)

    def _execute_request(self, method: str, **keywords) -> ResponseInfoModel:
        try:

            allow_redirects = keywords.get('allow_redirects', None)
            if allow_redirects is None:
                allow_redirects = False
            else:
                allow_redirects = keywords['allow_redirects']
                del keywords['allow_redirects']

            headers = keywords.get('headers', {})
            if 'cookie' not in headers:
                headers['cookie'] = self.get_cookie_str()

            if method == "GET":
                response = self.get_session().get(allow_redirects=allow_redirects, **keywords)
            elif method == "POST":
                if type(keywords['data']) == str:
                    submit_data = keywords['data'].encode('utf-8')
                elif type(keywords['data']) == bytes:
                    submit_data = keywords['data']
                elif type(keywords['data']) == dict:
                    submit_data = json.dumps(keywords['data'], ensure_ascii=False, separators=(",", ":")).encode(
                        'utf-8')
                elif type(keywords['data']) == list:
                    submit_data = json.dumps(keywords['data'], ensure_ascii=False, separators=(",", ":")).encode(
                        'utf-8')
                else:
                    submit_data = ""

                del keywords['data']
                response = self.get_session().post(allow_redirects=allow_redirects, data=submit_data, **keywords)
            elif method == "PATCH":
                data = keywords.get('data', None)
                submit_data = data if isinstance(data, str) else json.dumps(data, separators=(',', ':')) if data else ""
                del keywords['data']
                response = self.get_session().patch(allow_redirects=allow_redirects, data=submit_data, **keywords)
            elif method == "PUT":
                data = keywords.get('data', None)
                submit_data = data if isinstance(data, str) else json.dumps(data, separators=(',', ':')) if data else ""
                del keywords['data']
                response = self.get_session().put(allow_redirects=allow_redirects, data=submit_data, **keywords)
            else:
                raise ValueError("method is invalid")

            self.cookie_update(dict(self.get_session().cookies))
            self.get_session().cookies.clear()
            return ResponseInfoModel(data_bytes=response.content, status=response.status_code, headers=response.headers,
                                     url=response.url)
        except CurlError as e:
            raise ServiceError(ServiceStateEnum.CURL_EXCEPTION)
        except Timeout as e:
            raise ServiceError(ServiceStateEnum.HTTP_TIMEOUT)

    def __init__(self, **kwargs):
        super().__init__()
