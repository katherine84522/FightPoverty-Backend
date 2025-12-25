# app/db/repositories.py
from typing import Optional, Dict, Any

from src.db.models import User
from src.db.db import get_redis


class UserRepository:
    """
    與 Redis 互動的 User 資料存取層。

    Redis 結構：
      - user:{username} => Hash(id, username, password, role, email, ...)
      - user:id:{id}    => String(username)
    """

    def __init__(self):
        self._redis = get_redis()

    # Key helpers
    def _key_by_username(self, username: str) -> str:
        return f"user:{username}"

    def _index_by_id(self, user_id: int | str) -> str:
        return f"user:id:{user_id}"

    def get_by_username(self, username: str) -> Optional[User]:
        key = self._key_by_username(username)
        data: Dict[str, Any] = self._redis.hgetall(key)
        if not data:
            return None

        # Redis 全是字串，必要欄位轉型
        if "id" in data:
            try:
                data["id"] = int(data["id"])
            except ValueError:
                pass

        # role 欄位會是字串（例如 "store"），Pydantic 會自動轉成 UserRole
        return User(**data)

    def get_by_id(self, user_id: int | str) -> Optional[User]:
        # 先從 index 找 username
        index_key = self._index_by_id(user_id)
        username = self._redis.get(index_key)
        if not username:
            return None
        return self.get_by_username(username)

    def save(self, user: User) -> None:
        """
        新增 / 更新使用者。
        建議用在註冊 / 後台管理。
        """
        key = self._key_by_username(user.username)
        data = user.model_dump() # Enum 會存成 value（字串）

        # 寫入 Hash
        self._redis.hset(key, mapping=data)

        # 更新 id 索引
        self._redis.set(self._index_by_id(user.id), user.username)

    def delete_by_username(self, username: str) -> None:
        user = self.get_by_username(username)
        if not user:
            return
        self._redis.delete(self._key_by_username(username))
        self._redis.delete(self._index_by_id(user.id))
