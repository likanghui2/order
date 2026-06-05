import base64
import hashlib
import secrets

from Crypto.Cipher import AES

from common.utils.aes_ciphering import AesCiphering
from common.utils.rsa_ciphering import RsaCiphering
from common.utils.string_util import StringUtil


class Pay2c2pUtil:
    RSA_MODULUS = "BFD658ECC48FABEAA42B69316B1DF58DAD5E35BF1BA6045FB820B006DD6B0DE87101414DB0494BFF2324266648B2B358A539BF8E3AE4131FC397327A9083D1387A9C9E3D6DCBEC878E89E49B2080DE497E94A535A64FF16CEE6A1666437C469B82574BBCEE7DC0636B506ED712AB010A8B6B31CD62C5C2C7281A7E8DE72548A5"
    RSA_EXPONENT = "10001"

    @classmethod
    def encrypt_card_info(cls,card_number:str,year: str,month: str,cvv: str):

        # 生成加密使用的aes密钥
        aes_key = StringUtil.generate_custom_random_string("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*()-+=_",8)

        # RSA加密 AES密钥 PKCS#1 v1.5填充
        aes_encode_byte = RsaCiphering.rsa_encrypt_pkcs_v1_5(Pay2c2pUtil.RSA_MODULUS,Pay2c2pUtil.RSA_EXPONENT,aes_key)
        aes_key_encode_base64 = base64.b64encode(aes_encode_byte).decode('utf-8')

        # 生成随机IV
        temp_iv = secrets.token_bytes(8)
        key_hex,iv_hex = cls.generate_aes_key_and_iv_hex(aes_key.encode('utf-8'),temp_iv)

        # 明文拼接
        plaintext_data = f'{card_number};{month};{year};{cvv}'
        # 开始AES加密
        card_info_encode = AesCiphering.encrypt(plaintext_data.encode('utf-8'),bytes.fromhex(key_hex),bytes.fromhex(iv_hex),AES.MODE_CBC)

        # 固定特征 + 随机IV + AES结果 组成最终结果
        # Salted__ [83, 97, 108, 116, 101, 100, 95, 95]
        card_info_encode = 'Salted__'.encode('utf-8') + temp_iv + card_info_encode
        card_info_encode_base64 = base64.b64encode(card_info_encode).decode('utf-8')

        t = hex(len(aes_key_encode_base64))[2:]
        h = len(t)
        while 4 > h:
            t = '0' + t
            h += 1

        return t + aes_key_encode_base64 + card_info_encode_base64



    @classmethod
    def generate_aes_key_and_iv_hex(cls,temp_key: bytes,temp_iv: bytes):
        """
            通过临时key，iv，进行MD5，构建实际使用的KEY,IV
        :param temp_key:
        :param temp_iv:
        :return:
        """

        temp_bytes = temp_key + temp_iv
        temp_h = [hashlib.md5(temp_bytes).digest()]
        temp_u = temp_h[0]
        for i in range(1,3):
            temp_h.append(hashlib.md5(temp_h[i-1] + temp_bytes).digest())
            temp_u = temp_u + temp_h[i]

        key = temp_u[0:32]
        iv = temp_u[32:32+16]
        return key.hex(), iv.hex()
