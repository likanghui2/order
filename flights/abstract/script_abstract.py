from abc import ABC,abstractmethod
from typing import Optional

from typing_extensions import TypedDict, Unpack

from common.model.response_info_model import ResponseInfoModel





class ScriptAbstract(ABC):
    @abstractmethod
    def search(self,**kwargs) -> ResponseInfoModel:
        pass