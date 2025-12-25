import os
from datetime import datetime, timezone
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from src.routers import auth
from src.db.db import get_redis  # 這個是有 @lru_cache 的同步 redis client


@asynccontextmanager
async def lifespan(app: FastAPI):
    redis_conn = None

    try:
        # 取得全域共用的 Redis client
        redis_conn = get_redis()

        # 啟動時測試一下連線狀況（同步呼叫 OK，這邊還在啟動階段）
        try:
            redis_conn.ping()
            print("✅ Successfully connected to Redis.")
        except Exception as e:
            # 不讓整個服務直接掛掉，但把錯誤印出來
            print(f"⚠️ Failed to ping Redis on startup: {e}")

        # 如果之後你想在 app.state 上共用，也可以加這行（選配）
        app.state.redis = redis_conn

        # 把控制權交回給 FastAPI（開始處理請求）
        yield

    finally:
        print("🧹 Closing Redis connection.")
        try:
            if redis_conn is not None:
                redis_conn.close()
        except Exception as e:
            print(f"⚠️ Error while closing Redis: {e}")

        # 把 @lru_cache 的 cache 清掉，確保下次重啟不會殘留舊連線物件
        try:
            get_redis.cache_clear()
        except Exception as e:
            print(f"⚠️ Failed to clear get_redis cache: {e}")


# Create FastAPI app and include routers
app = FastAPI(title="homeless-donation-api", lifespan=lifespan)
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])


@app.get("/health")
def health_check():
    return JSONResponse(
        content={
            "success": True,
            "message": "Server is running",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )


@app.get("/")
def read_root():
    return JSONResponse(
        content={"status": 0, "message": "Server is running."},
        status_code=200
    )


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", "3001")),
        reload=os.getenv("RELOAD", "0") == "1",
    )
