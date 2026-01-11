# src/routers/stores.py
# 商店管理路由

from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse

from src.db.models import (
    Store,
    StoreCreate,
    StoreUpdate,
    Status,
    UserRole,
)
from src.db.repositories import StoreRepository, ProductRepository, TransactionRepository
from src.routers.auth import authenticate_token

router = APIRouter()

# Repository 實例
store_repo = StoreRepository()
product_repo = ProductRepository()
transaction_repo = TransactionRepository()


# ─────────────────────────────────────────────────────────
# CRUD Endpoints（需要認證）
# ─────────────────────────────────────────────────────────
@router.post("")
async def create_store(
    data: StoreCreate,
    request: Request,
    user_payload: Dict[str, Any] = Depends(authenticate_token),
):
    """
    新增商店。

    權限：system_admin, association_admin
    """
    user_role = user_payload.get("role")
    allowed_roles = [UserRole.SYSTEM_ADMIN.value, UserRole.ASSOCIATION_ADMIN.value]
    if user_role not in allowed_roles:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"success": False, "message": "權限不足"},
        )

    # 建立商店
    store_id = uuid4()
    store = store_repo.create(store_id, data)

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "success": True,
            "message": "商店建立成功",
            "data": {
                "id": str(store.id),
                "name": store.name,
                "qr_code": store.qr_code,
                "category": store.category,
                "status": store.status.value,
                "created_at": store.created_at.isoformat(),
            },
        },
    )


@router.get("")
async def list_stores(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    association_id: Optional[UUID] = None,
    user_payload: Dict[str, Any] = Depends(authenticate_token),
):
    """
    列出商店（支援分頁、狀態篩選、商圈篩選）。

    權限：system_admin, ngo_admin, store（只能看自己的）, association_admin, association_partner
    """
    user_role = user_payload.get("role")

    # 商店角色只能看自己的商店
    if user_role == UserRole.STORE.value:
        user_store_id = user_payload.get("store_id")
        if user_store_id:
            store = store_repo.get_by_id(user_store_id)
            if store:
                return JSONResponse(
                    content={
                        "success": True,
                        "data": [
                            {
                                "id": str(store.id),
                                "name": store.name,
                                "qr_code": store.qr_code,
                                "category": store.category,
                                "address": store.address,
                                "phone": store.phone,
                                "total_income": store.total_income,
                                "status": store.status.value,
                                "created_at": store.created_at.isoformat(),
                            }
                        ],
                        "meta": {"page": 1, "limit": 1, "total": 1, "total_pages": 1},
                    }
                )
        return JSONResponse(
            content={
                "success": True,
                "data": [],
                "meta": {"page": 1, "limit": limit, "total": 0, "total_pages": 0},
            }
        )

    # 其他角色
    allowed_roles = [
        UserRole.SYSTEM_ADMIN.value,
        UserRole.NGO_ADMIN.value,
        UserRole.ASSOCIATION_ADMIN.value,
        UserRole.ASSOCIATION_PARTNER.value,
    ]
    if user_role not in allowed_roles:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"success": False, "message": "權限不足"},
        )

    # 商圈角色只能看自己商圈的商店
    if user_role in [UserRole.ASSOCIATION_ADMIN.value, UserRole.ASSOCIATION_PARTNER.value]:
        user_association_id = user_payload.get("association_id")
        if user_association_id:
            association_id = UUID(user_association_id) if isinstance(user_association_id, str) else user_association_id

    # 轉換狀態篩選
    status_enum = None
    if status_filter:
        try:
            status_enum = Status(status_filter)
        except ValueError:
            pass

    # 查詢
    stores_list, total = store_repo.list_all(
        page=page,
        limit=limit,
        status_filter=status_enum,
        association_id=association_id,
    )

    total_pages = (total + limit - 1) // limit

    # 取得每個商店的交易數量
    store_tx_counts: dict[str, int] = {}
    for s in stores_list:
        _, tx_count = transaction_repo.list_by_store(s.id, page=1, limit=1)
        store_tx_counts[str(s.id)] = tx_count

    return JSONResponse(
        content={
            "success": True,
            "data": [
                {
                    "id": str(s.id),
                    "name": s.name,
                    "qr_code": s.qr_code,
                    "category": s.category,
                    "address": s.address,
                    "phone": s.phone,
                    "total_income": s.total_income,
                    "transaction_count": store_tx_counts.get(str(s.id), 0),
                    "status": s.status.value,
                    "association_id": str(s.association_id) if s.association_id else None,
                    "created_at": s.created_at.isoformat(),
                }
                for s in stores_list
            ],
            "meta": {
                "page": page,
                "limit": limit,
                "total": total,
                "total_pages": total_pages,
            },
        }
    )


@router.get("/{store_id}")
async def get_store(
    store_id: UUID,
    request: Request,
    user_payload: Dict[str, Any] = Depends(authenticate_token),
):
    """
    取得單一商店詳細資料。

    權限：system_admin, store（只能看自己的）, association_admin, association_partner
    """
    user_role = user_payload.get("role")

    # 商店角色只能看自己的商店
    if user_role == UserRole.STORE.value:
        user_store_id = user_payload.get("store_id")
        if str(store_id) != str(user_store_id):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"success": False, "message": "權限不足"},
            )

    store = store_repo.get_by_id(store_id)
    if not store:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"success": False, "message": "找不到該商店"},
        )

    # 取得產品列表
    products = product_repo.list_by_store(store_id)

    return JSONResponse(
        content={
            "success": True,
            "data": {
                "id": str(store.id),
                "name": store.name,
                "qr_code": store.qr_code,
                "category": store.category,
                "address": store.address,
                "phone": store.phone,
                "total_income": store.total_income,
                "status": store.status.value,
                "association_id": str(store.association_id) if store.association_id else None,
                "created_at": store.created_at.isoformat(),
                "updated_at": store.updated_at.isoformat(),
                "products": [
                    {
                        "id": str(p.id),
                        "name": p.name,
                        "points": p.points,
                        "category": p.category.value,
                        "status": p.status.value,
                    }
                    for p in products
                ],
            },
        }
    )


@router.patch("/{store_id}")
async def update_store(
    store_id: UUID,
    data: StoreUpdate,
    request: Request,
    user_payload: Dict[str, Any] = Depends(authenticate_token),
):
    """
    更新商店資料。

    權限：system_admin, store（只能更新自己的）, association_admin
    """
    user_role = user_payload.get("role")

    # 商店角色只能更新自己的商店
    if user_role == UserRole.STORE.value:
        user_store_id = user_payload.get("store_id")
        if str(store_id) != str(user_store_id):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"success": False, "message": "權限不足"},
            )

    # 檢查商店是否存在
    store = store_repo.get_by_id(store_id)
    if not store:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"success": False, "message": "找不到該商店"},
        )

    # 更新
    updates = data.model_dump(exclude_unset=True)
    if "status" in updates and updates["status"]:
        updates["status"] = updates["status"].value
    if "association_id" in updates and updates["association_id"]:
        updates["association_id"] = str(updates["association_id"])

    updated = store_repo.update(store_id, updates)

    return JSONResponse(
        content={
            "success": True,
            "message": "商店資料已更新",
            "data": {
                "id": str(updated.id),
                "name": updated.name,
                "status": updated.status.value,
                "updated_at": updated.updated_at.isoformat(),
            },
        }
    )
