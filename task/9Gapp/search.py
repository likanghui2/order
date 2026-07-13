from datetime import datetime
from typing import Optional

from common.decorators.task_decorator import task_decorator
from common.global_variable import GlobalVariable
from common.model.task.request_search_task_data_model import RequestSearchTaskDataModel
from common.utils import celery_util, log_util, machine_cache_util
from common.utils.proxy_ext_util import proxy_info_from_ext
from flights.sunphuquocairways_9g.service.app_service import AppService

CELERY_APP = celery_util.create(GlobalVariable.RABBITMQ_USERNAME, GlobalVariable.RABBITMQ_PASSWORD)
CACHE = machine_cache_util.MachineCache()
LOG = log_util.LogUtil("sunPhuQuocAirwaysAppSearch")


def _app_date(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    normalized = str(value).strip()
    if len(normalized) == 8 and normalized.isdigit():
        parsed = datetime.strptime(normalized, "%Y%m%d")
    elif len(normalized) >= 10 and normalized[4] == "-":
        parsed = datetime.strptime(normalized[:10], "%Y-%m-%d")
    else:
        return normalized
    return parsed.strftime("%Y-%m-%dT00:00:00.000")


def _run_search(service: AppService, search_data: RequestSearchTaskDataModel):
    return service.search(
        dep_airport=search_data.dep_airport,
        arr_airport=search_data.arr_airport,
        dep_date=_app_date(search_data.dep_date),
        ret_date=_app_date(search_data.ret_date),
        adt_number=search_data.adult_number,
        chd_number=search_data.child_number,
        currency_code=search_data.currency_code,
        promo_code=search_data.private_code[0] if search_data.private_code else "",
    )


@CELERY_APP.task(bind=True)
@task_decorator(LOG)
def main(self, search_data: RequestSearchTaskDataModel):
    script_cache = CACHE.get_data()
    if script_cache is None:
        service = AppService(proxy_info_from_ext(search_data.ext))
        service.initialize_session()
    else:
        service = script_cache["value"]

    response = _run_search(service, search_data)

    if script_cache is None:
        CACHE.set_data(service, 280)
    else:
        CACHE.set_data(script_cache["value"], None, script_cache["timeOut"])
    return response


if __name__ == "__main__":
    print(main({
        "taskId": "9gapp-local-search",
        "taskType": "search",
        "source": "9GAPP",
        "taskData": {
            "depAirport": "SGN",
            "arrAirport": "PQC",
            "depDate": "20260720",
            "retDate": "",
            "adultNumber": 1,
            "childNumber": 0,
            "currencyCode": "VND",
            "freightRateType": "PT",
            "privateCode": [],
            "ext": {
                "proxy": {
                    "host": "proxy.example.com",
                    "port": 8080,
                    "username": "YOUR_USERNAME",
                    "password": "YOUR_PASSWORD",
                    "region": "vn",
                    "sessId": None,
                    "sessionTime": 10,
                    "format": "http://{username}:{password}@{host}:{port}",
                },
            },
        },
    }))
