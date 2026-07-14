from common.decorators.task_decorator import task_decorator
from common.enums.task_type_enum import TaskTypeEnum
from common.global_variable import GlobalVariable
from common.model.task.request_search_task_data_model import RequestSearchTaskDataModel
from common.utils import celery_util, log_util, machine_cache_util
from common.utils.proxy_ext_util import proxy_info_from_ext
from flights.vietjet.service.web_service import WebService

CELERY_APP = celery_util.create(GlobalVariable.RABBITMQ_USERNAME, GlobalVariable.RABBITMQ_PASSWORD)
CACHE = machine_cache_util.MachineCache()

LOG = log_util.LogUtil('vietjetSearch')


def _search(self, search_data: RequestSearchTaskDataModel):
    script_cache = CACHE.get_data()
    if script_cache is None:
        service = WebService(proxy_info_from_ext(search_data.ext))
        service.get_seesion(departure_place=search_data.dep_airport,arrival=search_data.arr_airport)
    else:
        service = script_cache['value']

    journey_info_model = service.search(
            dep_airport=search_data.dep_airport,
            arr_airport=search_data.arr_airport,
            dep_date=search_data.dep_date,
            adt_number=search_data.adult_number,
            chd_number=search_data.child_number,
            infant_count=0,
            currency_code=search_data.currency_code,
            ret_date=search_data.ret_date, is_hold=True
        )
    if script_cache is None:
        CACHE.set_data(service, 280)
    else:
        CACHE.set_data(script_cache['value'], None, script_cache['timeOut'])
    return journey_info_model


@CELERY_APP.task(bind=True)
@task_decorator(LOG)
def main(self, search_data: RequestSearchTaskDataModel):
    return _search(self, search_data)


@CELERY_APP.task(bind=True, name="task.VZweb.search.main")
@task_decorator(LOG)
def vz_main(self, search_data: RequestSearchTaskDataModel):
    return _search(self, search_data)


if __name__ == '__main__':
    for  i in  range(10000000000):
        print( i)
        main({
    "taskId": "VJWEB-HKG-SGN-VJ877-20260708-87028-SEARCH-RUN13653-39385f77",
    "source": "VJWEB",
    "taskType": "search",
    "taskData": {
        "callbackData": {
            "callData": "",
            "callUrl": ""
        },
        "freightRateType": "PT",
        "depAirport": "HKG",
        "arrAirport": "SGN",
        "depDate": "2026-07-08",
        "retDate": "",
        "adultNumber": 1,
        "childNumber": 0,
        "currencyCode": "VND",
        "flightNumber": "VJ877",
        "cabin": "A",
        "cabinLevel": "Y",
        "privateCode": [],
        "ext": {
            "proxy": {
                "source": "VJWEB",
                "host": "proxy.iproyal.net",
                "port": 9000,
                "username": "rakdvjweb01",
                "password": "rakdvjvj01",
                "region": "sg",
                "sessId": None,
                "sessionTime": 10,
                "format": "http://client-{username}_area-{region}_session-{sessId}_life-{sessionTime}:{password}@{host}:{port}"
            }
        }
    }
})
