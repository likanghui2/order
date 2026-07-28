import time
from typing import Optional

from common.errors.service_error import ServiceError, ServiceStateEnum
from common.utils import log_util, machine_cache_util
from flights.malaysiaairlines_mh.service.web_service import WebService


CACHE = machine_cache_util.MachineCache()
LOG = log_util.LogUtil("malaysiaAirlinesWebSessionCache")
CACHE_TIMEOUT_SECONDS = 480
REUSABLE_ERROR_CODES = {
    ServiceStateEnum.NO_FLIGHT_DATA.name,
    ServiceStateEnum.NO_AVAILABLE_FLIGHT_NUMBER.name,
    ServiceStateEnum.NO_AVAILABLE_BUNDLE.name,
    ServiceStateEnum.NO_AVAILABLE_CABIN.name,
}


def can_reuse_service(error: ServiceError) -> bool:
    return error.code in REUSABLE_ERROR_CODES


def cache_service(service: WebService, cached: Optional[dict] = None) -> bool:
    if cached is None:
        CACHE.set_data(service, CACHE_TIMEOUT_SECONDS)
        LOG.info(f"MH会话已缓存[{CACHE_TIMEOUT_SECONDS}]秒")
        return True

    timeout = int(cached["timeOut"])
    if int(time.time()) >= timeout:
        LOG.info(f"MH会话回收时已过期，丢弃会话[{timeout}]")
        return False

    CACHE.set_data(service, None, timeout)
    LOG.info(f"MH会话已回收，沿用过期时间[{timeout}]")
    return True
