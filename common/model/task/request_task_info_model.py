from typing import Any

from pydantic import BaseModel,Field


class RequestTaskInfoModel(BaseModel):
    task_id: str = Field(..., alias='taskId')
    task_type: str = Field(..., alias='taskType')
    source: str = Field(..., alias='source')
    task_data: Any = Field(..., alias='taskData')
