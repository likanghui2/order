import json

from pydantic import BaseModel, Field


class ResponseInfoModel(BaseModel):
    data_bytes: bytes = Field(...)
    status: int = Field(...)
    headers: dict = Field(...)
    url: str = Field(...)

    def to_dict(self):
        return json.loads(self.data_bytes.decode('utf-8'))

    def to_text(self):
        try:
            return self.data_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return f"<binary data: {len(self.data_bytes)} bytes>"

    @property
    def location(self):
        return next(
            (value for key, value in self.headers.items() if key == "Location" or key == "location"), None)
