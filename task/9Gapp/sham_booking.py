from decimal import Decimal

from common.decorators.task_decorator import task_decorator
from common.enums.order_state_enum import OrderStateEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.global_variable import GlobalVariable
from common.model.task.request_sham_booking_task_data_model import RequestShamBookingTaskDataModel
from common.model.task.response_order_info_model import ResponseOrderInfoModel
from common.utils import celery_util, log_util
from common.utils.flight_util import FlightUtil
from common.utils.proxy_ext_util import proxy_info_from_ext
from common.utils.sham_booking_util import ShamBookingUtil
from flights.sunphuquocairways_9g.flight_common.booking_utils import app_date
from flights.sunphuquocairways_9g.service.app_service import AppService

CELERY_APP = celery_util.create(GlobalVariable.RABBITMQ_USERNAME, GlobalVariable.RABBITMQ_PASSWORD)
LOG = log_util.LogUtil("sunPhuQuocAirwaysAppShamBooking")


@CELERY_APP.task(bind=True)
@task_decorator(LOG)
def main(
    self,
    sham_booking_data: RequestShamBookingTaskDataModel,
    response_order_data: ResponseOrderInfoModel,
):
    service = AppService(proxy_info_from_ext(sham_booking_data.ext))
    service.initialize_session()
    ext = sham_booking_data.ext or {}
    try:
        passenger_count = int(ext.get("passengerCount", 1))
    except (TypeError, ValueError):
        raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "passengerCount")
    if passenger_count <= 0:
        raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "passengerCount")

    journeys = service.search(
        dep_airport=sham_booking_data.dep_airport,
        arr_airport=sham_booking_data.arr_airport,
        dep_date=app_date(sham_booking_data.dep_date),
        ret_date=None,
        adt_number=passenger_count,
        chd_number=0,
        currency_code=sham_booking_data.booking_config.currency_code,
        promo_code="",
    )
    matches = FlightUtil.number_filter(journeys, sham_booking_data.flight_number)
    if len(matches) != 1:
        raise ServiceError(ServiceStateEnum.NO_AVAILABLE_FLIGHT_NUMBER, sham_booking_data.flight_number)
    journey = matches[0]
    if not journey.bundles:
        raise ServiceError(ServiceStateEnum.NO_AVAILABLE_BUNDLE)
    bundles = journey.bundles
    if sham_booking_data.cabin:
        bundles = [bundle for bundle in bundles if bundle.cabin == sham_booking_data.cabin]
        if not bundles:
            current_cabins = "|".join(bundle.cabin or "" for bundle in journey.bundles)
            raise ServiceError(
                ServiceStateEnum.NO_AVAILABLE_CABIN,
                sham_booking_data.cabin,
                current_cabins,
            )
    if not bundles:
        raise ServiceError(ServiceStateEnum.NO_AVAILABLE_BUNDLE)
    use_bundle = bundles[0]
    if use_bundle.seat <= 0:
        raise ServiceError(
            ServiceStateEnum.NO_AVAILABLE_CABIN,
            sham_booking_data.cabin or "",
            use_bundle.cabin or "",
        )
    if use_bundle.seat < passenger_count:
        raise ServiceError(
            ServiceStateEnum.BUSINESS_ERROR,
            f"余座不足，当前余座[{use_bundle.seat}]，目标人数[{passenger_count}]",
        )

    passengers = ShamBookingUtil.build_sham_passenger_info(passenger_count, True)
    contact_info = ShamBookingUtil.build_sham_contact_info()
    contact_info.last_name = passengers[0].last_name
    contact_info.first_name = passengers[0].first_name

    booking_id, pnr = service.create_and_hold(
        bundle=use_bundle,
        passengers=passengers,
        contact_info=contact_info,
        currency_code=sham_booking_data.booking_config.currency_code,
    )

    journey.bundles = [use_bundle]
    response_order_data.order_number = booking_id
    response_order_data.pnr = pnr
    response_order_data.order_state = OrderStateEnum.HOLD
    response_order_data.journeys = [journey]
    response_order_data.passengers = passengers
    response_order_data.contact_info = contact_info
    response_order_data.currency_code = use_bundle.price_info.currency
    response_order_data.total_amount = Decimal(passenger_count) * (
        use_bundle.price_info.adult_ticket_price + use_bundle.price_info.adult_tax_price
    )
    return response_order_data


if __name__ == "__main__":
    # 运行前请先实时搜索，并更新日期、航班号、舱位和产品。
    print(main({
        "taskId": "9gapp-local-sham-booking",
        "taskType": "shamBooking",
        "source": "9GAPP",
        "taskData": {
            "depAirport": "PQC",
            "arrAirport": "SGN",
            "depDate": "20260720",
            "flightNumber": "9G1984",
            "cabin": "Y",
            "bookingConfig": {
                "bookRate": 10,
                "currencyCode": "VND",
            },
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
                    },
            },
        },
    }))
