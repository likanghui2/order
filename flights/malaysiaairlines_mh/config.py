import json
from pathlib import Path


class MalaysiaAirlinesConfig:
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36"
    )

    CURRENCY_KEY = {
        "MYR": "KULMH08FX",
        "THB": "BKKMH08FX",
        "IDR": "JKTMH08FX",
        "VND": "HANMH08FX",
        "INR": "BOMMH08FX",
        "USD": "MNLMH08FX",
        "HKD": "TYOMH08FX",
        "CNY": "BJSMH08FX",
        "EUR": "PARMH08FX",
        "SAR": "JKTMH08FX",
        "LKR": "CMBMH08FX",
        "NZD": "AKLMH08FX",
        "AUD": "SYDMH08FX",
        "QAR": "DOHMH08FX",
        "NPR": "KTMMH08FX",
        "TWD": "TPEMH08FX",
        "GBP": "LONMH08FX",
        "KRW": "SELMH08FX",
        "JPY": "TYOMH08UR",
    }

    # 与当前框架 Thai Airways Web 共用验证码服务账号。
    DANLI_APP_ID = "m05cmm7ub8vm1pgasjpo8sdp9tl6mkzp"
    NOCAPTCHA_API_KEY = "e05b056e-3d13-494e-af0d-b934bff84220"

    # Malaysia Airlines 旧框架 Web 初始化凭据。
    OAUTH_CLIENT_ID = "XCgHLH17Xbj7BQLpxH0xSUG9XfRtYh6l"
    OAUTH_CLIENT_SECRET = "P6bw7YqVn3VfQQ3Z"
    _FARE_FAMILIES = json.loads(
        (Path(__file__).with_name("fare_families.json")).read_text()
    )

    @classmethod
    def bundle_info(cls, fare_family_code: str) -> dict:
        """Normalize MH's market-specific fare-family codes."""
        code = str(fare_family_code or "").upper()
        exact = cls._FARE_FAMILIES.get(code)
        if exact:
            cabin_text = str(exact["cabin_bag"]).upper().replace(" ", "")
            cabin_pieces = 2 if "X" in cabin_text else 1
            cabin_weight = int(cabin_text.split("X")[-1]) * cabin_pieces
            return {
                "tag": exact["tag"],
                "cabin_pieces": cabin_pieces,
                "cabin_weight": cabin_weight,
                "checkin_weight": int(exact["checkin_bag"]),
            }
        if code.startswith(("BUS", "BSS")):
            return {
                "tag": "Business",
                "cabin_pieces": 2,
                "cabin_weight": 14,
                "checkin_weight": 40,
            }
        rules = (
            (("BUSMIL",), "Enrich Base", 2, 7, 40),
            (("FIRSTCLA",), "First Class Flex", 2, 7, 50),
            (("BUSST", "BUSSS", "BUSSB", "BSSTSP", "BUSSP"), "Business Suite", 2, 7, 55),
            (("BUSBCC", "STUBUPR", "BUSPPR", "STUJST"), "Business Basic", 2, 7, 40),
            (("BUSFXX", "STUBUS", "STBUS", "BSS", "STUJFX"), "Business Flex", 2, 7, 50),
            (("STUFI", "STFLEX", "STUYFX", "FLEX", "FLXXY", "FLESP"), "Economy Flex", 1, 7, 35),
            (("STUYST", "SMART", "SMASP"), "Economy Smart", 1, 7, 30),
            (("STUYPR", "PROMO", "PROSP"), "Economy Promo", 1, 7, 30),
            (("STUBASIC", "STUBK", "STUYBC", "BASEK", "BASIC", "BASSP"), "Economy Basic", 1, 7, 25),
            (("STULIET", "STULT", "LETI"), "Economy Value", 1, 7, 20),
            (("STUCDS", "CSD", "ECOATR", "ECOJET"), "Economy Codeshare", 1, 7, 35),
            (("FFTP",), "MHflypass", 1, 7, 35),
        )
        for prefixes, tag, pieces, cabin_weight, checkin_weight in rules:
            if any(prefix in code for prefix in prefixes):
                return {
                    "tag": tag,
                    "cabin_pieces": pieces,
                    "cabin_weight": cabin_weight * pieces,
                    "checkin_weight": checkin_weight,
                }
        return {
            "tag": "Economy",
            "cabin_pieces": 1,
            "cabin_weight": 7,
            "checkin_weight": 20,
        }
