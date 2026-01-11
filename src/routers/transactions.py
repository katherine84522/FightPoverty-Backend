# src/routers/transactions.py
# 交易路由

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse

from src.db.models import TransactionCreate, UserRole
from src.db.repositories import TransactionRepository, HomelessPersonRepository, StoreRepository
from src.routers.auth import authenticate_token
from src.services.transaction_service import (
    TransactionService,
    TransactionError,
    InsufficientBalanceError,
    HomelessNotFoundError,
    StoreNotFoundError,
    HomelessInactiveError,
    StoreInactiveError,
    ProductInactiveError,
    TransactionLockError,
)

router = APIRouter()

# Service 實例
transaction_service = TransactionService()
transaction_repo = TransactionRepository()
homeless_repo = HomelessPersonRepository()
store_repo = StoreRepository()


# ─────────────────────────────────────────────────────────
# 建立交易
# ─────────────────────────────────────────────────────────
@router.post("")
async def create_transaction(
    data: TransactionCreate,
    request: Request,
    user_payload: Dict[str, Any] = Depends(authenticate_token),
):
    """
    建立交易。

    權限：store 角色
    """
    user_role = user_payload.get("role")

    # 只有商店角色可以發起交易
    if user_role != UserRole.STORE.value:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"success": False, "message": "只有商店可以發起交易"},
        )

    try:
        transaction = transaction_service.create_transaction(data)

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={
                "success": True,
                "message": "交易成功",
                "data": {
                    "id": str(transaction.id),
                    "homeless_id": str(transaction.homeless_id),
                    "store_id": str(transaction.store_id),
                    "product_name": transaction.product_name,
                    "amount": transaction.amount,
                    "balance_before": transaction.balance_before,
                    "balance_after": transaction.balance_after,
                    "status": transaction.status.value,
                    "created_at": transaction.created_at.isoformat(),
                },
            },
        )

    except InsufficientBalanceError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "success": False,
                "message": e.message,
                "error": {"code": e.code, "details": e.details},
            },
        )

    except HomelessNotFoundError as e:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "success": False,
                "message": e.message,
                "error": {"code": e.code, "details": e.details},
            },
        )

    except StoreNotFoundError as e:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "success": False,
                "message": e.message,
                "error": {"code": e.code, "details": e.details},
            },
        )

    except HomelessInactiveError as e:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "success": False,
                "message": e.message,
                "error": {"code": e.code, "details": e.details},
            },
        )

    except StoreInactiveError as e:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "success": False,
                "message": e.message,
                "error": {"code": e.code, "details": e.details},
            },
        )

    except ProductInactiveError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "success": False,
                "message": e.message,
                "error": {"code": e.code, "details": e.details},
            },
        )

    except TransactionLockError as e:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "success": False,
                "message": e.message,
                "error": {"code": e.code, "details": e.details},
            },
        )

    except TransactionError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "success": False,
                "message": e.message,
                "error": {"code": e.code, "details": e.details},
            },
        )


# ─────────────────────────────────────────────────────────
# 取得單筆交易
# ─────────────────────────────────────────────────────────
@router.get("/{transaction_id}")
async def get_transaction(
    transaction_id: UUID,
    request: Request,
    user_payload: Dict[str, Any] = Depends(authenticate_token),
):
    """
    取得單筆交易記錄。

    權限：system_admin, ngo_admin, store（只能看自己商店的）
    """
    user_role = user_payload.get("role")

    transaction = transaction_repo.get_by_id(transaction_id)
    if not transaction:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"success": False, "message": "找不到該交易記錄"},
        )

    # 商店只能看自己商店的交易
    if user_role == UserRole.STORE.value:
        user_store_id = user_payload.get("store_id")
        if str(transaction.store_id) != str(user_store_id):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"success": False, "message": "權限不足"},
            )

    return JSONResponse(
        content={
            "success": True,
            "data": {
                "id": str(transaction.id),
                "homeless_id": str(transaction.homeless_id),
                "homeless_qr_code": transaction.homeless_qr_code,
                "store_id": str(transaction.store_id),
                "store_qr_code": transaction.store_qr_code,
                "product_id": str(transaction.product_id) if transaction.product_id else None,
                "product_name": transaction.product_name,
                "amount": transaction.amount,
                "balance_before": transaction.balance_before,
                "balance_after": transaction.balance_after,
                "status": transaction.status.value,
                "created_at": transaction.created_at.isoformat(),
            },
        }
    )


