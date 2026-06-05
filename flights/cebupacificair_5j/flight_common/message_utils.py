import base64
import hashlib
import hmac
from hashlib import md5
from typing import Optional, Tuple

from Crypto import Random
from Crypto.Cipher import AES

from common.utils.aes_ciphering import AesCiphering


class MessageUtils:
    def __init__(self, authorization: Optional[str], x_auth_token: Optional[str], park: Optional[str]):
        self.__authorization = authorization
        self.__x_auth_token = x_auth_token
        self.__park = park

    def get_aes_key_and_iv(self, key: Optional[str] = None) -> Tuple[bytes, bytes, bytes]:
        if key is None:
            if self.__authorization and self.__x_auth_token:
                token = f"{self.__authorization}{self.__x_auth_token}{self.__park}"
            else:
                token = self.__park
        else:
            token = key

        salt = Random.new().read(8)
        token_bytes = token.encode("utf-8") + salt
        token_key = md5(token_bytes).digest()
        result_key = token_key
        while len(result_key) < 48:
            token_key = md5(token_key + token_bytes).digest()
            result_key += token_key

        return result_key[:32], result_key[32:], salt

    def encrypt_message(self, message: str, input_key: Optional[str] = None) -> str:
        key, iv, salt = self.get_aes_key_and_iv(input_key)
        cipher_text = AesCiphering.encrypt(
            data=message.encode('utf-8'),
            key=key,
            iv=iv,
            mode=AES.MODE_CBC,
        )
        return base64.b64encode(b'Salted__' + salt + cipher_text).decode('utf-8')

    @staticmethod
    def hash_utils(key: str, message: str) -> str:
        hmac_hash = hmac.new(key.encode(), message.encode(), hashlib.sha256).digest()
        return base64.b64encode(hmac_hash).decode()
