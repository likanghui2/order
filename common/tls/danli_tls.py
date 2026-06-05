import json
from typing import Any, Optional, List
import http.cookies
from requests import Timeout

from common.decorators.http_log_decorator import http_log_decorator
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.proxy_Info_model import ProxyInfoModel
from common.model.response_info_model import ResponseInfoModel
from common.tls.__tls_abstract import TlsAbstract
from curl_cffi import requests, CurlError

from common.utils.log_util import LogUtil


class DanLiTls(TlsAbstract):

    def __init__(self, appid_key: str):
        super().__init__()
        self.__appid_key = appid_key
        self.__log = LogUtil('DanLiTls')
    def cookie_update(self, cookie_data):
        cookie_obj_data = http.cookies.SimpleCookie(cookie_data)
        t = self.get_cookie_dict()
        for x in cookie_obj_data:
            t[cookie_obj_data[x].key] = cookie_obj_data[x].value

    @http_log_decorator()
    def get(self, url: str, headers: dict[str, Any], timeout: int = 60, **keywords) -> ResponseInfoModel:
        return self._execute_request(method="GET", url=url, headers=headers, timeout=timeout, **keywords)

    @http_log_decorator()
    def post(self, url: str, headers: dict[str, Any], data: [dict, str, bytes], timeout: int = 60,
             **keywords) -> ResponseInfoModel:
        return self._execute_request(method="POST", url=url, headers=headers, data=data, timeout=timeout, **keywords)

    def initialize(self, proxy_info_data: Optional[ProxyInfoModel]):
        if proxy_info_data:
            self.set_proxy_info_data(proxy_info_data)
            if proxy_info_data.format.find('{sessId}') != -1:
                self.generate_sess_id()

    def _execute_request(self, method: str, **keywords) -> ResponseInfoModel:
        try:
            headers = keywords.get('headers', {})
            if 'cookie' not in headers or 'Cookie' not in headers:
                if self.get_cookie_str():
                    headers['cookie'] = self.get_cookie_str()
            if method == 'GET':
                submit_data = None
            elif method == 'POST':
                if type(keywords['data']) == str:
                    submit_data = keywords['data']
                elif type(keywords['data']) == bytes:
                    submit_data = keywords['data']
                elif type(keywords['data']) == dict:
                    submit_data = json.dumps(keywords['data'])
                else:
                    raise ValueError("data is required")
            else:
                raise ValueError("method is required")

            proxy_data = self.get_proxy_data().get_proxy_info_to_string()

            proxy_start_index = proxy_data.find('http://')
            proxy_start_end = proxy_data.find('@')
            proxy_auth = proxy_data[proxy_start_index + 7:proxy_start_end]
            data = {
                'appid': self.__appid_key,
                'method': method.upper(),
                'headers': headers,
                'url': keywords['url'],
                # 'userAgent': headers.get('user-agent') or headers.get('User-Agent'),
                'body': submit_data,
                'proxyIp': self.get_proxy_data().host,
                'proxyPort': self.get_proxy_data().port,
                'proxyAuth': proxy_auth,
                "timeOut": 30,

            }
            r = requests.post('http://akmtls.zjdanli.com/tls', headers={
                "Content-Type": "application/json",
                "accept-encoding": "gzip, deflate, br"
            }, json=data, timeout=60)
            response_json = r.json()
            print(response_json)
            self.cookie_update("".join([x for x in response_json['cookies']]))
            return ResponseInfoModel(data_bytes=response_json['result'].encode('utf-8'),
                                     status=response_json['httpCode'], headers=response_json['headers'],
                                     url=response_json.get('url', keywords['url']))
        except CurlError as e:
            self.__log.error(e)
            raise ServiceError(ServiceStateEnum.CURL_EXCEPTION)
        except Timeout as e:
            self.__log.error(e)
            raise ServiceError(ServiceStateEnum.HTTP_TIMEOUT)
        except Exception as e:
            self.__log.error(e)
            raise ServiceError(ServiceStateEnum.HTTP_EXCEPTION)
