

class DictUtil:

    @classmethod
    def reverse_lookup(cls,d, target_value):
        reversed_dict = {val: key for key, val in d.items()}
        return reversed_dict.get(target_value)  # 避免 KeyError