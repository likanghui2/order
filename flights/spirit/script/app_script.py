import random
import string
import uuid
from typing import List, Tuple

from curl_cffi import requests

from common.decorators.retry_decorator import retry_decorator
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.proxy_Info_model import ProxyInfoModel
from common.tls.curl_cffi_tls import CurlCffiTls


class AppScript:
    def __init__(self, proxy_info_data: ProxyInfoModel):
        self.__tls = None
        self.__proxy_info_data = proxy_info_data
        self.__token = None
        self.__api_url = 'https://api.spirit.com/customermobileprod/1.0.38'
        self.__app_ver = '3.8.0 (1248)'
        self.__sessor = None
        self.__key = 'c6567af50d544dfbb3bc5dd99c6bb177'
        self.__device_id = ''.join(random.sample(string.hexdigits.lower() + string.digits, 16))
        self.__ua = 'GuestMobileApp/3.8.0 (Android 31; Build/SP1A.210812.016.C1)'

    def initialize(self):
        self.__tls = CurlCffiTls()
        self.__tls.initialize(self.__proxy_info_data)

    def get_abck(self):
        self.initialize()
        url = 'http://akamai-bmp-server.python.svc.cluster.local:1337/akamai/bmp'
        # url = 'http://192.168.1.199:1337/akamai/bmp'


        data = {
            "app": "com.spirit.customerapp",
            "lang": "en",
            "version": "3.3.4",
        }
        html = requests.post(url, json=data, timeout=20, proxies=None, verify=False)
        obj = html.json()
        if obj['sensor']:
            self.__sessor = obj['sensor']

    @retry_decorator(retry_service_error_list=[(ServiceStateEnum.AKM_RISK_CHECK_FAILED,get_abck)])
    def get_token(self):
        url = f'{self.__api_url}/v2/Token'
        if not self.__sessor:
            self.get_abck()
        headers = {
            'ocp-apim-subscription-key': self.__key,
            'correlationid': self.__device_id,
            'user-id': '',
            'Platform': 'Android',
            'App-Version': self.__app_ver,
            'accept-encoding': 'gzip',
            'user-agent': self.__ua,
            'x-dynatrace': f'MT_3_1_9417635868_22-0_{uuid.uuid4()}_1_659_32',
            # 'cache-control': 'no-cache',
            'Content-Type':'application/json; charset=UTF-8',
            'X-acf-sensor-data': self.__sessor

        }
        data = {
            "applicationName": "customerMobileApp",
            "credentials": {
                "location": "",
                "alternateIdentifier": "",
                "domain": "",
                "username": "",
                "channelType": "",
                "password": ""
            }
        }

        response = self.__tls.post(url=url, data=data, headers=headers)
        if response.status != 201:
            if response.status == 403:
                raise ServiceError(ServiceStateEnum.AKM_RISK_CHECK_FAILED)
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

        token = response.to_dict()['data']['token']
        self.__x_auth_token = token

    @retry_decorator(retry_service_error_list=[(ServiceStateEnum.AKM_RISK_CHECK_FAILED, get_abck)])
    def availability(self,
                     dep_airport: str,
                     arr_airport: str,
                     dep_date: str,
                     adult_count: int,
                     child_count: int,
                     promo_code: str,
                     currency: str) :

        url = f'{self.__api_url}/v5/Flight/Search'

        data = {
            "birthDates": [],
            "codes": {
                "currency": currency
            },
            "criteria": [{
                "dates": {
                    "beginDate": dep_date,
                    "endDate": dep_date
                },
                "searchDestinationMacs": False,
                "searchOriginMacs": False,
                "stations": {
                    "destinationStationCodes": [arr_airport],
                    "originStationCodes": [dep_airport]
                }
            }],
            "fareFilters": {
                "loyalty": "MonetaryOnly"
            },
            "passengers": {
                "types": [{
                    "count": adult_count,
                    "type": "ADT"
                }]
            },
            "promotionCode": "",
            "user_flow": "booking"
        }

        if child_count > 0:
            data['passengers']['types'].append({'count': child_count, 'type': 'CHD'})

        headers = {
            'ocp-apim-subscription-key': self.__key,
            'correlationid': self.__device_id,
            'user-id': '',
            'platform': 'Android',
            'app-version': self.__app_ver,
            'accept-encoding': 'gzip',
            'user-agent': self.__ua,
            'x-dynatrace': f'MT_3_1_8417635868_22-0_{uuid.uuid4()}_1_659_32',
            'cache-control': 'no-cache',
            'x-bearer-token': self.__x_auth_token,
            'X-acf-sensor-data': self.__sessor,
            'Content-Type': 'application/json; charset=UTF-8',
        }

        response = self.__tls.post(
            url=url,
            headers=headers,
            data=data
        )

        if response.status != 200:
            if response.status == 400 and 'There are no available flights on the dates specified' in response.text:
                raise ServiceError(ServiceStateEnum.NO_FLIGHT_DATA)
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

        return response
