from typing import Optional

from common.model.proxy_Info_model import ProxyInfoModel
from flights.spirit.flight_common.flight_info_parser import FlightInfoParser
from flights.spirit.script.app_script import AppScript


class AppService:

    def __init__(self, proxy_info_data: ProxyInfoModel):
        self.__script = AppScript(proxy_info_data)

    def init_token(self):
        self.__script.get_abck()
        self.__script.get_token()

    def search(self,
               dep_airport: str,
               arr_airport: str,
               dep_date: str,
               adt_number: int,
               chd_number: int,
               infant_count: int,
               currency_code: str,
               ret_date: Optional[str] = None):

        response = self.__script.availability(
            dep_airport=dep_airport,
            arr_airport=arr_airport,
            dep_date=dep_date,
            adult_count=adt_number,
            child_count=chd_number,
            promo_code='',
            currency=currency_code,
        )

        return FlightInfoParser.journey_info_parser(response.to_dict()['data']['journeys'],currency_code)