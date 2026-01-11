# src/routers/users.py
# 使用者帳號管理路由

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

# 台灣時區 (UTC+8)
TW_TIMEZONE = timezone(timedelta(hours=8))

import bcrypt
from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse

from src.db.models import User, UserCreate, UserRole, Status
from src.db.repositories import UserRepository
from src.routers.auth import authenticate_token

router = APIRouter()

# Repository 實例
user_repo = UserRepository()


def hash_password(password: str) -> str:
    """雜湊密碼"""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


# ─────────────────────────────────────────────────────────
# 列出夥伴帳號
# ─────────────────────────────────────────────────────────
@router.get("")
async def list_users(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user_payload: Dict[str, Any] = Depends(authenticate_token),
):
    """
    列出夥伴帳號。

    權限：
    - ngo_admin: 可列出 ngo_partner
    - association_admin: 可列出 association_partner（僅限自己商圈）
    """
    user_role = user_payload.get("role")

    # NGO Admin 列出 NGO Partner
    if user_role == UserRole.NGO_ADMIN.value:
        users, total = user_repo.list_by_role(
            role=UserRole.NGO_PARTNER,
            page=page,
            limit=limit,
        )
    # Association Admin 列出自己商圈的 Association Partner
    elif user_role == UserRole.ASSOCIATION_ADMIN.value:
        association_id = user_payload.get("association_id")
        if not association_id:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"success": False, "message": "找不到所屬商圈"},
            )
        users, total = user_repo.list_by_role(
            role=UserRole.ASSOCIATION_PARTNER,
            page=page,
            limit=limit,
            association_id=UUID(association_id) if isinstance(association_id, str) else association_id,
        )
    else:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"success": False, "message": "權限不足"},
        )

    total_pages = (total + limit - 1) // limit

    return JSONResponse(
        content={
            "success": True,
            "data": [
                {
                    "id": str(u.id),
                    "username": u.username,
                    "name": u.name,
                    "role": u.role.value if hasattr(u.role, 'value') else u.role,
                    "email": u.email,
                    "phone": u.phone,
                    "status": u.status.value if hasattr(u.status, 'value') else u.status,
                    "lastLoginAt": u.last_login_at.isoformat() if u.last_login_at else None,
                    "createdAt": u.created_at.isoformat(),
                }
                for u in users
            ],
            "meta": {
                "page": page,
                "limit": limit,
                "total": total,
                "totalPages": total_pages,
            },
        }
    )


# ─────────────────────────────────────────────────────────
# 新增夥伴帳號
# ─────────────────────────────────────────────────────────
@router.post("")
async def create_user(
    data: UserCreate,
    request: Request,
    user_payload: Dict[str, Any] = Depends(authenticate_token),
):
    """
    新增夥伴帳號。

    權限：
    - ngo_admin: 可新增 ngo_partner
    - association_admin: 可新增 association_partner（自動設定為同商圈）
    """
    user_role = user_payload.get("role")

    # 檢查使用者名稱是否已存在
    existing = user_repo.get_by_username(data.username)
    if existing:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "message": "使用者名稱已存在"},
        )

    # NGO Admin 只能新增 NGO Partner
    if user_role == UserRole.NGO_ADMIN.value:
        if data.role != UserRole.NGO_PARTNER:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"success": False, "message": "只能新增 NGO 夥伴帳號"},
            )
        association_id = None
    # Association Admin 只能新增 Association Partner
    elif user_role == UserRole.ASSOCIATION_ADMIN.value:
        if data.role != UserRole.ASSOCIATION_PARTNER:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"success": False, "message": "只能新增商圈夥伴帳號"},
            )
        # 自動設定為管理員的商圈
        admin_association_id = user_payload.get("association_id")
        if not admin_association_id:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"success": False, "message": "找不到所屬商圈"},
            )
        association_id = UUID(admin_association_id) if isinstance(admin_association_id, str) else admin_association_id
    else:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"success": False, "message": "權限不足"},
        )

    # 建立使用者
    now = datetime.now(TW_TIMEZONE)
    user = User(
        id=uuid4(),
        username=data.username,
        password=hash_password(data.password),
        name=data.name,
        role=data.role,
        email=data.email,
        phone=data.phone,
        status=Status.ACTIVE,
        store_id=None,
        homeless_id=None,
        association_id=association_id,
        created_at=now,
        updated_at=now,
    )

    user_repo.create(user)

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "success": True,
            "message": "帳號建立成功",
            "data": {
                "id": str(user.id),
                "username": user.username,
                "name": user.name,
                "role": user.role.value,
                "email": user.email,
                "phone": user.phone,
                "status": user.status.value,
                "createdAt": user.created_at.isoformat(),
            },
        },
    )


