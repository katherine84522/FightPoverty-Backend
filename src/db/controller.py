from typing import Dict, Optional, Any, Union

from uuid import UUID
import bcrypt

from src.db.repositories import UserRepository
from src.db.models import User

user_repo = UserRepository()


async def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """
    依 username 查詢使用者，回傳 dict 或 None。
    """
    user = user_repo.get_by_username(username)
    return user.model_dump() if user else None


async def get_user_by_id(user_id: int | str) -> Optional[Dict[str, Any]]:
    """
    依 user_id 查詢使用者，回傳 dict 或 None。
    """
    user = user_repo.get_by_id(user_id)
    return user.model_dump() if user else None


async def verify_password(plain: str, stored: str) -> bool:
    """
    密碼驗證。
    """
    if not stored:
        return False

    try:
        return bcrypt.checkpw(plain.encode("utf-8"), stored.encode("utf-8"))
    except Exception:
        return False


async def get_user_info(user: Union[User, Dict[str, Any]]) -> Dict[str, Any]:
    """
    整理要回傳給前端的使用者資訊。
    確保所有欄位都是 JSON 可序列化（尤其是 UUID 要轉成 str）。
    """
    if isinstance(user, User):
        data = user.model_dump()
    else:
        data = dict(user)

    # UUID 轉 str
    user_id = data.get("id")
    if isinstance(user_id, UUID):
        user_id = str(user_id)

    return {
        "id": user_id,
        "username": data.get("username"),
        "role": data.get("role"),   # Enum 在 dict 裡是字串 value，例如 "store"
        "email": data.get("email"),
    }
