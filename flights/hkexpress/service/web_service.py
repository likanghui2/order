import json
from pickle import FRAME
from typing import Optional

from common.model.proxy_Info_model import ProxyInfoModel
from ..script.web_script import WebScript
from ..flight_common.flight_info_parser import FlightInfoParser


class WebService:
    def __init__(self, proxy_info_data: ProxyInfoModel):
        self.__script = WebScript(proxy_info_data)


    def search(self,
               dep_airport: str,
               arr_airport: str,
               dep_date: str,
               adt_number: int,
               chd_number: int,
               infant_count: int,
               currency_code: str,
               ret_date: Optional[str] = None):

        response = self.__script.search(
            dep_airport=dep_airport,
            arr_airport=arr_airport,
            dep_date=dep_date,
            adt_number=adt_number,
            chd_number=chd_number,
            infant_count=infant_count,
            currency_code=currency_code,
            ret_date=ret_date
        )


        response_dict = response.to_dict()
        journey_list = FlightInfoParser.journey_info_parser(response_dict['trip'],0)
        return journey_list
