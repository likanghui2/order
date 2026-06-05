import time
import json
import redis
from typing import Optional

from common.global_variable import GlobalVariable


class RedisTokenQueue:
    """
    Redis token 队列（分布式版）
    - 使用 list 保证 FIFO
    - 使用 hash 存 token + 时间戳
    - 自动过期：超过 10 分钟不返回
    """

    EXPIRE_SECONDS = 600  # token 最大有效期

    def __init__(self, prefix="token_queue"):
        self.r = redis.Redis(
            host=GlobalVariable.REDIS_HOST,
            port=GlobalVariable.REDIS_PORT,
            db=0,
            username=GlobalVariable.REDIS_USERNAME,
            password=GlobalVariable.REDIS_PASSWORD,
            decode_responses=True
        )
        self.key_list = f"{prefix}:list"
        self.key_hash = f"{prefix}:hash"

    def add(self, token: str):
        """存 token（追加到队列尾部）"""
        now = int(time.time())
        self.r.hset(self.key_hash, token, now)
        self.r.rpush(self.key_list, token)
        return self.r.llen(self.key_list)

    def get(self, threshold_seconds: int) -> Optional[str]:
        """
        获取符合条件的最早 token：
        created_age >= threshold_seconds AND < EXPIRE_SECONDS
        """
        now = int(time.time())

        while True:
            token = self.r.lpop(self.key_list)
            if not token:
                return None  # 队列空

            created_at = self.r.hget(self.key_hash, token)
            if not created_at:
                continue

            created_at = int(created_at)
            age = now - created_at

            # 自动清理超过 10 分钟的 token
            if age >= self.EXPIRE_SECONDS:
                self.r.hdel(self.key_hash, token)
                continue

            # 满足阈值 → 返回并删除哈希值
            if age >= threshold_seconds:
                self.r.hdel(self.key_hash, token)
                return token

            # 不满足 → 重新放回队列尾部（保持 FIFO）
            self.r.rpush(self.key_list, token)
            return None
