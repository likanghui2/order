import random
import string


class StringUtil:

    @staticmethod
    def extract_between(text, start_str, end_str):
        start_idx = text.find(start_str) + len(start_str)  # 起始子串后位置
        end_idx = text[start_idx:].find(end_str)  # 结束子串前位置
        if start_idx != -1 and end_idx != -1:
            return text[start_idx:start_idx+end_idx]  # 提取中间内容
        return ""  # 未找到返回空

    @staticmethod
    def generate_random_string(
            length=10,
            force_alpha_first=True,
            capitalize_first=False,
            use_symbols=False,
            add_digits=False
    ):
        """
        生成随机字符串
        参数：
            length: int - 字符串长度（默认10）
            use_symbols: bool - 是否包含符号（默认True）
            capitalize_first: bool - 首字母是否大写（默认False）
            force_alpha_first: bool - 是否强制首字符为字母（默认False）
            add_digits: bool - 是否包含数字（默认False）

        返回：
            str - 生成的随机字符串
        """
        if length < 1:
            raise ValueError("Length must be at least 1")

        # 构建基础字符池（始终包含字母）
        chars = string.ascii_letters  # A-Z a-z

        # 添加数字（如果启用）
        if add_digits:
            chars += string.digits  # 0-9

        # 添加符号（如果启用）
        if use_symbols:
            chars += string.punctuation  # !"#$%&'()*+,-./:;<=>?@[\]^_`{|}~

        # 检查首字母大写可行性
        if capitalize_first and not any(c.isalpha() for c in chars):
            raise ValueError("Cannot capitalize first character when no letters are allowed")

        # 生成首字符
        if force_alpha_first:
            # 强制首字符为字母
            if capitalize_first:
                first_char = random.choice(string.ascii_uppercase)
            else:
                first_char = random.choice(string.ascii_lowercase)
        else:
            # 随机选择首字符
            if capitalize_first:
                # 需要首字母大写（从所有字母中选）
                first_char = random.choice(string.ascii_uppercase)
            else:
                first_char = random.choice(chars)

        # 生成剩余字符
        remaining_chars = ''.join(random.choices(chars, k=length - 1))

        return first_char + remaining_chars

    @classmethod
    def extract_between(cls, text, start, end):
        """
            从文本中提取开始和结束标识符之间的内容。
        参数：
            text: 要从中提取内容的原始文本。
            start: 开始标识符。
            end: 结束标识符。
        返回：
            开始和结束标识符之间的内容。
        """
        start_index = text.find(start)
        if start_index == -1:
            return None  # 如果未找到开始标识符，返回 None

        start_index += len(start)  # 移动到开始标识符之后
        end_index = text.find(end, start_index)
        if end_index == -1:
            return None  # 如果未找到结束标识符，返回 None

        return text[start_index:end_index]

    @classmethod
    def generate_custom_random_string(cls,base_chars, length, readable=False):
        """
        生成定制化的随机字符串

        Args:
            base_chars (str): 用户提供的基准字符串
            length (int): 需要生成的随机字符串的长度
            readable (bool, optional): 是否避免使用易混淆字符. 默认为 False.

        Returns:
            str: 生成的随机字符串
        """
        if not base_chars:
            if readable:
                # 使用更易识别的字符集，避免 '0', 'O', '1', 'l' 等易混淆字符[6](@ref)
                base_chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnopqrstuvwxyz23456789'
            else:
                base_chars = string.ascii_letters + string.digits

        random_string = ''.join(random.choices(base_chars, k=length))
        return random_string