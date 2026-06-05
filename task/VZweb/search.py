from common.decorators.task_decorator import task_decorator
from common.enums.task_type_enum import TaskTypeEnum
from common.global_variable import GlobalVariable
from common.model.task.request_search_task_data_model import RequestSearchTaskDataModel
from common.utils import celery_util, log_util, machine_cache_util
from flights.vietjet.service.vz_web_service import VZWebService

CELERY_APP = celery_util.create(GlobalVariable.RABBITMQ_USERNAME, GlobalVariable.RABBITMQ_PASSWORD)
CACHE = machine_cache_util.MachineCache()
LOG = log_util.LogUtil("vzWebSearch")


def _search(self, search_data: RequestSearchTaskDataModel):
    script_cache = CACHE.get_data()
    if script_cache is None:
        service = VZWebService(GlobalVariable.PROXY_INFO_DATA)
    else:
        service = script_cache["value"]

    journey_info_model = service.search(
        dep_airport=search_data.dep_airport,
        arr_airport=search_data.arr_airport,
        dep_date=search_data.dep_date,
        adt_number=search_data.adult_number,
        chd_number=search_data.child_number,
        infant_count=0,
        currency_code=search_data.currency_code,
        ret_date=search_data.ret_date,
    )

    if script_cache is None:
        CACHE.set_data(service, 280)
    else:
        CACHE.set_data(script_cache["value"], None, script_cache["timeOut"])
    return journey_info_model


@CELERY_APP.task(bind=True)
@task_decorator(LOG)
def main(self, search_data: RequestSearchTaskDataModel):
    return _search(self, search_data)


if __name__ == "__main__":
    main({
        "taskId": "123",
        "taskType": TaskTypeEnum.SEARCH.value,
        "source": "VZweb",
        "taskData": {
            "callbackData": {
                "callData": "60|C"
            },
            "freightRateType": "PT",
            "depAirport": "CAN",
            "arrAirport": "SGN",
            "depDate": "2026-06-01",
            "retDate": "",
            "adultNumber": 1,
            "childNumber": 0,
            "currencyCode": "THB"
        }
    })
