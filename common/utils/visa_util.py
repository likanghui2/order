import base64
import json
import urllib.parse
import uuid
from typing import Optional

from bs4 import BeautifulSoup

from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.proxy_Info_model import ProxyInfoModel
from common.tls.curl_cffi_tls import CurlCffiTls


class Visa:
    def __init__(self, proxy_info: Optional[ProxyInfoModel],
                 accept_language: str = "en-US,en;q=0.9"):
        self.__http_utils = CurlCffiTls()
        self.__http_utils.initialize(proxy_info_data=proxy_info, impersonate="chrome136")
        self.__accept_language = accept_language

    def render_method_url(self, url: str, payload: str, user_agent: str = None, headers_options: dict = None):
        if headers_options is None:
            headers_options = {}
        user_agent = user_agent or (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
        )
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-language": self.__accept_language,
            "cache-control": "no-cache",
            "content-type": "application/x-www-form-urlencoded",
            "origin": "https://geo.cardinalcommerce.com",
            "pragma": "no-cache",
            "priority": "u=0, i",
            "sec-ch-ua": '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
            "sec-fetch-dest": "iframe",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "cross-site",
            "sec-fetch-storage-access": "none",
            "upgrade-insecure-requests": "1",
            "user-agent": user_agent,
        }
        headers.update(headers_options)
        response = self.__http_utils.post(
            url=url,
            headers=headers,
            data=urllib.parse.urlencode({"threeDSMethodData": payload}),
            allow_redirects=True
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        soup = BeautifulSoup(response.to_text(), "html.parser")
        hidden_inputs = {}
        for inp in soup.find_all("input", {"type": "hidden"}):
            name = inp.get("name") or inp.get("id")
            value = inp.get("value", "")
            if name:
                hidden_inputs[name] = value
        return hidden_inputs

    def save_browser_data(self, params, ua, org_unit_id, reference_id, headers_options: dict = None,
                          fingerprint: str = None, fingerprinting_time: int = 75,
                          available_js_fonts: list = None, do_not_track: str = 'unspecified',
                          adblock: bool = False, platform: str = 'Win32',
                          screen_resolution: str = '2560x1440', usable_resolution: str = '2560x1392'):
        if headers_options is None:
            headers_options = {}
        if available_js_fonts is None:
            available_js_fonts = [
                "Arial", "Arial Black", "Calibri", "Cambria", "Cambria Math", "Comic Sans MS", "Consolas",
                "Courier", "Courier New", "Georgia", "Helvetica", "Impact", "Lucida Console",
                "Lucida Sans Unicode", "Microsoft Sans Serif", "MS Gothic", "MS PGothic", "MS Sans Serif",
                "MS Serif", "Palatino Linotype", "Segoe Print", "Segoe Script", "Segoe UI", "Segoe UI Light",
                "Segoe UI Semibold", "Segoe UI Symbol", "Tahoma", "Times", "Times New Roman", "Trebuchet MS",
                "Verdana", "Wingdings"
            ]
        headers = {
            "accept": "*/*",
            "accept-language": self.__accept_language,
            "cache-control": "no-cache",
            "content-type": "application/json",
            "origin": "https://methodurl.vcas.visa.com",
            "pragma": "no-cache",
            "priority": "u=1, i",
            "sec-ch-ua": '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "sec-fetch-storage-access": "none",
            "user-agent": ua,
            "x-requested-with": "XMLHttpRequest",
        }
        headers.update(headers_options)
        data = {
            "Cookies": {
                "Legacy": True,
                "LocalStorage": True,
                "SessionStorage": True,
            },
            "DeviceChannel": "Browser",
            "Extended": {
                "Browser": {
                    "Adblock": adblock,
                    "AvailableJsFonts": available_js_fonts,
                    "DoNotTrack": do_not_track,
                    "JavaEnabled": False,
                },
                "Device": {
                    "ColorDepth": 24,
                    "Cpu": "unknown",
                    "Platform": platform,
                    "TouchSupport": {
                        "MaxTouchPoints": 0,
                        "OnTouchStartAvailable": False,
                        "TouchEventCreationSuccessful": False,
                    },
                },
            },
            "Fingerprint": fingerprint or str(uuid.uuid4().hex),
            "FingerprintingTime": fingerprinting_time,
            "FingerprintDetails": {
                "Version": "1.5.1",
            },
            "Language": "zh-CN",
            "Latitude": None,
            "Longitude": None,
            "OrgUnitId": org_unit_id,
            "Plugins": [
                "PDF Viewer::Portable Document Format::application/pdf~pdf,text/pdf~pdf",
                "Chrome PDF Viewer::Portable Document Format::application/pdf~pdf,text/pdf~pdf",
                "Chromium PDF Viewer::Portable Document Format::application/pdf~pdf,text/pdf~pdf",
                "Microsoft Edge PDF Viewer::Portable Document Format::application/pdf~pdf,text/pdf~pdf",
                "WebKit built-in PDF::Portable Document Format::application/pdf~pdf,text/pdf~pdf",
            ],
            "ReferenceId": reference_id,
            "Referrer": "",
            "Screen": {
                "FakedResolution": False,
                "Ratio": 1.7777777777777777,
                "Resolution": screen_resolution,
                "UsableResolution": usable_resolution,
                "CCAScreenSize": "01",
            },
            "CallSignEnabled": False,
            "ThreatMetrixEnabled": True,
            "ThreatMetrixEventType": "PAYMENT",
            "ThreeDSServerTransId": reference_id,
            "TimeOffset": -480,
            "UserAgent": ua,
            "UserAgentDetails": {
                "FakedOS": False,
                "FakedBrowser": False,
            },
        }
        response = self.__http_utils.post(
            url=f"https://methodurl.vcas.visa.com/DeviceFingerprintWeb/V2/Browser/SaveBrowserData?{urllib.parse.urlencode(params)}",
            headers=headers,
            data=json.dumps(data),
            allow_redirects=True
        )
        if response.status != 200:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_text()

    def vcdi(self, url: str, client_id: str, product_code: str, client_request_id: str,
             user_agent: str = None, headers_options: dict = None):
        if headers_options is None:
            headers_options = {}
        user_agent = user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:149.0) Gecko/20100101 Firefox/149.0"
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": self.__accept_language,
            "content-type": "application/x-www-form-urlencoded",
            "origin": "https://geo.cardinalcommerce.com",
            "referer": "https://geo.cardinalcommerce.com/",
            "upgrade-insecure-requests": "1",
            "user-agent": user_agent,
        }
        headers.update(headers_options)
        payload = base64.b64encode(json.dumps({
            "clientId": client_id,
            "productCode": product_code,
            "clientRequestId": client_request_id
        }, separators=(",", ":")).encode()).decode()
        response = self.__http_utils.post(
            url=url,
            headers=headers,
            data=urllib.parse.urlencode({"vdipMethodData": payload}),
            allow_redirects=True
        )
        if response.status not in [0, 200]:
            raise ServiceError(ServiceStateEnum.HTTP_RESPONSE_STATE_NOT_SATISFY, response.status)
        return response.to_text()
