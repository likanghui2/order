import json
import uuid
from typing import Optional

from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.proxy_Info_model import ProxyInfoModel
from common.tls.curl_cffi_tls import CurlCffiTls
from flights.thaiairways_tg.config import ThaiairwaysConfig


class WebScript:
    def __init__(self, proxy_info: Optional[ProxyInfoModel] = None):
        self.__proxy_info = proxy_info
        self.__tls = CurlCffiTls()
        self.__ua = ThaiairwaysConfig.UA
        self.__uuid = str(uuid.uuid4())
        self.__booking_authorization = None
        self.__booking_session_id = None

    def initialize_session(self):
        self.__tls.initialize(self.__proxy_info, impersonate="chrome120")

    def auth_www(self, airport_data: list[tuple[str, str, str]]):
        first_route = airport_data[0]
        response = self.__tls.post(
            url='https://www.thaiairways.com/flight/auth',
            headers=self.__www_headers("https://www.thaiairways.com/booking/select-flight/", auth=False),
            data=json.dumps({
                "itineraries": [
                    {
                        "id": 1,
                        "originLocationCode": first_route[0],
                        "destinationLocationCode": first_route[1],
                        "departureDateTime": f"{first_route[2]}T00:00:00.000"
                    }
                ],
                "facts": {
                    "EXTERNAL_ID1": "IN_NORMAL",
                    "EXTERNAL_ID9": "India"
                },
                "officeId": None,
                "countryCode": "jp",
                "languageCode": "en",
                "user": "website",
                "userGroup": "online"
            }),
            timeout=60,
        )
        self.__check_response(response, 200)
        data = response.to_dict()
        self.__booking_authorization = f"{data['token_type']} {data['access_token']}"
        self.__booking_session_id = next(
            (value for key, value in response.headers.items() if key.lower() == "booking_session_id"),
            None
        )

    def www_search_flight(self, data: dict) -> dict:
        response = self.__tls.post(
            url='https://www.thaiairways.com/flight/search/air-bounds',
            headers=self.__www_headers("https://www.thaiairways.com/booking/select-flight/"),
            data=json.dumps(data),
            timeout=60,
        )
        if "NO FLIGHTS FOUND" in response.to_text():
            raise ServiceError(ServiceStateEnum.NO_FLIGHT_DATA)
        self.__check_response(response, 200)
        return response.to_dict()

    def www_sell_flight(self, keys: list[str]) -> dict:
        response = self.__tls.post(
            url='https://www.thaiairways.com/cart/',
            headers=self.__www_headers("https://www.thaiairways.com/booking/select-flight/"),
            data=json.dumps({"airBoundIds": keys}),
            timeout=60,
        )
        self.__check_response(response, 201)
        return response.to_dict()

    def www_retrieve_cart(self, cart_id: str) -> dict:
        response = self.__tls.post(
            url='https://www.thaiairways.com/cart/retrieve',
            headers=self.__www_headers("https://www.thaiairways.com/booking/passenger-details/"),
            data=json.dumps({"cartId": cart_id}),
            timeout=60,
        )
        self.__check_response(response, 200)
        return response.to_dict()

    def www_baggage_policies(self, cart_id: str) -> dict:
        response = self.__tls.post(
            url='https://www.thaiairways.com/flight/baggage/policies',
            headers=self.__www_headers("https://www.thaiairways.com/booking/passenger-details/"),
            data=json.dumps({"cartId": cart_id}),
            timeout=60,
        )
        self.__check_response(response, 200)
        return response.to_dict()

    def www_add_passenger(self, data: dict) -> dict:
        response = self.__tls.post(
            url='https://www.thaiairways.com/cart/traveler',
            headers=self.__www_headers("https://www.thaiairways.com/booking/passenger-details/"),
            data=json.dumps(data),
            timeout=60,
        )
        self.__check_response(response, 200)
        return response.to_dict()

    def www_add_contacts(self, data: dict) -> dict:
        response = self.__tls.post(
            url='https://www.thaiairways.com/cart/contact',
            headers=self.__www_headers("https://www.thaiairways.com/booking/passenger-details/"),
            data=json.dumps(data),
            timeout=60,
        )
        self.__check_response(response, 201)
        return response.to_dict()

    def www_duplicate_traveler(self, cart_id: str) -> dict:
        response = self.__tls.post(
            url='https://www.thaiairways.com/cart/traveler/duplicate',
            headers=self.__www_headers("https://www.thaiairways.com/booking/passenger-details/"),
            data=json.dumps({"cartId": cart_id}),
            timeout=60,
        )
        self.__check_response(response, 200)
        return response.to_dict()

    def www_orders(self, cart_id: str, travelers: list[dict]) -> dict:
        response = self.__tls.post(
            url='https://www.thaiairways.com/order/',
            headers=self.__www_headers("https://www.thaiairways.com/booking/passenger-details/"),
            data=json.dumps({
                "cartId": cart_id,
                "travelers": travelers,
            }),
            timeout=60,
        )
        self.__check_response(response, 201)
        return response.to_dict()

    def www_order_retrieve(self, order_id: str, last_name: str) -> dict:
        response = self.__tls.post(
            url='https://www.thaiairways.com/order/retrieve',
            headers=self.__www_headers("https://www.thaiairways.com/booking/extra-services/"),
            data=json.dumps({
                "lastName": last_name,
                "orderId": order_id,
            }),
            timeout=60,
        )
        self.__check_response(response, 200)
        return response.to_dict()

    def www_order_baggage_policies(self, order_id: str, last_name: str) -> dict:
        response = self.__tls.post(
            url='https://www.thaiairways.com/flight/baggage/policies',
            headers=self.__www_headers("https://www.thaiairways.com/booking/extra-services/"),
            data=json.dumps({
                "lastName": last_name,
                "orderId": order_id,
            }),
            timeout=60,
        )
        self.__check_response(response, 200)
        return response.to_dict()

    def www_ancillaries_catalogue(self, order_id: str, last_name: str) -> dict:
        response = self.__tls.post(
            url='https://www.thaiairways.com/ancillaries/service/catalogue',
            headers=self.__www_headers("https://www.thaiairways.com/booking/extra-services/"),
            data=json.dumps({
                "lastName": last_name,
                "orderId": order_id,
            }),
            timeout=60,
        )
        self.__check_response(response, 200)
        return response.to_dict()

    def www_payment_init(self, order_id: str, last_name: str) -> dict:
        response = self.__tls.post(
            url='https://www.thaiairways.com/order/payment/init',
            headers=self.__www_headers("https://www.thaiairways.com/booking/extra-services/"),
            data=json.dumps({
                "lastName": last_name,
                "orderId": order_id,
                "module": "BOOKING",
            }),
            timeout=60,
        )
        self.__check_response(response, 200)
        return response.to_dict()

    def www_payment_process(self, url: str) -> str:
        response = self.__tls.get(
            url=url,
            headers=self.__www_page_headers(referer="https://payment.paco.2c2p.com/"),
            timeout=60,
        )
        self.__check_response(response, 200)
        return response.to_text()

    def www_ticketing_payment_status(self, order_number: str, referer: str) -> dict:
        response = self.__tls.post(
            url="https://www.thaiairways.com/ticketing/payment/status",
            headers=self.__www_headers(referer),
            data=json.dumps({"orderNumber": str(order_number)}),
            timeout=60,
        )
        self.__check_response(response, 200)
        return response.to_dict()

    def paco_payment_page_ui(self, payment_id: str) -> dict:
        response = self.__tls.get(
            url=f"https://payment-api.paco.2c2p.com/1.0/Payment/paymentPageUI/{payment_id}",
            headers=self.__paco_headers(),
            timeout=60,
        )
        self.__check_response(response, 200)
        return response.to_dict()

    def paco_server_public_key(self) -> str:
        response = self.__tls.get(
            url="https://payment-api.paco.2c2p.com/1.0/Security/getServerPublicKey",
            headers=self.__paco_headers(),
            timeout=60,
        )
        self.__check_response(response, 200)
        try:
            data = response.to_dict()
        except json.JSONDecodeError:
            return response.to_text().strip().strip('"')

        if isinstance(data, str):
            return data.strip().strip('"')
        if isinstance(data, dict):
            server_key = data.get("PublicKey") or data.get("publicKey") or data.get("data")
            if isinstance(server_key, dict):
                server_key = server_key.get("PublicKey") or server_key.get("publicKey")
            if server_key:
                return str(server_key).strip().strip('"')
        raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "serverPublicKey")

    def paco_check_card(self, office_guid: str, data: dict) -> dict:
        response = self.__tls.post(
            url=f"https://payment-api.paco.2c2p.com/1.0/Office/{office_guid}/checkCard",
            headers=self.__paco_headers(),
            data=data,
            timeout=60,
        )
        self.__check_response(response, 200)
        return response.to_dict()

    def paco_card_holder_validate(self, data: dict) -> bool:
        response = self.__tls.post(
            url="https://payment-api.paco.2c2p.com/1.0/Payment/paymentPageUI/cardHolderValidate",
            headers=self.__paco_headers(),
            data=data,
            timeout=60,
        )
        self.__check_response(response, 200)
        return bool(response.to_dict())

    def paco_payment_non_ui(self, data: dict, api_key: str, api_version: str = "1.0") -> dict:
        response = self.__tls.post(
            url=f"https://payment-api.paco.2c2p.com/{api_version}/Payment/NonUi",
            headers=self.__paco_headers(api_key=api_key),
            data=data,
            timeout=60,
        )
        if response.status not in [200, 400]:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return self.__response_to_dict(response)

    def paco_payment_status(self, payment_id: str) -> dict:
        response = self.__tls.get(
            url=f"https://payment-api.paco.2c2p.com/1.0/Payment/status/{payment_id}?language=en",
            headers=self.__paco_headers(),
            timeout=60,
        )
        self.__check_response(response, 200)
        return response.to_dict()

    def __www_headers(self, referer: str, auth: bool = True) -> dict:
        headers = {
            "Host": "www.thaiairways.com",
            "user-agent": self.__ua,
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-US,en;q=0.5",
            "accept-encoding": "gzip, deflate, br, zstd",
            "content-type": "application/json",
            "origin": "https://www.thaiairways.com",
            "referer": referer,
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "ama-client-ref": self.__uuid,
        }
        if auth and self.__booking_authorization:
            headers["booking_authorization"] = self.__booking_authorization
        if auth and self.__booking_session_id:
            headers["booking_session_id"] = self.__booking_session_id
        return headers

    def __www_page_headers(self, referer: str) -> dict:
        return {
            "Host": "www.thaiairways.com",
            "user-agent": self.__ua,
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "en-US,en;q=0.5",
            "accept-encoding": "gzip, deflate, br, zstd",
            "referer": referer,
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "cross-site",
            "upgrade-insecure-requests": "1",
            "cache-control": "no-cache",
            "pragma": "no-cache",
        }

    def __paco_headers(self, api_key: str = None) -> dict:
        headers = {
            "Host": "payment-api.paco.2c2p.com",
            "user-agent": self.__ua,
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-US,en;q=0.5",
            "accept-encoding": "gzip, deflate, br, zstd",
            "content-type": "application/json",
            "origin": "https://payment.paco.2c2p.com",
            "referer": "https://payment.paco.2c2p.com/",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "cookie": "",
        }
        if api_key:
            headers["apiKey"] = api_key
        return headers

    @staticmethod
    def __response_to_dict(response) -> dict:
        response_text = response.to_text()
        if not response_text:
            return {"status": response.status}
        try:
            data = response.to_dict()
        except json.JSONDecodeError:
            data = response_text
        return {
            "status": response.status,
            "data": data,
        }

    @staticmethod
    def __check_response(response, expected_status: int):
        if response.status != expected_status:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
