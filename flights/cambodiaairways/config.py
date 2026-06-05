class Config:
    BASE_URL = 'https://www.cambodia-airways.com/caweb/backend'
    IMAGE_URL = 'https://www.cambodia-airways.com/image'
    ORIGIN = 'https://www.cambodia-airways.com'
    REFERER = 'https://www.cambodia-airways.com/'
    USER_AGENT = (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:150.0) '
        'Gecko/20100101 Firefox/150.0'
    )

    RSA_MODULUS_HEX = (
        'c7d5d9e6bfbe39e488839bc367ffb690dcc388de4ed6ec6dd38645876197574587'
        'cd3b36e1730b95100973aeb9835f7991d9daa964ffb93e59bacfe6426ea037'
    )
    RSA_EXPONENT = 65537

    DEFAULT_CABIN_GRADE = 'Y'
    DEFAULT_INFANT_NUMBER = 0
    DEFAULT_AVAILABLE_SEAT = 9
    DEFAULT_LANGUAGE = '1'
    CAPTCHA_RETRY_COUNT = 5

    NATION_MAPPING = {
        'US': {'cn': '美国', 'code': 'United States', 'num': 'US', 'pre': '1', 'kh': 'United States'},
        'CN': {'cn': '中国', 'code': 'China', 'num': 'CN', 'pre': '86', 'kh': 'China'},
        'HK': {'cn': '中国香港', 'code': 'Hong Kong, China', 'num': 'HK', 'pre': '852', 'kh': 'Hong Kong, China'},
        'MO': {'cn': '中国澳门', 'code': 'Macau, China', 'num': 'MO', 'pre': '853', 'kh': 'Macau, China'},
        'KH': {'cn': '柬埔寨', 'code': 'Cambodia', 'num': 'KH', 'pre': '855', 'kh': 'Cambodia'},
        'LA': {'cn': '老挝', 'code': 'LAOS', 'num': 'LA', 'pre': '856', 'kh': 'LAOS'},
        'MY': {'cn': '马来西亚', 'code': 'Malaysia', 'num': 'MY', 'pre': '60', 'kh': 'Malaysia'},
        'SG': {'cn': '新加坡', 'code': 'Singapore', 'num': 'SG', 'pre': '65', 'kh': 'Singapore'},
        'TH': {'cn': '泰国', 'code': 'Thailand', 'num': 'TH', 'pre': '66', 'kh': 'Thailand'},
        'VN': {'cn': '越南', 'code': 'Vietnam', 'num': 'VN', 'pre': '84', 'kh': 'Vietnam'},
    }

    AIRPORTS = [
        {'airportCode': 'KOS', 'airportName': 'Sihanoukville', 'cityName': 'Cambodia'},
        {'airportCode': 'KTI', 'airportName': 'Phnom Penh Techo International Airport', 'cityName': 'Cambodia'},
        {'airportCode': 'SAI', 'airportName': 'Siem Reap', 'cityName': 'Cambodia'},
        {'airportCode': 'CAN', 'airportName': 'Guangzhou (Terminal 3)', 'cityName': 'China'},
        {'airportCode': 'CKG', 'airportName': 'Chongqing', 'cityName': 'China'},
        {'airportCode': 'CSX', 'airportName': 'Changsha (Terminal 2)', 'cityName': 'China'},
        {'airportCode': 'HAK', 'airportName': 'Haikou', 'cityName': 'China'},
        {'airportCode': 'NKG', 'airportName': 'Nanjing', 'cityName': 'China'},
        {'airportCode': 'SYX', 'airportName': 'Sanya', 'cityName': 'China'},
        {'airportCode': 'SZX', 'airportName': 'Shenzhen', 'cityName': 'China'},
        {'airportCode': 'TFU', 'airportName': 'Chengdu Tianfu', 'cityName': 'China'},
        {'airportCode': 'HKG', 'airportName': 'Hong Kong(Terminal 1)', 'cityName': 'Hong Kong, China'},
        {'airportCode': 'VTE', 'airportName': 'Vientiane - Wattay', 'cityName': 'LAOS'},
        {'airportCode': 'MFM', 'airportName': 'Macau', 'cityName': 'Macau, China'},
        {'airportCode': 'KUL', 'airportName': 'Kuala Lumpur (Terminal 2)', 'cityName': 'Malaysia'},
        {'airportCode': 'RGN', 'airportName': 'Yangon', 'cityName': 'Myanmar'},
        {'airportCode': 'SIN', 'airportName': 'Singapore', 'cityName': 'Singapore'},
        {'airportCode': 'BKK', 'airportName': 'Bangkok', 'cityName': 'Thailand'},
        {'airportCode': 'CXR', 'airportName': 'Nha Trang', 'cityName': 'Vietnam'},
    ]

    @classmethod
    def get_airport(cls, airport_code: str) -> dict:
        return next((item for item in cls.AIRPORTS if item.get('airportCode') == airport_code), {})

    @classmethod
    def get_airport_route_label(cls, airport_code: str) -> list:
        airport = cls.get_airport(airport_code)
        return [
            airport.get('airportName') or airport_code,
            airport_code,
            airport.get('cityName') or '',
        ]

    @classmethod
    def get_nation(cls, nationality: str) -> dict:
        return cls.NATION_MAPPING.get((nationality or '').upper()) or cls.NATION_MAPPING['US']
