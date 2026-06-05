from common.enums.document_type_enum import DocumentTypeEnum
from common.enums.gender_enum import GenderEnum
from common.enums.order_state_enum import OrderStateEnum
from common.enums.passenger_type_enum import PassengerTypeEnum


class Config:
    APP_USER_AGENT = "okhttp/4.11.0"
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    BUNDLE_TYPE_U_LITE = 'Ultra Lite'
    BUNDLE_TYPE_LITE = 'Lite'
    BUNDLE_TYPE_ESSE = 'Essential'
    BUNDLE_TYPE_MAX = 'Max'
    TITLE_MAP = {
        'ADT_M':'MR',
        'ADT_F':'MS',
        'CHD_M':'MASTER',
        'CHD_F':'MISS'
    }

    GENDER_MAP = {
        GenderEnum.M:"MALE",
        GenderEnum.F:"FEMALE",
        "MR": GenderEnum.M,
        "MS": GenderEnum.F,
        "MRS": GenderEnum.F,
        "MISS": GenderEnum.M,
    }

    PASSENGER_TYPE_MAP = {
        'ADT':PassengerTypeEnum.ADT,
        'CHD':PassengerTypeEnum.CHD,
    }

    DOCUMENT_TYPE_MAP = {
        DocumentTypeEnum.PASSPORT:"PASSPORT",
        DocumentTypeEnum.PERMIT_HK_MACAO:"TRAVEL_PERMIT_HK_MACAO"
    }

    FARE_TYPE_MAP = {
        "GO0":"U_LITE",
        "GO1":"LITE",
        "GO2":"ESSE",
        "GO3":"MAX",
    }

    PAYMENT_STATUS_MAP = {
        'SETTLED':OrderStateEnum.OPEN_FOR_USE,
        'UNSETTLED':OrderStateEnum.HOLD
    }