

from enum import Enum

class PassengerTypeEnum(Enum):
    ADT = "ADT"
    CHD = "CHD"
    INF = "INF"

    @staticmethod
    def get_value(name):
        try:
            return PassengerTypeEnum[name].value
        except KeyError:
            return None

    @staticmethod
    def get_object(name):
        try:
            return PassengerTypeEnum[name]
        except KeyError:
            return None