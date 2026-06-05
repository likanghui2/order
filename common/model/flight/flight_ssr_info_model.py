from typing import List

from pydantic import BaseModel, Field

from common.model.flight.flight_baggage_model import FlightBaggageModel


class FlightSsrInfoModel(BaseModel):
    baggage: List[FlightBaggageModel] = Field(default=[], alias='baggage')
