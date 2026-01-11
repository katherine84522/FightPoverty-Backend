from typing import Dict, Optional, Any, Union

from uuid import UUID
import bcrypt

from src.db.repositories import UserRepository
from src.db.models import User

user_repo = UserRepository()

# 延遲導入以避免循環導入
_store_repo = None
_homeless_repo = None


def _get_store_repo():
    global _store_repo
    if _store_repo is None:
        from src.db.repositories import StoreRepository
        _store_repo = StoreRepository()
    return _store_repo


def _get_homeless_repo():
    global _homeless_repo
    if _homeless_repo is None:
        from src.db.repositories import HomelessPersonRepository
        _homeless_repo = HomelessPersonRepository()
    return _homeless_repo


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
    包含關聯的 store 或 homeless 資訊（如有）。
    """
    if isinstance(user, User):
        data = user.model_dump()
    else:
        data = dict(user)

    # UUID 轉 str
    user_id = data.get("id")
    if isinstance(user_id, UUID):
        user_id = str(user_id)

    result = {
        "id": user_id,
        "username": data.get("username"),
        "name": data.get("name"),
        "role": data.get("role"),   # Enum 在 dict 裡是字串 value，例如 "store"
        "email": data.get("email"),
        "phone": data.get("phone"),
    }

    # 如果是商店角色，附加商店資訊
    store_id = data.get("store_id")
    if store_id:
        if isinstance(store_id, UUID):
            store_id = str(store_id)
        result["store_id"] = store_id

        # 取得商店的 QR Code
        store = _get_store_repo().get_by_id(store_id)
        if store:
            result["store_qr_code"] = store.qr_code
            result["store_name"] = store.name

    # 如果是街友角色，附加街友資訊
    homeless_id = data.get("homeless_id")
    if homeless_id:
        if isinstance(homeless_id, UUID):
            homeless_id = str(homeless_id)
        result["homeless_id"] = homeless_id

        # 取得街友的完整資訊
        homeless = _get_homeless_repo().get_by_id(homeless_id)
        if homeless:
            result["qr_code"] = homeless.qr_code
            result["balance"] = homeless.balance
            result["id_number"] = homeless.id_number
            result["address"] = homeless.address
            result["emergency_contact"] = homeless.emergency_contact
            result["emergency_phone"] = homeless.emergency_phone
            result["notes"] = homeless.notes

    # 如果是商圈角色，附加商圈資訊
    association_id = data.get("association_id")
    if association_id:
        if isinstance(association_id, UUID):
            association_id = str(association_id)
        result["association_id"] = association_id

    return result
