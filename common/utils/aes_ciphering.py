import base64

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad


class AesCiphering:

    @staticmethod
    def encrypt(data: bytes, key: bytes, iv: bytes, mode) -> bytes:
        padded_plain_text = pad(data, AES.block_size)

        # 创建 AES CBC 加密器
        if mode == 1:
            cipher = AES.new(key, mode)
        else:
            cipher = AES.new(key, mode, iv)

        # 加密明文
        cipher_text = cipher.encrypt(padded_plain_text)
        return cipher_text

    @staticmethod
    def decrypt(data: bytes, key: bytes, iv: bytes, mode) -> bytes:
        # 创建 AES 解密器（判断是否使用 iv）
        if mode == AES.MODE_ECB:
            cipher = AES.new(key, mode)
        else:
            cipher = AES.new(key, mode, iv)

        # 解密密文
        decrypted_data = cipher.decrypt(data)

        # 移除填充并返回明文
        plain_text = unpad(decrypted_data, AES.block_size)
        return plain_text
