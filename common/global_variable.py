"""
@Project     : zhongyi_flight
@Author      : ciwei
@Date        : 2024/6/27 14:51 
@Description : 
@versions    : 1.0.0.0
"""
import json
import os

from common.model.proxy_Info_model import ProxyInfoModel
from common.utils import log_util
# 初始化环境变量
_ENV_STRING = os.environ.get("ENV")
_ENV_INT =  "DEV"
# 生产环境，禁止print输出

if _ENV_STRING == "DEV" or _ENV_STRING is None:
    os.environ.setdefault("RABBITMQ_HOST", '127.0.0.1')
    os.environ.setdefault("RABBITMQ_PORT", '5672')
    os.environ.setdefault("RABBITMQ_VIRTUAL_HOST", '')
    os.environ.setdefault("RABBITMQ_USERNAME", 'ciwei')
    os.environ.setdefault("RABBITMQ_PASSWORD", 'ciwei')

    os.environ.setdefault("REDIS_HOST", '127.0.0.1')
    os.environ.setdefault("REDIS_PORT", '6379')
    os.environ.setdefault("REDIS_USERNAME", '')
    os.environ.setdefault("REDIS_PASSWORD", '')

    os.environ.setdefault("PROXY_HOST", 'proxy.iproyal.net')
    os.environ.setdefault("PROXY_PORT", '9000')
    os.environ.setdefault("PROXY_USERNAME", 'xiaohao1')
    os.environ.setdefault("PROXY_PASSWORD", 'lvwei8214786')
    os.environ.setdefault("PROXY_REGION", 'de')
    os.environ.setdefault("PROXY_SESSION_TIME", '10')

if _ENV_STRING == "PROD":
    _ENV_INT = "PROD"
    # os.environ.setdefault("RABBITMQ_HOST", 'rabbitmq.rabbitmq-system.svc.cluster.local')
    # os.environ.setdefault("RABBITMQ_PORT", '5672')
    # os.environ.setdefault("RABBITMQ_VIRTUAL_HOST", '')
    #
    # os.environ.setdefault("REDIS_HOST", 'redis-ha-haproxy.redis.svc.cluster.local')
    # os.environ.setdefault("REDIS_PORT", '6379')
    # os.environ.setdefault("REDIS_USERNAME", '')
    # os.environ.setdefault("REDIS_PASSWORD", 'd2023')
    print(os.environ.get("PROXY_HOST"))


class GlobalVariable:
    ENV = _ENV_INT  # 环境变量
    PROXY_INFO_DATA = ProxyInfoModel(
        host=os.environ.get("PROXY_HOST"),
        port=int(os.environ.get("PROXY_PORT")),
        username=os.environ.get("PROXY_USERNAME"),
        password=os.environ.get("PROXY_PASSWORD"),
        region=os.environ.get("PROXY_REGION") if os.environ.get("PROXY_REGION") else None,
        session_time=int(os.environ.get("PROXY_SESSION_TIME")) if os.environ.get("PROXY_SESSION_TIME") else None,
        format=os.environ.get("PROXY_FORMAT") if os.environ.get("PROXY_FORMAT") else 'http://client-{username}_area-{region}_session-{sessId}_life-{sessionTime}:{password}@{host}:{port}',
    )  # 代理信息
    # PROXY_INFO_DATA = ProxyInfoModel(
    #     host="gw.dataimpulse.com",
    #     port=int(823),
    #     username='9218a3e1e54c5a2ee31e',
    #     password='6f63ad4e69b63ee6',
    #     region='th,my,sg,id',
    #     session_time=10,
    #     format='http://{username}__cr.{region}:{password}@{host}:{port}',
    # )  # 代理信息
    ENV = _ENV_STRING  # 环境变量
    RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST")  # rabbitmq host
    RABBITMQ_PORT = int(os.environ.get("RABBITMQ_PORT"))  # rabbitmq port
    RABBITMQ_VIRTUAL_HOST = os.environ.get("RABBITMQ_VIRTUAL_HOST")  # rabbitmq host
    RABBITMQ_USERNAME = os.environ.get('RABBITMQ_USERNAME')
    RABBITMQ_PASSWORD = os.environ.get('RABBITMQ_PASSWORD')

    REDIS_HOST = os.environ.get("REDIS_HOST")  # redis host
    REDIS_PORT = int(os.environ.get("REDIS_PORT"))  # redis port
    REDIS_TASK_RESULT_DB = 0
    REDIS_USERNAME = os.environ.get("REDIS_USERNAME")
    REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD")  # redis password
    OUTPUT_HTTP_LOG = bool(os.environ.get("OUTPUT_HTTP_LOG")) if os.environ.get("OUTPUT_HTTP_LOG") else True
