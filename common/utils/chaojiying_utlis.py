#!/usr/bin/env python
# coding:utf-8

from hashlib import md5
from typing import Dict, Any, Optional

import requests


class ChaojiyingClient:
    """
    超级鹰识别服务客户端
    官方文档: http://www.chaojiying.com/api-21.html
    """

    def __init__(self, username: str, password: str, soft_id: str):
        """
        初始化识别客户端

        Args:
            username (str): 超级鹰账号
            password (str): 超级鹰密码（明文）
            soft_id (str): 软件 ID，可在超级鹰后台查看
        """
        self.username = username
        self.password = md5(password.encode('utf-8')).hexdigest()
        self.soft_id = soft_id
        self.base_params: dict = {
            'user': self.username,
            'pass2': self.password,
            'softid': self.soft_id,
        }
        self.headers = {
            'Connection': 'Keep-Alive',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        }

    def _post(self, url: str, data: Dict[str, Any], files: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        统一发送 POST 请求

        Args:
            url (str): 请求地址
            data (Dict[str, Any]): 请求数据
            files (Optional[Dict[str, Any]]): 文件数据

        Returns:
            Dict[str, Any]: JSON 响应结果
        """
        try:
            response = requests.post(url, data=data, files=files, headers=self.headers, timeout=15)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"err_no": -1, "err_str": str(e)}

    def solve_captcha(self, image_bytes: bytes, code_type: int) -> Dict[str, Any]:
        """
        上传图片并识别验证码

        Args:
            image_bytes (bytes): 图片二进制内容
            code_type (int): 验证码类型，参考 http://www.chaojiying.com/price.html

        Returns:
            Dict[str, Any]: 响应结果 JSON
        """
        data = {'codetype': code_type}
        data.update(self.base_params)
        files = {'userfile': ('captcha.jpg', image_bytes)}
        return self._post("http://upload.chaojiying.net/Upload/Processing.php", data, files)

    def report_error(self, pic_id: str) -> Dict[str, Any]:
        """
        上报识别错误的验证码 ID

        Args:
            pic_id (str): 识别返回结果中的 pic_id

        Returns:
            Dict[str, Any]: 响应结果
        """
        data = {
            'id': pic_id,
        }
        data.update(self.base_params)
        return self._post("https://upload.chaojiying.net/Upload/ReportError.php", data)
