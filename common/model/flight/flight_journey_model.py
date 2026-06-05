from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_serializer, field_validator

from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_segment_model import FlightSegmentModel
from common.utils.date_util import DateUtil


class FlightJourneyModel(BaseModel):
    segments: List[FlightSegmentModel] = Field(...,alias='segments')
    bundles: List[FlightBundleModel] = Field(...,alias='bundles')
    journey_key: str = Field(...,alias='journeyKey')
    dep_airport: str = Field(...,alias='depAirport')
    arr_airport: str = Field(...,alias='arrAirport')
    dep_time: datetime = Field(...,alias='depTime')
    arr_time: datetime = Field(...,alias='arrTime')
    ext: Optional[dict] = Field(default={},alias='ext')

    @field_validator('dep_time', 'arr_time', mode='before')
    @classmethod
    def date_string_parser(cls, v):
        if isinstance(v, str):
            parsed = DateUtil.string_to_date_auto(v)
            if parsed is not None:
                return parsed
        return v

    @field_serializer('dep_time','arr_time', when_used='json')
    def decimal_serializer(self, v:datetime):
        return v.strftime('%Y%m%d%H%M')
