# src/routers/reports.py
# 報表路由

import csv
import io
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from src.db.models import UserRole
from src.db.repositories import (
    TransactionRepository,
    AllocationRepository,
    HomelessPersonRepository,
    StoreRepository,
)
from src.routers.auth import authenticate_token

router = APIRouter()

# Repository 實例
transaction_repo = TransactionRepository()
allocation_repo = AllocationRepository()
homeless_repo = HomelessPersonRepository()
store_repo = StoreRepository()


@router.get("/summary")
async def get_summary_report(
    request: Request,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user_payload: Dict[str, Any] = Depends(authenticate_token),
):
    """
    取得統計摘要報表。

    權限：system_admin, ngo_admin, association_admin, association_partner
    """
    user_role = user_payload.get("role")
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

    # 解析日期
    start_datetime = None
    end_datetime = None
    if start_date:
        try:
            start_datetime = datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError:
            pass
    if end_date:
        try:
            end_datetime = datetime.strptime(end_date, "%Y-%m-%d")
            end_datetime = end_datetime.replace(hour=23, minute=59, second=59)
        except ValueError:
            pass

    # 取得交易統計
    transactions, total_transactions = transaction_repo.list_all(
        page=1,
        limit=10000,  # 取得所有交易用於統計
        start_date=start_datetime,
        end_date=end_datetime,
    )

    total_amount = sum(tx.amount for tx in transactions)
    completed_count = len([tx for tx in transactions if tx.status.value == "completed"])

    # 取得配額統計
    allocations, total_allocations = allocation_repo.list_all(
        page=1,
        limit=10000,
        start_date=start_datetime,
        end_date=end_datetime,
    )

    total_allocated = sum(a.amount for a in allocations)

    # 取得街友統計
    homeless_list, total_homeless = homeless_repo.list_all(page=1, limit=10000)
    active_homeless = len([h for h in homeless_list if h.status.value == "active"])
    total_balance = sum(h.balance for h in homeless_list)

    # 取得商店統計
    stores_list, total_stores = store_repo.list_all(page=1, limit=10000)
    active_stores = len([s for s in stores_list if s.status.value == "active"])
    total_income = sum(s.total_income for s in stores_list)

    return JSONResponse(
        content={
            "success": True,
            "data": {
                "period": {
                    "start_date": start_date,
                    "end_date": end_date,
                },
                "transactions": {
                    "total_count": total_transactions,
                    "completed_count": completed_count,
                    "total_amount": total_amount,
                },
                "allocations": {
                    "total_count": total_allocations,
                    "total_amount": total_allocated,
                },
                "homeless": {
                    "total_count": total_homeless,
                    "active_count": active_homeless,
                    "total_balance": total_balance,
                },
                "stores": {
                    "total_count": total_stores,
                    "active_count": active_stores,
                    "total_income": total_income,
                },
            },
        }
    )


@router.get("/store/{store_id}")
async def get_store_report(
    store_id: UUID,
    request: Request,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user_payload: Dict[str, Any] = Depends(authenticate_token),
):
    """
    取得商店報表。

    權限：system_admin, store（只能看自己的）, association_admin, association_partner
    """
    user_role = user_payload.get("role")

    # 商店只能看自己的報表
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

    # 解析日期
    start_datetime = None
    end_datetime = None
    if start_date:
        try:
            start_datetime = datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError:
            pass
    if end_date:
        try:
            end_datetime = datetime.strptime(end_date, "%Y-%m-%d")
            end_datetime = end_datetime.replace(hour=23, minute=59, second=59)
        except ValueError:
            pass

    # 取得商店交易
    transactions, total = transaction_repo.list_by_store(
        store_id=store_id,
        page=1,
        limit=10000,
        start_date=start_datetime,
        end_date=end_datetime,
    )

    total_amount = sum(tx.amount for tx in transactions)

    # 按日期分組統計
    daily_stats: Dict[str, Dict[str, Any]] = {}
    for tx in transactions:
        date_key = tx.created_at.strftime("%Y-%m-%d")
        if date_key not in daily_stats:
            daily_stats[date_key] = {"count": 0, "amount": 0}
        daily_stats[date_key]["count"] += 1
        daily_stats[date_key]["amount"] += tx.amount

    return JSONResponse(
        content={
            "success": True,
            "data": {
                "store": {
                    "id": str(store.id),
                    "name": store.name,
                    "total_income": store.total_income,
                },
                "period": {
                    "start_date": start_date,
                    "end_date": end_date,
                },
                "summary": {
                    "total_transactions": total,
                    "total_amount": total_amount,
                },
                "daily": [
                    {"date": date, "count": stats["count"], "amount": stats["amount"]}
                    for date, stats in sorted(daily_stats.items(), reverse=True)
                ],
            },
        }
    )


