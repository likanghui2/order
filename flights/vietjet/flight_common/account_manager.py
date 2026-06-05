import json
import os
import ast
import time
import random
import redis

from common.global_variable import GlobalVariable


class AccountManager:
    """
    💼 Redis账号管理类
    功能：
        - 管理航司官网账号的 PNR 占位与 Authorization 缓存
        - 自动清理过期 PNR（1小时）和 Authorization（5天）
        - 提供获取可用账号的统一接口
    """

    def __init__(self):
        """
        初始化Redis连接与参数配置
        """
        self.r = redis.Redis(
            host=GlobalVariable.REDIS_HOST,
            port=GlobalVariable.REDIS_PORT,
            db=0,
            username=GlobalVariable.REDIS_USERNAME,
            password=GlobalVariable.REDIS_PASSWORD,
            decode_responses=True
        )
        self.MAX_PNR = 2  # 每个账号最多允许的PNR数量
        self.PNR_EXPIRE = 3700  # 每个PNR有效期（秒）
        self.AUTH_EXPIRE = 5 * 24 * 3600  # Authorization有效期（秒）

        # 从环境变量中读取账号密码（格式：{'userA': '123', 'userB': '456'}）
        default_accounts = {
            "84 376732342": "258369",
            "84 332139432": "170704",
            "84 378808118": "686868",
            "84 353082117": "230206",
            "84 584894845": "301124",
            "84 764285962": "100003",
            "84 906317230": "230408",
            "84 913785421": "091378",
            "84 354322664": "030408",
            "84 979864956": "261208",
            # "84 832800714": "083280",
            "84 338043298": "050428",
            "84 972255331": "210899",
            "84 829528886": "123789",
            "84 777187432": "385110",
            "84 984051257": "100625",
            "84 974712604": "222333",
            "84 336696003": "369369",
            "84 763171770": "221205",
            "84 363966414": "030408",
            "84 365868652": "152702",
            "84 911926498": "900369",
            "84 368509201": "050698",
            "84 979431537": "190308",
            "84 978197336": "456123",
            "84 948998935": "251200",
            "84 389265854": "109199",
            "84 364270936": "852009",
            "84 398772259": "120503",
            "84 964524815": "291020",
            "84 856289066": "261309",
            "84 967758109": "121219",
            "84 979477827": "192007",
            "84 867314725": "838609",
            "84 966431041": "280503",
            "84 787257248": "270723",
            "84 355868453": "221019",
            "84 369611502": "123888",
            "84 869403425": "112233",
            "84 774392134": "062006",
            "84 338468506": "280288",
            "84 911973113": "159753",
            "84 961568044": "120205",
            "84 386068920": "120904",
            "84 375146707": "211106",
            "84 704759972": "111112",
            "84 344769532": "160699",
            "84 865437313": "152702",
            "84 366465232": "060105",
            "84 363550223": "020608",
            "84 824019469": "000001",
            "84 988208728": "030926",
        }
        default_accounts = json.dumps(default_accounts)
        accounts_raw = os.getenv("ACCOUNTS", default_accounts)
        self.ACCOUNTS = ast.literal_eval(accounts_raw)

    # === 工具函数 ===
    @staticmethod
    def get_key(account: str) -> str:
        """生成Redis中该账号的key"""
        return f"account:{account}"

    # === 清理逻辑 ===

    def cleanup(self, account: str):
        """
        清理指定账号下的过期PNR和Authorization
        """
        k = self.get_key(account)
        data = self.r.hgetall(k)
        now = int(time.time())

        # 清除过期PNR
        for f, v in list(data.items()):
            if f.startswith("pnr_") and now - int(v) > self.PNR_EXPIRE:
                self.r.hdel(k, f)

        # 清除过期Authorization
        auth_time = data.get("auth_time")
        if auth_time and now - int(auth_time) > self.AUTH_EXPIRE:
            self.r.hdel(k, "authorization", "auth_time")

    # === 判断逻辑 ===

    def is_available(self, account: str) -> bool:
        """
        判断账号是否还能占位（PNR < MAX_PNR）
        """
        k = self.get_key(account)
        self.cleanup(account)
        pnr_count = len([f for f in self.r.hkeys(k) if f.startswith("pnr_")])
        return pnr_count < self.MAX_PNR

    # === 数据写入 ===

    def save_pnr(self, account: str, pnr: str):
        """
        保存PNR（不会自动过期，但cleanup会定期清理）
        """
        if not self.is_available(account):
            print(f"❌ {account} 已占满PNR")
            return False
        k = self.get_key(account)
        self.r.hset(k, f"pnr_{pnr}", str(int(time.time())))
        print(f"✅ {account} 添加PNR成功：{pnr}")
        return True

    def save_authorization(self, account: str, token: str):
        """
        保存账号的Authorization Token
        """
        k = self.get_key(account)
        now = int(time.time())
        self.r.hset(k, mapping={
            "authorization": token,
            "auth_time": now
        })
        print(f"🔑 {account} Authorization 已更新")

    # === 账号获取 ===

    def get_one_account(self):
        """
        获取一个可用账号：
            ✅ 优先返回有有效token的账号；
            ⚙️ 否则返回账号密码，用于重新登录。
        """
        candidates = list(self.ACCOUNTS.keys())
        random.shuffle(candidates)

        for acc in candidates:
            if not self.is_available(acc):
                continue

            token = self.r.hget(self.get_key(acc), "authorization")
            if token:
                return {"account": acc, "password": self.ACCOUNTS[acc], "authorization": token}
            else:
                return {"account": acc, "password": self.ACCOUNTS[acc]}

        return None

    def delete_authorization(self, account: str, ):
        """
        删除指定账号的 Authorization 信息（authorization + auth_time）
        """
        key = self.get_key(account)
        removed = self.r.hdel(key, "authorization", "auth_time")

        if removed:
            print(f"✅ 已清除 {account} 的 authorization 信息（共删除 {removed} 个字段）")
        else:
            print(f"ℹ️ {account} 没有可清除的 authorization 信息")

    # === 调试辅助 ===

    def show_status(self):
        """显示所有账号当前的PNR数和token状态"""
        print("\n📊 当前账号状态：")
        for acc in self.ACCOUNTS:
            k = self.get_key(acc)
            data = self.r.hgetall(k)
            pnr_count = len([f for f in data if f.startswith("pnr_")])
            has_auth = "authorization" in data
            print(f" - {acc}: PNR={pnr_count}, Token={'✅' if has_auth else '❌'}")


# === 示例运行 ===
if __name__ == "__main__":
    manager = AccountManager()

    # 模拟写入 token
    manager.save_authorization("userA", "Bearer eyJhbGciOiJ9.userA")

    # 模拟添加PNR
    manager.save_pnr("userB", "PNR003")
    manager.save_pnr("userB", "PNR004")

    # 获取账号
    result = manager.get_one_account()
    if result:
        print("✅ 分配账号：", result)
    else:
        print("❌ 当前没有可用账号")

    manager.show_status()
