from common.enums.gender_enum import GenderEnum
from common.enums.passenger_type_enum import PassengerTypeEnum
from common.enums.ssr_type_enum import SsrTypeEnum


class CebupacificairConfig:
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    )
    XAT = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJjb2RlVmVyc2lvbiI6Imh2dzlZcnBPTWRmenJ5RkZKZ1I5SHo0Umo3NnFoM25FIn0."
        "FQhLXkyaetq7RZb4wIoTTdGFcHFiopsxvRsZpRlEtiU"
    )
    SECR = "kC2ghRh4XthMdfdY"
    PARK = "r27tQrELZedih9r0"
    AESK = "d15be270a756e84bae09ea88b12e80af6596541e6a5266f73a6980f1669bd718"
    HASH_KEY = "kAYDgiHzp0TeNkgUjMdHFANw3pATzAjE"

    TITLE_ROUTE = {
        GenderEnum.M: {
            PassengerTypeEnum.ADT: 'MR',
            PassengerTypeEnum.CHD: 'MR',
        },
        GenderEnum.F: {
            PassengerTypeEnum.ADT: 'MS',
            PassengerTypeEnum.CHD: 'MS',
        },
    }

    GENDER_ROUTE = {
        GenderEnum.M: 'Male',
        GenderEnum.F: 'Female',
    }

    PRODUCT_RULE = {
        'EASYPC': {
            'baggage_data': [
                {'type': SsrTypeEnum.HAND_BAGGAGE, 'weight': 7},
                {'type': SsrTypeEnum.HAULING_BAGGAGE, 'weight': 20},
            ],
            'tag': 'GO Easy',
        },
        'FLEXPC': {
            'baggage_data': [
                {'type': SsrTypeEnum.HAND_BAGGAGE, 'weight': 7},
                {'type': SsrTypeEnum.HAULING_BAGGAGE, 'weight': 20},
            ],
            'tag': 'GO Flexi',
        },
        'EDPC': {
            'baggage_data': [
                {'type': SsrTypeEnum.HAND_BAGGAGE, 'weight': 7},
                {'type': SsrTypeEnum.HAULING_BAGGAGE, 'weight': 20},
            ],
            'tag': 'GO Easy',
        },
        'FDPC': {
            'baggage_data': [
                {'type': SsrTypeEnum.HAND_BAGGAGE, 'weight': 7},
                {'type': SsrTypeEnum.HAULING_BAGGAGE, 'weight': 20},
            ],
            'tag': 'GO Flexi',
        },
    }

    TAX_SCALE = {
        'PVG_MNL': 0.5, 'CAN_MNL': 0.5, 'XMN_MNL': 0.5, 'TPE_MNL': 0.5,
        'HKG_MNL': 0.5, 'HKG_CEB': 0.5, 'HKG_CRK': 0.5, 'MFM_MNL': 0.5,
        'ICN_MNL': 0.5, 'ICN_CEB': 0.5, 'NRT_MNL': 0.5, 'NRT_CRK': 0.5,
        'NRT_CEB': 0.5, 'NGO_MNL': 0.5, 'FUK_MNL': 0.5, 'KIX_MNL': 0.5,
        'HAN_MNL': 0.5, 'SGN_MNL': 0.5, 'DAD_MNL': 0.5, 'SYD_MNL': 0.5,
        'MEL_MNL': 0.5, 'DXB_MNL': 0.5, 'SIN_MNL': 0.5, 'SIN_CEB': 0.5,
        'SIN_CRK': 0.5, 'BWN_MNL': 0.5, 'BKK_MNL': 0.5, 'BKK_CRK': 0.5,
        'KUL_MNL': 0.5, 'BKI_MNL': 0.5, 'CGK_MNL': 0.5, 'DPS_MNL': 0.5,
        'MNL_PVG': 0.5, 'MNL_CAN': 0.5, 'MNL_XMN': 0.5, 'MNL_TPE': 0.5,
        'MNL_HKG': 0.5, 'CEB_HKG': 0.5, 'CRK_HKG': 0.5, 'MNL_MFM': 0.5,
        'MNL_ICN': 0.5, 'CEB_ICN': 0.5, 'MNL_NRT': 0.5, 'CRK_NRT': 0.5,
        'CEB_NRT': 0.5, 'MNL_NGO': 0.5, 'MNL_FUK': 0.5, 'MNL_KIX': 0.5,
        'MNL_HAN': 0.5, 'MNL_SGN': 0.5, 'MNL_DAD': 0.5, 'MNL_SYD': 0.5,
        'MNL_MEL': 0.5, 'MNL_DXB': 0.5, 'MNL_SIN': 0.5, 'CEB_SIN': 0.5,
        'CRK_SIN': 0.5, 'MNL_BWN': 0.5, 'MNL_BKK': 0.5, 'CRK_BKK': 0.5,
        'MNL_KUL': 0.5, 'MNL_BKI': 0.5, 'MNL_CGK': 0.5, 'MNL_DPS': 0.5,
        'MNL_CEB': 0.6, 'MNL_BCD': 0.6, 'MNL_DRP': 0.6, 'MNL_PPS': 0.6,
        'MNL_ILO': 0.6, 'MNL_BXU': 0.6, 'MNL_LAO': 0.6, 'MNL_OZC': 0.6,
        'MNL_DPL': 0.6, 'MNL_RXS': 0.6, 'MNL_KLO': 0.6, 'MNL_DGT': 0.6,
        'MNL_PAG': 0.6, 'MNL_TUG': 0.6, 'MNL_VRC': 0.6, 'MNL_CYZ': 0.6,
        'MNL_DVO': 0.6, 'MNL_CGY': 0.6, 'MNL_TAC': 0.6, 'MNL_GES': 0.6,
        'MNL_TAG': 0.6, 'MNL_MPH': 0.6, 'MNL_ZAM': 0.6, 'CEB_ILO': 0.6,
        'CEB_CGY': 0.6, 'CEB_GES': 0.6, 'CEB_CRK': 0.6, 'CEB_ZAM': 0.6,
        'CEB_DVO': 0.6, 'CEB_PPS': 0.6, 'CEB_BXU': 0.6, 'CEB_DPL': 0.6,
        'CEB_DRP': 0.6, 'CEB_MPH': 0.6, 'GES_CRK': 0.6, 'GES_ILO': 0.6,
        'DVO_ILO': 0.6, 'DVO_TAG': 0.6, 'DVO_BCD': 0.6, 'DVO_ZAM': 0.6,
        'ILO_CGY': 0.6, 'ILO_PPS': 0.6, 'ILO_CRK': 0.6, 'ZAM_TWT': 0.6,
        'CRK_MPH': 0.6, 'CEB_MNL': 0.6, 'BCD_MNL': 0.6, 'DRP_MNL': 0.6,
        'PPS_MNL': 0.6, 'ILO_MNL': 0.6, 'BXU_MNL': 0.6, 'LAO_MNL': 0.6,
        'OZC_MNL': 0.6, 'DPL_MNL': 0.6, 'RXS_MNL': 0.6, 'KLO_MNL': 0.6,
        'DGT_MNL': 0.6, 'PAG_MNL': 0.6, 'TUG_MNL': 0.6, 'VRC_MNL': 0.6,
        'CYZ_MNL': 0.6, 'DVO_MNL': 0.6, 'CGY_MNL': 0.6, 'TAC_MNL': 0.6,
        'GES_MNL': 0.6, 'TAG_MNL': 0.6, 'MPH_MNL': 0.6, 'ZAM_MNL': 0.6,
        'ILO_CEB': 0.6, 'CGY_CEB': 0.6, 'GES_CEB': 0.6, 'CRK_CEB': 0.6,
        'ZAM_CEB': 0.6, 'DVO_CEB': 0.6, 'PPS_CEB': 0.6, 'BXU_CEB': 0.6,
        'DPL_CEB': 0.6, 'DRP_CEB': 0.6, 'MPH_CEB': 0.6, 'CRK_GES': 0.6,
        'ILO_GES': 0.6, 'ILO_DVO': 0.6, 'TAG_DVO': 0.6, 'BCD_DVO': 0.6,
        'ZAM_DVO': 0.6, 'CGY_ILO': 0.6, 'PPS_ILO': 0.6, 'CRK_ILO': 0.6,
        'TWT_ZAM': 0.6, 'MPH_CRK': 0.6, 'DVO_IAO': 0.6, 'DVO_CGY': 0.6,
        'CEB_USU': 0.6, 'CEB_TAC': 0.6, 'CEB_IAO': 0.6, 'CEB_OZC': 0.6,
        'CEB_BCD': 0.6, 'CEB_CYP': 0.6, 'CEB_SUG': 0.6, 'CEB_CGM': 0.6,
        'CEB_WNP': 0.6, 'CEB_PAG': 0.6, 'CEB_DGT': 0.6, 'MNL_MBT': 0.6,
        'MNL_IAO': 0.6, 'MNL_USU': 0.6, 'MNL_SJI': 0.6, 'MNL_SUG': 0.6,
        'MNL_WNP': 0.6, 'IAO_DVO': 0.6, 'CGY_DVO': 0.6, 'USU_CEB': 0.6,
        'TAC_CEB': 0.6, 'IAO_CEB': 0.6, 'OZC_CEB': 0.6, 'BCD_CEB': 0.6,
        'CYP_CEB': 0.6, 'SUG_CEB': 0.6, 'CGM_CEB': 0.6, 'WNP_CEB': 0.6,
        'PAG_CEB': 0.6, 'DGT_CEB': 0.6, 'MBT_MNL': 0.6, 'IAO_MNL': 0.6,
        'USU_MNL': 0.6, 'SJI_MNL': 0.6, 'SUG_MNL': 0.6, 'WNP_MNL': 0.6,
    }

    DOCUMENT_AIRPORT = ['PEK', 'PVG', 'CAN', 'XMN', 'SZX']
