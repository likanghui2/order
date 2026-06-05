import random
from typing import Optional

from pydantic import BaseModel, Field
from ..utils.string_util import StringUtil


class ProxyInfoModel(BaseModel):
    host: str = Field(..., description='代理地址')
    port: int = Field(..., description='代理端口')
    username: Optional[str] = Field(default=None, description='代理用户名')
    password: Optional[str] = Field(default=None, description='代理密码')
    region: Optional[str] = Field(default=None, description='代理区域')
    sess_id: Optional[str] = Field(default=None, description='session')
    session_time: Optional[int] = Field(default=None, description='session time')
    format: str = Field(default=None,description="proxy format")
    def generate_sess_id(self):
        self.sess_id = f'{StringUtil.generate_random_string()}{random.randint(1000, 9999)}'



    def get_proxy_info_to_string(self):
        proxy_url = self.format
        k_data = {
            "host": self.host,
            "port": self.port,
        }
        if self.format.find('{username}') != -1:
            if self.username is None or self.password is None:
                raise ValueError('username and password are required')
            else:
                k_data['username'] = self.username
                k_data['password'] = self.password


        if self.format.find('{region}') != -1:
            if self.region is None:
                raise ValueError('region is required')
            k_data['region'] = self.region

        if self.format.find('{sessId}') != -1:
            if self.sess_id is None:
                raise ValueError('sessId is required')
            k_data['sessId'] = self.sess_id

        if self.format.find('{sessionTime}') != -1:
            if self.session_time is None:
                raise ValueError('sessionTime is required')
            k_data['sessionTime'] = self.session_time

        proxy_url = proxy_url.format(**k_data)
        return proxy_url