@router.get("/export")
async def export_report(
    request: Request,
    type: str = Query(..., description="報表類型：transactions, allocations, homeless, stores"),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user_payload: Dict[str, Any] = Depends(authenticate_token),
):
    """
    匯出報表為 CSV。

    權限：system_admin, ngo_admin, store（只能匯出自己的交易）,
          association_admin, association_partner（只能匯出交易）
    """
    user_role = user_payload.get("role")
    allowed_roles = [
        UserRole.SYSTEM_ADMIN.value,
        UserRole.NGO_ADMIN.value,
        UserRole.STORE.value,
        UserRole.ASSOCIATION_ADMIN.value,
        UserRole.ASSOCIATION_PARTNER.value,
    ]
    if user_role not in allowed_roles:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"success": False, "message": "權限不足"},
        )

    # 店家和商圈角色只能匯出交易記錄
    limited_roles = [
        UserRole.STORE.value,
        UserRole.ASSOCIATION_ADMIN.value,
        UserRole.ASSOCIATION_PARTNER.value,
    ]
    if user_role in limited_roles and type != "transactions":
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"success": False, "message": "只能匯出交易記錄"},
        )

    # 解析日期
    start_datetime = None
    end_datetime = None
    if start_date:
        try:
            start_datetime = datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError:
            pass
    if end_date:
        try:
            end_datetime = datetime.strptime(end_date, "%Y-%m-%d")
            end_datetime = end_datetime.replace(hour=23, minute=59, second=59)
        except ValueError:
            pass

    # 根據類型生成 CSV
    output = io.StringIO()
    output.write("\ufeff")  # UTF-8 BOM for Excel

    if type == "transactions":
        # 店家只能匯出自己的交易
        if user_role == UserRole.STORE.value:
            user_store_id = user_payload.get("store_id")
            if not user_store_id:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={"success": False, "message": "找不到商店資訊"},
                )
            transactions, _ = transaction_repo.list_by_store(
                store_id=UUID(user_store_id),
                page=1,
                limit=10000,
                start_date=start_datetime,
                end_date=end_datetime,
            )
        else:
            transactions, _ = transaction_repo.list_all(
                page=1,
                limit=10000,
                start_date=start_datetime,
                end_date=end_datetime,
            )
        writer = csv.writer(output)
        writer.writerow([
            "交易ID", "街友ID", "商店ID", "產品名稱", "金額",
            "交易前餘額", "交易後餘額", "狀態", "交易時間"
        ])
        for tx in transactions:
            writer.writerow([
                str(tx.id),
                str(tx.homeless_id),
                str(tx.store_id),
                tx.product_name,
                tx.amount,
                tx.balance_before,
                tx.balance_after,
                tx.status.value,
                tx.created_at.isoformat(),
            ])
        filename = "transactions.csv"

    elif type == "allocations":
        allocations, _ = allocation_repo.list_all(
            page=1,
            limit=10000,
            start_date=start_datetime,
            end_date=end_datetime,
        )
        writer = csv.writer(output)
        writer.writerow([
            "配額ID", "街友ID", "管理員ID", "金額",
            "配額前餘額", "配額後餘額", "備註", "配額時間"
        ])
        for a in allocations:
            writer.writerow([
                str(a.id),
                str(a.homeless_id),
                str(a.admin_id),
                a.amount,
                a.balance_before,
                a.balance_after,
                a.notes or "",
                a.created_at.isoformat(),
            ])
        filename = "allocations.csv"

    elif type == "homeless":
        homeless_list, _ = homeless_repo.list_all(page=1, limit=10000)
        writer = csv.writer(output)
        writer.writerow([
            "街友ID", "姓名", "身分證字號", "QR Code", "餘額",
            "電話", "地址", "狀態", "建立時間"
        ])
        for h in homeless_list:
            writer.writerow([
                str(h.id),
                h.name,
                h.id_number,
                h.qr_code,
                h.balance,
                h.phone or "",
                h.address or "",
                h.status.value,
                h.created_at.isoformat(),
            ])
        filename = "homeless.csv"

    elif type == "stores":
        stores_list, _ = store_repo.list_all(page=1, limit=10000)
        writer = csv.writer(output)
        writer.writerow([
            "商店ID", "名稱", "QR Code", "類別", "地址",
            "電話", "累計收入", "狀態", "建立時間"
        ])
        for s in stores_list:
            writer.writerow([
                str(s.id),
                s.name,
                s.qr_code,
                s.category or "",
                s.address or "",
                s.phone or "",
                s.total_income,
                s.status.value,
                s.created_at.isoformat(),
            ])
        filename = "stores.csv"

    else:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "success": False,
                "message": "不支援的報表類型，支援類型：transactions, allocations, homeless, stores",
            },
        )

    # 返回 CSV 檔案
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
