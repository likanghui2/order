import random
from typing import Optional


class HeadersUtlis:

    @staticmethod
    def _normalize_device(device: Optional[str] = None) -> str:
        if not device:
            return random.choice(["windows", "windows", "mac", "android", "ios"])

        device = device.lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "win": "windows",
            "window": "windows",
            "windows": "windows",
            "pc": "windows",
            "mac": "mac",
            "macos": "mac",
            "mac_os": "mac",
            "osx": "mac",
            "darwin": "mac",
            "android": "android",
            "ios": "ios",
            "iphone": "ios",
            "ipad": "ios",
            "desktop": random.choice(["windows", "mac"]),
            "mobile": random.choice(["android", "ios"]),
        }
        if device not in aliases:
            raise ValueError(f"unsupported header profile device: {device}")
        return aliases[device]

    @staticmethod
    def random_header_profile(device: Optional[str] = None, chrome_major: Optional[int] = None) -> dict:
        """Build one internally consistent browser header profile."""
        chrome_major = chrome_major or 146
        device = HeadersUtlis._normalize_device(device)
        android_platform = (
            f"Linux; Android {random.choice([12, 13, 14, 15])}; "
            f"{random.choice(['SM-S918B', 'Pixel 7', 'Pixel 8', 'M2101K9G'])}"
        )
        ios_version = random.choice(["16_7", "17_6", "18_1", "18_2"])
        ios_device = random.choice([
            f"iPhone; CPU iPhone OS {ios_version} like Mac OS X",
            f"iPad; CPU OS {ios_version} like Mac OS X",
        ])
        device_profiles = {
            "windows": {
                "platform": "Windows",
                "ua_platform": "Windows NT 10.0; Win64; x64",
                "sec_ch_ua_platform": '"Windows"',
                "mobile": False,
                "browser": "chrome",
                "supports_sec_ch": True,
            },
            "mac": {
                "platform": "macOS",
                "ua_platform": "Macintosh; Intel Mac OS X 10_15_7",
                "sec_ch_ua_platform": '"macOS"',
                "mobile": False,
                "browser": "chrome",
                "supports_sec_ch": True,
            },
            "android": {
                "platform": "Android",
                "ua_platform": android_platform,
                "sec_ch_ua_platform": '"Android"',
                "mobile": True,
                "browser": "chrome",
                "supports_sec_ch": True,
            },
            "ios": {
                "platform": "iOS",
                "ua_platform": ios_device,
                "sec_ch_ua_platform": '"iOS"',
                "mobile": True,
                "browser": "safari",
                "supports_sec_ch": False,
            },
        }
        profile = device_profiles[device]
        accept_language = random.choice([
            "en-US,en;q=0.9",
            "en-GB,en;q=0.9",
            "en-MY,en-US;q=0.9,en;q=0.8",
            "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
            "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        ])
        if profile["browser"] == "safari":
            safari_version = ios_version.replace("_", ".")
            user_agent = (
                f"Mozilla/5.0 ({profile['ua_platform']}) AppleWebKit/605.1.15 "
                f"(KHTML, like Gecko) Version/{safari_version} Mobile/15E148 Safari/604.1"
            )
            sec_ch_ua = ""
        else:
            chrome_version = f"{chrome_major}.0.0.0"
            mobile_mark = " Mobile" if profile["mobile"] else ""
            user_agent = (
                f"Mozilla/5.0 ({profile['ua_platform']}) AppleWebKit/537.36 "
                f"(KHTML, like Gecko) Chrome/{chrome_version}{mobile_mark} Safari/537.36"
            )
            sec_ch_ua = (
                f'"Google Chrome";v="{chrome_major}", '
                f'"Chromium";v="{chrome_major}", '
                '"Not A(Brand";v="24"'
            )
        return {
            "accept_language": accept_language,
            "user_agent": user_agent,
            "x_useragent": "Mobile-Web" if profile["mobile"] else "Web",
            "browser": profile["browser"],
            "sec_ch_ua": sec_ch_ua,
            "sec_ch_ua_mobile": "?1" if profile["mobile"] else "?0",
            "sec_ch_ua_platform": profile["sec_ch_ua_platform"],
            "supports_sec_ch": profile["supports_sec_ch"],
            "platform": profile["platform"],
            "chrome_major": chrome_major,
        }

    @staticmethod
    def browser_header_overrides(profile: dict, x_user_agent: Optional[str] = None,
                                 include_sec_ch: bool = True, lower_case: bool = True) -> dict:
        """Return profile fields in header-key form for merging into a request header dict."""
        name_map = {
            "accept_language": "accept-language" if lower_case else "Accept-Language",
            "user_agent": "user-agent" if lower_case else "User-Agent",
            "x_useragent": "x-useragent" if lower_case else "X-UserAgent",
        }
        headers = {
            name_map["accept_language"]: profile["accept_language"],
            name_map["user_agent"]: profile["user_agent"],
            name_map["x_useragent"]: x_user_agent or profile["x_useragent"],
        }
        if include_sec_ch and profile.get("supports_sec_ch", True):
            headers.update({
                "sec-ch-ua": profile["sec_ch_ua"],
                "sec-ch-ua-mobile": profile["sec_ch_ua_mobile"],
                "sec-ch-ua-platform": profile["sec_ch_ua_platform"],
            })
        return headers
