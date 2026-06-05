import json
import time
import urllib.parse
from typing import Optional
from urllib.parse import urlencode

from common.decorators.retry_decorator import retry_decorator
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.proxy_Info_model import ProxyInfoModel
from common.tls.curl_cffi_tls import CurlCffiTls
from common.utils.danli_captcha_util import DanLiCaptchaUtil
from common.utils.string_util import StringUtil

DANLI_CAPTCHA = DanLiCaptchaUtil('7j58fx77bifxt2jhx01pwoek7asgp6xm')

class WebScript:
    def __init__(self, proxy_info_data: ProxyInfoModel):
        self.__tls = CurlCffiTls()
        self.__tls.initialize(proxy_info_data,impersonate='chrome136')
        self.__ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
        self.__sid = None
        self.__mark = None
        self.__cloudflare_key = None
        self.__err_type = None

    @retry_decorator([(ServiceStateEnum.API_RESPONSE_EXCEPTION, None),(ServiceStateEnum.API_RESPONSE_FAILED, None)])
    def init_cloudflare(self):
        time.sleep(0.5)
        cookie, ua, proxy,self.__cloudflare_key = DANLI_CAPTCHA.get_cloudflare("www.lionairthai.com")
        cookie_array = cookie.split(';')
        data = []

        for i in cookie_array:
            if i.find('__cf_bm') != -1 or i.find("cf_clearance") != -1:
                data.append(i)

        # print(cookie)
        #print(cookie, ua, proxy,self.__cloudflare_key)
        self.__tls.set_proxy_info_str(proxy)
        self.__ua = ua
        self.__tls.cookie_update(";".join(data))

    def cloudflare_feedback(self):
        DANLI_CAPTCHA.feedback(self.__cloudflare_key,self.__err_type)

    @retry_decorator([(ServiceStateEnum.CURL_EXCEPTION, None)])
    def init_sid(self):
        headers = {
            "Host": "www.lionairthai.com",
            "Connection": "keep-alive",
            "Content-Length": "0",
            "sec-ch-ua-platform": "\"Windows\"",
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": self.__ua,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/json; charset=utf-8",
            "sec-ch-ua-mobile": "?0",
            "Origin": "https://www.lionairthai.com",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Referer": "https://www.lionairthai.com/",
            "Accept-Encoding":"gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8,hy;q=0.7,as;q=0.6,ast;q=0.5"
        }

        response = self.__tls.post(url="https://www.lionairthai.com/GetIpAddress.aspx/GetIp", headers=headers)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, 200)
        self.__sid = response.to_dict()['d']

    @retry_decorator([(ServiceStateEnum.CLOUD_FLARE_CHECK_FAILURE, (cloudflare_feedback,init_cloudflare)),(ServiceStateEnum.CURL_EXCEPTION, None)])
    def default(self):
        headers = {
            "Host": "search.lionairthai.com",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": self.__ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Dest": "document",
            "Referer": "https://search.lionairthai.com/",
            "Accept-Encoding":"gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8,hy;q=0.7,as;q=0.6,ast;q=0.5"
        }

        response = self.__tls.get(url="https://search.lionairthai.com/default.aspx?t=" + self.__mark, headers=headers)
        if response.status != 200:
            if response.status == 403:
                self.__err_type = 1
                raise ServiceError(ServiceStateEnum.CLOUD_FLARE_CHECK_FAILURE)
            if response.status == 429:
                self.__err_type = 2
                raise ServiceError(ServiceStateEnum.CLOUD_FLARE_CHECK_FAILURE)
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, 200)

        t = StringUtil.extract_between(response.to_text(), 'SL/Flight.aspx?t=', "'")
        if t:
            self.__mark = t
            return 0

        t = StringUtil.extract_between(response.to_text(), './default.aspx?t=', '"')
        self.__mark = t

        return 1

    def block_search_init(self):
        headers = {
            "Host":"search.lionairthai.com",
            "Connection":"keep-alive",
            "Cache-Control":"max-age=0",
            "Origin":"https://search.lionairthai.com",
            "Content-Type":"application/x-www-form-urlencoded",
            "Upgrade-Insecure-Requests":"1",
            "User-Agent":self.__ua,
            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Sec-Fetch-Site":"same-origin",
            "Sec-Fetch-Mode":"navigate",
            "Sec-Fetch-User":"?1",
            "Sec-Fetch-Dest":"document",
            "Referer":"https://search.lionairthai.com/",
            "Accept-Encoding":"gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8,hy;q=0.7,as;q=0.6,ast;q=0.5"
        }

        response = self.__tls.get(url="https://search.lionairthai.com/SL/BlockSearch.aspx?t=" + self.__mark, headers=headers)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, 200)

        return response.to_text()

    def block_search(self,data):
        headers = {
            "Host":"search.lionairthai.com",
            "Connection":"keep-alive",
            "Cache-Control":"max-age=0",
            "Origin":"https://search.lionairthai.com",
            "Content-Type":"application/x-www-form-urlencoded",
            "Upgrade-Insecure-Requests":"1",
            "User-Agent":self.__ua,
            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Sec-Fetch-Site":"same-origin",
            "Sec-Fetch-Mode":"navigate",
            "Sec-Fetch-User":"?1",
            "Sec-Fetch-Dest":"document",
            "Referer":"https://search.lionairthai.com/",
            "Accept-Encoding":"gzip, deflate, br, zstd",
            "Accept-Language":"en-AU,en;q=0.9,ak;q=0.8,sq;q=0.7,am;q=0.6,ar;q=0.5,zh-CN;q=0.4,zh;q=0.3"
        }

        response = self.__tls.post(url="https://search.lionairthai.com/SL/BlockSearch.aspx?t=" + self.__mark, headers=headers,data=data)
        if response.status != 302:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, 302)

    @retry_decorator([(ServiceStateEnum.CLOUD_FLARE_CHECK_FAILURE,(cloudflare_feedback,init_cloudflare))])
    def get_flight_search(self):
        #self.init_cloudflare()
        headers = {
            "Host": "search.lionairthai.com",
            "Connection": "keep-alive",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/json; charset=UTF-8",
            "User-Agent": self.__ua,
            "sec-ch-ua-platform-version": "\"10.0.0\"",
            "Origin": "https://search.lionairthai.com",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Referer": "https://search.lionairthai.com/",
            "Accept-Encoding":"gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8,hy;q=0.7,as;q=0.6,ast;q=0.5"
        }

        response = self.__tls.post(url="https://search.lionairthai.com/SL/Flight.aspx/GetFlightSearch", headers=headers,data={'t':self.__mark})
        if response.status != 200:
            if response.status == 403:
                self.__err_type = 1
                raise ServiceError(ServiceStateEnum.CLOUD_FLARE_CHECK_FAILURE)
            if response.status == 429:
                self.__err_type = 2
                raise ServiceError(ServiceStateEnum.CLOUD_FLARE_CHECK_FAILURE)
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, 200)
        return response.to_dict()

    @retry_decorator([(ServiceStateEnum.CLOUD_FLARE_CHECK_FAILURE,[cloudflare_feedback,init_cloudflare]),(ServiceStateEnum.CURL_EXCEPTION,init_cloudflare)])
    def search_init(self,dep_airport: str,arr_airport: str,dep_date: str,adt_number: int,chd_number: Optional[int] = 0):
        headers = {
            "Host": "search.lionairthai.com",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": self.__ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Sec-Fetch-Site": "same-site",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-User": "?1",
            "Sec-Fetch-Dest": "document",
            "Referer": "https://www.lionairthai.com/",
            "Accept-Encoding":"gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8,hy;q=0.7,as;q=0.6,ast;q=0.5"
        }

        data = {
            'aid': 207,
            'depCity': dep_airport,
            'arrCity': arr_airport,
            'Jtype': 1,
            'depDate': dep_date,
            'arrDate':dep_date,
            'adult1': adt_number,
            'child1': chd_number,
            'infant1': 0,
            'promotioncode': '',
            # 'df': 'UK',
            # 'afid': '0',
            'b2b': 0,
            # 'St': 'fa',
            # 'DFlight': 'false',
            # 'roomcount': 1,
            'sid': self.__sid,
            'culture': 'en-GB'
        }

        data = urllib.parse.urlencode(data)

        print(data)
        url = "https://search.lionairthai.com/search.aspx?" + data
        response = self.__tls.get(url=url, headers=headers)

        if response.status != 200:
            if response.status == 403:
                self.__err_type = 1
                raise ServiceError(ServiceStateEnum.CLOUD_FLARE_CHECK_FAILURE)
            if response.status == 429:
                self.__err_type = 2
                raise ServiceError(ServiceStateEnum.CLOUD_FLARE_CHECK_FAILURE)
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, 200)

        self.__mark = StringUtil.extract_between(response.to_text(), 'default.aspx?t=', '\'')

    def booking_html(self):
        self.init_cloudflare()
        headers = {
            "Host":"search.lionairthai.com",
            "Connection":"keep-alive",
            "Cache-Control":"max-age=0",
            "sec-ch-ua-platform":"\"Windows\"",
            "Origin":"https://search.lionairthai.com",
            "Content-Type":"application/x-www-form-urlencoded",
            "Upgrade-Insecure-Requests":"1",
            "User-Agent":self.__ua,
            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Sec-Fetch-Site":"same-origin",
            "Sec-Fetch-Mode":"navigate",
            "Sec-Fetch-User":"?1",
            "Sec-Fetch-Dest":"document",
            "Referer":"https://search.lionairthai.com/",
            "Accept-Encoding":"gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8,hy;q=0.7,as;q=0.6,ast;q=0.5"
        }

        response = self.__tls.get(url=f"https://search.lionairthai.com/SL/Flight.aspx?t={self.__mark}",headers=headers)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, 200)
        return response.to_text()

    def get_package_summary(self,data):
        headers = {
            "Host":"search.lionairthai.com",
            "Connection":"keep-alive",
            "X-Requested-With":"XMLHttpRequest",
            "sec-ch-ua-full-version":"\"140.0.7339.81\"",
            "Accept":"application/json, text/javascript, */*; q=0.01",
            "Content-Type":"application/json; charset=UTF-8",
            "User-Agent":self.__ua,
            "sec-ch-ua-platform-version":"\"10.0.0\"",
            "Origin":"https://search.lionairthai.com",
            "Sec-Fetch-Site":"same-origin",
            "Sec-Fetch-Mode":"cors",
            "Sec-Fetch-Dest":"empty",
            "Referer":"https://search.lionairthai.com/",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8,hy;q=0.7,as;q=0.6,ast;q=0.5"
        }

        submit_data = "{'Req':'"+json.dumps(data)+"','t':'"+self.__mark+"'}"
        response = self.__tls.post(url='https://search.lionairthai.com/SL/Flight.aspx/GetPackageSummary',headers=headers,data=submit_data)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, 200)

    def passenger_html(self):
        headers = {
            "Host":"search.lionairthai.com",
            "Connection":"keep-alive",
            "Cache-Control":"max-age=0",
            "Upgrade-Insecure-Requests":"1",
            "User-Agent":self.__ua,
            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Sec-Fetch-Site":"same-origin",
            "Sec-Fetch-Mode":"navigate",
            "Sec-Fetch-User":"?1",
            "Sec-Fetch-Dest":"document",
            "Referer":"https://search.lionairthai.com/",
            "Accept-Encoding":"gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8,hy;q=0.7,as;q=0.6,ast;q=0.5"
        }

        response = self.__tls.get(url=f'https://search.lionairthai.com/SL/Passenger.aspx?t={self.__mark}',headers=headers)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, 200)
        return response.to_text()

    def booking(self,submit_data):
        headers = {
        "Host":"search.lionairthai.com",
        "Connection":"keep-alive",
        "Cache-Control":"max-age=0",
        "Origin":"https://search.lionairthai.com",
        "Content-Type":"application/x-www-form-urlencoded",
        "Upgrade-Insecure-Requests":"1",
        "User-Agent":self.__ua,
        "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Sec-Fetch-Site":"same-origin",
        "Sec-Fetch-Mode":"navigate",
        "Sec-Fetch-User":"?1",
        "Sec-Fetch-Dest":"document",
        "Referer":"https://search.lionairthai.com/",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8,hy;q=0.7,as;q=0.6,ast;q=0.5"
    }

        response = self.__tls.post(url=f"https://search.lionairthai.com/SL/Flight.aspx?t={self.__mark}",
                                   headers=headers,
                                   data=submit_data)

        check_text = response.to_text().find('Your total price has changed from')

        if response.status != 302 and check_text == -1:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, 302)


    def passenger_add(self,submit_data):
        headers = {
            "Host":"search.lionairthai.com",
            "Connection":"keep-alive",
            "X-MicrosoftAjax":"Delta=true",
            "Content-Type":"application/x-www-form-urlencoded; charset=UTF-8",
            "User-Agent":self.__ua,
            "sec-ch-ua-platform-version":"\"10.0.0\"",
            "Accept":"*/*",
            "Origin":"https://search.lionairthai.com",
            "Sec-Fetch-Site":"same-origin",
            "Sec-Fetch-Mode":"cors",
            "Sec-Fetch-Dest":"empty",
            "Referer":"https://search.lionairthai.com/",
            "Accept-Encoding":"gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8,hy;q=0.7,as;q=0.6,ast;q=0.5"
        }

        response = self.__tls.post(url=f"https://search.lionairthai.com/SL/Passenger.aspx?t={self.__mark}",
                                   headers=headers,
                                   data=submit_data)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, 200)
        return response.to_text()

    def optional_add_ons_html(self):
        headers = {
            "Host":"search.lionairthai.com",
            "Connection":"keep-alive",
            "Upgrade-Insecure-Requests":"1",
            "User-Agent":self.__ua,
            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Sec-Fetch-Site":"same-origin",
            "Sec-Fetch-Mode":"navigate",
            "Sec-Fetch-Dest":"document",
            "Referer":"https://search.lionairthai.com/",
            "Accept-Encoding":"gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8,hy;q=0.7,as;q=0.6,ast;q=0.5"
        }


        response = self.__tls.get(url=f'https://search.lionairthai.com/SL/OptionalAddOns.aspx?t={self.__mark}',headers=headers)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, 200)
        return response.to_text()

    def optional_add_ons(self,data):
        headers = {
            "Host":"search.lionairthai.com",
            "Connection":"keep-alive",
            "Cache-Control":"max-age=0",
            "Origin":"https://search.lionairthai.com",
            "Content-Type":"application/x-www-form-urlencoded",
            "Upgrade-Insecure-Requests":"1",
            "User-Agent":self.__ua,
            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Sec-Fetch-Site":"same-origin",
            "Sec-Fetch-Mode":"navigate",
            "Sec-Fetch-User":"?1",
            "Sec-Fetch-Dest":"document",
            "Referer":"https://search.lionairthai.com/",
            "Accept-Encoding":"gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8,hy;q=0.7,as;q=0.6,ast;q=0.5"
        }

        response = self.__tls.post(url=f'https://search.lionairthai.com/SL/OptionalAddOns.aspx?t={self.__mark}',headers=headers,data=data)
        if response.status != 302:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, 302)

        return response

    def booking_payment_html(self):
        headers = {
            "Host":"search.lionairthai.com",
            "Connection":"keep-alive",
            "Cache-Control":"max-age=0",
            "Upgrade-Insecure-Requests":"1",
            "User-Agent":self.__ua,
            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Sec-Fetch-Site":"same-origin",
            "Sec-Fetch-Mode":"navigate",
            "Sec-Fetch-User":"?1",
            "Sec-Fetch-Dest":"document",
            "Referer":"https://search.lionairthai.com/",
            "Accept-Encoding":"gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8,hy;q=0.7,as;q=0.6,ast;q=0.5"
        }

        response = self.__tls.get(url=f'https://search.lionairthai.com/SL/FlightBooking.aspx?t={self.__mark}',headers=headers)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, 200)
        return response.to_text()

    def booking_payment(self, data):
        headers = {
            "Host":"search.lionairthai.com",
            "Connection":"keep-alive",
            "Cache-Control":"max-age=0",
            "Origin":"https://search.lionairthai.com",
            "Content-Type":"application/x-www-form-urlencoded",
            "Upgrade-Insecure-Requests":"1",
            "User-Agent":self.__ua,
            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Sec-Fetch-Site":"same-origin",
            "Sec-Fetch-Mode":"navigate",
            "Sec-Fetch-User":"?1",
            "Sec-Fetch-Dest":"document",
            "Referer":"https://search.lionairthai.com/",
            "Accept-Encoding":"gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8,hy;q=0.7,as;q=0.6,ast;q=0.5"
        }

        response = self.__tls.post(url=f'https://search.lionairthai.com/SL/FlightBooking.aspx?t={self.__mark}',headers=headers,data=data)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, 200)

        return response.to_text()

    def redirect_link(self,data):
        headers = {
            "Host":"search.lionairthai.com",
            "Connection":"keep-alive",
            "Cache-Control":"max-age=0",
            "Origin":"https://search.lionairthai.com",
            "Content-Type":"application/x-www-form-urlencoded",
            "Upgrade-Insecure-Requests":"1",
            "User-Agent":self.__ua,
            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Sec-Fetch-Site":"same-origin",
            "Sec-Fetch-Mode":"navigate",
            "Sec-Fetch-Dest":"document",
            "Referer":"https://search.lionairthai.com/",
            "Accept-Encoding":"gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8,hy;q=0.7,as;q=0.6,ast;q=0.5"
        }

        response = self.__tls.post(url='https://search.lionairthai.com/securepayment/RedirectLink.aspx',headers=headers,data=data)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, 200)

        return response.to_text()

    def redirect_url(self,location: str):

        headers = {
            "Host":"search.lionairthai.com",
            "Connection":"keep-alive",
            "User-Agent":self.__ua,
            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Sec-Fetch-Site":"same-site",
            "Sec-Fetch-Mode":"navigate",
            "Sec-Fetch-User":"?1",
            "Sec-Fetch-Dest":"document",
            "Referer":"https://www.lionairthai.com/",
            "Accept-Encoding":"gzip, deflate, br, zstd",
            "Accept-Language":"zh-CN,zh;q=0.9,en-CA;q=0.8,en;q=0.7,id;q=0.6"
        }

        response = self.__tls.get(url=location,headers=headers)
        return response



    def online_add_on_booking(self,pnr: str,last_name: str,first_name: str):
        self.init_cloudflare()
        headers = {
            "Host":"search.lionairthai.com",
            "Connection":"keep-alive",
            "Cache-Control":"max-age=0",
            "Origin":"https://www.lionairthai.com",
            "Content-Type":"application/x-www-form-urlencoded",
            "Upgrade-Insecure-Requests":"1",
            "User-Agent":self.__ua,
            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Sec-Fetch-Site":"same-site",
            "Sec-Fetch-Mode":"navigate",
            "Sec-Fetch-User":"?1",
            "Sec-Fetch-Dest":"document",
            "Referer":"https://www.lionairthai.com/",
            "Accept-Encoding":"gzip, deflate, br, zstd",
            "Accept-Language":"zh-CN,zh;q=0.9,en-CA;q=0.8,en;q=0.7,id;q=0.6"
        }

        data = f'opr={pnr}&ofn={first_name}&oln={last_name}'

        response = self.__tls.post(url="https://search.lionairthai.com/sl/onlineaddonbooking.aspx",headers=headers,data=data)
        if response.status != 302:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, 302)

        response = self.redirect_url('https://search.lionairthai.com' + response.headers['location'])
        if response.status != 302:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, 302)

        response = self.redirect_url('https://search.lionairthai.com' + response.headers['location'])
        if response.status != 302:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, 302)


        location = response.headers['location']
        response = self.redirect_url('https://search.lionairthai.com' + response.headers['location'])
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, 200)

        return response.to_text(),location


    def manage_addons(self,data,location):
        headers = {
            "Host":"search.lionairthai.com",
            "Connection":"keep-alive",
            "Origin":"https://search.lionairthai.com",
            "Content-Type":"application/x-www-form-urlencoded",
            "Upgrade-Insecure-Requests":"1",
            "User-Agent":self.__ua,
            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Sec-Fetch-Site":"same-origin",
            "Sec-Fetch-Mode":"navigate",
            "Sec-Fetch-User":"?1",
            "Sec-Fetch-Dest":"document",
            "Accept-Encoding":"gzip, deflate, br, zstd",
            "Accept-Language":"zh-CN,zh;q=0.9,en-CA;q=0.8,en;q=0.7,id;q=0.6"
        }

        url_p = urllib.parse.urlparse(location)
        t = urllib.parse.parse_qs(url_p.query)
        self.__mark = t['t'][0]
        data = urlencode(data,doseq=True)
        response = self.__tls.post(url=f"https://search.lionairthai.com/{location}",headers=headers,data=data)
        if response.status != 302:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, 302)

    def get_meals(self):
        headers = {
            "Host":"search.lionairthai.com",
            "Connection":"keep-alive",
            "Accept":"application/json, text/javascript, */*; q=0.01",
            "Content-Type":"application/json; charset=UTF-8",
            "User-Agent":self.__ua,
            "Origin":"https://search.lionairthai.com",
            "Sec-Fetch-Site":"same-origin",
            "Sec-Fetch-Mode":"cors",
            "Sec-Fetch-Dest":"empty",
            "Referer":"https://search.lionairthai.com/",
            "Accept-Encoding":"gzip, deflate, br, zstd",
            "Accept-Language":"zh-CN,zh;q=0.9,en-CA;q=0.8,en;q=0.7,id;q=0.6"
        }

        data = {'t':self.__mark}

        response = self.__tls.post(url='https://search.lionairthai.com/SL/OptionalAddOns.aspx/GetMeals',headers=headers,data=data)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, 200)

        return response.to_dict()


