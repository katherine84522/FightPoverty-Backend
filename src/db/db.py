from functools import lru_cache
import redis
import os
from dotenv import load_dotenv

load_dotenv()

# 這裡你之後可以改成從環境變數讀
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))


@lru_cache
def get_redis() -> redis.Redis:
    """
    回傳一個全域共用的 Redis client。
    lru_cache 確保整個程式生命週期只建立一次連線實例。
    """
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True,  # 自動把 bytes 轉成 str
    )
