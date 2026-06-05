from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

from ..model.proxy_Info_model import ProxyInfoModel
from ..model.response_info_model import ResponseInfoModel
from ..utils.log_util import LogUtil


class TlsAbstract(ABC):

    def __init__(self):
        self.__proxy_data: Optional[ProxyInfoModel] = None
        self.__session = None
        self.__cookie_dict: Dict[str, str] = {}
        self.__timeout_second: int = 60
        self.__log = LogUtil('TlsAbstract')
    def generate_sess_id(self):
        """

        :return:
        """
        self.__proxy_data.generate_sess_id()

    def get_proxy_data(self) -> ProxyInfoModel:
        """

        :return:
        """
        return self.__proxy_data

    def get_session(self):
        return self.__session

    def get_cookie_dict(self):
        return self.__cookie_dict

    def get_cookie_str(self):
        return ';'.join([f'{key}={value}' for key, value in self.__cookie_dict.items()])

    def set_default_timeout(self, second: int):
        self.__timeout_second = second

    def set_proxy_info_data(self, proxy_info_data: ProxyInfoModel):
        self.__proxy_data = proxy_info_data

    def set_session(self, session):
        self.__session = session

    @abstractmethod
    def cookie_update(self, **kwargs):
        """

        :return:
        """
        pass

    @abstractmethod
    def get(self, url: str, headers: dict[str, Any], timeout: int = 60, **keywords) -> ResponseInfoModel:
        pass

    @abstractmethod
    def post(self,url: str,headers:dict[str,Any],data:[dict,str,bytes],timeout: int = 60,**keywords) -> ResponseInfoModel:
        pass

    @abstractmethod
    def initialize(self, **keywords):
        pass

    def del_cookie(self, cookie_name: str):
        if cookie_name in self.__cookie_dict:
            del self.__cookie_dict[cookie_name]