# ─────────────────────────────────────────────────────────
# 列出交易記錄
# ─────────────────────────────────────────────────────────
@router.get("")
async def list_transactions(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    homeless_id: Optional[UUID] = None,
    store_id: Optional[UUID] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user_payload: Dict[str, Any] = Depends(authenticate_token),
):
    """
    列出交易記錄。

    權限：
    - system_admin, ngo_admin: 可看所有交易
    - store: 只能看自己商店的交易
    - homeless: 只能看自己的交易
    """
    user_role = user_payload.get("role")

    # 解析日期
    start_datetime = None
    end_datetime = None
    if start_date:
        try:
            start_datetime = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        except ValueError:
            try:
                start_datetime = datetime.strptime(start_date, "%Y-%m-%d")
            except ValueError:
                pass
    if end_date:
        try:
            end_datetime = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        except ValueError:
            try:
                end_datetime = datetime.strptime(end_date, "%Y-%m-%d")
                # 設為當天結束
                end_datetime = end_datetime.replace(hour=23, minute=59, second=59)
            except ValueError:
                pass

    # 根據角色決定查詢範圍
    if user_role == UserRole.STORE.value:
        # 商店只能看自己的交易
        user_store_id = user_payload.get("store_id")
        if user_store_id:
            store_id = UUID(user_store_id) if isinstance(user_store_id, str) else user_store_id
        transactions, total = transaction_repo.list_by_store(
            store_id=store_id,
            page=page,
            limit=limit,
            start_date=start_datetime,
            end_date=end_datetime,
        )
    elif user_role == UserRole.HOMELESS.value:
        # 街友只能看自己的交易
        user_homeless_id = user_payload.get("homeless_id")
        if user_homeless_id:
            homeless_id = UUID(user_homeless_id) if isinstance(user_homeless_id, str) else user_homeless_id
        transactions, total = transaction_repo.list_by_homeless(
            homeless_id=homeless_id,
            page=page,
            limit=limit,
            start_date=start_datetime,
            end_date=end_datetime,
        )
    elif homeless_id:
        # 查詢特定街友的交易
        transactions, total = transaction_repo.list_by_homeless(
            homeless_id=homeless_id,
            page=page,
            limit=limit,
            start_date=start_datetime,
            end_date=end_datetime,
        )
    elif store_id:
        # 查詢特定商店的交易
        transactions, total = transaction_repo.list_by_store(
            store_id=store_id,
            page=page,
            limit=limit,
            start_date=start_datetime,
            end_date=end_datetime,
        )
    else:
        # 管理員可以看所有交易
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
        transactions, total = transaction_repo.list_all(
            page=page,
            limit=limit,
            start_date=start_datetime,
            end_date=end_datetime,
        )

    total_pages = (total + limit - 1) // limit

    # 批量獲取店家和街友名稱（避免 N+1 查詢問題）
    store_names: dict[str, str] = {}
    homeless_names: dict[str, str] = {}
    for tx in transactions:
        if str(tx.store_id) not in store_names:
            store = store_repo.get_by_id(tx.store_id)
            store_names[str(tx.store_id)] = store.name if store else "商店"
        if str(tx.homeless_id) not in homeless_names:
            homeless = homeless_repo.get_by_id(tx.homeless_id)
            homeless_names[str(tx.homeless_id)] = homeless.name if homeless else "街友"

    return JSONResponse(
        content={
            "success": True,
            "data": [
                {
                    "id": str(tx.id),
                    "homeless_id": str(tx.homeless_id),
                    "homeless_name": homeless_names.get(str(tx.homeless_id), "街友"),
                    "store_id": str(tx.store_id),
                    "store_name": store_names.get(str(tx.store_id), "商店"),
                    "product_name": tx.product_name,
                    "amount": tx.amount,
                    "balance_before": tx.balance_before,
                    "balance_after": tx.balance_after,
                    "status": tx.status.value,
                    "created_at": tx.created_at.isoformat(),
                }
                for tx in transactions
            ],
            "meta": {
                "page": page,
                "limit": limit,
                "total": total,
                "total_pages": total_pages,
            },
        }
    )
