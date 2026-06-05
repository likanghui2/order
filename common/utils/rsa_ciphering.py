import base64
import binascii

from Crypto.Cipher import PKCS1_OAEP, PKCS1_v1_5
from Crypto.Hash import SHA256, SHA1
from Crypto.PublicKey import RSA


# 自定义 MGF1 使用 SHA-1
def mgf1_sha1(seed: bytes, length: int) -> bytes:
    """
    MGF1 实现，基于 SHA-1
    :param seed: 输入种子
    :param length: 生成掩码的目标长度
    :return: 掩码（长度为 length）
    """
    mask = b""
    counter = 0
    while len(mask) < length:
        counter_bytes = counter.to_bytes(4, byteorder="big")  # 整数计数器转换为 4 字节
        mask += SHA1.new(seed + counter_bytes).digest()  # 拼接 seed 和 counter
        counter += 1
    return mask[:length]


class RsaCiphering:
    def __init__(self, rsa_public_key: str, pkcs: int = 1, hasg_algo: bool = None):
        """
        初始化加密处理类。

        Args:
            rsa_public_key (str): PEM 格式的 RSA 公钥。
            pkcs (int): 用来判断填充方式
        """
        if pkcs == 1:
            if hasg_algo:
                self.rsa_cipher = PKCS1_OAEP.new(RSA.import_key(rsa_public_key), hashAlgo=SHA256)
            else:
                self.rsa_cipher = PKCS1_OAEP.new(RSA.import_key(rsa_public_key))
        else:
            self.rsa_cipher = PKCS1_v1_5.new(RSA.import_key(base64.b64decode(rsa_public_key)))

    def encrypt(self, data: str) -> str:
        """
        使用 RSA 公钥加密数据。

        Args:
            data (str): 要加密的数据（str）。

        Returns:
            str: Base64 编码的加密结果。
        """
        encrypted_data = self.rsa_cipher.encrypt(data.encode('utf-8'))
        return base64.b64encode(encrypted_data).decode('utf-8')

    @classmethod
    def rsa_encrypt_pkcs_v1_5(cls,hex_n, hex_e, data):
        n = int(hex_n, 16)
        e = int(hex_e, 16)

        # 3. 使用模数n和指数e构建RSA公钥对象
        public_key = RSA.construct((n, e))

        # 4. 创建使用PKCS#1 v1.5填充的加密器
        cipher = PKCS1_v1_5.new(public_key)


        # 6. 执行加密
        ciphertext = cipher.encrypt(data.encode('utf-8'))
        return ciphertext

    @classmethod
    def rsa_encrypt(cls, hex_n, hex_e, data):
        """
        使用给定的公钥模数 (n) 和公钥指数 (e) 加密数据。

        :param hex_n: 公钥模数的十六进制字符串
        :param hex_e: 公钥指数的十六进制字符串
        :param data: 需要加密的数据（字符串）
        :return: 加密后的数据，十六进制字符串形式
        """
        # 将公钥模数和公钥指数从十六进制转换为整数
        n = int(hex_n, 16)
        e = int(hex_e, 16)

        # 创建 RSA 公钥对象
        public_key = RSA.construct((n, e))
        cipher = PKCS1_OAEP.new(
            public_key,
            hashAlgo=SHA256,
            mgfunc=mgf1_sha1
        )

        # 加密数据
        encrypted_data = cipher.encrypt(data.encode())

        # 返回加密后的数据的十六进制表示
        return encrypted_data
