from common.decorators.task_decorator import task_decorator
from common.global_variable import GlobalVariable
from common.model.task.request_search_task_data_model import RequestSearchTaskDataModel
from common.utils import celery_util, log_util, machine_cache_util
from common.utils.proxy_ext_util import proxy_info_from_ext
from flights.garuda.service.app_service import AppService

CELERY_APP = celery_util.create(GlobalVariable.RABBITMQ_USERNAME, GlobalVariable.RABBITMQ_PASSWORD)
LOG = log_util.LogUtil("garudaAppSearch")
CACHE = machine_cache_util.MachineCache()


@CELERY_APP.task(bind=True)
@task_decorator(LOG)
def main(self, search_data: RequestSearchTaskDataModel):
    script_cache = CACHE.get_data()
    if script_cache is None:
        service = AppService(proxy_info_from_ext(search_data.ext))
        service.initialize_session()
    else:
        service = script_cache["value"]

    response = service.search(
        dep_airport=search_data.dep_airport,
        arr_airport=search_data.arr_airport,
        dep_date=search_data.dep_date,
        ret_date=search_data.ret_date,
        adt_number=search_data.adult_number,
        chd_number=search_data.child_number,
        currency_code=search_data.currency_code,
    )

    if script_cache is None:
        CACHE.set_data(service, 280)
    else:
        CACHE.set_data(script_cache["value"], None, script_cache["timeOut"])
    return response


if __name__ == "__main__":
    for i in range(10):
        print(i)
        main(
        {
            "taskId": "123",
            "taskType": "search",
            "source": "GAAPP",
            "taskData": {
                "depAirport": "PVG",
                "arrAirport": "CGK",
                "depDate": "2026-06-17",
                "retDate": "",
                "adultNumber": 1,
                "childNumber": 0,
                "currencyCode": "IDR",
                "flightNumber": None,
                "callbackData": {"callData": "", "callUrl": ""},
                "configData": None,
                "freightRateType": "PT",
            },
        }
    )
