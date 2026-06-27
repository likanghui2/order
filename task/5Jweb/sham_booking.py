from decimal import Decimal
from typing import List, Optional

from common.decorators.task_decorator import task_decorator
from common.enums.order_state_enum import OrderStateEnum
from common.enums.task_type_enum import TaskTypeEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.global_variable import GlobalVariable
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.order.passenger_info_model import PassengerInfoModel
from common.model.task.request_sham_booking_task_data_model import RequestShamBookingTaskDataModel
from common.model.task.response_order_info_model import ResponseOrderInfoModel
from common.utils import celery_util, log_util
from common.utils.date_util import DateUtil
from common.utils.flight_util import FlightUtil
from common.utils.proxy_ext_util import proxy_info_from_ext
from common.utils.sham_booking_util import ShamBookingUtil
from flights.cebupacificair_5j.service.web_service import WebService

CELERY_APP = celery_util.create(GlobalVariable.RABBITMQ_USERNAME, GlobalVariable.RABBITMQ_PASSWORD)

LOG = log_util.LogUtil('cebupacificairShamBooking')


def _select_bundle(journey: FlightJourneyModel,
                   cabin: Optional[str],
                   ext: Optional[dict]) -> FlightBundleModel:
    bundles = journey.bundles
    if cabin:
        bundles = [bundle for bundle in bundles if bundle.cabin == cabin]
        if not bundles:
            current_cabin = journey.bundles[0].cabin if journey.bundles else ''
            raise ServiceError(ServiceStateEnum.NO_AVAILABLE_CABIN, cabin, current_cabin)

    ext = ext or {}
    product_tag = ext.get('productTag')
    if product_tag:
        bundle = next((item for item in bundles if item.product_tag == product_tag), None)
        if bundle is None:
            raise ServiceError(ServiceStateEnum.NO_AVAILABLE_BUNDLE)
        return bundle

    bundle_code = ext.get('bundleCode')
    if bundle_code:
        bundle = next((item for item in bundles if item.code == bundle_code), None)
        if bundle is None:
            raise ServiceError(ServiceStateEnum.NO_AVAILABLE_BUNDLE)
        return bundle

    return next((item for item in bundles if item.product_tag == 'GO Basic'), bundles[0])


@CELERY_APP.task(bind=True)
@task_decorator(LOG)
def main(self,
         sham_booking_data: RequestShamBookingTaskDataModel,
         response_order_data: ResponseOrderInfoModel):
    LOG.info("初始化押位对象")
    service = WebService(proxy_info_from_ext(sham_booking_data.ext))
    service.initialize_html_session_booking()

    dep_date = DateUtil.string_to_target_format(sham_booking_data.dep_date, '%Y-%m-%d')
    journey_list = service.availability(
        airport_data=[(
            sham_booking_data.dep_airport,
            sham_booking_data.arr_airport,
            dep_date,
        )],
        adult_count=1,
        child_count=0,
        currency=sham_booking_data.booking_config.currency_code,
    )
    journey_list = FlightUtil.number_filter(journey_list, sham_booking_data.flight_number)
    if len(journey_list) != 1:
        raise ServiceError(ServiceStateEnum.NO_AVAILABLE_FLIGHT_NUMBER, sham_booking_data.flight_number)
    journey = journey_list[0]
    use_bundle = _select_bundle(journey, sham_booking_data.cabin, sham_booking_data.ext)
    print(use_bundle.seat, use_bundle.cabin)
    if use_bundle.seat == 0:
        raise ServiceError(ServiceStateEnum.NO_AVAILABLE_CABIN, sham_booking_data.cabin, use_bundle.cabin)
    seat_number = use_bundle.seat
    contact_info = ShamBookingUtil.build_sham_contact_info()
    passengers: List[PassengerInfoModel] = ShamBookingUtil.build_sham_passenger_info(seat_number, True)
    contact_info.last_name = passengers[0].last_name
    contact_info.first_name = passengers[0].first_name

    service.trip(
        dep_airport=sham_booking_data.dep_airport,
        journey=journey,
        bundle=use_bundle,
        adult_count=seat_number,
        child_count=0,
        passengers=passengers,
    )
    # source_data = service.add_passenger(
    #     passengers=passengers,
    #     contact_info=contact_info,
    #     purchasing=True,
    # )
    # service.commit(passengers=passengers, source_data=source_data)
    # payment_response = service.init_payment()
    # LOG.info(f"init_payment响应长度: {len(payment_response)}")

    journey.bundles = [use_bundle]
    response_order_data.order_number = '111111'
    response_order_data.pnr = '111111'
    response_order_data.order_state = OrderStateEnum.HOLD
    response_order_data.journeys = [journey]
    response_order_data.passengers = passengers
    response_order_data.contact_info = contact_info
    response_order_data.currency_code = use_bundle.price_info.currency
    response_order_data.total_amount = (
            use_bundle.price_info.adult_ticket_price + use_bundle.price_info.adult_tax_price
            or Decimal('0')
    )

    return response_order_data


if __name__ == '__main__':
    for i in range(1000):

        main({
            "taskId": "e95ff47d4b5f43498b6f13caa5d7c3db",
            "taskType": "shamBooking",
            "source": "5JWEB",
            "taskData": {
                "depAirport": "CEB",
                "arrAirport": "HKG",
                "depDate": "20260529",
                "flightNumber": "5J236",
                "cabin": "",
                "bookingConfig": {
                    "bookRate": 10,
                    "currencyCode": "PHP"
                },
                "callbackData": {
                    "callData": "",
                    "callUrl": "http://trip-api.bjrakd.com/triplex-foreign-external/external/task/pressureback/seatNewCallback"
                }
            }
        })
