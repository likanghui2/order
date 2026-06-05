from common.decorators.task_decorator import task_decorator
from common.enums.task_type_enum import TaskTypeEnum
from common.global_variable import GlobalVariable
from common.model.task.request_search_task_data_model import RequestSearchTaskDataModel
from common.utils import celery_util, log_util, machine_cache_util
from common.utils.date_util import DateUtil
from flights.thaiairways_tg.service.web_service import WebService

CELERY_APP = celery_util.create(GlobalVariable.RABBITMQ_USERNAME, GlobalVariable.RABBITMQ_PASSWORD)
CACHE = machine_cache_util.MachineCache()
LOG = log_util.LogUtil('TGSearch')


@CELERY_APP.task(bind=True)
@task_decorator(LOG)
def main(self, search_data: RequestSearchTaskDataModel):
    script_cache = CACHE.get_data()
    if script_cache is None:
        service = WebService(GlobalVariable.PROXY_INFO_DATA)
        service.initialize_session()
    else:
        service = script_cache['value']

    promo_code = search_data.private_code[0] if search_data.private_code else ''
    response = service.search(
        dep_airport=search_data.dep_airport,
        arr_airport=search_data.arr_airport,
        dep_date=DateUtil.string_to_target_format(search_data.dep_date, '%Y-%m-%d'),
        adt_number=search_data.adult_number,
        chd_number=search_data.child_number,
        currency_code=search_data.currency_code,
        cabin_level=search_data.cabin_level or 'Y',
        promo_code=promo_code,
        ret_date=(
            DateUtil.string_to_target_format(search_data.ret_date, '%Y-%m-%d')
            if search_data.ret_date
            else None
        ),
    )

    if script_cache is None:
        CACHE.set_data(service, 280)
    else:
        CACHE.set_data(script_cache['value'], None, script_cache['timeOut'])
    return response


if __name__ == '__main__':
    t = main({
        "taskId": "test_tg_search_001",
        "taskType": TaskTypeEnum.SEARCH.value,
        "source": "TGWEB",
        "taskData": {
            "depAirport": "BKK",
            "arrAirport": "PEK",
            "depDate": "20260529",
            "retDate": "",
            "adultNumber": 1,
            "childNumber": 1,
            "currencyCode": "THB",
            "freightRateType": "PT",
            "cabinLevel": "Y",
            "privateCode": [],
            "callbackData": {
                "callData": "",
                "callUrl": ""
            }
        }
    })
    print(t)
