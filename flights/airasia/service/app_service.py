from common.errors.service_error import ServiceStateEnum, ServiceError
from flights.airasia.flight_common.flight_info_parser import FlightInfoParser
from flights.airasia.script.app_script import AppScript


class AppService:
    def __init__(self, proxy_info):
        self.__script = AppScript(proxy_info)
        self.__script.initialize()

    def initialization(self):
        self.__script.init_jwt()

    def search(self, dep_airport: str,
               arr_airport: str,
               currency_code: str,
               dep_date: str,
               adt_number: int,
               chd_number: int):

        response = self.__script.search(
            dep_airport,
            arr_airport,
            currency_code,
            dep_date,
            adt_number,
            chd_number
        )

        journey_list = FlightInfoParser.journey_info_parser(response['searchResults'])

        if len(journey_list) == 0:
            raise ServiceError(ServiceStateEnum.NO_FLIGHT_DATA)
        return journey_list