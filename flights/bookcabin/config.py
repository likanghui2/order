class BookCabinConfig:
    AIRLINE_CODE = "BCM"

    WEB_BASE_URL = "https://www.bookcabin.com"
    IBE_API_BASE_URL = "https://api-ibe.bookcabin.com"
    IBE_API2_BASE_URL = "https://api2-ibe.bookcabin.com"

    FLIGHT_SEARCH_BASE_URL = f"{IBE_API_BASE_URL}/flight/v2"
    FLIGHT_CART_BASE_URL = f"{IBE_API2_BASE_URL}/flight-cart/v2"
    FLIGHT_ANCILLARY_BASE_URL = f"{IBE_API2_BASE_URL}/flight-ancillary/v2"
    FLIGHT_BOOKING_BASE_URL = f"{IBE_API2_BASE_URL}/flight-booking/api/flight/v2"
    ORDER_BASE_URL = f"{IBE_API2_BASE_URL}/gobc-order/api"

    LANGUAGE = "en"
    DEFAULT_CABIN_CLASS = "ECONOMY"
    TIMEOUT = 60
    MAX_BOOKING_SEAT_COUNT = 9
    DEFAULT_NATIONALITY_CODE = "840"

    USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:152.0) "
        "Gecko/20100101 Firefox/152.0"
    )

    COUNTRY_CODE_FALLBACK = {
        "CN": "156",
        "HK": "344",
        "ID": "360",
        "JP": "392",
        "KR": "410",
        "MY": "458",
        "PH": "608",
        "SG": "702",
        "TH": "764",
        "TW": "158",
        "US": "840",
        "VN": "704",
    }
