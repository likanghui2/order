class LionairthaiConfigV2:
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    )
    SEC_CH_UA = '"Not=A?Brand";v="99", "Chromium";v="136", "Google Chrome";v="136"'
    AES_KEY = b"azSQcPZqOhq2FgI="

    CURRENCY_POINT_OF_SALE = {
        "AED": "AE", "AUD": "AU", "BDT": "BD", "CNY": "CN",
        "HKD": "HK", "IDR": "ID", "INR": "IN", "JPY": "JP",
        "KRW": "KR", "MYR": "MY", "NZD": "NZ", "SAR": "SA",
        "SGD": "SG", "THB": "TH", "TWD": "TW", "USD": "VN",
    }
    PASSENGER_TITLE = {
        "ADT_M": "Mr", "ADT_F": "Miss", "CHD_M": "Mstr", "CHD_F": "Miss",
    }
    AIRPORT_COUNTRIES = {
        "AU": {"ADL", "BNE", "CBR", "MEL", "PER", "SYD"},
        "BD": {"CGP", "DAC"},
        "CN": {
            "CAN", "CGO", "CKG", "CSX", "CZX", "HAK", "HFE", "HGH",
            "KHN", "KMG", "KWE", "KWL", "LHW", "MFM", "NGB", "NKG",
            "NNG", "PKX", "PVG", "SYX", "SZX", "TFU", "TNA", "TSN",
            "TYN", "WUH", "XIY", "XMN", "XNN",
        },
        "HK": {"HKG"},
        "ID": {
            "ABU", "AEG", "AMQ", "ARD", "BDJ", "BDO", "BEJ", "BIK",
            "BJW", "BKS", "BMU", "BPN", "BTH", "BTJ", "BTW", "BUW",
            "BWX", "BXB", "CGK", "DEX", "DJB", "DJJ", "DPS", "DTB",
            "DUM", "ENE", "FKQ", "FLZ", "GLX", "GNS", "GTO", "HLP",
            "JOG", "KAZ", "KBU", "KDI", "KNG", "KNO", "KOE", "KTG",
            "LBJ", "LKA", "LLO", "LOP", "LSW", "LUV", "LUW", "MDC",
            "MED", "MEQ", "MES", "MJU", "MKF", "MKQ", "MKW", "MLG",
            "MNA", "MOF", "NAH", "NBX", "NTX", "OTI", "PDG", "PGK",
            "PKN", "PKU", "PKY", "PLM", "PLW", "PNK", "PSJ", "PUM",
            "RTI", "SMG", "SMQ", "SOC", "SOQ", "SRG", "SUB", "SWQ",
            "SXK", "TJQ", "TKG", "TLI", "TMC", "TNJ", "TRK", "TTE",
            "TXE", "UOL", "UPG", "VPM", "WGP", "WMX", "WNI", "WUB",
            "YIA", "YKR",
        },
        "IN": {"AMD", "ATQ", "BLR", "BOM", "CCU", "COK", "DEL", "MAA", "TRV", "TRZ", "VNS", "VTZ"},
        "JP": {"CTS", "FUK", "KIX", "NGO", "NRT", "OKA"},
        "KH": {"KOS", "PNH"},
        "KR": {"ICN"},
        "LK": {"CMB"},
        "MM": {"RGN"},
        "MV": {"MLE"},
        "MY": {"AOR", "BKI", "IPH", "JHB", "KBR", "KCH", "KTE", "KUA", "KUL", "LBU", "LGK", "MKZ", "MYY", "PEN", "SZB", "TGG", "TWU"},
        "NP": {"KTM"},
        "PK": {"LHE"},
        "RU": {"NGK"},
        "SA": {"JED"},
        "SG": {"SIN"},
        "TH": {"BKK", "CEI", "CNX", "DMK", "HDY", "HHQ", "HKT", "KBV", "KKC", "KOP", "NNT", "NST", "PHS", "TST", "UBP", "URT", "USM", "UTH", "UTP"},
        "TW": {"KHH", "TPE"},
        "US": {"BDG"},
        "UZ": {"TAS"},
        "VN": {"DAD", "HAN", "SGN"},
    }

    @classmethod
    def airport_country(cls, airport: str) -> str:
        airport = str(airport or "").strip().upper()
        for country, airports in cls.AIRPORT_COUNTRIES.items():
            if airport in airports:
                return country
        raise ValueError(f"未配置机场国家代码[{airport}]")
