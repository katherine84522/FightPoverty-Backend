# src/utils/decorators.py
# 角色權限裝飾器

from functools import wraps
from typing import Callable, List, Union

from fastapi import HTTPException, Request, status

from src.db.models import UserRole


def require_roles(*allowed_roles: Union[UserRole, str]) -> Callable:
    """
    角色權限檢查裝飾器。

    用法：
        @router.get("/admin-only")
        @require_roles(UserRole.SYSTEM_ADMIN, UserRole.NGO_ADMIN)
        async def admin_endpoint(request: Request):
            ...

    Args:
        allowed_roles: 允許存取的角色列表（可以是 UserRole enum 或字串）

    注意：
        - 此裝飾器需要在 route 裝飾器之後使用
        - endpoint 函式需要接收 request: Request 參數
        - 使用前需先透過 jwt_manager 驗證並將 user payload 存入 request.state.user
    """
    # 將所有角色轉換為字串值以便比較
    allowed_role_values: List[str] = []
    for role in allowed_roles:
        if isinstance(role, UserRole):
            allowed_role_values.append(role.value)
        else:
            allowed_role_values.append(str(role))

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 從 kwargs 或 args 中取得 request
            request: Request = kwargs.get("request")
            if request is None:
                # 嘗試從 args 中找到 Request 物件
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            if request is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="無法取得 Request 物件",
                )

            # 從 request.state 取得使用者資訊（由認證中介層設定）
            user_payload = getattr(request.state, "user", None)
            if user_payload is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="未經認證",
                )

            # 取得使用者角色
            user_role = user_payload.get("role")
            if user_role is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="無法取得使用者角色",
                )

            # 檢查角色是否在允許列表中
            if user_role not in allowed_role_values:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="權限不足",
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def require_any_role() -> Callable:
    """
    僅需要已登入（任何角色皆可）的裝飾器。

    用法：
        @router.get("/profile")
        @require_any_role()
        async def get_profile(request: Request):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request: Request = kwargs.get("request")
            if request is None:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            if request is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="無法取得 Request 物件",
                )

            user_payload = getattr(request.state, "user", None)
            if user_payload is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="未經認證",
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


# 常用角色組合的便捷裝飾器
def require_ngo_roles() -> Callable:
    """僅允許 NGO 相關角色（system_admin, ngo_admin, ngo_partner）"""
    return require_roles(
        UserRole.SYSTEM_ADMIN,
        UserRole.NGO_ADMIN,
        UserRole.NGO_PARTNER,
    )


def require_admin_roles() -> Callable:
    """僅允許管理員角色（system_admin, ngo_admin）"""
    return require_roles(
        UserRole.SYSTEM_ADMIN,
        UserRole.NGO_ADMIN,
    )


def require_store_roles() -> Callable:
    """僅允許商店相關角色"""
    return require_roles(
        UserRole.SYSTEM_ADMIN,
        UserRole.STORE,
    )


def require_association_roles() -> Callable:
    """僅允許商圈相關角色"""
    return require_roles(
        UserRole.SYSTEM_ADMIN,
        UserRole.ASSOCIATION_ADMIN,
        UserRole.ASSOCIATION_PARTNER,
    )
