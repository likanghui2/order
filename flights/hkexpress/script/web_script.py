from typing import Optional

from common.model.proxy_Info_model import ProxyInfoModel
from common.model.response_info_model import ResponseInfoModel
from common.tls.curl_cffi_tls import CurlCffiTls
from flights.hkexpress.config import Config


class WebScript:

    def __init__(self, proxy_info_data: ProxyInfoModel):
        self.__tls = CurlCffiTls()
        self.__tls.initialize(proxy_info_data)

    def search(self,
               dep_airport: str,
               arr_airport: str,
               dep_date: str,
               adt_number: int,
               chd_number: int,
               infant_count: int,
               currency_code: str,
               ret_date: Optional[str] = None) -> ResponseInfoModel:

        flights_data = {
            "origin": dep_airport,
            "destination": arr_airport,
            "begin_date": dep_date,
        }

        if ret_date:
            flights_data["end_date"] = ret_date

        submit_data = {
            "application_code": "IBE",
            "flights": [flights_data],
            "currency_code": currency_code,
            "promotion_code": "",
            "passengers": {
                "adult_count": adt_number,
                "infant_count": infant_count,
                "children_count": chd_number
            }
        }

        headers = {
            "Host": "api.hkexpress.com",
            "Connection": "keep-alive",
            "sec-ch-ua-platform": "\"Windows\"",
            "Authorization": "Bearer",
            "X-SIGNATURE": "dummy",
            "User-Agent": Config.USER_AGENT,
            "Content-Type": "application/json",
            "Accept": "*/*",
            "Origin": "https://mybooking.hkexpress.com",
            "Sec-Fetch-Site": "same-site",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Referer": "https://mybooking.hkexpress.com/",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9,af;q=0.8,ak;q=0.7,sq;q=0.6"
        }

        response = self.__tls.post(url="https://api.hkexpress.com/w/flt-booking-query/public/v1/availability/search",
                                   headers=headers, data=submit_data)

        if response.status != 200:
            raise Exception(f'response Status error {response.status}')
        return response

    def trip(self, fare_key_list: list, adt_number: int, chd_number: int, currency_code: str) -> ResponseInfoModel:
        journeys = []

        for i in fare_key_list:
            journeys.append({
                'journey_key': fare_key_list[i][0],
                'fare_availability_key': fare_key_list[i][1],
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
            "Host": "api.hkexpress.com",
            "Connection": "keep-alive",
            "sec-ch-ua-platform": "\"Windows\"",
            "Authorization": "Bearer",
            "sec-ch-ua-mobile": "?0",
            "X-MLC-ACCESS-TOKEN": "",
            "X-SIGNATURE": "dummy",
            "User-Agent": Config.USER_AGENT,
            "Content-Type": "application/json",
            "Accept": "*/*",
            "Origin": "https://mybooking.hkexpress.com",
            "Sec-Fetch-Site": "same-site",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Referer": "https://mybooking.hkexpress.com/",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9,af;q=0.8,ak;q=0.7,sq;q=0.6"
        }

        response = self.__tls.post(url="https://api.hkexpress.com/w/flt-booking-mgmt/v1/trip",
                                   headers=headers,
                                   data=data)

        return response
