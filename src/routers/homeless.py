# src/routers/homeless.py
# 街友管理路由

from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse

from src.db.models import (
    HomelessPerson,
    HomelessPersonCreate,
    HomelessPersonUpdate,
    PaginationMeta,
    Status,
)
from src.db.repositories import HomelessPersonRepository
from src.routers.auth import authenticate_token
from src.utils.decorators import require_roles
from src.db.models import UserRole

router = APIRouter()

# Repository 實例
homeless_repo = HomelessPersonRepository()


# ─────────────────────────────────────────────────────────
# QR Code 查詢（公開 endpoint，用於交易）
# ─────────────────────────────────────────────────────────
@router.get("/qr/{qr_code}")
async def get_homeless_by_qr(qr_code: str):
    """
    透過 QR Code 取得街友資料。

    此 endpoint 用於商店掃描街友 QR Code 時使用，
    只返回交易所需的基本資訊。
    """
    homeless = homeless_repo.get_by_qr_code(qr_code)

    if not homeless:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "success": False,
                "message": "找不到該街友",
                "error": {"code": "HOMELESS_NOT_FOUND", "details": {"qr_code": qr_code}},
            },
        )

    # 檢查狀態
    if homeless.status != Status.ACTIVE:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "success": False,
                "message": "該街友帳戶已停用",
                "error": {"code": "HOMELESS_INACTIVE", "details": {"status": homeless.status.value}},
            },
        )

    return JSONResponse(
        content={
            "success": True,
            "data": {
                "id": str(homeless.id),
                "name": homeless.name,
                "qr_code": homeless.qr_code,
                "balance": homeless.balance,
                "status": homeless.status.value,
                "photo_url": homeless.photo_url,
            },
        }
    )


# ─────────────────────────────────────────────────────────
# CRUD Endpoints（需要認證）
# ─────────────────────────────────────────────────────────
@router.post("")
async def create_homeless(
    data: HomelessPersonCreate,
    request: Request,
    user_payload: Dict[str, Any] = Depends(authenticate_token),
):
    """
    新增街友。

    權限：system_admin, ngo_admin, ngo_partner
    """
    # 檢查角色權限
    user_role = user_payload.get("role")
    allowed_roles = [UserRole.SYSTEM_ADMIN.value, UserRole.NGO_ADMIN.value, UserRole.NGO_PARTNER.value]
    if user_role not in allowed_roles:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"success": False, "message": "權限不足"},
        )

    # 檢查身分證是否已存在
    existing = homeless_repo.get_by_id_number(data.id_number)
    if existing:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "success": False,
                "message": "該身分證字號已註冊",
                "error": {"code": "DUPLICATE_ID_NUMBER"},
            },
        )

    # 建立街友
    homeless_id = uuid4()
    homeless = homeless_repo.create(homeless_id, data)

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "success": True,
            "message": "街友建立成功",
            "data": {
                "id": str(homeless.id),
                "name": homeless.name,
                "id_number": homeless.id_number,
                "qr_code": homeless.qr_code,
                "balance": homeless.balance,
                "status": homeless.status.value,
                "created_at": homeless.created_at.isoformat(),
            },
        },
    )


@router.get("")
async def list_homeless(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = None,
    user_payload: Dict[str, Any] = Depends(authenticate_token),
):
    """
    列出街友（支援分頁、狀態篩選、搜尋）。

    權限：system_admin, ngo_admin, ngo_partner
    """
    # 檢查角色權限
    user_role = user_payload.get("role")
    allowed_roles = [UserRole.SYSTEM_ADMIN.value, UserRole.NGO_ADMIN.value, UserRole.NGO_PARTNER.value]
    if user_role not in allowed_roles:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"success": False, "message": "權限不足"},
        )

    # 轉換狀態篩選
    status_enum = None
    if status_filter:
        try:
            status_enum = Status(status_filter)
        except ValueError:
            pass

    # 查詢
    homeless_list, total = homeless_repo.list_all(
        page=page,
        limit=limit,
        status_filter=status_enum,
        search=search,
    )

    # 計算分頁資訊
    total_pages = (total + limit - 1) // limit

    return JSONResponse(
        content={
            "success": True,
            "data": [
                {
                    "id": str(h.id),
                    "name": h.name,
                    "id_number": h.id_number,
                    "qr_code": h.qr_code,
                    "balance": h.balance,
                    "phone": h.phone,
                    "address": h.address,
                    "emergency_contact": h.emergency_contact,
                    "emergency_phone": h.emergency_phone,
                    "notes": h.notes,
                    "status": h.status.value,
                    "created_at": h.created_at.isoformat(),
                }
                for h in homeless_list
            ],
            "meta": {
                "page": page,
                "limit": limit,
                "total": total,
                "total_pages": total_pages,
            },
        }
    )


