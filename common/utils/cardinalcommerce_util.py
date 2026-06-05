import json
import uuid

from curl_cffi import requests

from common.errors.service_error import ServiceError, ServiceStateEnum
from common.utils.string_util import StringUtil


class CardinalcommerceUtil:

    def __init__(self, proxy_str, agent: str, accept_language: str = "en-US,en;q=0.9"):
        self.__session = requests.Session()
        if proxy_str:
            self.__session.proxies = {
                'http': proxy_str,
                'https': proxy_str
            }

        self.__agent = agent
        self.__accept_language = accept_language

    def jwt_init(self, jwt):

        if self.__agent == 'Android':
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; PHZ110 Build/PQ3A.190705.05211459)",
                "Host": "centinelapi.cardinalcommerce.com",
                "Connection": "Keep-Alive",
                "Accept-Encoding": "gzip",
            }

            data = {
                "BrowserPayload": {
                    "Order": {},
                    "SupportsAlternativePayments": {
                        "cca": True
                    }
                },
                "Client": {
                    "Agent": "CardinalMobileSdk_Android",
                    "Version": "2.2.7-5"
                },
                "ServerJWT": jwt
            }
        else:
            headers = {
                "Host": "centinelapi.cardinalcommerce.com",
                "Connection": "keep-alive",
                "Content-Type": "application/json;charset=UTF-8",
                "sec-ch-ua-mobile": "?0",
                "User-Agent": self.__agent,
                "Accept": "*/*",
                "Sec-Fetch-Site": "cross-site",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Dest": "empty",
                "Accept-Encoding": "gzip, deflate, br, zstd",
                "Accept-Language": self.__accept_language
            }
            data = {
                "BrowserPayload": {
                    "Order": {
                        "OrderDetails": {},
                        "Consumer": {
                            "BillingAddress": {},
                            "ShippingAddress": {},
                            "Account": {}
                        },
                        "Cart": [],
                        "Token": {},
                        "Authorization": {},
                        "Options": {},
                        "CCAExtension": {}
                    },
                    "SupportsAlternativePayments": {
                        "cca": True,
                        "hostedFields": False,
                        "applepay": False,
                        "discoverwallet": False,
                        "wallet": False,
                        "paypal": False,
                        "visacheckout": False
                    }
                },
                "Client": {
                    "Agent": "SongbirdJS",
                    "Version": "1.35.0"
                },
                "ConsumerSessionId": None,
                "ServerJWT": jwt
            }
        response = self.__session.post(url='https://centinelapi.cardinalcommerce.com/V1/Order/JWT/Init',
                                       headers=headers,
                                       json=data)
        if response.status_code != 200:
            raise ServiceError(ServiceStateEnum.RESPONSE_STATE_ERROR, response.status_code)
        return response.json()

    def save_browser_data(self, reference_id: str, org_unit_id: str) -> None:

        if self.__agent == 'Android':
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; PHZ110 Build/PQ3A.190705.05211459)",
                "Host": "geo.cardinalcommerce.com",
                "Connection": "Keep-Alive",
                "Accept-Encoding": "gzip",
            }

            data = {
                "ReferenceId": reference_id,
                "OrgUnitId": org_unit_id,
                "Origin": "CardinalMobileSdk_Android",
                "DeviceChannel": "SDK",
                "Fingerprint": "Android\/graceltexx\/gracelte:9\/PQ3A.190705.05211459\/G9700FXXU1APFO:user\/release-keys",
                "UserAgent": "OPPO",
                "ThreatMetrixEnabled": True,
                "ThreatMetrixEventType": "PAYMENT",
                "NativeData": {
                    "ConnectionData": {
                        "BluetoothData": {
                            "IsBluetoothEnabled": True
                        },
                        "NetworkData": {
                            "Is5GHzBandSupport": False,
                            "IsDeviceToApRttSupported": False,
                            "IsEnhancedPowerReportingSupported": False,
                            "IsP2pSupported": True,
                            "IsPreferredNetworkOffloadSupported": False,
                            "IsScanAlwaysAvailable": False,
                            "IsTdlsSupported": False,
                            "BSSID": "00:db:ac:a2:cc:88",
                            "NetworkID": 0,
                            "SSID": "\"\"airport-MIouBG\"\""
                        }
                    },
                    "Language": "中文",
                    "LocationData": {
                        "Latitude": "39.915001765",
                        "Longitude": "116.40399933799999"
                    },
                    "DeviceData": {
                        "BootLoader": "unknown",
                        "Brand": "OPPO",
                        "ColorDepth": "320",
                        "Density": 2,
                        "DensityDpi": 320,
                        "Device": "gracelte",
                        "DeviceName": "PHZ110",
                        "Display": "PQ3A.190705.05211459 release-keys",
                        "GetTotalBytes": 2642198528,
                        "Hardware": "qcom",
                        "Locale": "zh-CN",
                        "Manufacturer": "OPPO",
                        "Model": "PHZ110",
                        "Product": "PHZ110",
                        "Radio": "unknown",
                        "ScaledDensity": 2,
                        "ScreenDensity": 2,
                        "ScreenResolution": "720*1280",
                        "Tags": "release-keys",
                        "Time": "1747810742000",
                        "Type": "user",
                        "User": "build",
                        "Xdpi": 320,
                        "Ydpi": 320
                    },
                    "OS": {
                        "ApiVersion": "28",
                        "CodeName": "REL",
                        "Incremental": "G9700FXXU1APFO",
                        "OsName": "P",
                        "PreviewSdkInt": 0,
                        "SdkInt": 28,
                        "SecurityPatch": "2019-07-05",
                        "Type": "Android",
                        "Version": "9"
                    },
                    "ConfigurationData": {
                        "Environment": "PRODUCTION",
                        "ProxyAddress": "",
                        "RenderType": ["OTP", "SINGLE_SELECT", "MULTI_SELECT", "OOB", "HTML"],
                        "Timeout": 8000,
                        "UiType": "BOTH",
                        "EnableDFSync": True,
                        "EnableLogging": True,
                        "LocationDataConsentGiven": True
                    },
                    "UserData": {
                        "SettingsData": {
                            "AccelerometerRotation": 0,
                            "BluetoothDiscoverability": 0,
                            "BluetoothDiscoverabilityTimeout": 0,
                            "DateFormat": "0",
                            "DtmfToneWhenDialing": "1",
                            "EndButtonBehavior": "0",
                            "HapticFeedbackEnabled": "1",
                            "ModeRingerStreamsAffected": "422",
                            "NotificationSound": "content:\/\/media\/internal\/audio\/media\/177",
                            "MuteStreamsAffected": "47",
                            "Ringtone": "content:\/\/media\/internal\/audio\/media\/43",
                            "ScreenBrightness": "102",
                            "ScreenBrightnessMode": "0",
                            "ScreenOffTimeout": "2147483647",
                            "SoundEffectsEnabled": "1",
                            "TextAutoCaps": "0",
                            "TextAutoPunctuate": -1,
                            "TextAutoReplace": "0",
                            "UserRotation": "0",
                            "VibrateOn": "0",
                            "VibrateWhenRinging": "0",
                            "DtmfToneTypeWhenDialing": "0",
                            "AccessibilityEnabled": "0",
                            "AccessibilitySpeakPassword": "1",
                            "DefaultInputMethod": "com.android.inputmethod.pinyin\/.InputService",
                            "InputMethodSelectorVisibility": "0",
                            "EnabledInputMethods": "0",
                            "InstallNonMarketApps": "1",
                            "TtsDefaultRate": "0",
                            "TtsDefaultSynth": "0",
                            "TtsEnabledPlugins": "0",
                            "AdbEnabled": "0",
                            "AirplaneModeRadios": "cell,bluetooth,wifi,nfc,wimax",
                            "AlwaysFinishActivities": "0",
                            "AutoTime": "1",
                            "AutoTimeZone": "1",
                            "HttpProxy": "0",
                            "NetworkPreference": "0",
                            "StayOnWhilePluggedIn": "0",
                            "TransitionAnimationScale": 0,
                            "UsbMassStorageEnabled": "1",
                            "UseGoogleMail": "0",
                            "WaitForDebugger": "0",
                            "WifiNetworksAvailableNotificationOn": "1",
                            "AnimatorDurationScale": "1",
                            "DataRoaming": "1",
                            "DeviceProvisioned": "1",
                            "TtsDefaultPitch": "0",
                            "SkipFirstUseHints": "0",
                            "EnabledAccessibilityServices": "0",
                            "AccessibilityDisplayInversionEnabled": "0",
                            "LocationMode": "1"
                        }
                    },
                    "SecurityWarnings": {
                        "IsAppTrusted": False,
                        "IsJailbroken": True,
                        "IsSDKTempered": False,
                        "IsEmulator": False,
                        "IsDebuggerAttached": False,
                        "IsOSSupported": True
                    },
                    "SdkVersion": "2.2.7-5",
                    "SDKAppId": "41d84c28-dbe6-4299-818b-8850fcdd4227",
                    "SDK3DSSupport": ["2.1.0", "2.2.0"]
                }
            }

        response = self.__session.post(
            url='https://geo.cardinalcommerce.com/DeviceFingerprintWeb/V2/Browser/SaveBrowserData', headers=headers,
            json=data)

        if response.status_code != 200:
            raise ServiceError(ServiceStateEnum.RESPONSE_STATE_ERROR, response.status_code)

        print(response.text)

    def render_post(self, url: str, data: str, headers_options: dict = None):
        """

        Args:
            url:
            data:

        Returns:

        """
        if headers_options is None:
            headers_options = {}

        headers = {
            "Connection": "keep-alive",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "Origin": "https://centinelapi.cardinalcommerce.com",
            "Content-Type": "application/x-www-form-urlencoded",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": self.__agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Sec-Fetch-Site": "same-site",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Dest": "iframe",
            "Referer": "https://centinelapi.cardinalcommerce.com/",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": self.__accept_language
        }
        for key, value in headers_options.items():
            headers[key] = value

        response = self.__session.post(
            url=url,
            headers=headers,
            data=data, timeout=60
        )

        if response.status_code != 200:
            raise ServiceError(ServiceStateEnum.RESPONSE_STATE_ERROR, response.status_code)

        result_text = StringUtil.extract_between(response.text, 'profiler.start(', ')')
        return json.loads(result_text)

    def notification_post(self, url: str, data: str, headers_options: dict = None):
        if headers_options is None:
            headers_options = {}

        headers = {
            "Connection": "keep-alive",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "Origin": "https://triplink-acs-3ds-sgp.triplinkintl.com",
            "Content-Type": "application/x-www-form-urlencoded",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": self.__agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Dest": "iframe",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": self.__accept_language
        }
        for key, value in headers_options.items():
            headers[key] = value

        response = self.__session.post(url=url, headers=headers, data=data, timeout=60)
        if response.status_code != 200:
            raise ServiceError(ServiceStateEnum.RESPONSE_STATE_ERROR, response.status_code)

    def save_browser_data_windows(self,
                                  nonce: str,
                                  reference_id: str,
                                  org_unit_id: str,
                                  referrer: str,
                                  headers_options: dict = None,
                                  origin: str = "CruiseAPI"):

        if headers_options is None:
            headers_options = {}

        headers = {
            "User-Agent": self.__agent,
            "Accept": "*/*",
            "Accept-Language": self.__accept_language,
            "Accept-Encoding": "gzip, deflate, br",
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://geo.cardinalcommerce.com",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin"
        }

        for key, value in headers_options.items():
            headers[key] = value

        submit_data = {
            "Cookies": {
                "Legacy": True,
                "LocalStorage": True,
                "SessionStorage": True
            },
            "DeviceChannel": "Browser",
            "Extended": {
                "Browser": {
                    "Adblock": True, "AvailableJsFonts": [], "DoNotTrack": "unknown", "JavaEnabled": False},
                "Device": {"ColorDepth": 24, "Cpu": "unknown", "Platform": "Win32",
                           "TouchSupport": {"MaxTouchPoints": 0, "OnTouchStartAvailable": False,
                                            "TouchEventCreationSuccessful": False}}},
            "Fingerprint": str(uuid.uuid4().hex), "FingerprintingTime": 15,
            "FingerprintDetails": {"Version": "1.5.1"}, "Language": "zh-CN", "Latitude": None,
            "Longitude": None, "OrgUnitId": org_unit_id, "Origin": origin,
            "Plugins": ["PDF Viewer::Portable Document Format::application/pdf~pdf,text/pdf~pdf",
                        "Chrome PDF Viewer::Portable Document Format::application/pdf~pdf,text/pdf~pdf",
                        "Chromium PDF Viewer::Portable Document Format::application/pdf~pdf,text/pdf~pdf",
                        "Microsoft Edge PDF Viewer::Portable Document Format::application/pdf~pdf,text/pdf~pdf",
                        "WebKit built-in PDF::Portable Document Format::application/pdf~pdf,text/pdf~pdf"],
            "ReferenceId": reference_id,
            "Referrer": referrer,
            "Screen": {
                "FakedResolution": False,
                "Ratio": 1.7777777777777777,
                "Resolution": "2560x1440",
                "UsableResolution": "2560x1400",
                "CCAScreenSize": "01"  # "02"
            }, "CallSignEnabled": None,
            "ThreatMetrixEnabled": False, "ThreatMetrixEventType": "PAYMENT",
            "ThreatMetrixAlias": "Default", "TimeOffset": -480,
            "UserAgent": self.__agent,
            "UserAgentDetails": {"FakedOS": False, "FakedBrowser": False},
            "BinSessionId": nonce}

        response = self.__session.post(
            url="https://geo.cardinalcommerce.com/DeviceFingerprintWeb/V2/Browser/SaveBrowserData",
            data=json.dumps(submit_data),
            headers=headers
        )

        if response.status_code != 200:
            raise ServiceError(ServiceStateEnum.RESPONSE_STATE_ERROR, response.status_code)

    def cardinalcommerce_save_browser_data(self,
                                           nonce: str,
                                           reference_id: str,
                                           org_unit_id: str,
                                           user_agent: str,
                                           referrer: str,
                                           headers_options: dict = None,
                                           origin: str = "CruiseAPI",
                                           fingerprint: str = None,
                                           fingerprinting_time: int = 106,
                                           available_js_fonts: list = None,
                                           do_not_track: str = "unspecified",
                                           adblock: bool = False,
                                           usable_resolution: str = "2560x1392",
                                           screen_resolution: str = "2560x1440",
                                           vcdi_client_request_id: str = None):
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
            "User-Agent": user_agent,
            "Accept": "*/*",
            "Accept-Language": self.__accept_language,
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://geo.cardinalcommerce.com",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin"
        }
        for key, value in headers_options.items():
            headers[key] = value

        submit_data = {
            "Cookies": {
                "Legacy": True,
                "LocalStorage": True,
                "SessionStorage": True
            },
            "DeviceChannel": "Browser",
            "Extended": {
                "Browser": {
                    "Adblock": adblock,
                    "AvailableJsFonts": available_js_fonts,
                    "DoNotTrack": do_not_track,
                    "JavaEnabled": False
                },
                "Device": {
                    "ColorDepth": 24,
                    "Cpu": "unknown",
                    "Platform": "Win32",
                    "TouchSupport": {
                        "MaxTouchPoints": 0,
                        "OnTouchStartAvailable": False,
                        "TouchEventCreationSuccessful": False
                    }
                }
            },
            "Fingerprint": fingerprint or str(uuid.uuid4().hex),
            "FingerprintingTime": fingerprinting_time,
            "FingerprintDetails": {"Version": "1.5.1"},
            "Language": "zh-CN",
            "Latitude": None,
            "Longitude": None,
            "OrgUnitId": org_unit_id,
            "Origin": origin,
            "Plugins": [
                "PDF Viewer::Portable Document Format::application/pdf~pdf,text/pdf~pdf",
                "Chrome PDF Viewer::Portable Document Format::application/pdf~pdf,text/pdf~pdf",
                "Chromium PDF Viewer::Portable Document Format::application/pdf~pdf,text/pdf~pdf",
                "Microsoft Edge PDF Viewer::Portable Document Format::application/pdf~pdf,text/pdf~pdf",
                "WebKit built-in PDF::Portable Document Format::application/pdf~pdf,text/pdf~pdf"
            ],
            "ReferenceId": reference_id,
            "Referrer": referrer,
            "Screen": {
                "FakedResolution": False,
                "Ratio": 1.7777777777777777,
                "Resolution": screen_resolution,
                "UsableResolution": usable_resolution,
                "CCAScreenSize": "01"
            },
            "CallSignEnabled": None,
            "ThreatMetrixEnabled": False,
            "ThreatMetrixEventType": "PAYMENT",
            "ThreatMetrixAlias": "Default",
            "TimeOffset": -480,
            "UserAgent": user_agent,
            "UserAgentDetails": {"FakedOS": False, "FakedBrowser": False},
            "BinSessionId": nonce
        }
        if vcdi_client_request_id:
            submit_data["VcdiClientRequestId"] = vcdi_client_request_id

        response = self.__session.post(
            url="https://geo.cardinalcommerce.com/DeviceFingerprintWeb/V2/Browser/SaveBrowserData",
            data=json.dumps(submit_data),
            headers=headers
        )
        if response.status_code != 200:
            raise ServiceError(ServiceStateEnum.RESPONSE_STATE_ERROR, response.status_code)

    def cardinaltrusted_init_jwt(self, jwt, user_agent, headers_options: dict = None,
                                 client_version: str = '2.0.0'):
        if headers_options is None:
            headers_options = {}

        headers = {
            'accept': '*/*',
            'accept-language': self.__accept_language,
            'cache-control': 'no-cache',
            'content-type': 'application/json;charset=UTF-8',
            'origin': 'https://fly.sunphuquocairways.com',
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'referer': 'https://fly.sunphuquocairways.com/',
            'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'cross-site',
            'user-agent': user_agent,
            'x-cardinal-tid': 'Tid-1e61901d-36e5-4888-b449-7291b2da3db5',
        }
        for key, value in headers_options.items():
            headers[key] = value

        submit_data = {
            'BrowserPayload': {
                'Order': {
                    'OrderDetails': {},
                    'Consumer': {
                        'BillingAddress': {},
                        'ShippingAddress': {},
                        'Account': {},
                    },
                    'Cart': [],
                    'Token': {},
                    'Authorization': {},
                    'Options': {},
                    'CCAExtension': {},
                },
                'SupportsAlternativePayments': {
                    'cca': True,
                },
            },
            'Client': {
                'Agent': 'SongbirdJS',
                'Version': client_version,
            },
            'ConsumerSessionId': None,
            'ServerJWT': jwt,
        }

        response = self.__session.post(
            url="https://client.cardinaltrusted.com/centinelapi/V1/Order/JWT/Init",
            json=submit_data,
            headers=headers
        )
        if response.status_code != 200:
            raise ServiceError(ServiceStateEnum.RESPONSE_STATE_ERROR, response.status_code)
        return response.json()
