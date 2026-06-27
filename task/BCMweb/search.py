from common.decorators.task_decorator import task_decorator
from common.enums.task_type_enum import TaskTypeEnum
from common.global_variable import GlobalVariable
from common.model.task.request_search_task_data_model import RequestSearchTaskDataModel
from common.utils import celery_util, log_util, machine_cache_util
from common.utils.date_util import DateUtil
from common.utils.proxy_ext_util import proxy_info_from_ext
from flights.bookcabin.config import BookCabinConfig
from flights.bookcabin.service.web_service import WebService

CELERY_APP = celery_util.create(GlobalVariable.RABBITMQ_USERNAME, GlobalVariable.RABBITMQ_PASSWORD)
CACHE = machine_cache_util.MachineCache()
LOG = log_util.LogUtil("BCMwebSearch")


@CELERY_APP.task(bind=True)
@task_decorator(LOG)
def main(self, search_data: RequestSearchTaskDataModel):
    service_cache = CACHE.get_data()
    if service_cache is None:
        service = WebService(proxy_info_from_ext(search_data.ext))
        service.initialize_session()
    else:
        service = service_cache["value"]

    promo_code = search_data.private_code[0] if search_data.private_code else ""
    journey_list = service.search(
        dep_airport=search_data.dep_airport,
        arr_airport=search_data.arr_airport,
        dep_date=DateUtil.string_to_target_format(search_data.dep_date, "%Y-%m-%d"),
        adult_count=search_data.adult_number,
        child_count=search_data.child_number,
        currency_code=search_data.currency_code,
        ret_date=DateUtil.string_to_target_format(search_data.ret_date, "%Y-%m-%d") if search_data.ret_date else None,
        promo_code=promo_code,
        cabin_class=search_data.cabin_level or BookCabinConfig.DEFAULT_CABIN_CLASS,
    )

    if service_cache is None:
        CACHE.set_data(service, 300)
    else:
        CACHE.set_data(service_cache["value"], None, service_cache["timeOut"])
    return journey_list


if __name__ == "__main__":
    main({
        "taskId": "bcm-search-demo",
        "taskType": TaskTypeEnum.SEARCH.value,
        "source": "BCMweb",
        "taskData": {
            "depAirport": "KUL",
            "arrAirport": "CGO",
            "depDate": "2026-07-31",
            "retDate": "",
            "adultNumber": 1,
            "childNumber": 0,
            "currencyCode": "IDR",
            "freightRateType": "PT",
            "privateCode": [],
            "callbackData": {
                "callData": "",
                "callUrl": "",
            },
        },
    })
