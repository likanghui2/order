from common.enums.gender_enum import GenderEnum
from common.enums.order_state_enum import OrderStateEnum
from common.enums.passenger_type_enum import PassengerTypeEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.order.contact_info_model import ContactInfoModel
from common.model.order.passenger_info_model import PassengerInfoModel
from common.model.order.payment_info_model import PaymentInfoModel
from flights.sunphuquocairways_9g.service.web_service import WebService
from tests.flight_9gweb.test_web_order_parser import itinerary


PASSENGERS = [
    PassengerInfoModel(
        type=PassengerTypeEnum.ADT,
        lastName="LOVELACE",
        firstName="ADA",
        gender=GenderEnum.F,
        birthday="1990-01-01",
        ext={"travelerId": "traveler-1"},
    )
]
CONTACT = ContactInfoModel(
    lastName="LOVELACE",
    firstName="ADA",
    emailAddress="ada@example.com",
    phoneCode="+84",
    phoneNumber="901234567",
)
CARD = PaymentInfoModel(
    type="CARD",
    cardNumber="4111111111111111",
    cardExpiryDate="08/29",
    cardHolderName="ADA LOVELACE",
    cardType="VI",
    cardCVV="123",
)


class FakeCardinal:
    def __init__(self):
        self.calls = []

    def cardinaltrusted_init_jwt(self, jwt, user_agent):
        self.calls.append(("jwt", jwt, user_agent))
        return {"status": "ok"}

    def render_post(self, url, data):
        self.calls.append(("render", url, data))
        return {
            "nonce": "nonce-1",
            "referenceId": "ref-1",
            "orgUnitId": "org-1",
            "features": {"merchantMethodUrlCollection": {"methodUrls": []}},
        }

    def cardinalcommerce_save_browser_data(self, **kwargs):
        self.calls.append(("save", kwargs))


class PaymentScript:
    def __init__(self, fail_add=False, ticket_ready=True):
        self.fail_add = fail_add
        self.ticket_ready = ticket_ready
        self.payment_action_names = []
        self.add_payment_calls = 0
        self.payment_record_calls = 0
        self.itinerary_calls = 0

    def payment_methods(self, pnr, last_name):
        return {
            "data": {
                "remainingAmount": {"value": 1250000, "currencyCode": "VND"},
                "availablePaymentMethods": [
                    {"id": "pp-1", "paymentType": "CheckoutFormPayment"}
                ],
            }
        }

    def payment_action(self, payload):
        action = payload["action"]
        self.payment_action_names.append(action)
        if action == "load":
            return {"loaded": True}
        if action == "tdsinit":
            assert payload["data"]["mopdata"]["vendor"] == "visa"
            return {"jwt": "jwt-1"}
        if action == "add":
            self.add_payment_calls += 1
            if self.fail_add:
                raise ServiceError(ServiceStateEnum.PAYMENT_FAILED)
            assert payload["data"]["mopdata"]["tdsSessionId"] == "ref-1"
            return {"actionToken": "action-token-1"}
        raise AssertionError(action)

    def payment_records(self, pnr, last_name, payload):
        self.payment_record_calls += 1
        assert payload["paymentRequests"][0]["paymentMethod"]["actionToken"] == "action-token-1"
        return {"data": {"status": "AUTHORIZED"}}

    def get_itinerary(self, pnr, last_name):
        self.itinerary_calls += 1
        return itinerary() if self.ticket_ready else itinerary(ticket_status=None)


def payment_service(script):
    cardinal = FakeCardinal()
    service = WebService(None, script=script, cardinal_factory=lambda *args, **kwargs: cardinal)
    return service, cardinal


def test_pay_order_submits_payment_once_and_returns_ticket_numbers():
    script = PaymentScript()
    service, cardinal = payment_service(script)

    result = service.pay_order("ABC123", PASSENGERS, CONTACT, CARD)

    assert script.payment_action_names == ["load", "tdsinit", "add"]
    assert script.add_payment_calls == 1
    assert script.payment_record_calls == 1
    assert script.itinerary_calls == 1
    assert [call[0] for call in cardinal.calls] == ["jwt", "render", "save"]
    assert result.order_state == OrderStateEnum.OPEN_FOR_USE
    assert result.passengers[0].ticket_number == "1234567890123"


def test_payment_failure_is_not_retried():
    script = PaymentScript(fail_add=True)
    service, _ = payment_service(script)

    try:
        service.pay_order("ABC123", PASSENGERS, CONTACT, CARD)
    except BaseException:
        pass

    assert script.add_payment_calls == 1
    assert script.payment_record_calls == 0


def test_rejects_unsupported_card_before_any_payment_action():
    script = PaymentScript()
    service, _ = payment_service(script)
    unsupported = CARD.model_copy(update={"card_type": "AX"})

    try:
        service.pay_order("ABC123", PASSENGERS, CONTACT, unsupported)
    except ServiceError:
        pass
    else:
        raise AssertionError("unsupported card should fail")

    assert script.payment_action_names == []


def test_ticket_polling_stops_after_five_attempts(monkeypatch):
    script = PaymentScript(ticket_ready=False)
    service, _ = payment_service(script)
    monkeypatch.setattr("flights.sunphuquocairways_9g.service.web_service.time.sleep", lambda _: None)

    try:
        service.pay_order("ABC123", PASSENGERS, CONTACT, CARD)
    except ServiceError:
        pass
    else:
        raise AssertionError("unticketed order should hit the polling limit")

    assert script.itinerary_calls == 5
    assert script.add_payment_calls == 1
    assert script.payment_record_calls == 1
