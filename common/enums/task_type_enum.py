from enum import Enum


class TaskTypeEnum(Enum):
    SEARCH = "search"
    VERIFY = "verify"
    BOOKING = "booking"
    ORDER_DETAIL = "orderDetail"
    SHAM_BOOKING = "shamBooking"
    CANCEL = "cancelOrder"
