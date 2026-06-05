import json
import random
import string
import traceback
from curl_cffi import requests

from common.errors.service_error import ServiceError, ServiceStateEnum

from common.utils.log_util import LogUtil
LOG = LogUtil('danLICaptcha')
class DanLiCaptchaUtil:
    def __init__(self, api_key):
        self.__api_key = api_key

    def get_cloudflare(self, host):
        try:
            url = 'http://api-cf.zjdanli.com/cloudflare/getCookieUseOne'
            #url = 'http://api-usa.zjdanli.com/cloudflare/getCookie'
            header = {
                "Content-Type": "application/json"
            }
            data = {"appid": self.__api_key, "host": host}
            res = requests.post(url=url, headers=header, json=data, timeout=60, verify=False).json()
            LOG.info(json.dumps(res))
            if res.get('code') == '0':
                data = res.get('data')
                ua = data.get('ua')
                proxy = data.get('proxy')
                cookie = data.get('cookie')
                key = data.get('key')
                return cookie, ua, proxy,key
            else:
                raise ServiceError(ServiceStateEnum.API_RESPONSE_FAILED)
        except Exception as e:
            print(traceback.format_exc())
            raise ServiceError(ServiceStateEnum.API_RESPONSE_EXCEPTION)

    def feedback(self,key, err_type):
        url = 'http://api-cf.zjdanli.com/cloudflare/feedback'
        header = {
            "Content-Type": "application/json"
        }
        data = {"appid": self.__api_key, "key": key, "errType": err_type}
        print('deleteData',data)
        res = requests.post(url=url, headers=header, json=data).json()
        print('deleteDataResult',res)

    def akamai_ck_get(self, api_name: str):
        """
        发送一个POST请求到丹里Akamai API
        Args:
            api_name: API名称(对应网站)，用于构造URL的一部分。

        Returns:
            dict: 返回API的响应内容。

        """
        data = {
            'appid': self.__api_key,
        }
        headers = {
            'Content-Type': 'application/json;charset=UTF-8'
        }  # api.zjdanli.com # api-usa.zjdanli.com
        response = requests.post(f"http://api.zjdanli.com/akamai/cookie/{api_name}",
                                 json=data, headers=headers)
        print(response.json())
        if response.json()['code'] != "0":
            raise ServiceError(ServiceStateEnum.API_RESPONSE_EXCEPTION, response.json()['msg'])
        return response.json()

    def cloudflare_turnstile(self, host: str, sitekey: str):

        url = "http://api-cf.zjdanli.com/cloudflare/getTurnstileToken"

        payload = json.dumps({
            "appid": self.__api_key,
            "sitekey": sitekey,
            "host": host
        })
        headers = {
            'Content-Type': 'application/json'
        }
        try:
            response = requests.request("POST", url, headers=headers, data=payload)
        except Exception as e:
            raise ServiceError(ServiceStateEnum.API_RESPONSE_EXCEPTION, e)
        res_json = response.json()
        if res_json.get('code') != '0':
            raise ServiceError(ServiceStateEnum.API_RESPONSE_EXCEPTION, response.json()['msg'])
        print(res_json)
        return res_json['data']

    def __incapsula_get_jwt_token(self,session: requests.Session,verify_url: str,host:str,user_agent: str ):
        headers = {
            "Connection": "keep-alive",
            "sec-ch-ua-platform": "\"Windows\"",
            "User-Agent": user_agent,
            "Accept": "application/json; charset=utf-8",
            "Content-Type": "text/plain; charset=utf-8",
            "sec-ch-ua-mobile": "?0",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "es,en-US;q=0.9,en;q=0.8"
        }

        response = session.post(verify_url + f"?d={host}", headers=headers, json={"f": "gpc"})
        print(response.text)
        return response.text.strip('"')

    def __submit_incapsula_solver(self,incapsula_data: str,verify_url: str,user_agent: str,host: str,session: requests.Session):
        headers = {
            "Connection": "keep-alive",
            "User-Agent": user_agent,
            "Accept": "application/json; charset=utf-8",
            "Content-Type": "text/plain; charset=utf-8",
            "sec-ch-ua-mobile": "?0",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "es-419,es;q=0.9"
        }

        response = session.post(url=verify_url + f"?d={host }", headers=headers, data=incapsula_data)
        return response.json()['token']

    def incapsula_token_get(self,verify_url: str,proxy_data: str,host: str,jwt_required:bool,user_agent: str):

        session = requests.Session(impersonate='chrome136',proxies={'all':proxy_data},verify=False)
        jwt_token = None if jwt_required == False else self.__incapsula_get_jwt_token(session=session,host=host,user_agent=user_agent,verify_url=verify_url)
        data = {
            'appId': self.__api_key,
            'url': verify_url + f"?s={''.join(random.choices(string.ascii_lowercase + string.digits, k=6))}",
            'ua': user_agent,
        }
        if jwt_token is not None:
            data['jwtToken'] = jwt_token

        response = requests.Session().post(url='http://api-84.zjdanli.com/incapsula/reese84v2', json=data)
        incapsula_data = response.json().get('data')
        return self.__submit_incapsula_solver(incapsula_data,verify_url,user_agent,host,session)


if __name__ == '__main__':

    def incapsula_test():
        proxy = f'http://user-ciwei001-region-jp-sessid-aaaa{random.randint(100000,999999)}-sesstime-15-keep-true:ciwei001@rox.zjdanli.com:4600'
        DANLI_CAPTCHA = DanLiCaptchaUtil('7j58fx77bifxt2jhx01pwoek7asgp6xm')
        incapsula_token = DANLI_CAPTCHA.incapsula_token_get(verify_url="https://booking.vietnamairlines.com/Put-and-I-pull-their-Light-I-go-woman-O-the-viol/OKH9SC3iqYKBQuit1BFulwBSToX748kxZM6TsL6An5E",
                                                           user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
                                                           host="booking.vietnamairlines.com",
                                                           proxy_data=proxy,
                                                           jwt_required=True)
        print(incapsula_token)


    incapsula_test()