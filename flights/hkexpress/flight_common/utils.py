import base64


class Utils:

    @staticmethod
    def base64url_to_hex(e):
        # 替换 Base64URL 特殊字符
        e = e.replace('-', '+').replace('_', '/')
        # 补齐长度
        padding = len(e) % 4
        if padding == 1:
            raise ValueError("InvalidLengthError: Input base64url string is the wrong length to determine padding")
        elif padding > 0:
            e += "=" * (4 - padding)
        # 解码 Base64 并转换为十六进制
        decoded = base64.b64decode(e)
        return decoded.hex()