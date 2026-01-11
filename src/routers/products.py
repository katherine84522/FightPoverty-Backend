# src/routers/products.py
# 產品管理路由

from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse

from src.db.models import (
    Product,
    ProductCreate,
    ProductUpdate,
    Status,
    UserRole,
)
from src.db.repositories import ProductRepository, StoreRepository
from src.routers.auth import authenticate_token

router = APIRouter()

# Repository 實例
product_repo = ProductRepository()
store_repo = StoreRepository()


# ─────────────────────────────────────────────────────────
# 商店產品 CRUD
# ─────────────────────────────────────────────────────────
@router.post("/stores/{store_id}/products")
async def create_product(
    store_id: UUID,
    data: ProductCreate,
    request: Request,
    user_payload: Dict[str, Any] = Depends(authenticate_token),
):
    """
    新增商店產品。

    權限：system_admin, store（只能新增自己商店的產品）
    """
    user_role = user_payload.get("role")

    # 商店角色只能新增自己商店的產品
    if user_role == UserRole.STORE.value:
        user_store_id = user_payload.get("store_id")
        if str(store_id) != str(user_store_id):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"success": False, "message": "權限不足"},
            )
    elif user_role != UserRole.SYSTEM_ADMIN.value:
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

    # 建立產品
    product_id = uuid4()
    product = product_repo.create(product_id, store_id, data)

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "success": True,
            "message": "產品建立成功",
            "data": {
                "id": str(product.id),
                "store_id": str(product.store_id),
                "name": product.name,
                "points": product.points,
                "category": product.category.value,
                "description": product.description,
                "status": product.status.value,
                "created_at": product.created_at.isoformat(),
            },
        },
    )


@router.get("/stores/{store_id}/products")
async def list_store_products(
    store_id: UUID,
    request: Request,
    status_filter: Optional[str] = Query(None, alias="status"),
    user_payload: Dict[str, Any] = Depends(authenticate_token),
):
    """
    列出商店的所有產品。

    權限：system_admin, store（只能看自己商店的）, 其他角色可看
    """
    user_role = user_payload.get("role")

    # 商店角色只能看自己商店的產品
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

    # 轉換狀態篩選
    status_enum = None
    if status_filter:
        try:
            status_enum = Status(status_filter)
        except ValueError:
            pass

    # 查詢
    products = product_repo.list_by_store(store_id, status_filter=status_enum)

    return JSONResponse(
        content={
            "success": True,
            "data": [
                {
                    "id": str(p.id),
                    "store_id": str(p.store_id),
                    "name": p.name,
                    "points": p.points,
                    "category": p.category.value,
                    "description": p.description,
                    "status": p.status.value,
                    "created_at": p.created_at.isoformat(),
                }
                for p in products
            ],
        }
    )


# ─────────────────────────────────────────────────────────
# 產品 CRUD（直接操作）
# ─────────────────────────────────────────────────────────
@router.get("/products/{product_id}")
async def get_product(
    product_id: UUID,
    request: Request,
    user_payload: Dict[str, Any] = Depends(authenticate_token),
):
    """
    取得單一產品詳細資料。
    """
    product = product_repo.get_by_id(product_id)
    if not product:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"success": False, "message": "找不到該產品"},
        )

    return JSONResponse(
        content={
            "success": True,
            "data": {
                "id": str(product.id),
                "store_id": str(product.store_id),
                "name": product.name,
                "points": product.points,
                "category": product.category.value,
                "description": product.description,
                "status": product.status.value,
                "created_at": product.created_at.isoformat(),
                "updated_at": product.updated_at.isoformat(),
            },
        }
    )


@router.patch("/products/{product_id}")
async def update_product(
    product_id: UUID,
    data: ProductUpdate,
    request: Request,
    user_payload: Dict[str, Any] = Depends(authenticate_token),
):
    """
    更新產品資料。

    權限：system_admin, store（只能更新自己商店的產品）
    """
    user_role = user_payload.get("role")

    # 檢查產品是否存在
    product = product_repo.get_by_id(product_id)
    if not product:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"success": False, "message": "找不到該產品"},
        )

    # 商店角色只能更新自己商店的產品
    if user_role == UserRole.STORE.value:
        user_store_id = user_payload.get("store_id")
        if str(product.store_id) != str(user_store_id):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"success": False, "message": "權限不足"},
            )
    elif user_role != UserRole.SYSTEM_ADMIN.value:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"success": False, "message": "權限不足"},
        )

    # 更新
    updates = data.model_dump(exclude_unset=True)
    if "status" in updates and updates["status"]:
        updates["status"] = updates["status"].value
    if "category" in updates and updates["category"]:
        updates["category"] = updates["category"].value

    updated = product_repo.update(product_id, updates)

    return JSONResponse(
        content={
            "success": True,
            "message": "產品資料已更新",
            "data": {
                "id": str(updated.id),
                "name": updated.name,
                "points": updated.points,
                "status": updated.status.value,
                "updated_at": updated.updated_at.isoformat(),
            },
        }
    )


@router.delete("/products/{product_id}")
async def delete_product(
    product_id: UUID,
    request: Request,
    user_payload: Dict[str, Any] = Depends(authenticate_token),
):
    """
    刪除產品（軟刪除）。

    權限：system_admin, store（只能刪除自己商店的產品）
    """
    user_role = user_payload.get("role")

    # 檢查產品是否存在
    product = product_repo.get_by_id(product_id)
    if not product:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"success": False, "message": "找不到該產品"},
        )

    # 商店角色只能刪除自己商店的產品
    if user_role == UserRole.STORE.value:
        user_store_id = user_payload.get("store_id")
        if str(product.store_id) != str(user_store_id):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"success": False, "message": "權限不足"},
            )
    elif user_role != UserRole.SYSTEM_ADMIN.value:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"success": False, "message": "權限不足"},
        )

    # 軟刪除
    product_repo.delete(product_id)

    return JSONResponse(
        content={"success": True, "message": "產品已停用"}
    )
