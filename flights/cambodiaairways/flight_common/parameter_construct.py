import base64
import os
import random
import time
from typing import Dict, Optional, Union

from flights.cambodiaairways.config import Config


class ParameterConstruct:
    @classmethod
    def build_search_data(cls,
                          dep_airport: str,
                          arr_airport: str,
                          dep_date: str,
                          adt_number: int,
                          chd_number: int,
                          ret_date: Optional[str] = None,
                          cabin_grade: str = Config.DEFAULT_CABIN_GRADE) -> Dict[str, Union[str, dict]]:
        group_id = cls.generate_group_id()
        plain_data = {
            'from': dep_airport,
            'to': arr_airport,
            'leaveDate': dep_date,
            'returnDate': ret_date or '',
            'kind': '1' if ret_date else '0',
            'groupId': group_id,
            'cabinGrade': cabin_grade,
            'adultNum': str(adt_number),
            'childNum': str(chd_number),
            'infantNum': str(Config.DEFAULT_INFANT_NUMBER),
        }
        encrypted_data = cls.encrypt_search_data(plain_data)
        encrypted_data['_plain'] = plain_data
        return encrypted_data

    @classmethod
    def encrypt_search_data(cls, plain_data: Dict[str, str]) -> Dict[str, str]:
        encrypted_data = {}
        for key, value in plain_data.items():
            if key == 'returnDate' and not value:
                encrypted_data[key] = ''
                continue
            encrypted_data[key] = cls.rsa_encrypt(value)
        return encrypted_data

    @staticmethod
    def generate_group_id() -> str:
        value = str(int(time.time() * 1000))[6:12]
        first_random = random.randint(0, 9)
        second_random = random.randint(0, 9)
        prefix_random = random.randint(0, 9)
        suffix = abs(first_random - second_random) if prefix_random <= 6 else first_random + second_random

        value = f'{prefix_random}{value}'
        value = f'{value[:3]}{first_random}{value[3:]}'
        value = f'{value[:4]}{second_random}{value[4:]}'
        return f'{value}{suffix}'

    @staticmethod
    def rsa_encrypt(value: str) -> str:
        modulus = int(Config.RSA_MODULUS_HEX, 16)
        exponent = Config.RSA_EXPONENT
        key_size = (modulus.bit_length() + 7) // 8
        data = value.encode('utf-8')
        if len(data) > key_size - 11:
            raise ValueError('RSA plaintext is too long')

        padding_length = key_size - len(data) - 3
        padding = bytearray()
        while len(padding) < padding_length:
            random_byte = os.urandom(1)
            if random_byte != b'\x00':
                padding.extend(random_byte)

        block = b'\x00\x02' + bytes(padding) + b'\x00' + data
        encrypted_value = pow(int.from_bytes(block, 'big'), exponent, modulus).to_bytes(key_size, 'big')
        return base64.b64encode(encrypted_value).decode()
