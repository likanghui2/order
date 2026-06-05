from typing import List

from common.enums.document_type_enum import DocumentTypeEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.order.contact_info_model import ContactInfoModel
from common.model.order.passenger_info_model import PassengerInfoModel
from common.utils.date_util import DateUtil
from flights.cebupacificair_5j.config import CebupacificairConfig


class CebupacificairBookingUtils:
    @staticmethod
    def check_document_data(dep_airport: str,
                            arr_airport: str,
                            passenger_list: List[PassengerInfoModel]) -> bool:
        if dep_airport not in CebupacificairConfig.DOCUMENT_AIRPORT \
                and arr_airport not in CebupacificairConfig.DOCUMENT_AIRPORT:
            return False

        invalid_names = [
            passenger.get_passenger_name()
            for passenger in passenger_list
            if passenger.document_info is None
               or not passenger.document_info.number
               or not passenger.document_info.nationality
               or not passenger.document_info.issuing_country
        ]
        if invalid_names:
            raise ServiceError(ServiceStateEnum.DOCUMENT_INFO_NOT_NULL, ','.join(invalid_names))
        return True

    @staticmethod
    def _date_format(date_text: str) -> str:
        return DateUtil.string_to_target_format(date_text, '%Y-%m-%d')

    @classmethod
    def passenger_utils(cls, passengers: List[PassengerInfoModel], purchasing: bool) -> List[dict]:
        passenger_infos = []
        for passenger in passengers:
            title = CebupacificairConfig.TITLE_ROUTE[passenger.gender][passenger.type]
            passenger_info = {
                'passengerKey': passenger.key,
                'isInfant': False,
                'name': {
                    'title': title,
                    'first': passenger.first_name,
                    'middle': '',
                    'last': passenger.last_name,
                    'suffix': '',
                },
                'info': {
                    'gender': CebupacificairConfig.GENDER_ROUTE[passenger.gender],
                    'dateOfBirth': cls._date_format(passenger.birthday),
                    'nationality': (
                        passenger.document_info.nationality
                        if passenger.document_info else 'US'
                    ),
                    'residentCountry': (
                        passenger.document_info.nationality
                        if passenger.document_info else 'US'
                    ),
                },
                'travelDocuments': [],
                'ssrs': [],
                'addresses': [],
            }
            if purchasing and passenger.document_info:
                document_type = 'P'
                if passenger.document_info.type != DocumentTypeEnum.PASSPORT:
                    document_type = str(passenger.document_info.type.value)
                passenger_info['travelDocuments'].append({
                    'documentTypeCode': document_type,
                    'name': {
                        'title': title,
                        'first': passenger.first_name,
                        'middle': '',
                        'last': passenger.last_name,
                        'suffix': '',
                    },
                    'gender': CebupacificairConfig.GENDER_ROUTE[passenger.gender],
                    'birthCountry': passenger.document_info.nationality,
                    'dateOfBirth': cls._date_format(passenger.birthday),
                    'nationality': passenger.document_info.nationality,
                    'number': passenger.document_info.number,
                    'issuedDate': None,
                    'issuedByCode': passenger.document_info.issuing_country,
                    'expirationDate': cls._date_format(passenger.document_info.expire_date),
                })
            passenger_infos.append(passenger_info)
        return passenger_infos

    @staticmethod
    def contact_dict_utils(contact_info: ContactInfoModel, passenger: PassengerInfoModel) -> dict:
        return {
            'contactTypeCode': 'P',
            'name': {
                'title': CebupacificairConfig.TITLE_ROUTE[passenger.gender][passenger.type],
                'first': passenger.first_name,
                'middle': '',
                'last': passenger.last_name,
                'suffix': '',
            },
            'emailAddress': contact_info.email_address,
            'address': None,
            'phoneNumbers': [
                {
                    'type': 'Home',
                    'number': f'{contact_info.phone_code}-{contact_info.phone_number}',
                }
            ],
        }

    @staticmethod
    def empty_addon_passenger_utils(passengers: List[PassengerInfoModel]) -> List[dict]:
        return [
            {
                'passengerKey': passenger.key,
                'ssrs': [],
            }
            for passenger in passengers
        ]
