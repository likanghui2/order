from typing import Optional

from pydantic import BaseModel, Field


class RequestCancelOrderTaskModel(BaseModel):
    pnr: str = Field(default="",alias="pnr")
    agent_user_name: Optional[str] = Field(default="",alias="agentUserName")
    agent_password: Optional[str] = Field(default="",alias="agentPassword")