import json
from typing import Optional, Dict

from curl_cffi import requests

from common.errors.service_error import ServiceError, ServiceStateEnum


class NoCaptchaUtil:

    def __init__(self, api_key):
        self.__api_key = api_key

    def submit(self, url, data):
        headers = {
            'User-Token': self.__api_key,
            'Content-Type': 'application/json',
        }
        response = requests.Session().post(url=url, headers=headers, json=data, timeout=60)

        if 'status' in response.json() and response.json()['status'] != 1:
            raise ServiceError(ServiceStateEnum.API_RESPONSE_FAILED)

        if 'success' in response.json() and response.json()['success'] != True:
            raise ServiceError(ServiceStateEnum.API_RESPONSE_FAILED)

        return response.json()

    def preflight(self):

        r = self.submit("https://api.nocaptcha.io/api/wanda/hcaptcha/preflight", {"sitekey": self.__api_key})
        return r['data']['preflight_uuid'], r['data']['data']['region']

    def hcaptcha_v2(self, site_key, href, region, proxy_data):
        resp = requests.get(url="https://ipinfo.io/json", headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
        }, timeout=60, proxies={'all': proxy_data}).json()
        data = {
            'branch': "mac1",
            'href': href,
            'sitekey': site_key,
            'region': region,
            'ip': resp['ip'],
            'timezone': resp['timezone'],
            'geolocation': resp['loc'],
            'proxy': proxy_data
        }

        return self.submit('https://api.nocaptcha.cn/api/wanda/hcaptcha/v2', data)

    def hcaptcha(self,
                 site_key: str,
                 referer: str,
                 rq_data: Optional[str] = None,
                 domain: Optional[str] = None,
                 proxy: Optional[str] = None,
                 region: Optional[str] = None,
                 invisible: Optional[bool] = False,
                 need_key: Optional[bool] = False,
                 preflight_uuid: Optional[str] = None, ):

        submit_data = {
            'sitekey': site_key,
            'referer': referer,
            "invisible": invisible,
            "need_key": need_key,
        }

        if rq_data: submit_data['rqdata'] = rq_data
        if domain: submit_data['domain'] = domain
        if proxy: submit_data['proxy'] = proxy
        if region: submit_data['region'] = region
        if preflight_uuid: submit_data['preflight_uuid'] = preflight_uuid

        return self.submit('https://api.nocaptcha.io/api/wanda/hcaptcha/universal', submit_data)

    def solve_recaptcha(self, referer: str,
                        sitekey: str,
                        title: str,
                        size: str = "invisible",
                        action: Optional[str] = None, proxy: Optional[str] = None) -> str:
        """
        获取 Google reCAPTCHA Token。

        Args:
            referer (str): 来源页。
            sitekey (str): Google reCAPTCHA site key。
            title (str): 页面标题。
            size (str): 验证码尺寸（默认为 invisible）。
            action (Optional[str]): 执行动作名称。
            proxy
        Returns:
            str: 验证 token。
        """
        data = {
            "referer": referer,
            "sitekey": sitekey,
            "size": size,
            "title": title,
            "action": action,
            "proxy": proxy,
        }
        return self.submit("https://api.nocaptcha.io/api/wanda/recaptcha/enterprise", data)['data']['token']

    def solve_cf_turnstile(self, url: str, sitekey: str, proxy: Optional[str] = None) -> Dict:
        """
        解决 Cloudflare Turnstile 验证。

        Args:
            proxy:
            url (str): 页面 URL。
            sitekey (str): Turnstile 验证公钥。

        Returns:
            Dict: 响应完整数据。
        """
        data = {
            "href": url,
            "sitekey": sitekey,
            "proxy": proxy,
        }
        return self.submit("https://api.nocaptcha.io/api/wanda/cloudflare/universal", data)['data']['token']
