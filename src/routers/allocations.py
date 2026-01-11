# src/routers/allocations.py
# 點數配額路由

from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse

from src.db.models import AllocationCreate, UserRole, Status
from src.db.repositories import (
    AllocationRepository,
    HomelessPersonRepository,
    SystemConfigRepository,
)
from src.routers.auth import authenticate_token

router = APIRouter()

# Repository 實例
allocation_repo = AllocationRepository()
homeless_repo = HomelessPersonRepository()
config_repo = SystemConfigRepository()


@router.post("")
async def create_allocation(
    data: AllocationCreate,
    request: Request,
    user_payload: Dict[str, Any] = Depends(authenticate_token),
):
    """
    配發點數給街友。

    權限：system_admin, ngo_admin, ngo_partner
    """
    user_role = user_payload.get("role")
    allowed_roles = [
        UserRole.SYSTEM_ADMIN.value,
        UserRole.NGO_ADMIN.value,
        UserRole.NGO_PARTNER.value,
    ]
    if user_role not in allowed_roles:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"success": False, "message": "權限不足"},
        )

    # 檢查街友是否存在
    homeless = homeless_repo.get_by_id(data.homeless_id)
    if not homeless:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"success": False, "message": "找不到該街友"},
        )

    # 檢查街友狀態
    if homeless.status != Status.ACTIVE:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "message": "該街友帳戶已停用"},
        )

    # 取得系統設定的限額
    max_allocation_limit = config_repo.get_int("max_allocation_limit", 1000)
    max_balance_limit = config_repo.get_int("max_balance_limit", 10000)

    # 檢查單次配額上限
    if data.amount > max_allocation_limit:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "success": False,
                "message": f"單次配額不得超過 {max_allocation_limit} 點",
                "error": {
                    "code": "ALLOCATION_LIMIT_EXCEEDED",
                    "details": {"max_limit": max_allocation_limit, "requested": data.amount},
                },
            },
        )

    # 檢查配額後餘額是否超過上限
    balance_after = homeless.balance + data.amount
    if balance_after > max_balance_limit:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "success": False,
                "message": f"配額後餘額將超過上限 {max_balance_limit} 點",
                "error": {
                    "code": "BALANCE_LIMIT_EXCEEDED",
                    "details": {
                        "current_balance": homeless.balance,
                        "requested": data.amount,
                        "max_limit": max_balance_limit,
                    },
                },
            },
        )

    # 取得操作者 ID
    admin_id = UUID(user_payload.get("userId"))

    # 建立配額記錄並更新餘額
    allocation_id = uuid4()
    allocation = allocation_repo.create(
        allocation_id=allocation_id,
        homeless_id=data.homeless_id,
        admin_id=admin_id,
        amount=data.amount,
        balance_before=homeless.balance,
        balance_after=balance_after,
        notes=data.notes,
    )

    # 更新街友餘額
    homeless_repo.update_balance(data.homeless_id, balance_after)

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "success": True,
            "message": "點數配額成功",
            "data": {
                "id": str(allocation.id),
                "homeless_id": str(allocation.homeless_id),
                "amount": allocation.amount,
                "balance_before": allocation.balance_before,
                "balance_after": allocation.balance_after,
                "notes": allocation.notes,
                "created_at": allocation.created_at.isoformat(),
            },
        },
    )


@router.get("")
async def list_allocations(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    homeless_id: Optional[UUID] = None,
    user_payload: Dict[str, Any] = Depends(authenticate_token),
):
    """
    列出配額記錄。

    權限：system_admin, ngo_admin, ngo_partner
    """
    user_role = user_payload.get("role")
    allowed_roles = [
        UserRole.SYSTEM_ADMIN.value,
        UserRole.NGO_ADMIN.value,
        UserRole.NGO_PARTNER.value,
    ]
    if user_role not in allowed_roles:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"success": False, "message": "權限不足"},
        )

    if homeless_id:
        # 查詢特定街友的配額
        allocations, total = allocation_repo.list_by_homeless(
            homeless_id=homeless_id,
            page=page,
            limit=limit,
        )
    else:
        # 查詢所有配額
        allocations, total = allocation_repo.list_all(
            page=page,
            limit=limit,
        )

    total_pages = (total + limit - 1) // limit

    return JSONResponse(
        content={
            "success": True,
            "data": [
                {
                    "id": str(a.id),
                    "homeless_id": str(a.homeless_id),
                    "admin_id": str(a.admin_id),
                    "amount": a.amount,
                    "balance_before": a.balance_before,
                    "balance_after": a.balance_after,
                    "notes": a.notes,
                    "created_at": a.created_at.isoformat(),
                }
                for a in allocations
            ],
            "meta": {
                "page": page,
                "limit": limit,
                "total": total,
                "total_pages": total_pages,
            },
        }
    )
