import hashlib
import hmac
import json
import random
import string
import time
import uuid
from typing import Optional

from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.proxy_Info_model import ProxyInfoModel
from common.tls.curl_cffi_tls import CurlCffiTls
from common.utils.danli_captcha_util import DanLiCaptchaUtil
from flights.sunphuquocairways_9g.config import Config
from flights.sunphuquocairways_9g.flight_common.app_trace_cache import NineGAppTraceCache


class AppScript:
    def __init__(
        self,
        proxy_info: Optional[ProxyInfoModel] = None,
        tls=None,
        captcha=None,
        trace_cache=None,
    ):
        self._proxy_info = proxy_info
        self._tls = tls or CurlCffiTls()
        self._captcha = captcha or DanLiCaptchaUtil(Config.INCAPSULA_APP_ID)
        self._device_id = str(uuid.uuid4()).upper()
        self.trace_id = None
        self.timeout = 60
        self._trace_cache = trace_cache if trace_cache is not None else NineGAppTraceCache()

    def initialize_session(self) -> None:
        self._tls.initialize(self._proxy_info, impersonate="chrome146")

    def common_headers(
        self,
        office_id: str = "",
        accept_language: str = "en",
        x_lang: str = "en",
    ) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": accept_language,
            "Content-Type": "application/json",
            "User-Agent": Config.USER_AGENT,
            "x-device-id": self._device_id,
            "x-lang": x_lang,
        }
        if self.trace_id:
            headers["Spa-Trace-Id"] = self.trace_id
        if office_id:
            headers["X-Office-Id"] = office_id
        return headers

    def signed_headers(
        self,
        body: str,
        office_id: str = "",
        accept_language: str = "en",
        x_lang: str = "en",
    ) -> dict[str, str]:
        timestamp = str(int(time.time() * 1000))
        nonce = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
        signing_string = f"POST|/normal/search|{timestamp}|{body}|{nonce}"
        signature = hmac.new(
            Config.HMAC_API_SECRET.encode(),
            signing_string.encode(),
            hashlib.sha256,
        ).hexdigest()
        headers = self.common_headers(office_id, accept_language, x_lang)
        headers.update(
            {
                "X-Api-Key": Config.HMAC_API_KEY,
                "X-Timestamp": timestamp,
                "X-Nonce": nonce,
                "X-Signature": signature,
            }
        )
        return headers

    @staticmethod
    def compact_json(value: dict) -> str:
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False)

    def search(
        self,
        airport_data: list[tuple[str, str, str]],
        adult_count: int,
        child_count: int,
        infant_count: int = 0,
        promo_code: str = "",
        office_id: str = "",
        accept_language: str = "en",
        x_lang: str = "en",
    ) -> dict:
        payload = {
            "list_route": [
                {
                    "flight_date": flight_date,
                    "departure": departure,
                    "arrival": arrival,
                    "is_requested_bound": True,
                    "flexibility": "3",
                }
                for departure, arrival, flight_date in airport_data
            ],
            "adult": adult_count,
            "child": child_count,
            "infant": infant_count,
            "option": {"promo_code": promo_code or "", "is_show_out": True},
        }
        body = self.compact_json(payload)
        response = self._tls.post(
            url=f"{Config.API_BASE}/booking/normal/search",
            headers=self.signed_headers(body, office_id, accept_language, x_lang),
            data=body,
            timeout=self.timeout,
        )
        data = self._check_response(response)
        trace_id = str(data.get("trace_id") or "").strip()
        if not trace_id:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "9GAPP响应缺少trace_id")
        self._trace_cache.save(trace_id)
        self.trace_id = None
        return data

    def create_order(
        self,
        trip_ids: list[str],
        passenger_list: list[dict],
        contact_list: list[dict],
        office_id: str = "",
        accept_language: str = "en",
        x_lang: str = "en",
    ) -> dict:
        create_succeeded = False
        try:
            trace_id = self._trace_cache.pop_ready()
            if not trace_id:
                raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "9GAPP暂无可用trace_id")
            self.trace_id = trace_id
            time.sleep(Config.CREATE_ORDER_WAIT_SECONDS)
            token = self._captcha.incapsula_token_get(
                verify_url=Config.INCAPSULA_URL,
                proxy_data=self._proxy_info.get_proxy_info_to_string() if self._proxy_info else None,
                host="fly.sunphuquocairways.com",
                jwt_required=False,
                user_agent=Config.USER_AGENT,
            )
            headers = self.common_headers(office_id, accept_language, x_lang)
            headers["x-d-token"] = token
            response = self._tls.post(
                url=f"{Config.API_BASE}/booking/normal/create/order",
                headers=headers,
                data=self.compact_json(
                    {
                        "trip_ids": trip_ids,
                        "list_passenger": passenger_list,
                        "list_contact": contact_list,
                    }
                ),
                timeout=self.timeout,
            )
            data = self._check_response(response)
            create_succeeded = True
            return data
        finally:
            if not create_succeeded:
                self.trace_id = None

    def hold_booking(
        self,
        booking_id: str,
        office_id: str = "",
        accept_language: str = "en",
        x_lang: str = "en",
    ) -> dict:
        try:
            response = self._tls.post(
                url=f"{Config.API_BASE}/booking/normal/create/hold-booking",
                headers=self.common_headers(office_id, accept_language, x_lang),
                data=self.compact_json({"booking_id": booking_id}),
                timeout=self.timeout,
            )
            return self._check_response(response)
        finally:
            self.trace_id = None

    @staticmethod
    def _check_response(response) -> dict:
        text = response.to_text()
        if "NO FLIGHTS FOUND" in text or "NO AVAILABLE FLIGHT" in text:
            raise ServiceError(ServiceStateEnum.NO_FLIGHT_DATA)
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        try:
            data = response.to_dict()
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "9GAPP响应不是有效JSON")
        if data.get("success") is False or data.get("error"):
            raise ServiceError(ServiceStateEnum.API_RESPONSE_FAILED)
        return data