@router.get("/{homeless_id}")
async def get_homeless(
    homeless_id: UUID,
    request: Request,
    user_payload: Dict[str, Any] = Depends(authenticate_token),
):
    """
    取得單一街友詳細資料。

    權限：system_admin, ngo_admin, ngo_partner
    """
    # 檢查角色權限
    user_role = user_payload.get("role")
    allowed_roles = [UserRole.SYSTEM_ADMIN.value, UserRole.NGO_ADMIN.value, UserRole.NGO_PARTNER.value]
    if user_role not in allowed_roles:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"success": False, "message": "權限不足"},
        )

    homeless = homeless_repo.get_by_id(homeless_id)
    if not homeless:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"success": False, "message": "找不到該街友"},
        )

    return JSONResponse(
        content={
            "success": True,
            "data": {
                "id": str(homeless.id),
                "name": homeless.name,
                "id_number": homeless.id_number,
                "qr_code": homeless.qr_code,
                "balance": homeless.balance,
                "phone": homeless.phone,
                "address": homeless.address,
                "emergency_contact": homeless.emergency_contact,
                "emergency_phone": homeless.emergency_phone,
                "notes": homeless.notes,
                "photo_url": homeless.photo_url,
                "status": homeless.status.value,
                "created_at": homeless.created_at.isoformat(),
                "updated_at": homeless.updated_at.isoformat(),
            },
        }
    )


@router.patch("/{homeless_id}")
async def update_homeless(
    homeless_id: UUID,
    data: HomelessPersonUpdate,
    request: Request,
    user_payload: Dict[str, Any] = Depends(authenticate_token),
):
    """
    更新街友資料。

    權限：system_admin, ngo_admin, ngo_partner
    """
    # 檢查角色權限
    user_role = user_payload.get("role")
    allowed_roles = [UserRole.SYSTEM_ADMIN.value, UserRole.NGO_ADMIN.value, UserRole.NGO_PARTNER.value]
    if user_role not in allowed_roles:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"success": False, "message": "權限不足"},
        )

    # 檢查街友是否存在
    homeless = homeless_repo.get_by_id(homeless_id)
    if not homeless:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"success": False, "message": "找不到該街友"},
        )

    # 更新
    updates = data.model_dump(exclude_unset=True)
    if "status" in updates and updates["status"]:
        updates["status"] = updates["status"].value

    updated = homeless_repo.update(homeless_id, updates)

    return JSONResponse(
        content={
            "success": True,
            "message": "街友資料已更新",
            "data": {
                "id": str(updated.id),
                "name": updated.name,
                "status": updated.status.value,
                "updated_at": updated.updated_at.isoformat(),
            },
        }
    )


@router.delete("/{homeless_id}")
async def delete_homeless(
    homeless_id: UUID,
    request: Request,
    user_payload: Dict[str, Any] = Depends(authenticate_token),
):
    """
    刪除街友（軟刪除：設為 inactive）。

    權限：system_admin, ngo_admin
    """
    # 檢查角色權限
    user_role = user_payload.get("role")
    allowed_roles = [UserRole.SYSTEM_ADMIN.value, UserRole.NGO_ADMIN.value]
    if user_role not in allowed_roles:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"success": False, "message": "權限不足"},
        )

    # 檢查街友是否存在
    homeless = homeless_repo.get_by_id(homeless_id)
    if not homeless:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"success": False, "message": "找不到該街友"},
        )

    # 軟刪除
    homeless_repo.delete(homeless_id)

    return JSONResponse(
        content={"success": True, "message": "街友已停用"}
    )


@router.post("/{homeless_id}/reissue-qr")
async def reissue_qr_code(
    homeless_id: UUID,
    request: Request,
    user_payload: Dict[str, Any] = Depends(authenticate_token),
):
    """
    重新發放 QR Code。

    權限：system_admin, ngo_admin
    """
    # 檢查角色權限
    user_role = user_payload.get("role")
    allowed_roles = [UserRole.SYSTEM_ADMIN.value, UserRole.NGO_ADMIN.value]
    if user_role not in allowed_roles:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"success": False, "message": "權限不足"},
        )

    # 重新發放
    new_qr_code = homeless_repo.reissue_qr_code(homeless_id)
    if not new_qr_code:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"success": False, "message": "找不到該街友"},
        )

    return JSONResponse(
        content={
            "success": True,
            "message": "QR Code 已重新發放",
            "data": {"qr_code": new_qr_code},
        }
    )
