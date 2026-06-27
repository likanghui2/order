import time

from common.decorators.task_decorator import task_decorator
from common.enums.task_type_enum import TaskTypeEnum
from common.global_variable import GlobalVariable
from common.model.task.request_search_task_data_model import RequestSearchTaskDataModel
from common.utils import celery_util, log_util, machine_cache_util
from common.utils.proxy_ext_util import proxy_info_from_ext
from flights.cebupacificair_5j.service.web_service import WebService

CELERY_APP = celery_util.create(GlobalVariable.RABBITMQ_USERNAME, GlobalVariable.RABBITMQ_PASSWORD)
CACHE = machine_cache_util.MachineCache()

LOG = log_util.LogUtil('cebupacificairSearch')


@CELERY_APP.task(bind=True)
@task_decorator(LOG)
def main(self, search_data: RequestSearchTaskDataModel):
    script_cache = CACHE.get_data()
    if script_cache is None:
        LOG.info("重新初始化对象")
        service = WebService(proxy_info_from_ext(search_data.ext))
        service.initialize_session()
        service.initialize_html_session()
    else:
        LOG.info("使用缓存对象")
        service = script_cache['value']

    airport_data = [
        (
            search_data.dep_airport if index == 0 else search_data.arr_airport,
            search_data.arr_airport if index == 0 else search_data.dep_airport,
            search_data.dep_date if index == 0 else search_data.ret_date,
        )
        for index in range(2)
        if index == 0 or search_data.ret_date
    ]

    time.sleep(1)
    response = service.availability(
        airport_data=airport_data,
        currency=search_data.currency_code,
        adult_count=search_data.adult_number,
        child_count=search_data.child_number,
    )

    if script_cache is None:
        CACHE.set_data(service, 300)
    else:
        CACHE.set_data(script_cache['value'], None, script_cache['timeOut'])
    return response


if __name__ == '__main__':
    for i in range(10):
        main({
            "taskId": "123",
            "taskType": TaskTypeEnum.SEARCH.value,
            "source": "5Jweb",
            "taskData": {
                "callbackData": {
                    "callData": "60|C"
                },
                "freightRateType": "PT",
                "depAirport": "HKG",
                "arrAirport": "MNL",
                "depDate": "2026-06-01",
                "retDate": "",
                "adultNumber": 1,
                "childNumber": 0,
                "currencyCode": "HKD"
            }
        })
