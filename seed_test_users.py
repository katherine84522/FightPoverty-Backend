# seed_test_users.py
# 測試帳號初始化腳本 - 建立測試用帳號及關聯資料

import uuid
import secrets
from datetime import datetime, timezone, timedelta

# 台灣時區 (UTC+8)
TW_TIMEZONE = timezone(timedelta(hours=8))
import bcrypt
from redis import Redis

from src.db.db import get_redis


# =========================================================
# 工具函式
# =========================================================
def hash_password(plain: str) -> str:
    """使用 bcrypt 將明碼轉成 hash 字串"""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def generate_qr_code(prefix: str) -> str:
    """生成唯一 QR Code"""
    return f"{prefix}_{secrets.token_hex(5).upper()}"


def main() -> None:
    redis_conn: Redis = get_redis()  # type: ignore
    now = datetime.now(TW_TIMEZONE).isoformat()

    print("🚀 開始寫入測試資料到 Redis...\n")

    # ─────────────────────────────────────────────────────────
    # 1. 建立測試街友資料
    # ─────────────────────────────────────────────────────────
    print("📝 建立測試街友資料...")

    homeless_id = str(uuid.uuid4())
    homeless_qr_code = generate_qr_code("HL")
    homeless_data = {
        "id": homeless_id,
        "name": "測試街友",
        "id_number": "A123456789",
        "qr_code": homeless_qr_code,
        "balance": "500",
        "phone": "0912345678",
        "address": "台北市測試區",
        "emergency_contact": "緊急聯絡人",
        "emergency_phone": "0987654321",
        "notes": "測試帳號",
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    redis_conn.hset(f"homeless:{homeless_id}", mapping=homeless_data)
    redis_conn.set(f"homeless:qr:{homeless_qr_code}", homeless_id)
    redis_conn.set(f"homeless:id_number:A123456789", homeless_id)
    redis_conn.sadd("homeless:all", homeless_id)
    print(f"  ✔ 測試街友 (ID: {homeless_id[:8]}...)")

    # ─────────────────────────────────────────────────────────
    # 2. 建立測試商店資料
    # ─────────────────────────────────────────────────────────
    print("📝 建立測試商店資料...")

    store_id = str(uuid.uuid4())
    store_qr_code = generate_qr_code("ST")
    store_data = {
        "id": store_id,
        "name": "測試商店",
        "qr_code": store_qr_code,
        "category": "餐飲",
        "address": "台北市測試路1號",
        "phone": "0223456789",
        "total_income": "0",
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    redis_conn.hset(f"store:{store_id}", mapping=store_data)
    redis_conn.set(f"store:qr:{store_qr_code}", store_id)
    redis_conn.sadd("store:all", store_id)
    print(f"  ✔ 測試商店 (ID: {store_id[:8]}...)")

    # ─────────────────────────────────────────────────────────
    # 2.5 建立測試商圈資料
    # ─────────────────────────────────────────────────────────
    print("📝 建立測試商圈資料...")

    association_id = str(uuid.uuid4())
    association_data = {
        "id": association_id,
        "name": "測試商圈",
        "description": "測試用商圈",
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    redis_conn.hset(f"association:{association_id}", mapping=association_data)
    redis_conn.sadd("associations:all", association_id)
    # 將商店加入商圈
    redis_conn.sadd(f"association:{association_id}:stores", store_id)
    # 更新商店的 association_id
    redis_conn.hset(f"store:{store_id}", "association_id", association_id)
    print(f"  ✔ 測試商圈 (ID: {association_id[:8]}...)")

    # 建立測試商品
    product_id = str(uuid.uuid4())
    product_data = {
        "id": product_id,
        "store_id": store_id,
        "name": "便當",
        "points": "50",
        "category": "meals",  # 使用英文 enum 值
        "description": "美味便當一份",
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    redis_conn.hset(f"product:{product_id}", mapping=product_data)
    redis_conn.sadd(f"store:{store_id}:products", product_id)
    print(f"  ✔ 測試商品: 便當 (50點)")

    # ─────────────────────────────────────────────────────────
    # 3. 建立測試使用者帳號
    # ─────────────────────────────────────────────────────────
    print("\n📝 建立測試使用者帳號...")

    test_users = [
        {
            "username": "admin",
            "password": "admin123",
            "name": "NGO 管理員",
            "role": "ngo_admin",
        },
        {
            "username": "system_admin",
            "password": "sysadmin123",
            "name": "系統管理員",
            "role": "system_admin",
        },
        {
            "username": "store1",
            "password": "store123",
            "name": "測試商店帳號",
            "role": "store",
            "store_id": store_id,  # 關聯商店
        },
        {
            "username": "homeless1",
            "password": "homeless123",
            "name": "測試街友",
            "role": "homeless",
            "homeless_id": homeless_id,  # 關聯街友
        },
        {
            "username": "ngo_partner",
            "password": "partner123",
            "name": "NGO 合作夥伴",
            "role": "ngo_partner",
        },
        {
            "username": "association",
            "password": "assoc123",
            "name": "商圈管理員",
            "role": "association_admin",
            "association_id": association_id,  # 關聯商圈
        },
        {
            "username": "assoc_partner",
            "password": "assocpartner123",
            "name": "商圈合作夥伴",
            "role": "association_partner",
            "association_id": association_id,  # 關聯商圈
        },
    ]

    for u in test_users:
        user_id = str(uuid.uuid4())
        username = u["username"]

        # 主資料
        user_data = {
            "id": user_id,
            "username": username,
            "password": hash_password(u["password"]),
            "name": u["name"],
            "role": u["role"],
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }

        # 關聯 ID
        if "store_id" in u:
            user_data["store_id"] = u["store_id"]
        if "homeless_id" in u:
            user_data["homeless_id"] = u["homeless_id"]
        if "association_id" in u:
            user_data["association_id"] = u["association_id"]

        # 使用新的 key 結構
        redis_conn.hset(f"user:{user_id}", mapping=user_data)
        redis_conn.set(f"user:username:{username}", user_id)

        # 加入角色索引（用於帳號管理列表）
        redis_conn.sadd(f"users:role:{u['role']}", user_id)
        redis_conn.sadd("users:all", user_id)

        # 如果有 association_id，加入商圈使用者索引
        if "association_id" in u:
            redis_conn.sadd(f"association:{u['association_id']}:users", user_id)

        # 保留舊的 key 結構以保持向後相容
        redis_conn.hset(f"user:{username}", mapping=user_data)

        extra_info = ""
        if "store_id" in u:
            extra_info = f" → 商店:{store_qr_code}"
        if "homeless_id" in u:
            extra_info = f" → 街友:{homeless_qr_code}"
        if "association_id" in u:
            extra_info = f" → 商圈:{association_id[:8]}..."
        print(f"  ✔ {username} ({u['role']}){extra_info}")

    # ─────────────────────────────────────────────────────────
    # 4. 設定系統預設值
    # ─────────────────────────────────────────────────────────
    print("\n📝 設定系統預設值...")

    default_configs = {
        "max_balance_limit": {"value": "10000", "description": "最大餘額上限"},
        "max_allocation_limit": {"value": "1000", "description": "單次配額上限"},
        "default_page_size": {"value": "20", "description": "預設分頁大小"},
    }

    for key, config in default_configs.items():
        config_data = {
            "value": config["value"],
            "description": config["description"],
            "updated_at": now,
        }
        redis_conn.hset(f"config:{key}", mapping=config_data)
        print(f"  ✔ {key} = {config['value']}")

    print("\n🎉 測試資料建立完成！")
    print("\n📋 測試帳號資訊：")
    print("─" * 60)
    print(f"{'帳號':<20} {'密碼':<18} {'角色':<20}")
    print("─" * 60)
    for u in test_users:
        print(f"{u['username']:<20} {u['password']:<18} {u['role']:<20}")
    print("─" * 60)
    print(f"\n📦 測試街友 QR Code: {homeless_qr_code}")
    print(f"🏪 測試商店 QR Code: {store_qr_code}")


if __name__ == "__main__":
    main()
