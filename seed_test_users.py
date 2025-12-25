import uuid
import bcrypt
from redis import Redis

from src.db.db import get_redis  # 你之前的 get_redis


# =========================================================
# 測試帳號資料
# =========================================================
test_users = [
    {
        "username": "admin",
        "password": "admin123",
        "role": "ngo_admin",
    },
    {
        "username": "store1",
        "password": "store123",
        "role": "store",
    },
    {
        "username": "homeless1",
        "password": "homeless123",
        "role": "homeless",
    },
    {
        "username": "ngo_partner",
        "password": "partner123",
        "role": "ngo_partner",
    },
    {
        "username": "association",
        "password": "assoc123",
        "role": "association_admin",
    },
]


# =========================================================
# 密碼 hash（bcrypt）
# =========================================================
def hash_password(plain: str) -> str:
    """
    使用 bcrypt 將明碼轉成 hash 字串。
    """
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def main() -> None:
    # 你原本的 get_redis 若是 sync 版本，這裡直接用
    redis_conn: Redis = get_redis()  # type: ignore

    print("🚀 開始寫入測試帳號到 Redis...\n")

    for idx, u in enumerate(test_users, start=1):
        username = u["username"]
        key = f"user:{username}"

        data = {
            "id": str(uuid.uuid4()),
            "username": username,
            "password": hash_password(u["password"]),
            "role": u["role"],
        }

        # HSET user:{username} field1 val1 field2 val2 ...
        redis_conn.hset(key, mapping=data)

        print(f"✔ Seed user: {username} (role={u['role']}) → Redis key: {key}")

    print("\n🎉 所有測試帳號建立完成！")


if __name__ == "__main__":
    main()
