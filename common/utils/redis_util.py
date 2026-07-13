import time
import uuid
from typing import Optional

import redis
from redis import Redis

from common.global_variable import GlobalVariable


class RedisUtil:
    def __init__(
        self,
        host: str,
        port: str,
        username: Optional[str],
        password: Optional[str],
        db: Optional[int] = 0,
        socket_connect_timeout: Optional[float] = None,
        socket_timeout: Optional[float] = None,
    ):
        connection_kwargs = {
            "host": host,
            "port": port,
            "username": username,
            "password": password,
            "db": db,
        }
        if socket_connect_timeout is not None:
            connection_kwargs["socket_connect_timeout"] = socket_connect_timeout
        if socket_timeout is not None:
            connection_kwargs["socket_timeout"] = socket_timeout
        self.__pool = redis.ConnectionPool(**connection_kwargs)


    def get_pool(self):
        return self.__pool

    def get_redis_connection(self):
        redis_client = Redis(connection_pool=self.__pool)
        try:
            # 检查连接是否活跃
            if not redis_client.ping():
                raise ConnectionError("Redis连接不活跃")
        except ConnectionError:
            # 重置连接
            redis_client.connection_pool.disconnect()
            redis_client = self.get_redis_connection()

        return redis_client

    def up_expire(self,key,timeout):
        redis_client = self.get_redis_connection()
        redis_client.expire(key,timeout)

    def set_value_ex(self, key, value,timeout):
        redis_client = self.get_redis_connection()
        redis_client.set(key,value,ex=timeout)

    def get_value(self,key):
        redis_client = self.get_redis_connection()
        return redis_client.get(key)

    def get_hash_all(self,key):
        redis_client = self.get_redis_connection()
        return redis_client.hgetall(key)

    def exists(self,key):
        redis_client = self.get_redis_connection()
        return redis_client.exists(key)

    def delete_keys_with_transaction(self, pattern):
        """
        使用事务删除匹配模式的键
        :param pattern: 键的模式，例如 'cache:*', 'session:*'
        :return: True 成功，False 失败
        """
        r = self.get_redis_connection()
        try:
            # 【注意】首先使用 KEYS 命令获取所有匹配的键
            keys_to_delete = r.keys(pattern)
            if not keys_to_delete:
                return True  # 没有键需要删除，视为成功

            # 开启事务管道
            pipeline = r.pipeline()
            for key in keys_to_delete:
                pipeline.delete(key)  # 将删除命令添加到事务队列
            # 执行事务，原子性地删除所有键
            pipeline.execute()
            return True
        except redis.RedisError as e:
            print(f"删除键时发生错误: {e}")
            return False

    def delete_key(self,key):
        redis_client = self.get_redis_connection()
        redis_client.delete(key)

    def set_hash_field(self,key,field,value):
        redis_client = self.get_redis_connection()
        redis_client.hset(key,field,value)

    def list_push(self,key,value):
        redis_client = self.get_redis_connection()
        redis_client.lpush(key,value)

    def list_length(self,key):
        redis_client = self.get_redis_connection()
        return redis_client.llen(key)

    def list_get(self,key):
        redis_client = self.get_redis_connection()
        t = redis_client.lrange(key,0,-1)
        if t:
            t = [x.decode('utf-8') for x in t]
        return t

    def exists_in_list(self,key,value):
        redis_client = self.get_redis_connection()
        position = redis_client.lpos(key,value)
        return position is not None

    def acquire(self,task_id: str,identifier:str,timeout:int = 60, wait_timeout=5):
        lock_name = f'lock:{task_id}'
        redis_client = redis.Redis(connection_pool=self.__pool)
        """获取锁"""
        end = time.time() + wait_timeout
        while time.time() < end:
            # 尝试获取锁
            if redis_client.set(lock_name, identifier, nx=True, ex=timeout):
                return True
            time.sleep(0.001)  # 短暂等待
        return False

    def release(self,task_id: str,identifier: str):
        """释放锁"""
        # Lua脚本确保原子操作
        script = """
        if redis.call("GET", KEYS[1]) == ARGV[1] then
            return redis.call("DEL", KEYS[1])
        else
            return 0
        end
        """
        redis_client = redis.Redis(connection_pool=self.__pool)
        lock_name = f'lock:{task_id}'
        result = redis_client.eval(script, 1, lock_name, identifier)
        return result == 1


if __name__ == '__main__':
    REDIS_UTIL = RedisUtil(GlobalVariable.REDIS_HOST, GlobalVariable.REDIS_PORT, GlobalVariable.REDIS_USERNAME,
                           GlobalVariable.REDIS_PASSWORD)


    def delete_keys_by_pattern(host='localhost', port=6379, db=0, password=None, pattern='ds*'):
        """
        使用SCAN命令安全地删除匹配模式的键
        """
        # 连接到Redis服务器
        r = redis.Redis(host=host, port=port, db=db, password=password, decode_responses=True)

        try:
            # 初始化游标
            cursor = 0
            total_deleted = 0

            while True:
                # 使用SCAN命令迭代遍历，count可调整每批数量
                cursor, keys = r.scan(cursor=cursor, match=pattern, count=1000)

                # 如果本轮扫描到了键，则批量删除
                if keys:
                    # 使用delete(*keys)一次性删除本轮所有键，效率高于循环删除
                    deleted_count = r.delete(*keys)
                    total_deleted += deleted_count
                    print(f"已删除 {deleted_count} 个键。当前游标: {cursor}")

                # 当游标返回0时，表示遍历完成
                if cursor == 0:
                    break

            print(f"操作完成！总计删除 {total_deleted} 个匹配模式 '{pattern}' 的键。")

        except Exception as e:
            print(f"操作出错: {e}")
        finally:
            r.close()  # 关闭连接
