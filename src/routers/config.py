# src/routers/config.py
# 系統設定路由

from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from src.db.models import SystemConfigUpdate, UserRole
from src.db.repositories import SystemConfigRepository
from src.routers.auth import authenticate_token

router = APIRouter()

# Repository 實例
config_repo = SystemConfigRepository()


@router.get("")
async def list_configs(
    request: Request,
    user_payload: Dict[str, Any] = Depends(authenticate_token),
):
    """
    列出所有系統設定。

    權限：system_admin, ngo_admin
    """
    user_role = user_payload.get("role")
    allowed_roles = [UserRole.SYSTEM_ADMIN.value, UserRole.NGO_ADMIN.value]
    if user_role not in allowed_roles:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"success": False, "message": "權限不足"},
        )

    configs = config_repo.list_all()

    return JSONResponse(
        content={
            "success": True,
            "data": [
                {
                    "key": c.key,
                    "value": c.value,
                    "description": c.description,
                    "updated_by": str(c.updated_by) if c.updated_by else None,
                    "updated_at": c.updated_at.isoformat(),
                }
                for c in configs
            ],
        }
    )


@router.get("/{config_key}")
async def get_config(
    config_key: str,
    request: Request,
    user_payload: Dict[str, Any] = Depends(authenticate_token),
):
    """
    取得單一系統設定。

    權限：system_admin, ngo_admin
    """
    user_role = user_payload.get("role")
    allowed_roles = [UserRole.SYSTEM_ADMIN.value, UserRole.NGO_ADMIN.value]
    if user_role not in allowed_roles:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"success": False, "message": "權限不足"},
        )

    config = config_repo.get(config_key)
    if not config:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"success": False, "message": "找不到該設定"},
        )

    return JSONResponse(
        content={
            "success": True,
            "data": {
                "key": config.key,
                "value": config.value,
                "description": config.description,
                "updated_by": str(config.updated_by) if config.updated_by else None,
                "updated_at": config.updated_at.isoformat(),
            },
        }
    )


@router.patch("/{config_key}")
async def update_config(
    config_key: str,
    data: SystemConfigUpdate,
    request: Request,
    user_payload: Dict[str, Any] = Depends(authenticate_token),
):
    """
    更新系統設定。

    權限：system_admin, ngo_admin
    """
    user_role = user_payload.get("role")
    allowed_roles = [UserRole.SYSTEM_ADMIN.value, UserRole.NGO_ADMIN.value]
    if user_role not in allowed_roles:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"success": False, "message": "權限不足"},
        )

    # 取得操作者 ID
    updated_by = UUID(user_payload.get("userId"))

    # 更新設定
    config = config_repo.set(
        config_key=config_key,
        value=data.value,
        description=data.description,
        updated_by=updated_by,
    )

    return JSONResponse(
        content={
            "success": True,
            "message": "設定已更新",
            "data": {
                "key": config.key,
                "value": config.value,
                "description": config.description,
                "updated_by": str(config.updated_by) if config.updated_by else None,
                "updated_at": config.updated_at.isoformat(),
            },
        }
    )
