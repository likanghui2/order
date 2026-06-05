import base64
import hashlib
import json
import math
import random
import time
import uuid
from datetime import date, timedelta, datetime
from typing import Tuple
from urllib.parse import quote_plus

from Crypto.Cipher import PKCS1_OAEP
from Crypto.PublicKey import RSA


class VietjetSearchUtils:
    @staticmethod
    def h_g(e):
        parts = e.split("-")
        t = "".join(seg[0] + seg[-1] for seg in parts if len(seg) > 1)
        return "".join(str(ord(ch) ^ 1) for ch in t)

    @staticmethod
    def get_t():
        session_storage = {
            "ss-data-ga": str(uuid.uuid4())
        }
        local_storage = {
            "temp-data-ga": f"{uuid.uuid4()}-{int(time.time() * 1000)}"
        }
        p_p = {
            "b": "c3MtZGF0YS1nYQ==",
            "c": "dGVtcC1kYXRhLWdh",
            "f": "eC1wb3dlci13ZWItcy1k",
            "e": "dXNlci1hZ2VudC1scy1kYXRh",
            "d": "metaSearchKey",
            "a": {
                "Token": "token",
                "ExpireAt": "tokenExpireAt",
                "Provider": "auth_provider"
            }
        }

        n_key = base64.b64decode(p_p['b']).decode()
        a_key = base64.b64decode(p_p['c']).decode()
        f_key = base64.b64decode(p_p['f']).decode()
        e_key = base64.b64decode(p_p['e']).decode()

        n = session_storage.get(n_key)
        a = local_storage.get(a_key)

        r = a
        if r is not None:
            i = r.split("-")
            i.pop()
        else:
            i = []

        c = "-".join(n.split("-")[2:]) if n else None
        t = {f_key: f"{VietjetSearchUtils.h_g('-'.join(i))}-{VietjetSearchUtils.h_g(n)}-{c}" if n and c else "",
             e_key: a if a else ""}
        now = int(time.time() * 1000)
        chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        rnd = "".join(random.choice(chars) for _ in range(12))
        t["requestId"] = f"{rnd}-{now}"
        return t

    @staticmethod
    def d_a_stringify(d, parent_key=''):
        items = []
        for key, value in sorted(d.items()):
            new_key = f"{parent_key}[{quote_plus(str(key))}]" if parent_key else quote_plus(str(key))

            # 如果值是None，则替换为""
            if value is None:
                value = ""

            if isinstance(value, dict):
                items.append(VietjetSearchUtils.d_a_stringify(value, new_key))  # 递归处理字典
            elif isinstance(value, list):
                for sub_dict in value:
                    items.append(VietjetSearchUtils.d_a_stringify(sub_dict, new_key))  # 处理列表中的字典，直接展开
            else:
                items.append(f"{new_key}={quote_plus(str(value))}")
        result = '&'.join(items).replace('+', '%20')
        result = result.replace('[', '%5B').replace(']', '%5D')
        result = result.replace('True', 'true').replace('False', 'false').replace('None', 'null')
        return result

    @staticmethod
    def add_signature(o: dict) -> dict:
        query_str = VietjetSearchUtils.d_a_stringify(o).replace('&&', '&')
        signature = hashlib.sha256(query_str.encode("utf-8")).hexdigest()
        o["_signature"] = signature
        return o

    @staticmethod
    def rsa_encrypt(message):
        rsa_public_key = "-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAok58IrYXjeFjb6hPgrcv\nKis43ARDVIqowS2AJKivDp4+8uKDCWnjzBZTsuVvwKPzvVCxBzON2/DPpHU3wnRt\ndKSVzWju7HMKhuLxe04FsVw8+xvZTmguBj4jTczNLSLjK13lQr46J8j7JrmVUlPq\nGxIL/Bd3HNAIFuarZQkDsgx5fvdNrMbmT4edr1b3A8wRkhfo9tuE5Tmlx0YVUwyb\nzcI6hgLggCfNwwaClXyBt08NbGSIBcKYKjiQErND0EOnWcGyto7EhkpgGRfAeESo\n3hbmsiabThLd4t9iOWVHFSl+7B0q+1IGFjSo9qkvNdMUI4ZYdIKq+nCHufpuFMl7\nSwIDAQAB\n-----END PUBLIC KEY-----"
        rsa_key = RSA.importKey(rsa_public_key)
        cipher = PKCS1_OAEP.new(rsa_key)
        cipher_text = cipher.encrypt(message=message)
        return cipher_text

    @staticmethod
    def encrypt(message):
        message = json.dumps(message, separators=(',', ':'))
        # 公共组件加密出来的结果不能用
        message_byte = message.encode('utf-8')
        a = math.ceil(len(message_byte) / 214)
        a = 1 if a < 0 else a
        s = math.ceil(len(message_byte) / a)
        s = 1 if s < 0 else s

        result_array = []
        result_message = b''
        if a == 1:
            result_array.append(message_byte)
        else:
            for i in range(a):
                result_array.append(message_byte[i * s:(i + 1) * s])

        for i in result_array:
            result_message += VietjetSearchUtils.rsa_encrypt(i)
        return base64.b64encode(result_message).decode('utf-8')

    @staticmethod
    def duration_to_minutes(duration: str) -> int:
        """
        将形如 '8h 30m' 的飞行时长字符串转换为分钟数。

        Args:
            duration (str): 飞行时长字符串，例如 '8h 30m'

        Returns:
            int: 总分钟数
        """
        hours = 0
        minutes = 0

        # 按照空格分隔小时和分钟
        parts = duration.split()
        for part in parts:
            if 'h' in part:
                hours = int(part.replace('h', ''))
            elif 'm' in part:
                minutes = int(part.replace('m', ''))

        # 转换成总分钟数
        total_minutes = hours * 60 + minutes
        return total_minutes

    @staticmethod
    def adjust_arrival_datetime(departure_date: date, departure_time: time, arrival_time: time) -> Tuple[
         datetime, datetime]:
        """

        Args:
            departure_date:
            departure_time:
            arrival_time:

        Returns:

        """
        departure_datetime = datetime.combine(departure_date, departure_time)
        arrival_datetime = datetime.combine(departure_date, arrival_time)

        if arrival_datetime < departure_datetime:
            arrival_datetime += timedelta(days=1)

        return departure_datetime, arrival_datetime
