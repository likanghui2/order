import base64
import copy
import json
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.order.contact_info_model import ContactInfoModel
from common.model.order.payment_info_model import PaymentInfoModel


class PacoPayment:
    SUCCESS_CODES = {"PC-B050000", "PC-B050001", "PC-B050002", "PC-B052354"}
    CARD_TYPE_MAP = {
        "VI": "CC-VI",
        "VISA": "CC-VI",
        "MC": "CC-CA",
        "CA": "CC-CA",
        "MASTER": "CC-CA",
        "MASTERCARD": "CC-CA",
        "JC": "CC-JC",
        "JCB": "CC-JC",
        "UP": "CC-UP",
        "CUP": "CC-UP",
        "UNIONPAY": "CC-UP",
        "AX": "CC-AX",
        "AMEX": "CC-AX",
        "DC": "CC-DC",
        "DINERS": "CC-DC",
        "DS": "CC-DS",
        "DISCOVER": "CC-DS",
    }

    @classmethod
    def build_card_request(cls,
                           payment_page_data: dict,
                           payment_info: PaymentInfoModel,
                           contact_info: ContactInfoModel,
                           payment_type: str,
                           language: str = "en") -> dict:
        source_payment_info = payment_page_data.get("paymentInfo") or {}
        if not source_payment_info.get("id"):
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "paymentInfo.id")

        request_data = copy.deepcopy(source_payment_info)
        request_data["paymentId"] = source_payment_info["id"]
        request_data["apiRequest"] = {
            "requestMessageID": str(uuid.uuid4()),
            "requestDateTime": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "language": language,
        }
        request_data["creditCardDetails"] = {
            "cardNumber": payment_info.card_number.replace(" ", ""),
            "cardExpiryMMYY": cls.card_expiry_mmyy(payment_info.card_expiry_date),
            "cvvCode": payment_info.card_cvv,
            "payerName": payment_info.card_holder_name,
            "cardHolderName": payment_info.card_holder_name,
        }
        if source_payment_info.get("originalTransactionAmount") is not None:
            request_data["originalTransactionAmount"] = source_payment_info["originalTransactionAmount"]
        else:
            request_data.pop("originalTransactionAmount", None)
        request_data["paymentType"] = payment_type
        request_data["generalPayerDetails"] = request_data.get("generalPayerDetails") or {}
        request_data["generalPayerDetails"]["email"] = contact_info.email_address
        request_data["generalPayerDetails"].pop("mobilePhone", None)
        request_data["generalPayerDetails"].pop("mobilePhoneCountryCode", None)

        for key in ("id", "companyId", "createdAt", "transactionDateTime", "validTill"):
            request_data.pop(key, None)
        return request_data

    @staticmethod
    def build_check_card_request(payment_id: str,
                                 card_number: str,
                                 currency_code: str,
                                 payment_type: str = "CC") -> dict:
        return {
            "paymentId": payment_id,
            "cardNumber": card_number.replace(" ", ""),
            "paymentType": payment_type,
            "currencyCode": currency_code,
        }

    @staticmethod
    def payment_id(redirection_url: str) -> str:
        parsed_url = urlparse(redirection_url or "")
        payment_id = (parse_qs(parsed_url.query).get("pid") or [""])[0]
        if not payment_id:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "pid")
        return payment_id

    @classmethod
    def card_payment_type(cls, card_type: Optional[str], card_scheme: Optional[str] = None) -> str:
        if card_scheme:
            return f"CC-{card_scheme}"
        payment_type = cls.CARD_TYPE_MAP.get((card_type or "").replace("_", "").replace("-", "").upper())
        if payment_type is None:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "cardType")
        return payment_type

    @staticmethod
    def card_expiry_mmyy(card_expiry_date: str) -> str:
        expiry = re.sub(r"\D", "", card_expiry_date or "")
        if len(expiry) == 4:
            return expiry
        if len(expiry) == 6:
            return expiry[:2] + expiry[-2:]
        raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "cardExpiryDate")

    @staticmethod
    def encrypt_payload(payload: Any, server_public_key: str) -> dict:
        try:
            from nacl import public, utils
        except ImportError as exc:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "PyNaCl") from exc

        server_public_key = (server_public_key or "").strip().strip('"')
        if not server_public_key:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "serverPublicKey")

        if not isinstance(payload, dict):
            payload = {"payload": payload}
        client_private_key = public.PrivateKey.generate()
        server_key = public.PublicKey(base64.b64decode(server_public_key))
        nonce = utils.random(public.Box.NONCE_SIZE)
        box = public.Box(client_private_key, server_key)
        plain_text = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        cipher_text = box.encrypt(plain_text, nonce).ciphertext
        return {
            "nonce": base64.b64encode(nonce).decode(),
            "cipherText": base64.b64encode(cipher_text).decode(),
            "clientPublicKey": base64.b64encode(bytes(client_private_key.public_key)).decode(),
            "serverPublicKey": server_public_key,
        }

    @staticmethod
    def amount(transaction_amount: dict) -> tuple[Decimal, str]:
        currency = transaction_amount.get("currencyCode")
        if not currency:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "transactionAmount.currencyCode")
        if transaction_amount.get("amount") is not None:
            return Decimal(str(transaction_amount["amount"])), currency
        amount_text = transaction_amount.get("amountText")
        decimal_places = int(transaction_amount.get("decimalPlaces") or 2)
        if not amount_text:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "transactionAmount.amount")
        return Decimal(str(int(amount_text))) / (Decimal(10) ** decimal_places), currency

    @classmethod
    def response_code(cls, data: dict) -> Optional[str]:
        for path in (
            ("apiResponse", "responseCode"),
            ("data", "apiResponse", "responseCode"),
            ("data", "paymentInfo", "apiResponse", "responseCode"),
            ("data", "paymentInfo", "priorPaymentResponseDetails", "responseCode"),
            ("data", "webPaymentResult", "paymentStatusInfo", "responseCode"),
            ("data", "paymentStatusInfo", "responseCode"),
        ):
            value = cls._get(data, path)
            if value:
                return str(value)
        return None

    @classmethod
    def response_description(cls, data: dict) -> Optional[str]:
        for path in (
            ("apiResponse", "responseDescription"),
            ("apiResponse", "acquirerResponseDescription"),
            ("data", "paymentInfo", "priorPaymentResponseDetails", "marketingDescription"),
        ):
            value = cls._get(data, path)
            if value:
                return str(value)
        return None

    @classmethod
    def payment_status(cls, data: dict) -> Optional[str]:
        return cls._get(data, ("data", "paymentInfo", "paymentStatusInfo", "paymentStatus"))

    @classmethod
    def is_success(cls, data: dict) -> bool:
        return cls.response_code(data) in cls.SUCCESS_CODES or cls.payment_status(data) in {"A", "S"}

    @staticmethod
    def _get(data: dict, path: tuple[str, ...]):
        value = data
        for key in path:
            if not isinstance(value, dict):
                return None
            value = value.get(key)
        return value
