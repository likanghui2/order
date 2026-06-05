from typing import List, Optional

from pydantic import BaseModel, Field

from common.model.flight.flight_journey_model import FlightJourneyModel


class ResponseSearchInfoModel(BaseModel):
    journeys: Optional[List[FlightJourneyModel]] = Field(default=None, alias='journeys')


