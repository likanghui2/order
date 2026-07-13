from common.errors.service_error import ServiceError, ServiceStateEnum


class Config:
    API_BASE = "https://mobile-api.sunphuquocairways.com"
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
    )
    HMAC_API_KEY = "b8f9c77a-7c42-4f4d-9a1f-33ce4b27a6e0"
    HMAC_API_SECRET = "pR9#Zt3@Lf!8Qw"
    INCAPSULA_APP_ID = "m05cmm7ub8vm1pgasjpo8sdp9tl6mkzp"
    INCAPSULA_URL = (
        "https://fly.sunphuquocairways.com/"
        "haue-bout-banesse-Ang-Macduff-thin-the-ren-mines/"
        "99r6vGt4eN2_abeJnkAe2gl28K_MRzNFUB3C6lQVNAg"
    )
    CREATE_ORDER_WAIT_SECONDS = 30

    CURRENCY_CONTEXTS = {
        "VND": {"office_id": "HAN9G08MB", "accept_language": "vi", "x_lang": "vi"},
        "USD": {"office_id": "WAS9G08MB", "accept_language": "en", "x_lang": "en"},
        "SGD": {"office_id": "SIN9G08MB", "accept_language": "en", "x_lang": "en"},
        "THB": {"office_id": "BKK9G08MB", "accept_language": "th", "x_lang": "th"},
        "TWD": {"office_id": "TPE9G08MB", "accept_language": "en", "x_lang": "en"},
        "HKD": {"office_id": "HKG9G08MB", "accept_language": "tw", "x_lang": "tw"},
        "KRW": {"office_id": "SEL9G08MB", "accept_language": "en", "x_lang": "en"},
    }

    PRODUCT_TAG = {
        **{f"EL{number}": "ECONOMY LITE" for number in range(1, 14)},
        **{f"ES{number}": "ECONOMY CLASSIC" for number in range(1, 14)},
        **{f"EF{number}": "ECONOMY PLUS" for number in range(1, 14)},
        **{f"EP{number}": "ECONOMY FLEX" for number in range(1, 14)},
        **{f"PF{number}": "PREMIUM ECONOMY PLUS" for number in range(1, 14)},
        **{f"PP{number}": "PREMIUM ECONOMY FLEX" for number in range(1, 14)},
        **{f"BF{number}": "BUSINESS ELITE" for number in range(1, 14)},
        **{f"BP{number}": "BUSINESS PRIME" for number in range(1, 14)},
        "execplus": "Exec Plus",
        "bizclass": "Business Class",
        "basic": "Basic",
        "first": "First",
        "bussflex": "First",
        "smart": "Smart",
        "busflex": "Business",
        "superflex": "Super Flex",
        "ecorest": "Economy",
        "execflex": "Exec Flex",
        "ecosflex": "Economy Flex",
        "business": "Business",
        "ecoflex": "Premium Flex",
        "standard": "Standard",
    }

    @classmethod
    def currency_context(cls, currency: str) -> dict[str, str]:
        normalized = str(currency or "VND").upper()
        context = cls.CURRENCY_CONTEXTS.get(normalized)
        if context is None:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, f"9GAPP不支持币种[{currency}]")
        return context.copy()
