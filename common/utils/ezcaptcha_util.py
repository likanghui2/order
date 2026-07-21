import json
from time import sleep
from typing import Dict, Any

import requests

from common.errors.service_error import ServiceError, ServiceStateEnum
from common.utils.log_util import LogUtil


class EzCaptcha:
    """
    EzCaptcha 验证码解决服务封装
    """

    def __init__(self, client_key: str, timeout: int = 100):
        """
        初始化 EzCaptcha 客户端

        Args:
            client_key (str): 接入平台的 API 密钥
            timeout (int): 请求超时时间，单位秒，默认 100
        """
        self._client_key = client_key
        self._timeout = timeout
        self._log = LogUtil("EzCaptcha")

    def _solve_sync_task(self, task: Dict[str, Any], error_enum: ServiceStateEnum, task_type: str) -> Dict[str, Any]:
        """
        通用同步任务求解方法（适用于所有 EzCaptcha 任务）

        Args:
            task (Dict[str, Any]): 任务参数
            error_enum (ApiStateEnum): 出错时抛出的错误类型
            task_type (str): 日志追踪用的任务标识

        Returns:
            Dict[str, Any]: solution 字段内容
        """
        payload = {
            "clientKey": self._client_key,
            "task": task
        }

        self._log.info(json.dumps(payload, ensure_ascii=False), f"[{task_type}] 请求参数")

        try:
            response = requests.post(
                url="https://sync.ez-captcha.com/createSyncTask",
                json=payload,
                timeout=self._timeout
            )
            response.raise_for_status()
        except Exception as e:
            self._log.error(f"[{task_type}] 请求异常: {str(e)}")
            raise ServiceError(error_enum)

        self._log.info(response.text, f"[{task_type}] 响应结果")

        resp_json = response.json()
        if resp_json.get("errorId", 1) != 0:
            raise ServiceError(error_enum, resp_json.get("errorDescription", f"{task_type} 任务失败"))

        return resp_json.get("solution", {})

    def create_async_task(self, task: Dict[str, Any], error_enum: ServiceStateEnum, task_type: str) -> str:
        """
        创建 EzCaptcha 异步任务（仅返回 taskId，不自动获取结果）

        Args:
            task (Dict[str, Any]): 任务请求体，例如网站信息、验证码类型等
            error_enum (ApiStateEnum): 错误类型枚举
            task_type (str): 日志标识（如 'reCAPTCHA'）

        Returns:
            str: 异步任务 ID

        Raises:
            APIError: 若任务创建失败
        """
        payload = {
            "clientKey": self._client_key,
            "task": task
        }

        self._log.info(json.dumps(payload, ensure_ascii=False), f"[{task_type}] 异步任务创建参数")

        try:
            response = requests.post(
                url="https://api.ez-captcha.com/createTask",
                json=payload,
                timeout=self._timeout
            )
            self._log.info(response.text)
            response.raise_for_status()
        except Exception as e:
            self._log.error(f"[{task_type}] 异步任务创建请求失败: {str(e)}")
            raise ServiceError(error_enum)

        resp_json = response.json()
        self._log.info(json.dumps(resp_json, ensure_ascii=False), f"[{task_type}] 异步任务创建响应")

        if resp_json.get("errorId", 1) != 0:
            raise ServiceError(error_enum)

        return resp_json["taskId"]

    def get_async_task_result(self, task_id: str, error_enum: ServiceStateEnum, task_type: str,
                              retries: int = 15, delay: int = 5) -> Dict[str, Any]:
        """
        获取异步任务执行结果（通过轮询方式）

        Args:
            task_id (str): 任务 ID（由 createTask 返回）
            error_enum (ApiStateEnum): 出错时抛出的错误类型
            task_type (str): 日志记录用的任务名称
            retries (int): 最多重试次数，默认 15
            delay (int): 每次查询之间的等待时间（秒），默认 5

        Returns:
            Dict[str, Any]: 成功任务的 solution 内容

        Raises:
            APIError: 查询失败或超时
        """
        payload = {
            "clientKey": self._client_key,
            "taskId": task_id
        }

        for i in range(retries):
            try:
                response = requests.post(
                    url="https://api.ez-captcha.com/getTaskResult",
                    json=payload,
                    timeout=self._timeout
                )
                response.raise_for_status()
            except Exception as e:
                self._log.error(f"[{task_type}] 第 {i + 1} 次任务查询失败: {str(e)}")
                sleep(delay)
                continue

            result = response.json()
            self._log.info(json.dumps(result, ensure_ascii=False), f"[{task_type}] 第 {i + 1} 次查询结果")

            if result.get("errorId") != 0:
                raise ServiceError(error_enum)

            if result.get("status") == "ready":
                return result.get("solution", {})

            sleep(delay)

        raise ServiceError(error_enum)

    def solve_recaptcha(
            self,
            website_url: str,
            website_key: str,
            task_type: str,
            is_invisible: bool = False,
            action=None,
    ) -> str:
        """
        解决 Google reCAPTCHA，并返回 gRecaptchaResponse Token

        Args:
            action:
            website_url (str): 验证页面地址
            website_key (str): reCAPTCHA site key
            task_type (str): 任务类型，如 RecaptchaV2TaskProxyless
            is_invisible (bool): 是否为隐形验证，默认为 False

        Returns:
            str: gRecaptchaResponse Token
        """
        task = {
            "websiteURL": website_url,
            "websiteKey": website_key,
            "type": task_type,
            "isInvisible": is_invisible
        }
        if "V3" in task_type:
            task["pageAction"] = action
        task_id = self.create_async_task(task, ServiceStateEnum.API_RESPONSE_EXCEPTION, "reCAPTCHA")
        solution = self.get_async_task_result(task_id, ServiceStateEnum.API_RESPONSE_EXCEPTION, "reCAPTCHA")
        return solution['gRecaptchaResponse']

    def solve_cf_turnstile(
            self, website_url, website_key, action=None):
        task = {
            "websiteURL": website_url,
            "type": "CloudFlareTurnstileTask",
            "websiteKey": website_key,
        }
        if action:
            task["rqData"] = {"metadataAction": action}
        task_id = self.create_async_task(task, ServiceStateEnum.API_RESPONSE_EXCEPTION, "cf_turnstile")
        solution = self.get_async_task_result(task_id, ServiceStateEnum.API_RESPONSE_EXCEPTION, "cf_turnstile", retries=30, delay=1)

        return solution['token']
    def solve_cf_cookie(
            self, website_url, proxy):
        task = {
            "websiteURL": website_url,
            "type": "CloudFlare5STask",
            'proxy': proxy,
        }
        task_id = self.create_async_task(task, ServiceStateEnum.API_RESPONSE_EXCEPTION, "cf_cookie")
        solution = self.get_async_task_result(task_id, ServiceStateEnum.API_RESPONSE_EXCEPTION, "cf_cookie")

        return solution
