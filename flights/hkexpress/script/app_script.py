import copy
import decimal
import json
import random
from typing import Optional, List

from common.decorators.retry_decorator import retry_decorator
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.proxy_Info_model import ProxyInfoModel
from common.model.response_info_model import ResponseInfoModel
from common.tls.curl_cffi_tls import CurlCffiTls
from common.tls.danli_tls import DanLiTls
from common.utils.nocaptcha_util import NoCaptchaUtil
from flights.hkexpress.flight_common.parameter_construct import ParameterConstruct

NO_CAPTCHA = NoCaptchaUtil('e05b056e-3d13-494e-af0d-b934bff84220')


class AppScript:

    def __init__(self, proxy_info_data: ProxyInfoModel):
        self.__tls = CurlCffiTls()
        self.__danli = DanLiTls("7j58fx77bifxt2jhx01pwoek7asgp6xm")
        self.__token = None

        self.__proxy_info_data = proxy_info_data
        self.reset_proxy_ip()



    def get_ip(self):
        return self.__tls.get_ip()

    def get_proxy_str(self):
        return self.__tls.get_proxy_data().get_proxy_info_to_string()

    def reset_proxy_ip(self):
        self.__tls.initialize(self.__proxy_info_data)
        t = copy.deepcopy(self.__proxy_info_data)
        t.region = 'US'
        self.__danli.initialize(t)

    @retry_decorator([(ServiceStateEnum.CURL_EXCEPTION, reset_proxy_ip),(ServiceStateEnum.AKM_RISK_CHECK_FAILED,reset_proxy_ip)])
    def init_token(self):
        headers = {
            "accept": "application/json, text/plain, */*",
            "platform": "android",
            "x-signature": "X-SIGNATURE",
            "authorization": "",
            "x-mlc-access-token": "X-MLC-ACCESS-TOKEN",
            "x-uo-version-name": "4.8.0",
            "x-uo-version-code": "545",
            "Content-Type": "application/json",
            "Host": "api.hkexpress.com",
            "Connection": "Keep-Alive",
            "Accept-Encoding": "gzip",
            "User-Agent": "okhttp/4.11.0"
        }

        data = {"application_code": "MMB"}
        response = self.__tls.post(url="https://api.hkexpress.com/a/flt-booking-query/public/v1/nsk/token",
                                   headers=headers,
                                   data=data)

        if response.status != 201:
            if response.status == 403:
                raise ServiceError(ServiceStateEnum.AKM_RISK_CHECK_FAILED)
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

        self.__token = response.to_dict()['access_token']
        return response

    def ssr_booking(self, key_list: dict[str, List], currency_code: str) -> ResponseInfoModel:

        sumit_data = ParameterConstruct.ssr_booking_construct(key_list, currency_code)

        headers = {
            "accept": "application/json, text/plain, */*",
            "platform": "android",
            "x-signature": "X-SIGNATURE",
            "authorization": "",
            "x-mlc-access-token": "",
            "x-uo-version-name": "4.8.0",
            "x-uo-version-code": "545",
            "nsk_token": self.__token,
            "Content-Type": "application/json",
            "Host": "api.hkexpress.com",
            "Connection": "Keep-Alive",
            "Accept-Encoding": "gzip",
            "User-Agent": "okhttp/4.11.0"
        }

        response = self.__tls.post(url="https://api.hkexpress.com/a/flt-booking-query/v1/ssr-booking",
                                   headers=headers,
                                   data=sumit_data)

        if response.status != 200:
            raise Exception(f'response Status error {response.status}')
        return response

    @retry_decorator([(ServiceStateEnum.CURL_EXCEPTION, "")])
    def search(self,
               dep_airport: str,
               arr_airport: str,
               dep_date: str,
               adt_number: int,
               chd_number: int,
               infant_count: int,
               currency_code: str,
               promotion_code: Optional[str] = None,
               ret_date: Optional[str] = None) -> ResponseInfoModel:

        submit_data = ParameterConstruct.search_construct(
            dep_airport=dep_airport,
            arr_airport=arr_airport,
            dep_date=dep_date,
            ret_date=ret_date,
            adt_number=adt_number,
            chd_number=chd_number,
            currency_code=currency_code,
            promotion_code=promotion_code,
        )

        headers = {
            "accept": "application/json, text/plain, */*",
            "platform": "android",
            "x-signature": "X-SIGNATURE",
            "authorization": "",
            "nsk_token": self.__token,
            "x-mlc-access-token": "X-MLC-ACCESS-TOKEN",
            "x-uo-version-name": "4.8.0",
            "x-uo-version-code": "545",
            "Content-Type": "application/json",
            "Host": "api.hkexpress.com",
            "Connection": "Keep-Alive",
            "Accept-Encoding": "gzip",
            "User-Agent": "okhttp/4.11.0"
        }

        response = self.__tls.post(url="https://api.hkexpress.com/a/flt-booking-query/public/v1/availability/search",
                                   headers=headers, data=submit_data)

        if response.status != 200:
            raise Exception(f'response Status error {response.status}')
        return response

    def trip(self, fare_key_list: list, adt_number: int, chd_number: int, currency_code: str) -> ResponseInfoModel:

        journeys = []
        for i in fare_key_list:
            journeys.append({
                'journey_key': i[0],
                'fare_availability_key': i[1],
            })

        passengers = {}
        if chd_number != 0:
            passengers['children_count'] = chd_number

        passengers['adult_count'] = adt_number

        data = {
            "application_code": "IBE",
            "journeys": journeys,
            "passengers": passengers,
            "currency_code": currency_code,
        }

        headers = {
            "accept": "application/json, text/plain, */*",
            "platform": "android",
            "x-signature": "X-SIGNATURE",
            "authorization": "",
            "x-mlc-access-token": "",
            "x-uo-version-name": "4.8.0",
            "x-uo-version-code": "545",
            "nsk_token": self.__token,
            "Content-Type": "application/json",
            "Host": "api.hkexpress.com",
            "Connection": "Keep-Alive",
            "Accept-Encoding": "gzip",
            "User-Agent": "okhttp/4.11.0",
            #"Cookie":"bb5eb2836cd502ca31b712ccad8ea34d=89b73304646b5e7503c6bc4646fd4968; _abck=DCD7748A339E752CDAB00A0A0AB6153B~-1~YAAQBAWK3oq69jmXAQAAxIdPXg4vN0DuiRrjk6oJ4ZHTn5c4gGARfphqr65doGCPW2wG1mcZcE7yYqhr1Al2dw/evbzpAyBIhJKIIpRAPhVQbTGMLR4mU8Qs7z5jAV0cI0h5kIKlKD34PXCXBbUQnVKMGN15n4/8S5NqkCK8JLsmpLBuhlivUlEXpPFCo8WfRl9qDmwVHS3OWTfg2RHCEZVqr1SaLUl55HB/LLnXsIXnO0Ljv6t/c8d0vqM5bz2p88LRP+DTWaatenbrCM85fh0tmB6fCD/B7CFjneCgH9H3XpW/pDrpsehBmsQInJlGWU6+XTPn3h/Noxa9hw+gamt5X/sRGW5fp4huNyS3xBphDxo+mMu3Dh5Eg71maCFEGAh1ymWThcNSxelXc2pGQKFL9XgnMTIj6EGp6C5qS1a6AUiaf5nV5fXuYSnxhU8Z5ZyL1w==~-1~-1~-1; bm_sz=1A0212B32FE8DC1C3547CBD9F1ACC9DC~YAAQBAWK3ou69jmXAQAAxIdPXhyq4w30HqDnavuBReLVzPQ8L/Oh4t3QOxb4rpxv5fMaG+dJdApQdHZrua3ZUZtug59ispAhHk6n3O6qBX3IV+gMd5BG3PDDJSt3B+p6QqXDnhB9DCnVcOa1QFqDUaUKzbQjh5Ecr4Y+tVngCXW25UlsJEDNrFSbSoNyZ8XgVWVqZXqDs8bC8CMngtis8IGqD+MsYOoBMG/BbEemE4/BvQemct/aEqY7tYWG1NFiQJj4ZcanVRpZvM/2+I+HSJTMU5NuWRv6Q6+7V/QXGKYEXvKNPbrO91bWKRejA6xLf4BVqky8/3NWCeduS0ucG6G1mm0pm4ZiAuVO94r1zGqo~3424818~3687993; 82cc4f13d04b8b98e45"
        }

        response = self.__tls.post(url="https://api.hkexpress.com/a/flt-booking-mgmt/v1/trip",
                                   headers=headers,
                                   data=data)


        if response.status != 200:
            if response.to_text().find('SELL_TRIP_FAILURE') != -1:
                raise ServiceError(ServiceStateEnum.BOOKING_SEAT_FAILURE)
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

        self.__token = response.to_dict()['nsk_token']['access_token']
        return response

    def validation(self,
                   journeys: List[dict],
                   passengers: List[dict],
                   contact_person: dict,
                   ssrs: List[dict],
                   currency_code: str,
                   market: str) -> ResponseInfoModel:

        submit_data = {
            "promotion_code": "",
            "market": market,
            "language": None,
            "trip_type": "OW",
            "customer_country": market,
            "selected_currency_code": currency_code,
            "application_code": "IBE",
            "infant_total_amount": "0.000000000",
            "journeys": journeys,
            "passengers": passengers,
            "contact_person": contact_person,
            "ssrs": ssrs,
        }

        headers = {
            "accept": "application/json, text/plain, */*",
            "platform": "android",
            "x-signature": "X-SIGNATURE",
            "authorization": "",
            "x-mlc-access-token": "",
            "x-uo-version-name": "4.8.0",
            "x-uo-version-code": "545",
            "nsk_token": self.__token,
            "Content-Type": "application/json",
            "Host": "manage.hkexpress.com",
            "Connection": "Keep-Alive",
            "Accept-Encoding": "gzip",
            "User-Agent": "okhttp/4.11.0"
        }

        response = self.__tls.post(url="https://manage.hkexpress.com/a/order/v1/order/validation",
                                   headers=headers, data=submit_data)

        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response

    @retry_decorator([(ServiceStateEnum.API_RESPONSE_FAILED,reset_proxy_ip)],retry_max_number=5)
    def order(self, data: dict) -> ResponseInfoModel:


        proxy = self.__danli.get_proxy_data().get_proxy_info_to_string()
        hcap_data = NO_CAPTCHA.hcaptcha_v2('e8f86135-50b1-4b09-b467-55f97dbe0296',
                                    "https://mybooking.hkexpress.com/zh-CN/flight-booking/payment",
                                       self.__danli.get_proxy_data().region,
                                       proxy_data=proxy)


        # headers = {
        #     "accept": "application/json, text/plain, */*",
        #     "platform": "android",
        #     "x-signature": "X-SIGNATURE",
        #     "authorization": "",
        #     "x-mlc-access-token": "",
        #     "x-uo-version-name": "4.8.0",
        #     "x-uo-version-code": "545",
        #     "x-hcaptcha-response": token,
        #     "nsk_token": self.__token,
        #     "Content-Type": "application/json",
        #     "Host": "manage.hkexpress.com",
        #     "Connection": "Keep-Alive",
        #     "Accept-Encoding": "gzip",
        #     "User-Agent": "okhttp/4.11.0"
        # }

        headers = {
            # "Host":"manage.hkexpress.com",
            "Connection":"keep-alive",
            "Authorization":"Bearer",
            "X-HCAPTCHA-RESPONSE":hcap_data['data']['generated_pass_UUID'],
            "nsk_token":self.__token,
            # "sec-ch-ua-mobile":"?0",
            "X-MLC-ACCESS-TOKEN":"",
            "X-SIGNATURE":"dummy",
            #"User-Agent":f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{random.randint(131,139)}.0.0.0 Safari/537.36",
            #"User-Agent": hcap_data['extra']['user-agent'],
            "Content-Type":"application/json",
            "Accept":"*/*",
            "Origin":"https://mybooking.hkexpress.com",
            # "Sec-Fetch-Site":"same-site",
            # "Sec-Fetch-Mode":"cors",
            # "Sec-Fetch-Dest":"empty",
            "Referer":"https://mybooking.hkexpress.com/",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            # "Accept-Encoding":"gzip, deflate, br, zstd",
            # "sec-ch-ua-platform":hcap_data['extra']['sec-ch-ua-platform'],
            # "sec-ch-ua":hcap_data['extra']['sec-ch-ua'],
            #"Accept-Language":hcap_data['extra']['accept-language']
            # "Accept-Language": "en-US,en;q=0.5",
        }

        headers.update(hcap_data['extra'])

        response = self.__danli.post(url="https://manage.hkexpress.com/w/order/v1/order",
                                   headers=headers,
                                   data=data)
        if response.status != 202:
            if response.status == 400 and  response.to_text().find("UO_GENERIC_ERROR") != -1:
                raise ServiceError(ServiceStateEnum.HCAP_RISK_CHECK_FAILED)
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

        return response

    def get_payment_jwt(self):

        headers = {
            "accept": "application/json, text/plain, */*",
            "platform": "android",
            "x-signature": "X-SIGNATURE",
            "authorization": "",
            "x-mlc-access-token": "X-MLC-ACCESS-TOKEN",
            "x-uo-version-name": "4.8.0",
            "x-uo-version-code": "545",
            "Host": "manage.hkexpress.com",
            "Connection": "Keep-Alive",
            "Accept-Encoding": "gzip",
            "User-Agent": "okhttp/4.11.0"
        }

        response = self.__tls.get(url='https://manage.hkexpress.com/a/payment/v1/cardinal/jwt', headers=headers)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response

    def get_key_discovery(self):

        headers = {
            "accept": "application/json, text/plain, */*",
            "platform": "android",
            "x-signature": "X-SIGNATURE",
            "authorization": "",
            "x-mlc-access-token": "",
            "x-uo-version-name": "4.8.0",
            "x-uo-version-code": "545",
            "nsk_token": self.__token,
            "Host": "manage.hkexpress.com",
            "Connection": "Keep-Alive",
            "Accept-Encoding": "gzip",
            "User-Agent": "okhttp/4.11.0"
        }

        response = self.__tls.get(url='https://manage.hkexpress.com/a/payment/v1/payment/key-discovery', headers=headers)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response


    def look_up(self,
                order_number: str,
                card_number: str,
                exp_month: str,
                exp_year: str,
                reference_id: str,
                currency_code: str,
                last_name: str,
                first_name: str,
                total_amount: decimal.Decimal) -> ResponseInfoModel:


        data = {
            "order_number": order_number,
            "card_number": card_number,
            "card_exp_month": exp_month,
            "card_exp_year": '20' + exp_year,
            "billing_address_1": "",
            "billing_city": "",
            "billing_country_code": "",
            "billing_first_name": "",
            "billing_last_name": "",
            "billing_postal_code": "",
            "billing_full_name": f'{last_name} {first_name}',
            "billing_phone": "",
            "moblie_phone": "",
            "billing_state": "",
            "d_f_referenceId": reference_id,
            "currency_code": currency_code,
            "amount": int(total_amount.quantize(decimal.Decimal("0.00")) * 100),
            "email": "support@cardinalcommerce.com",
            "transation_mode": "P",
            "transaction_type": "C",
            "device_channel": "SDK",
            "cardinal_encrypted_data": ""
        }

        headers = {
            "accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Host": "manage.hkexpress.com",
            "Connection": "Keep-Alive",
            "Accept-Encoding": "gzip",
            "User-Agent": "okhttp/4.11.0"
        }

        response = self.__tls.post(
            url='https://manage.hkexpress.com/a/payment/v1/cardinal/mobile/cmpi-look-up/' + order_number,
            headers=headers,
            data=data)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response

    def create_payment(self,data) -> ResponseInfoModel:

        headers = {
            "accept":"application/json, text/plain, */*",
            "platform":"android",
            "x-signature":"X-SIGNATURE",
            "authorization":"",
            "x-mlc-access-token":"",
            "x-uo-version-name":"4.8.0",
            "x-uo-version-code":"545",
            "nsk_token":self.__token,
            "Content-Type":"application/json",
            "Host":"manage.hkexpress.com",
            "Connection":"Keep-Alive",
            "Accept-Encoding":"gzip",
            "User-Agent":"okhttp/4.11.0"
        }

        response = self.__tls.post(
            url='https://manage.hkexpress.com/a/payment/external/v1/payment/create-payment',
            headers=headers,
            data=data)

        if response.status != 201:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response

    def polling_status(self,order_number: str) -> ResponseInfoModel:

        headers = {
            "accept":"application/json, text/plain, */*",
            "platform":"android",
            "x-signature":"X-SIGNATURE",
            "authorization":"",
            "x-mlc-access-token":"",
            "x-uo-version-name":"4.8.0",
            "x-uo-version-code":"545",
            "nsk_token":self.__token,
            "Host":"manage.hkexpress.com",
            "Connection":"Keep-Alive",
            "Accept-Encoding":"gzip",
            "User-Agent":"okhttp/4.11.0"
        }
        response = self.__tls.get(
            url=f'https://manage.hkexpress.com/a/order/v1/order/{order_number}/polling-status',
            headers=headers
        )

        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response

    def retrieve(self,last_name: str,first_name: str,pnr: str):

        headers = {
            "accept":"application/json, text/plain, */*",
            "platform":"android",
            "x-signature":"X-SIGNATURE",
            "authorization":"",
            "x-mlc-access-token":"",
            "x-uo-version-name":"4.8.0",
            "x-uo-version-code":"545",
            "nsk_token":self.__token,
            "Content-Type":"application/json",
            "Host":"manage.hkexpress.com",
            "Connection":"Keep-Alive",
            "Accept-Encoding":"gzip",
            "User-Agent":"okhttp/4.11.0"
        }

        data = {"pnr_query_requests":[{"sales_reference":pnr,"first_name":first_name,"last_name":last_name}]}


        response = self.__tls.post(
            url=f'https://manage.hkexpress.com/a/order/v1/booking/retrieve',
            headers=headers,
            data=data
        )

        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

        return response

