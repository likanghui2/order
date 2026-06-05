from pydantic import BaseModel,Field


class RequestOrderDetailTaskModel(BaseModel):
    last_name: str = Field(...,alias="lastName")
    first_name: str = Field(...,alias="firstName")
    pnr: str = Field(...,alias="pnr")
    email: str = Field(default=None,alias="email")
