import base64
import datetime
import urllib.parse
from copy import copy
from urllib.parse import urlencode

import requests
from lxml import etree

from common.decorators.retry_decorator import retry_decorator
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.proxy_Info_model import ProxyInfoModel
from common.tls.curl_cffi_tls import CurlCffiTls
from common.utils.danli_captcha_util import DanLiCaptchaUtil
from common.utils.ezcaptcha_util import EzCaptcha
from common.utils.nocaptcha_util import NoCaptchaUtil
from common.utils.string_util import StringUtil
from flights.batik.lionair.config import LionAirIdConfig

DANLI_CAPTCHA = DanLiCaptchaUtil('7j58fx77bifxt2jhx01pwoek7asgp6xm')


class WebScript:
    def __init__(self, proxy_info_data: ProxyInfoModel):
        self.__proxy = proxy_info_data

        self.__tls = CurlCffiTls()
        self.__tls.initialize(proxy_info_data, impersonate='chrome136')
        self.__ua = LionAirIdConfig.USER_AGENT
        self.__accept = LionAirIdConfig.Accept
        self.__allow_currency_list = LionAirIdConfig.Allow_Currency_List
        self.timeout = 60
        self.referer = None

    def reset_proxy_ip(self):
        self.__tls.initialize(self.__proxy, impersonate='chrome136')

    @retry_decorator([(ServiceStateEnum.API_RESPONSE_FAILED, None), (ServiceStateEnum.API_RESPONSE_EXCEPTION, None)
                      ], retry_max_number=5)
    def get_cf(self):
        # no_captcha = NoCaptchaUtil(api_key='e05b056e-3d13-494e-af0d-b934bff84220', )
        #
        # return no_captcha.solve_cf_turnstile(
        #     url=self.referer,
        #     sitekey='0x4AAAAAAB6Tql_m8NwBajXg', proxy=self.__tls.get_proxy_data().get_proxy_info_to_string(), )
        captcha = EzCaptcha("a61ac9a3a6824569a584e10937a70ec0256199")
        return captcha.solve_cf_turnstile(
            website_url=self.referer,
            website_key='0x4AAAAAAB6gzPashcOIwir9',
        )

    def cf(self, website_url):
        a = EzCaptcha(client_key='806800777df44a2e988accf2bd2561bb597959')
        solution = a.solve_cf_cookie(website_url=website_url,
                                     proxy=self.__tls.get_proxy_data().get_proxy_info_to_string())
        self.user_agent = solution["header"]["user-agent"]
        self.__tls.cookie_update(solution["cookies"])

    @retry_decorator([(ServiceStateEnum.CLOUD_FLARE_CHECK_FAILURE, reset_proxy_ip)])
    def search(self,
               dep_airport: str,
               arr_airport: str,
               adult_count: int,
               child_count: int,
               dep_date: str):
        """

        Args:
            dep_airport:
            dep_date
            arr_airport:
            adult_count: 成人数量
            child_count: 儿童数量

        Returns:
            return：官网响应数据
        """
        headers = {
            'accept': self.__accept,
            'accept-language': 'en;q=0.8',
            'priority': 'u=0, i',
            'referer': 'https://secure.superairjet.com/',
            'sec-ch-ua': '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'same-site',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': self.__ua,
        }

        params = {
            'depart': dep_airport,
            'dest.1': arr_airport,
            'trip_type': 'one way',
            'date.0': datetime.datetime.strptime(dep_date, '%Y%m%d').strftime('%d %b %Y'),
            'date.1': '',
            'persons.0': adult_count,
            'persons.1': child_count,
            'persons.2': '0',
        }

        response = self.__tls.get(
            url=f'https://secure.superairjet.com/SuperAirJetIBE/OnlineBooking.aspx?{urllib.parse.urlencode(params)}',
            headers=headers)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        self.referer = response.url
        if "onTurnstileError" in response.to_text():
            headers = {
                'user-agent': self.__ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br, zstd",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://secure.superairjet.com",
                "Connection": "keep-alive",
                "Referer": "https://secure.superairjet.com/SuperAirJetIBE/OnlineBooking.aspx?trip_type=return&depart=JKT&dest.1=PLM&date.0=14+Mar+2026&date.1=27+Mar+2026&persons.0=1&persons.1=0&persons.2=0",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-User": "?1",
                "Priority": "u=0, i",
                "TE": "trailers"
            }
            token = self.get_cf()
            print("token:", token)
            data = {
                "__EVENTTARGET": "ctl00$additionalContent$btnVerifyTurnstileToken",
                "__EVENTARGUMENT": "",
                "__VIEWSTATE": StringUtil.extract_between(response.to_text(), 'id="__VIEWSTATE" value="', '"'),
                "__VIEWSTATEGENERATOR": StringUtil.extract_between(response.to_text(),
                                                                   'id="__VIEWSTATEGENERATOR" value="',
                                                                   '"'),
                "cf-turnstile-response": token,
                "ctl00$additionalContent$hidTurnstileToken": token
            }
            response = self.__tls.post(
                url=f"https://secure.superairjet.com/SuperAirJetIBE/AvailProcessing.aspx?{urllib.parse.urlencode(params)}",
                headers=copy(headers),
                data=urlencode(copy(data)))
            print(response.url)
            if "Default" in response.location:
                raise ServiceError(ServiceStateEnum.CLOUD_FLARE_CHECK_FAILURE)

    def get_booking_html(self):
        headers = {
            "Host": "secure.superairjet.com",
            "User-Agent": self.__ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Referer": self.referer,
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Priority": "u=0, i",
            "TE": "trailers"
        }
        response = self.__tls.get(url="https://secure.superairjet.com/SuperAirJetIBE/OnlineBooking.aspx",
                                  headers=copy(headers), timeout=60)
        if response.status == 302:
            response = self.__tls.get(url=f"https://secure.superairjet.com{response.location}",
                                      headers=copy(headers), timeout=60)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

        return response.to_text()

    def get_image_code(self, img_url='https://secure.superairjet.com/SuperAirJetIBE/CaptchaGenerator.aspx'):
        headers = {
            'accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
            'accept-language': 'zh-CN,zh;q=0.9',
            'priority': 'i',
            'sec-ch-ua': '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'image',
            'sec-fetch-mode': 'no-cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': self.__ua,
        }

        response = self.__tls.get(url=img_url, headers=headers)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        print({
            "project_name": "ctc_251218",
            "image": base64.b64encode(response.data_bytes).decode('utf-8'),

        })
        r = requests.post("https://orc.l-a-j.com/runtime/text/invoke", json={
            "project_name": "ctc_251218",
            "image": base64.b64encode(response.data_bytes).decode('utf-8'),

        })
        return r.json()['data']

    @staticmethod
    def get_views_data(flight_html_str):
        xpath_data = etree.HTML(flight_html_str)
        return {
            "__EVENTTARGET": ''.join(xpath_data.xpath('''//*[@id="__EVENTTARGET"]//@value''')).strip(),
            "__EVENTARGUMENT": ''.join(xpath_data.xpath('''//*[@id="__EVENTARGUMENT"]//@value''')).strip(),
            "__VIEWSTATE": ''.join(xpath_data.xpath('''//*[@id="__VIEWSTATE"]//@value''')).strip(),
            "__VIEWSTATEGENERATOR": ''.join(xpath_data.xpath('''//*[@id="__VIEWSTATEGENERATOR"]//@value''')).strip(),
        }

    def cart_booking(self, flight_id: str, dep_airport: str,
                     arr_airport: str,
                     dep_date: datetime,
                     adult_count: int,
                     child_count: int, flight_html_str: str, img_token: dict):

        headers = {
            'User-Agent': self.__ua,
            'Accept': self.__accept,
            'Content-Type': 'application/x-www-form-urlencoded',
            'cache-control': 'max-age=0',
            'sec-ch-ua': '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'origin': 'https://secure.superairjet.com',
            'upgrade-insecure-requests': '1',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-user': '?1',
            'sec-fetch-dest': 'document',
            'referer': 'https://secure.superairjet.com/SuperAirJetIBE/OnlineBooking.aspx',
            'accept-language': 'en;q=0.8',
            'priority': 'u=0, i',
        }
        data = {
            "ctl00$ctl00$mainContent$bookingMainContent$Outbound": flight_id,
            "ctl00$ctl00$mainContent$bookingMainContent$Insurance$TravelInsurance": "No",
            "ctl00$ctl00$mainContent$bookingMainContent$CodeNumberTextBox": img_token,
            "response": "",
            "ctl00$ctl00$mainContent$bookingMainContent$txtOBCellID": flight_id,
            "ctl00$ctl00$mainContent$bookingMainContent$txtIBCellID": "oneway",
            "ctl00$ctl00$mainContent$bookingMainContent$txtOBRowID": "",
            "ctl00$ctl00$mainContent$bookingMainContent$txtIBRowID": "",
            "ctl00$ctl00$mainContent$bookingAdditionalContent$ucFlightSelectionStep2$TripType": "rbOneWay",
            "ctl00$ctl00$mainContent$bookingAdditionalContent$ucFlightSelectionStep2$ddlOri": dep_airport,
            "ctl00$ctl00$mainContent$bookingAdditionalContent$ucFlightSelectionStep2$ddlDes": arr_airport,
            "DepartureDate": dep_date.strftime('%d %b %Y'),
            "ReturnDate": (dep_date + datetime.timedelta(days=1)).strftime('%d %b %Y'),
            "ctl00$ctl00$mainContent$bookingAdditionalContent$ucFlightSelectionStep2$ddlADTCount": str(adult_count),
            "ctl00$ctl00$mainContent$bookingAdditionalContent$ucFlightSelectionStep2$ddlCNNCount": str(child_count),
            "ctl00$ctl00$mainContent$bookingAdditionalContent$ucFlightSelectionStep2$ddlINFCount": "0",
            "ctl00$ctl00$mainContent$bookingAdditionalContent$ucFlightSelectionStep2$txtDepartureDate": dep_date.strftime('%d %b %Y'),
            "ctl00$ctl00$mainContent$bookingAdditionalContent$ucFlightSelectionStep2$txtReturnDate":  (dep_date + datetime.timedelta(days=1)).strftime(
                '%d %b %Y'),
            "ctl00$ctl00$additionalContent$additionalContent$hidTurnstileToken": ""
        }
        view_data = self.get_views_data(flight_html_str=flight_html_str)
        data.update(view_data)
        data["__EVENTTARGET"] = "ctl00$ctl00$mainContent$bookingMainContent$lbContinue"

        response = self.__tls.post(url='https://secure.superairjet.com/SuperAirJetIBE/Step2.aspx', headers=headers,
                                   data=urlencode(data), timeout=60)
        if "Please enter the correct CAPTCHA code" in response.to_text():
            raise ServiceError(ServiceStateEnum.ROBOT_CHECK, )
        if response.status != 302:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

        response = self.get_booking_html()
        if "Step3.aspx" not in response:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "订单创建失败")

        return response

    def passenger_booking(self, cart_html_str: str, cart_post_data: dict):

        headers = {
            'accept': self.__accept,
            'accept-language': 'en;q=0.8',
            'cache-control': 'max-age=0',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://secure.superairjet.com',
            'priority': 'u=0, i',
            'sec-ch-ua': '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'User-Agent': self.__ua,
        }

        view_data = self.get_views_data(flight_html_str=cart_html_str)
        cart_post_data.update(view_data)
        cart_post_data["__EVENTTARGET"] = "ctl00$ctl00$mainContent$bookingMainContent$lbContinue"
        response = self.__tls.post(url='https://secure.superairjet.com/SuperAirJetIBE/Step3.aspx', headers=headers,
                                   data=urlencode(cart_post_data))

        if response.status != 302:
            if "Duplicate booking is not permitted" in response.to_text():
                raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "重复预定")
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

        response = self.get_booking_html()

        if "Additional Baggage Selection" not in response:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "添加乘客失败")

        return response

    def add_baggage(self, add_on_html_str: str, baggage_str_key: str):

        headers = {
            'accept': self.__accept,
            'accept-language': 'en;q=0.8',
            'cache-control': 'max-age=0',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://secure.superairjet.com',
            'priority': 'u=0, i',
            'referer': 'https://secure.superairjet.com/SuperAirJetIBE/OnlineBooking.aspx',
            'sec-ch-ua': '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'User-Agent': self.__ua,
        }

        add_baggage_data = {
            "ctl00$ctl00$mainContent$bookingMainContent$hdnMedSelection": "",
            "ctl00$ctl00$mainContent$bookingMainContent$hdnBagSelection": baggage_str_key,
            "pax_Meal_Sel_0_0": "",
            "ctl00$ctl00$mainContent$bookingMainContent$hdnMealSelection": "",
            "ctl00$ctl00$mainContent$bookingMainContent$hdnMealDepPorts": "",
            "ctl00$ctl00$mainContent$bookingMainContent$hdnMealArrPorts": "",
            "ctl00$ctl00$mainContent$bookingMainContent$HiddenField1": "",
            "ctl00$ctl00$mainContent$bookingMainContent$HiddenField2": "",
            "ctl00$ctl00$mainContent$bookingMainContent$HiddenField3": "",
            "paxSel_0_0": ""
        }
        view_data = self.get_views_data(flight_html_str=add_on_html_str)
        add_baggage_data.update(view_data)
        add_baggage_data["__EVENTTARGET"] = "ctl00$ctl00$mainContent$bookingMainContent$lbContinue"
        response = self.__tls.post(url='https://secure.superairjet.com/SuperAirJetIBE/AddOns.aspx', headers=headers,
                                   data=urlencode(add_baggage_data), timeout=60)

        if response.status != 302:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

        response = self.get_booking_html()
        if "Payment Details" not in response:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "跳转支付页面失败")
        return response

    def atm_payment(self, pay_data, add_baggage_html):
        headers = {
            'accept': self.__accept,
            'accept-language': 'en;q=0.8',
            'cache-control': 'max-age=0',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://secure.superairjet.com',
            'priority': 'u=0, i',
            'referer': 'https://secure.superairjet.com/SuperAirJetIBE/OnlineBooking.aspx',
            'sec-ch-ua': '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'User-Agent': self.__ua,
        }
        view_data = self.get_views_data(flight_html_str=add_baggage_html)
        pay_data.update(view_data)

        response = self.__tls.post(url='https://secure.superairjet.com/SuperAirJetIBE/Payment.aspx', headers=headers,
                                   data=urlencode(pay_data), timeout=60)
        if response.status != 302:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

        response = self.get_booking_html()
        if "Booking Reference" not in response:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "获取pnr失败")
        return response