# ─────────────────────────────────────────────────────────
# 刪除夥伴帳號
# ─────────────────────────────────────────────────────────
@router.delete("/{user_id}")
async def delete_user(
    user_id: UUID,
    request: Request,
    user_payload: Dict[str, Any] = Depends(authenticate_token),
):
    """
    刪除夥伴帳號。

    權限：
    - ngo_admin: 可刪除 ngo_partner
    - association_admin: 可刪除 association_partner（僅限自己商圈）
    """
    admin_role = user_payload.get("role")

    # 取得要刪除的使用者
    user = user_repo.get_by_id(user_id)
    if not user:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"success": False, "message": "找不到該使用者"},
        )

    target_role = user.role.value if hasattr(user.role, 'value') else user.role

    # NGO Admin 只能刪除 NGO Partner
    if admin_role == UserRole.NGO_ADMIN.value:
        if target_role != UserRole.NGO_PARTNER.value:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"success": False, "message": "只能刪除 NGO 夥伴帳號"},
            )
    # Association Admin 只能刪除自己商圈的 Association Partner
    elif admin_role == UserRole.ASSOCIATION_ADMIN.value:
        if target_role != UserRole.ASSOCIATION_PARTNER.value:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"success": False, "message": "只能刪除商圈夥伴帳號"},
            )
        # 檢查是否為同商圈
        admin_association_id = user_payload.get("association_id")
        if not admin_association_id:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"success": False, "message": "找不到所屬商圈"},
            )
        user_assoc_id = str(user.association_id) if user.association_id else None
        if user_assoc_id != str(admin_association_id):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"success": False, "message": "只能刪除自己商圈的夥伴帳號"},
            )
    else:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"success": False, "message": "權限不足"},
        )

    # 刪除使用者
    user_repo.delete(user_id)

    return JSONResponse(
        content={"success": True, "message": "帳號已刪除"}
    )


# ─────────────────────────────────────────────────────────
# 取得單一使用者
# ─────────────────────────────────────────────────────────
@router.get("/{user_id}")
async def get_user(
    user_id: UUID,
    request: Request,
    user_payload: Dict[str, Any] = Depends(authenticate_token),
):
    """
    取得單一使用者詳細資料。

    權限：
    - ngo_admin: 可查看 ngo_partner
    - association_admin: 可查看 association_partner（僅限自己商圈）
    """
    admin_role = user_payload.get("role")

    user = user_repo.get_by_id(user_id)
    if not user:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"success": False, "message": "找不到該使用者"},
        )

    target_role = user.role.value if hasattr(user.role, 'value') else user.role

    # 權限檢查
    if admin_role == UserRole.NGO_ADMIN.value:
        if target_role != UserRole.NGO_PARTNER.value:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"success": False, "message": "權限不足"},
            )
    elif admin_role == UserRole.ASSOCIATION_ADMIN.value:
        if target_role != UserRole.ASSOCIATION_PARTNER.value:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"success": False, "message": "權限不足"},
            )
        admin_association_id = user_payload.get("association_id")
        user_assoc_id = str(user.association_id) if user.association_id else None
        if user_assoc_id != str(admin_association_id):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"success": False, "message": "權限不足"},
            )
    else:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"success": False, "message": "權限不足"},
        )

    return JSONResponse(
        content={
            "success": True,
            "data": {
                "id": str(user.id),
                "username": user.username,
                "name": user.name,
                "role": user.role.value if hasattr(user.role, 'value') else user.role,
                "email": user.email,
                "phone": user.phone,
                "status": user.status.value if hasattr(user.status, 'value') else user.status,
                "lastLoginAt": user.last_login_at.isoformat() if user.last_login_at else None,
                "createdAt": user.created_at.isoformat(),
                "updatedAt": user.updated_at.isoformat(),
            },
        }
    )
