from enum import Enum
from typing import Optional


class VjAppPaymentMethodEnum(Enum):
    # 已实测：VND，本地 QR；reserveV2 直接返回 reservation/orderNumber/pnr。
    VNPAY_QR = ("VJVNQR", "qr_code", "VND", "VND QR，已实测，返回订单号和 PNR")

    # 已实测：VND，本地 ATM/网银；reserveV2 直接返回 reservation/orderNumber/pnr。
    VNPAY_ATM = ("VJVNPAY", "domestic_debit_card", "VND", "VND ATM/网银，已实测，返回订单号和 PNR")

    # 已实测：VND，MoMo 钱包；走 GPAY，返回 transactionID 和 checkout endpoint。
    MOMO = ("VJPMOMO", "international_debit_card", "VND", "VND MoMo 钱包，已实测，返回 GPAY checkout")

    # 已实测：CNY，Apple Pay；走 GPAY，返回 transactionID 和 checkout endpoint。
    APPLE_PAY = ("VJPAPLE", "international_debit_card", "CNY", "CNY Apple Pay，已实测，返回 GPAY checkout")

    # 已实测：CNY/多币种，Visa；走 GPAY，返回 transactionID 和 checkout endpoint。
    VISA = ("VJPVI", "international_debit_card", "CNY", "Visa 国际卡，已实测，返回 GPAY checkout")

    # 已实测：CNY/多币种，JCB；走 GPAY，返回 transactionID 和 checkout endpoint。
    JCB = ("VJPJCB", "international_debit_card", "CNY", "JCB 国际卡，可用于 CNY，返回 GPAY checkout")

    # 可用：CNY/多币种，MasterCard；走 GPAY，返回 transactionID 和 checkout endpoint。
    MASTER_CARD = ("VJPMC", "international_debit_card", "CNY", "MasterCard 国际卡，可用于 CNY，返回 GPAY checkout")

    # 可用：USD/VND，Amex；当前 SGN-CAN CNY 不支持。
    AMEX = ("VJPAMEX", "international_debit_card", "USD", "Amex 国际卡，paymentMethod 当前仅 USD/VND")

    # 可用：VND，VietQR；QR 支付，未继续刷单。
    VIETQR = ("VJPVEQR", "qr_code", "VND", "VietQR，当前仅 VND，未继续刷单")

    # 可用：VND，NAPAS/ATM；国内借记卡，未继续刷单。
    NAPAS_ATM = ("VJPNAPA", "domestic_debit_card", "VND", "NAPAS/ATM，当前仅 VND，未继续刷单")

    # 可用：VND，SkyPay 钱包；需要 SkyPay/SkyJoy 登录态或 token 时再测。
    SKY_PAY = ("VJPSKY", "skyclub", "VND", "SkyPay/Skyclub，当前仅 VND，可能依赖登录 token")

    # 可用：VND，HDSS 先飞后付；后付链路，未继续刷单。
    HDSS_PAY_LATER = ("PLHDSS", "pay_later", "VND", "HDSS 后付，当前仅 VND，未继续刷单")

    # 可用：VND，HDSS 立即支付；HDSS 支付链路，未继续刷单。
    HDSS_PAY_NOW = ("VJHDSS", "international_debit_card", "VND", "HDSS 立即支付，当前仅 VND，未继续刷单")

    # 可用：AUD，Pay by Bank/Azupay；澳洲本地支付。
    AZUPAY = ("VJPAZID", "international_debit_card", "AUD", "Azupay/Pay by Bank，当前仅 AUD")

    # 可用：IDR，DOKU；印尼本地支付。
    DOKU = ("VJPDOKU", "international_debit_card", "IDR", "DOKU 印尼支付，当前仅 IDR")

    # 可用：KRW，Smartro；韩国本地支付。
    SMARTRO = ("VJPSMAR", "international_debit_card", "KRW", "Smartro 韩国支付，当前仅 KRW")

    # 可用：多币种，礼品券/优惠券；通常需要券码，不适合作为默认占位。
    VOUCHER = ("VO", "international_debit_card", "CNY", "礼品券/优惠券，多币种返回，通常需要券码")

    # 历史可用：Alipay；当前 SGN-CAN paymentMethod 未返回，暂不能实测。
    ALIPAY = ("VJPALI", "international_debit_card", "CNY", "Alipay，历史出现过，当前 paymentMethod 未返回")

    # 兼容旧 App 常量：Alipay 别名。
    ALIPAY_ALT = ("VJALIPA", "international_debit_card", "CNY", "Alipay 旧别名，当前 paymentMethod 未返回")

    # 兼容旧 App 常量：通用 pay later。
    PAY_LATER = ("PL6", "pay_later", "VND", "旧版/通用 Pay Later，当前接口不一定返回")

    # 兼容旧 App 常量：15/30 天后付。
    PAY_LATER_15 = ("PL15", "pay_later", "VND", "旧版 15 天后付，当前接口不一定返回")
    PAY_LATER_30 = ("PL30", "pay_later", "VND", "旧版 30 天后付，当前接口不一定返回")

    # 兼容旧 App 常量：VJ International Card。
    VJINT = ("VJINT", "vjint", "VND", "VJ International Card，旧版第三方网页支付")

    def __init__(self, identifier: str, type_payment: str, default_currency: str, note: str):
        self.identifier = identifier
        self.type_payment = type_payment
        self.default_currency = default_currency
        self.note = note

    @classmethod
    def from_identifier(cls, identifier: Optional[str]):
        if not identifier:
            return None
        upper_identifier = identifier.upper()
        for payment_method in cls:
            if payment_method.identifier.upper() == upper_identifier:
                return payment_method
        return None

    @classmethod
    def from_name_or_identifier(cls,
                                value: Optional[str],
                                default: Optional["VjAppPaymentMethodEnum"] = None):
        if not value:
            return default
        upper_value = value.upper()
        for payment_method in cls:
            if payment_method.name == upper_value or payment_method.identifier.upper() == upper_value:
                return payment_method
        return default
