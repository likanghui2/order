import base64
import hashlib
import json
import time

from common.model.task.response_order_info_model import ResponseOrderInfoModel
from common.utils.aes_ciphering import AesCiphering
from flights.batik.config import Config
import os
from typing import Tuple

from Crypto import Random

from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5
from pyquery import PyQuery as pq


class Utils:

    @staticmethod
    def get_country_by_currency(currency):
        for a1 in Config.AIRPORTS['data']:
            if a1['currency'] == currency.upper():
                return a1['countryCode']
        return None

    @staticmethod
    def get_country(air_code):
        for a1 in Config.AIRPORTS['data']:
            if a1['airportCode'] == air_code.upper():
                return a1['countryCode']
        return None

    @staticmethod
    def make_header_args(token: str):
        timestamp = str(int(time.time() * 1000))
        q = str(f'DC_PRD_CLIENT_IDDC_API_PRD_PasswordP{token}{timestamp}')
        hash_token = hashlib.sha256(q.encode()).hexdigest()

        return timestamp, hash_token

    @staticmethod
    def aes_encrypt(data: str) -> str:

        encrypted_data = AesCiphering.encrypt(data=str(data).encode('utf-8'), key=Config.AES_KEY,
                                              iv=Config.AES_IV, mode=2)

        encrypted_data = base64.b64encode(encrypted_data).decode('utf-8')

        return encrypted_data

    @staticmethod
    def aes_decrypt(data: str) -> dict:

        encrypted_data = AesCiphering.decrypt(data=base64.b64decode(data), key=Config.AES_KEY,
                                              iv=Config.AES_IV, mode=2)

        return json.loads(encrypted_data.decode())

    @staticmethod
    def pay_encrypt(card_info):

        # Generate random key (8 characters)
        def generate_random_key(length=8):
            chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*()-+=_"
            return "".join(chars[os.urandom(1)[0] % len(chars)] for _ in range(length))

        # RSA encryption
        def rsa_encrypt(data, public_key_pem):
            public_key = RSA.import_key(public_key_pem)
            cipher = PKCS1_v1_5.new(public_key)
            encrypted_data = cipher.encrypt(data.encode())
            return base64.b64encode(encrypted_data).decode()

        # Mask card number
        def mask_card_number(card_number):
            start = card_number[:6]
            end = card_number[-4:]
            middle = "X" * (len(card_number) - 10)
            return start + middle + end

        def get_aes_key_and_iv(key: str = None) -> Tuple[bytes, bytes, bytes]:
            """
                获取Aes key iv
            Returns:

            """

            salt = Random.new().read(8)
            d = b''
            d_i = b''
            while len(d) < 48:
                d_i = hashlib.md5(d_i + key.encode() + salt).digest()
                d += d_i
            return d[:32], d[32:48], salt

        def encrypt_message(message: str, input_key=None) -> str:
            """

            Args:
                message:

            Returns:

            """

            key, iv, salt = get_aes_key_and_iv(input_key)

            cipher_text = AesCiphering.encrypt(data=message.encode('utf-8'),
                                               key=key,
                                               iv=iv,
                                               mode=2)
            result_bytes = b'Salted__' + salt + cipher_text
            return base64.b64encode(result_bytes).decode('utf-8')

        random_key = generate_random_key()

        # Step 2: Encrypt `e` using RSA
        encrypted_key = rsa_encrypt(random_key, Config.PAY_RSA_KEY)

        # Step 3: Extract and mask card details
        card_number = card_info["cardnumber"]
        masked_card = mask_card_number(card_number)
        month = card_info["month"]
        year = card_info["year"]
        cvv = card_info["cvv"]

        # Special rules based on prefix
        if card_number.startswith("62") or card_number.startswith("81"):
            month = ""
            year = ""
            cvv = ""

        # Step 4: Create data string and encrypt it using AES
        data = f"{card_number};{month};{year};{cvv}"
        encrypted_data = encrypt_message(data, random_key)

        # Step 5: Combine encrypted key and data
        encrypted_key_length = hex(len(encrypted_key))[2:].zfill(4)
        final_encrypted_info = encrypted_key_length + encrypted_key + encrypted_data

        # Step 6: Return results
        return {
            "encryptedCardInfo": final_encrypted_info,
            "maskedCardInfo": masked_card,
            "expMonthCardInfo": card_info["month"],
            "expYearCardInfo": card_info["year"],
        }

    @staticmethod
    def concat_images_vertically_transparent_bytes(image_bytes_list):
        from PIL import Image
        import io
        images = [Image.open(io.BytesIO(b)).convert("RGBA") for b in image_bytes_list]
        max_width = max(img.width for img in images)
        total_height = sum(img.height for img in images)
        new_image = Image.new('RGBA', (max_width, total_height), (255, 255, 255, 255))
        y_offset = 0
        for img in images:
            new_image.paste(img, (0, y_offset), mask=img)
            y_offset += img.height

        output_buffer = io.BytesIO()
        new_image.save(output_buffer, format='PNG')
        output_bytes = output_buffer.getvalue()
        output_buffer.close()

        return output_bytes

    @classmethod
    def extract_form_data(cls, html_content):
        doc = pq(html_content)
        form = doc("form")  # 目前抓包，网页内只有一个表单
        action, form_data = cls.get_form_data(form)

        return action, form_data

    @classmethod
    def get_form_data(cls, form):
        # action = form.attrib["action"]
        action = form.attr("action")
        # print(action)
        inputs = form("input")
        form_data = {}
        for input_tag in inputs.items():
            # input_type = input_tag.attr("type")
            input_name = input_tag.attr("name") or ""
            input_value = input_tag.attr("value") or ""
            if input_name:
                form_data[input_name] = input_value
            # print(f"    Input - Type: {input_type}, Name: {input_name}, Value: {input_value}")
        # print(form_data)

        return action, form_data

    @staticmethod
    def parse_book_order(booking_info: dict, response_order_data: ResponseOrderInfoModel):
        for i in response_order_data.passengers:
            for j in booking_info['passengerInfos']:
                if i.last_name == j['surname'] and i.first_name == j['givenName']:
                    i.ticket_number = j['ticketNumber']
