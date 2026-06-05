from common.errors.service_error import ServiceStateEnum, ServiceError
from common.model.proxy_Info_model import ProxyInfoModel
from common.tls.curl_cffi_tls import CurlCffiTls


class AppScript:
    def __init__(self, proxy_info_data: ProxyInfoModel):
        self.__tls = CurlCffiTls()
        self.__proxy_info = proxy_info_data
        self.__jwt_token = None
        pass

    def initialize(self):
        self.__tls = CurlCffiTls(impersonate="chrome136")
        self.__tls.initialize(self.__proxy_info)

    def init_jwt(self):
        headers = {
            "Host": "www.airasia.com",
            "Connection": "keep-alive",
            "sec-ch-ua-full-version-list": "\"Google Chrome\";v=\"141.0.7390.55\",\"Not?A_Brand\";v=\"8.0.0.0\",\"Chromium\";v=\"141.0.7390.55\"",
            "sec-ch-ua-platform": "\"Windows\"",
            "sec-ch-ua": "\"Google Chrome\";v=\"141\",\"Not?A_Brand\";v=\"8\",\"Chromium\";v=\"141\"",
            "sec-ch-ua-bitness": "\"64\"",
            "sec-ch-ua-model": "\"\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-arch": "\"x86\"",
            "sec-ch-ua-full-version": "\"141.0.7390.55\"",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
            "sec-ch-ua-platform-version": "\"10.0.0\"",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "no-cors",
            "Sec-Fetch-Dest": "image",
            "Referer": "https://www.airasia.com/flights/search/?origin=HKG&destination=BKK&departDate=17/10/2025&tripType=O&adult=1&child=0&infant=0&locale=zh-hk&currency=CNY&airlineProfile=all&type=paired&cabinClass=economy&upsellWidget=true&upsellPremiumFlatbedWidget=true&isOC=true&isDC=true&uce=true&ancillaryAbTest=false&isAirasiaFlightOnly=true&providers=&taIDs=",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "en,ca;q=0.9,ceb;q=0.8,ckb;q=0.7"
        }
        response = self.__tls.get(url="https://www.airasia.com/en/gb", headers=headers)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

        data_text = response.to_text()
        start_index = data_text.find('"jwtToken":"') + len('"jwtToken":"')
        data_text = data_text[start_index:]
        end_index = data_text.find('",')
        data_text = data_text[:end_index]
        self.__jwt_token = data_text

    def search(self,
               dep_airport: str,
               arr_airport: str,
               currency_code: str,
               dep_date: str,
               adt_number: int,
               chd_number: int):
        headers = {
            "accept": "application/json, text/plain, */*",
            "x-fp-tkn": "dkmd",
            "x-cs-trace-id": "12334",
            "channel_hash": "33bf3283c72969b76042f5b7a7c8be0b2075519c31ee853d728420eeb7ce043d",
            "user-type": "MEMBER",
            "authorization":"Bearer " + self.__jwt_token,
            #"authorization": "Bearer eyJraWQiOiJmbGlnaHRzYW5kcm9pZCIsImFsZyI6IlJTMjU2In0.eyJqdGkiOiJhMjUzNmJlZC0yODk1LTRkN2MtOWUyYy04NWUzNzg4MDc2ODAiLCJpc3MiOiJvdGFAZmxpZ2h0cy5haXJhc2lhLmNvbSIsInN1YiI6ImZsaWdodHNhbmRyb2lkIiwiaWF0IjoxNzU5ODcwMzc1LCJleHAiOjE3NTk4NzE1NzV9.AOPEk2USNFtzRdc6IrjB0_ABGAzvYZR0kN3TOe0mRlyKckxrTdF2hdzjDkyjYxnqJDZzSelSjAVwrnb3zvh_6sMQOiIKPATwwpMMmtUvfkLpmeNq_QPLSYupYVIlrBKWWYH3oCERtrVS7okX0di7Ycl3lUeEDAXgnt_3ZjHLF_9G9YKuh_84F4juMaYZpm-BwmeRM3kDxLs8alGbTByzf0W9wSbVuqgWHiWFbBifltaC4MYazo6N8yQNQyum2sNPGAwSm8VW4RZBfB48viJ0b9Gde10QbwglbWpykrD5-Ef_2TQcQ2JDaeWGuxsZDylIb9S8DsxqsIjdDvv2O__iEqS4fzjPb3pENtkws0IWbCp8dv799t1lavjLLhOhak9bD1bRa4AnOBhgxztWnxsZU8GswcSzx673YDhMvrMwE7Sq3mRJOok4xSOa192fuTLz92AlS3U42KTxlaic_7AakLvk0D3NIW2Xl0d8vMIMopPDVuPwHYl7x6b9YIm0G_tmWxbdfgpuEgGh4r7fjbcNOJmtEX-e2Sx4WxtBniDhex2Y92TkgBTaxwLwEeWzpwjUZsX0LKuXcHh0Fex6Rm2hBMMcJBN9EBc8db2V4X2u196tv39LdXH544zflbG_n1NJUivbTQ9tnXkG2Q7NtK9UWbHAj3ReFlX0UuikbVImy5Iq",
            "ga-id": "59727de5-5ea9-43f2-a7c7-661bfa6a56ab",
            "Content-Type": "application/json",
            "Host": "flights.airasia.com",
            "Connection": "Keep-Alive",
            "Accept-Encoding": "gzip",
            "User-Agent": "okhttp/4.12.0"
        }

        data = {
            "consumerId": "sup1234",
            "flightJourney": {
                "journeyType": "O",
                "journeyDetails": [{
                    "origin": dep_airport,
                    "destination": arr_airport,
                    "departDate": dep_date,
                    "returnDate": None
                }],
                "passengers": {
                    "adult": adt_number,
                    "child": chd_number,
                    "infant": 0
                }
            },
            "searchContext": {
                "promocode": "",
                "sort": "cheapest",
                "filters": {
                    "cabin": {
                        "cabinClass": "ECONOMY",
                        "applyMixedClasses": False
                    },
                    "stops": {
                        "stopType": "ANY",
                        "allowOvernight": False
                    },
                    "duration": {
                        "maxTravelTimeInHrs": 59,
                        "maxStopoverTimeInHrs": 25,
                        "minStopoverTimeInHrs": 0
                    },
                    "carriers": {
                        "allowAllCarriers": False,
                        "onlyAllowedCarriers": ["AK", "D7", "FD", "QZ", "XJ", "Z2", "KT"],
                        "excludedCarriers": []
                    },
                    "departAirports": {
                        "allowAllAirports": True,
                        "allowedDepartAirports": []
                    },
                    "returnAirports": {
                        "allowAllAirports": True,
                        "allowedReturnAirports": []
                    },
                    "journey": "O"
                }
            },
            "userContext": {
                "locale": "zh-cn",
                "currency": currency_code,
                "geoId": "JP",
                "platform": "android",
                "version": 4661,
                "experimentVariants": []
            },
            "ssoDetails": {
                "accessToken": "",
                "refreshToken": "",
                "userId": ""
            },
            "selectedDepartFlight": None
        }
        response = self.__tls.post(
            url="https://flights.airasia.com/mobile/fp/search/flights/v5/aggregated-results?page=1&include_list=searchResults,currency,content,featureFlags,locale,vouchers,upsellSnap,upsellPremiumFlatBed&airlineProfile=all&type=paired&isPromoMessagesByCode=true&isOriginCity=true&isDestinationCity=true&uce=true",
            headers=headers,
            data=data)

        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)

        return response.to_dict()
