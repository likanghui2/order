from typing import Any, Optional

from pydantic import BaseModel, Field


class ResponseTaskInfoModel(BaseModel):
    status: int = Field(..., alias='status')
    message: str = Field(..., alias='message')
    task_id: str = Field(..., alias='taskId')
    source: str = Field(..., alias='source')
    data: Optional[Any] = Field(default=None, alias='data')
    call_data: Optional[str] = Field(default=None, alias='callData')