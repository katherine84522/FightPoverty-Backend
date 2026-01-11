
import os
from dotenv import load_dotenv

from typing import Any, Dict

from fastapi import APIRouter, Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse

from src.utils.jwt_manager import JWTManager
from src.utils.schemas import LoginRequest
from src.db.controller import (
    get_user_by_username,
    get_user_by_id,
    verify_password,
    get_user_info,
)

router = APIRouter()

load_dotenv()

# ----------------------------------------------------------------------
# JWT Manager 設定
# ----------------------------------------------------------------------
# JWT 設定（更新過期時間：access 60分鐘，refresh 60天）
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "DEFAULT_SECRET_KEY")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_ACCESS_EXPIRY_MINUTES = int(os.getenv("JWT_ACCESS_EXPIRY_MINUTES", 60))  # 1 小時
JWT_REFRESH_EXPIRY_DAYS = int(os.getenv("JWT_REFRESH_EXPIRY_DAYS", 60))  # 60 天（2 個月）

jwt_manager = JWTManager(
    secret_key=JWT_SECRET_KEY,
    algorithm=JWT_ALGORITHM,
    access_expire_minutes=JWT_ACCESS_EXPIRY_MINUTES,
    refresh_expire_days=JWT_REFRESH_EXPIRY_DAYS,
    access_cookie_name="accessToken",   # 跟 Express 版一致
    refresh_cookie_name="refreshToken", # 跟 Express 版一致
)


# Middlewares / Helpers
# ------------------------------
def authenticate_token(request: Request) -> Dict[str, Any]:
    """
    取 Access Token，失敗 → 401
    """
    return jwt_manager.get_user_from_cookie(request)


# ----------------------------------------------------------------------
# 登入：POST /login
# ----------------------------------------------------------------------
@router.post("/login")
async def login(request: LoginRequest):
    usrname = request.username
    password = request.password
    role = request.role

    # 驗證輸入
    if not all([usrname, password, role]):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "message": "請提供完整的登入資訊"},
        )

    # 驗證使用者
    user = await get_user_by_username(usrname)
    # 安全：避免 user 存在與否被探測
    if (not user) or (not await verify_password(password, user.get("password", ""))):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"success": False, "message": "帳號或密碼錯誤"},
        )

    # 驗證角色
    if user.get("role") != role:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"success": False, "message": "角色不符"},
        )

    # 準備 token payload（包含關聯 ID 以便權限檢查）
    user_info_for_token = {
        "id": user.get("id"),
        "role": user.get("role"),
    }
    # 加入關聯 ID
    if user.get("store_id"):
        user_info_for_token["store_id"] = user.get("store_id")
    if user.get("homeless_id"):
        user_info_for_token["homeless_id"] = user.get("homeless_id")
    if user.get("association_id"):
        user_info_for_token["association_id"] = user.get("association_id")

    # 生成 tokens
    access_token = jwt_manager.create_access_token(user_info_for_token)
    refresh_token = jwt_manager.create_refresh_token(user_info_for_token)

    # 設定 cookies
    response = JSONResponse(
        content={
            "success": True,
            "message": "登入成功",
            "user": await get_user_info(user),
        }
    )
    jwt_manager.set_auth_cookies(response, access_token, refresh_token)
    return response


# =========================================================
# 登出 API：POST /logout
# =========================================================
@router.post("/logout")
async def logout() -> JSONResponse:
    response = JSONResponse(
        content={"success": True, "message": "登出成功"}
    )
    jwt_manager.clear_auth_cookies(response)
    return response


# =========================================================
# Refresh Token API：POST /refresh
# =========================================================
@router.post("/refresh")
async def refresh(request: Request) -> JSONResponse:
    try:
        refresh_payload = jwt_manager.get_refresh_payload_from_cookie(request)
    except HTTPException:
        # refresh token 不存在 / 過期 / 無效
        response = JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"success": False, "message": "未提供或無效的 refresh token"},
        )
        jwt_manager.clear_auth_cookies(response)
        return response

    user_id = refresh_payload.get("userId")
    if not user_id:
        response = JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"success": False, "message": "無效 refresh token（缺少 userId）"},
        )
        jwt_manager.clear_auth_cookies(response)
        return response

    # 查找用戶
    user = await get_user_by_id(user_id)
    if not user:
        response = JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"success": False, "message": "用戶不存在"},
        )
        jwt_manager.clear_auth_cookies(response)
        return response

    # 生成新 access token（包含關聯 ID 以便權限檢查）
    user_info_for_token = {
        "id": user.get("id"),
        "role": user.get("role"),
    }
    # 加入關聯 ID
    if user.get("store_id"):
        user_info_for_token["store_id"] = user.get("store_id")
    if user.get("homeless_id"):
        user_info_for_token["homeless_id"] = user.get("homeless_id")
    if user.get("association_id"):
        user_info_for_token["association_id"] = user.get("association_id")

    new_access = jwt_manager.create_access_token(user_info_for_token)

    # 設 cookie
    response = JSONResponse(
        content={"success": True, "message": "Token 已刷新"}
    )
    response.set_cookie(
        key=jwt_manager.access_cookie_name,
        value=new_access,
        httponly=True,
        max_age=jwt_manager.access_expire_minutes * 60,
        samesite="lax",
        secure=True,
        path="/",
    )

    return response


# =========================================================
# 取得目前用戶資訊：GET /me
# =========================================================
@router.get("/me")
async def read_users_me(
    user_payload: Dict[str, Any] = Depends(authenticate_token),
):
    user_id = user_payload.get("userId")
    user = await get_user_by_id(user_id)

    if not user:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"success": False, "message": "用戶不存在"},
        )

    return JSONResponse(
        content={"success": True, "user": await get_user_info(user)}
    )


# =========================================================
# 驗證 Token：GET /verify
# =========================================================
@router.get("/verify")
async def verify_token(
    user_payload: Dict[str, Any] = Depends(authenticate_token),
):
    return JSONResponse(
        content={
            "success": True,
            "message": "Token 有效",
            "user": {
                "userId": user_payload.get("userId"),
                "role": user_payload.get("role"),
            },
        }
    )
