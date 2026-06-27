from datetime import datetime
from typing import Optional

from common.decorators.task_decorator import task_decorator
from common.enums.task_type_enum import TaskTypeEnum
from common.global_variable import GlobalVariable
from common.model.task.request_search_task_data_model import RequestSearchTaskDataModel
from common.utils import celery_util, log_util, machine_cache_util
from common.utils.proxy_ext_util import proxy_info_from_ext
from flights.vietjet.service.app_service import AppService

CELERY_APP = celery_util.create(GlobalVariable.RABBITMQ_USERNAME, GlobalVariable.RABBITMQ_PASSWORD)
CACHE = machine_cache_util.MachineCache()
LOG = log_util.LogUtil("vietjetAppSearch")


def _app_date(date_value: Optional[str]) -> Optional[str]:
    if not date_value:
        return None
    if len(date_value) == 8 and date_value.isdigit():
        return datetime.strptime(date_value, "%Y%m%d").strftime("%m-%d-%Y")
    if len(date_value) >= 10 and date_value[4] == "-":
        return datetime.strptime(date_value[:10], "%Y-%m-%d").strftime("%m-%d-%Y")
    return date_value


@CELERY_APP.task(bind=True)
@task_decorator(LOG)
def main(self, search_data: RequestSearchTaskDataModel):
    script_cache = CACHE.get_data()
    if script_cache is None:
        service = AppService(proxy_info_from_ext(search_data.ext))
    else:
        service = script_cache["value"]

    response = service.search(
        dep_airport=search_data.dep_airport,
        arr_airport=search_data.arr_airport,
        dep_date=_app_date(search_data.dep_date),
        ret_date=_app_date(search_data.ret_date),
        adult_count=search_data.adult_number,
        child_count=search_data.child_number,
        currency=search_data.currency_code,
        promo_code=search_data.private_code[0] if search_data.private_code else "",
    )

    if script_cache is None:
        CACHE.set_data(service, 280)
    else:
        CACHE.set_data(script_cache["value"], None, script_cache["timeOut"])
    return response


if __name__ == "__main__":
    for i in range(10000000000):
        print(i)
        main({
            "taskId": "123",
            "taskType": TaskTypeEnum.SEARCH.value,
            "source": "VJAPP",
            "taskData": {
                "callbackData": {
                    "callData": "60|C"
                },
                "freightRateType": "PT",
                "depAirport": "SGN",
                "arrAirport": "CAN",
                "depDate": "2026-07-29",
                "retDate": "",
                "adultNumber": 1,
                "childNumber": 0,
                "currencyCode": "USD",
                "privateCode": []
            }
        })
