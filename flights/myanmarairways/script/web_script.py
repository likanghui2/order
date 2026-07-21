import json
from datetime import datetime
from typing import Optional
from urllib.parse import urlencode

from common.decorators.retry_decorator import retry_decorator
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.proxy_Info_model import ProxyInfoModel
from common.tls.curl_cffi_tls import CurlCffiTls
from common.utils.danli_captcha_util import DanLiCaptchaUtil
from common.utils.ezcaptcha_util import EzCaptcha


def get_cloudflare_session() -> tuple[str, str, str, str]:
    """Provider seam: return cookie, user-agent, proxy and feedback key."""
    return DanLiCaptchaUtil("7j58fx77bifxt2jhx01pwoek7asgp6xm").get_cloudflare("crane.aero")


def get_turnstile_token(page_url: str) -> str:
    """Provider seam: solve the Turnstile rendered by the availability page."""
    captcha = EzCaptcha("a61ac9a3a6824569a584e10937a70ec0256199")
    return captcha.solve_cf_turnstile(
        website_url=page_url,
        website_key="0x4AAAAAADJegaLmo-2hC8iz",
        action="create-booking",
    )


class WebScript:
    def __init__(self, proxy_info: Optional[ProxyInfoModel] = None):
        self.cf_token = None
        self._tls = CurlCffiTls()
        self._user_agent = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:152.0) "
            "Gecko/20100101 Firefox/152.0"
        )
        self._cloudflare_key = None
        self._availability_url = "https://book-myanmar.crane.aero/ibe/availability"
        self._passenger_url = "https://book-myanmar.crane.aero/ibe/passenger"

    def initialize_session(self):
        self._tls.initialize(None, impersonate="chrome136")
        cookie, user_agent, proxy, self._cloudflare_key = get_cloudflare_session()
        print(proxy)
        self._tls.set_proxy_info_str(proxy)
        self._user_agent = user_agent or self._user_agent
        self._tls.cookie_update(cookie)

    @staticmethod
    def _date(value: str) -> str:
        normalized = str(value).strip()
        if len(normalized) == 8 and normalized.isdigit():
            parsed = datetime.strptime(normalized, "%Y%m%d")
        elif len(normalized) >= 10 and normalized[4] == "-":
            parsed = datetime.strptime(normalized[:10], "%Y-%m-%d")
        else:
            parsed = datetime.strptime(normalized[:10], "%d/%m/%Y")
        return parsed.strftime("%d/%m/%Y")

    def get_turnstile_token(self):
        self.cf_token = get_turnstile_token(self._availability_url)

    def search(self, dep_airport: str, arr_airport: str, dep_date: str, adult_count: int,
               child_count: int, currency: str, cabin_class: str) -> str:
        if child_count:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "8M 当前仅支持成人查询")
        date_text = self._date(dep_date)
        params = [
            ("currency", currency), ("language", "en"), ("tripType", "ONE_WAY"),
            ("depPort", dep_airport), ("arrPort", arr_airport),
            ("departureDate", date_text), ("returnDate", date_text),
            ("passengerQuantities[4].passengerType", "CTZP"),
            ("passengerQuantities[4].quantity", 0),
            ("passengerQuantities[0].passengerType", "ADULT"),
            ("passengerQuantities[0].quantity", adult_count),
            ("passengerQuantities[3].passengerType", "NTNL"),
            ("passengerQuantities[3].quantity", 0),
            ("passengerQuantities[1].passengerType", "CHILD"),
            ("passengerQuantities[1].quantity", 0),
            ("passengerQuantities[2].passengerType", "INFANT"),
            ("passengerQuantities[2].quantity", 0),
            ("cabinClass", cabin_class),
        ]
        url = f"https://book-myanmar.crane.aero/ibe/availability?{urlencode(params)}"
        self._availability_url = url
        headers = {
            "host": "book-myanmar.crane.aero",
            "user-agent": self._user_agent,
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "en-US,en;q=0.9",
            "accept-encoding": "gzip, deflate, br, zstd",
            "connection": "keep-alive",
            "referer": "https://www.maiair.com/",
            "upgrade-insecure-requests": "1",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "cross-site",
            "sec-fetch-user": "?1",
            "priority": "u=0, i",
        }
        response = self._tls.get(
            url=url,
            headers=headers,
            timeout=60,
            allow_redirects=True,
        )
        return self._html(response, "availability")

    def select_flight(self, fare_reference_id: str, avail_index: int, cid: str) -> None:
        select_params = {"_cid": cid, "availIndex": avail_index,
                         "fareReferenceId": fare_reference_id, "selectedPackageName": ""}
        select_url = f"https://book-myanmar.crane.aero/ibe/availability/selectFlight?{urlencode(select_params)}"
        headers = {
            "host": "book-myanmar.crane.aero",
            "user-agent": self._user_agent,
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "accept-encoding": "gzip, deflate, br, zstd",
            "content-type": "application/json; charset=utf-8",
            "ajax-request": "true",
            "x-requested-with": "XMLHttpRequest",
            "connection": "keep-alive",
            "referer": self._availability_url,
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "priority": "u=0",
        }
        selected = self._tls.get(
            url=select_url,
            headers=headers,
            timeout=60,
        )
        self._html(selected, "selectFlight")

    @retry_decorator(retry_service_error_list=[(ServiceStateEnum.CLOUD_FLARE_CHECK_FAILURE, get_turnstile_token)], retry_max_number=10)
    def create_booking(self, cid: str, sid: str) -> None:
        create_params = {"recaptchaToken": self.cf_token, "_cid": cid, "_sid": sid}
        create_url = f"https://book-myanmar.crane.aero/ibe/availability/createBooking?{urlencode(create_params)}"
        headers = {
            "host": "book-myanmar.crane.aero",
            "user-agent": self._user_agent,
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "accept-encoding": "gzip, deflate, br, zstd",
            "content-type": "application/json; charset=utf-8",
            "ajax-request": "true",
            "x-requested-with": "XMLHttpRequest",
            "origin": "https://book-myanmar.crane.aero",
            "connection": "keep-alive",
            "referer": self._availability_url,
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "content-length": "0",
            "te": "trailers",
        }
        created = self._tls.post(
            url=create_url,
            headers=headers,
            data="",
            timeout=60,
        )
        self._html(created, "createBooking", allow_empty=True)
        error_message = created.headers.get("x-error-message") or created.headers.get("X-Error-Message")
        if error_message == "Security check failed. Please try again.":
            raise ServiceError(ServiceStateEnum.CLOUD_FLARE_CHECK_FAILURE)

    def next(self, cid: str, sid: str) -> Optional[str]:
        next_url = "https://book-myanmar.crane.aero/ibe/availability/next"
        next_body = urlencode({"_sid": sid, "_cid": cid, "recaptchaToken": ""})
        headers = {
            "host": "book-myanmar.crane.aero",
            "user-agent": self._user_agent,
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "en-US,en;q=0.9",
            "accept-encoding": "gzip, deflate, br, zstd",
            "content-type": "application/x-www-form-urlencoded",
            "content-length": str(len(next_body.encode("utf-8"))),
            "origin": "https://book-myanmar.crane.aero",
            "connection": "keep-alive",
            "referer": self._availability_url,
            "upgrade-insecure-requests": "1",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "same-origin",
            "priority": "u=0, i",
            "te": "trailers",
        }
        advanced = self._tls.post(
            url=next_url,
            headers=headers,
            data=next_body,
            timeout=60,
        )
        if advanced.status not in (302, 303):
            self._html(advanced, "availability/next")
        return advanced.headers.get("location") or advanced.headers.get("Location")

    def passenger(self, cid: str, location: Optional[str] = None) -> str:
        passenger_url = location or f"https://book-myanmar.crane.aero/ibe/passenger?{urlencode({'_cid': cid})}"
        self._passenger_url = passenger_url
        headers = {
            "host": "book-myanmar.crane.aero",
            "user-agent": self._user_agent,
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "en-US,en;q=0.9",
            "accept-encoding": "gzip, deflate, br, zstd",
            "referer": self._availability_url,
            "connection": "keep-alive",
            "upgrade-insecure-requests": "1",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "same-origin",
            "priority": "u=0, i",
        }
        passenger = self._tls.get(
            url=passenger_url,
            headers=headers,
            timeout=60,
            allow_redirects=True,
        )
        return self._html(passenger, "passenger")

    def validate_passenger(self, passenger_data: dict, cid: str, sid: str) -> None:
        params = {"_cid": cid, "_sid": sid}
        validate_url = f"https://book-myanmar.crane.aero/ibe/passenger/validatePassenger?{urlencode(params)}"
        validate_body = json.dumps(passenger_data, ensure_ascii=False, separators=(",", ":"))
        headers = {
            "host": "book-myanmar.crane.aero",
            "user-agent": self._user_agent,
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "accept-encoding": "gzip, deflate, br, zstd",
            "content-type": "application/json; charset=utf-8",
            "ajax-request": "true",
            "x-requested-with": "XMLHttpRequest",
            "content-length": str(len(validate_body.encode("utf-8"))),
            "origin": "https://book-myanmar.crane.aero",
            "connection": "keep-alive",
            "referer": self._passenger_url,
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "priority": "u=0",
        }
        validated = self._tls.post(
            url=validate_url,
            headers=headers,
            data=validate_body,
            timeout=60,
        )
        error_message = validated.headers.get("x-error-message") or validated.headers.get("X-Error-Message")
        if error_message:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, error_message)
        self._html(validated, "passenger/validatePassenger", allow_empty=True)

    def save_passengers(self, passenger_body: str) -> Optional[str]:
        save_url = "https://book-myanmar.crane.aero/ibe/passenger/save"
        headers = {
            "host": "book-myanmar.crane.aero",
            "user-agent": self._user_agent,
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "en-US,en;q=0.9",
            "accept-encoding": "gzip, deflate, br, zstd",
            "content-type": "application/x-www-form-urlencoded",
            "content-length": str(len(passenger_body.encode("utf-8"))),
            "origin": "https://book-myanmar.crane.aero",
            "connection": "keep-alive",
            "referer": self._passenger_url,
            "upgrade-insecure-requests": "1",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "same-origin",
            "sec-fetch-user": "?1",
            "priority": "u=0, i",
            "te": "trailers",
        }
        saved = self._tls.post(
            url=save_url,
            headers=headers,
            data=passenger_body,
            timeout=60,
        )
        error_message = saved.headers.get("x-error-message") or saved.headers.get("X-Error-Message")
        if error_message:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, error_message)
        if saved.status not in (302, 303):
            self._html(saved, "passenger/save")
        return saved.headers.get("location") or saved.headers.get("Location")

    def _html(self, response, step: str, allow_empty: bool = False) -> str:
        if response.status in [403, 429]:
            if response.status == 403:
                DanLiCaptchaUtil("7j58fx77bifxt2jhx01pwoek7asgp6xm").feedback(self._cloudflare_key, 1)
            if response.status == 429:
                DanLiCaptchaUtil("7j58fx77bifxt2jhx01pwoek7asgp6xm").feedback(self._cloudflare_key, 2)
            raise ServiceError(ServiceStateEnum.CLOUD_FLARE_CHECK_FAILURE)
        text = response.to_text()
        if response.status not in (200, 302, 303):
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, f"{step}:{response.status}")
        if "Just a moment" in text or "_cf_chl_opt" in text:
            raise ServiceError(ServiceStateEnum.CLOUD_FLARE_CHECK_FAILURE)
        if not allow_empty and not text:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, step)
        return text
