# src/db/repositories.py
# Redis 資料存取層

import json
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple, Type, TypeVar
from uuid import UUID

# 台灣時區 (UTC+8)
TW_TIMEZONE = timezone(timedelta(hours=8))

from pydantic import BaseModel

from src.db.db import get_redis
from src.db.models import (
    User,
    UserRole,
    Status,
    HomelessPerson,
    HomelessPersonCreate,
    Store,
    StoreCreate,
    Product,
    ProductCreate,
    Transaction,
    TransactionCreate,
    TransactionStatus,
    Allocation,
    AllocationCreate,
    Association,
    AssociationCreate,
    SystemConfig,
)
from src.services.qr_service import generate_homeless_qr_code, generate_store_qr_code

T = TypeVar("T", bound=BaseModel)


# ─────────────────────────────────────────────────────────
# 基礎 Repository 工具函式
# ─────────────────────────────────────────────────────────
class BaseRepository:
    """Repository 基礎類別，提供共用的 Redis 操作方法"""

    def __init__(self):
        self._redis = get_redis()

    def _serialize_value(self, value: Any) -> str:
        """將值序列化為字串以存入 Redis"""
        if value is None:
            return ""
        if isinstance(value, (UUID, datetime)):
            return str(value)
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        # 處理 Enum 類型
        if hasattr(value, 'value'):
            return str(value.value)
        return str(value)

    def _deserialize_value(self, value: str, target_type: Type) -> Any:
        """從 Redis 字串反序列化為目標類型"""
        if value == "" or value is None:
            return None
        if target_type == UUID:
            return UUID(value)
        if target_type == datetime:
            return datetime.fromisoformat(value)
        if target_type == int:
            return int(value)
        if target_type == float:
            return float(value)
        if target_type == bool:
            return value.lower() == "true"
        return value

    def _model_to_hash(self, model: BaseModel) -> Dict[str, str]:
        """將 Pydantic model 轉換為 Redis Hash 格式"""
        data = model.model_dump()
        return {k: self._serialize_value(v) for k, v in data.items() if v is not None}

    def _hash_to_dict(self, data: Dict[bytes, bytes]) -> Dict[str, str]:
        """將 Redis Hash 結果轉換為字典"""
        return {k.decode() if isinstance(k, bytes) else k:
                v.decode() if isinstance(v, bytes) else v
                for k, v in data.items()}

    def _get_now(self) -> datetime:
        """取得當前時間（台灣時區 UTC+8）"""
        return datetime.now(TW_TIMEZONE)


# ─────────────────────────────────────────────────────────
# User Repository
# ─────────────────────────────────────────────────────────
class UserRepository(BaseRepository):
    """
    使用者資料存取層。

    Redis 結構：
      - user:{id} => Hash（使用者資料）
      - user:username:{username} => String（user_id）
    """

    def _key_by_id(self, user_id: str | UUID) -> str:
        return f"user:{user_id}"

    def _index_by_username(self, username: str) -> str:
        return f"user:username:{username}"

    def get_by_username(self, username: str) -> Optional[User]:
        """透過使用者名稱取得使用者"""
        index_key = self._index_by_username(username)
        user_id = self._redis.get(index_key)
        if not user_id:
            return None
        return self.get_by_id(user_id)

    def get_by_id(self, user_id: str | UUID) -> Optional[User]:
        """透過 ID 取得使用者"""
        key = self._key_by_id(user_id)
        data = self._redis.hgetall(key)
        if not data:
            return None

        data = self._hash_to_dict(data)
        # 轉換特殊欄位
        if "id" in data:
            data["id"] = UUID(data["id"])
        if "created_at" in data:
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if "updated_at" in data:
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        if "last_login_at" in data and data["last_login_at"]:
            data["last_login_at"] = datetime.fromisoformat(data["last_login_at"])
        if "store_id" in data and data["store_id"]:
            data["store_id"] = UUID(data["store_id"])
        if "homeless_id" in data and data["homeless_id"]:
            data["homeless_id"] = UUID(data["homeless_id"])
        if "association_id" in data and data["association_id"]:
            data["association_id"] = UUID(data["association_id"])

        return User(**data)

    def save(self, user: User) -> None:
        """儲存使用者"""
        key = self._key_by_id(user.id)
        data = self._model_to_hash(user)
        self._redis.hset(key, mapping=data)
        # 建立使用者名稱索引
        self._redis.set(self._index_by_username(user.username), str(user.id))

    def update_last_login(self, user_id: str | UUID) -> None:
        """更新最後登入時間"""
        key = self._key_by_id(user_id)
        now = self._get_now()
        self._redis.hset(key, "last_login_at", str(now))
        self._redis.hset(key, "updated_at", str(now))

    def update_status(self, user_id: str | UUID, status: Status) -> None:
        """更新使用者狀態"""
        key = self._key_by_id(user_id)
        now = self._get_now()
        self._redis.hset(key, "status", status.value)
        self._redis.hset(key, "updated_at", str(now))

    def delete(self, user_id: str | UUID) -> None:
        """刪除使用者"""
        user = self.get_by_id(user_id)
        if user:
            self._redis.delete(self._key_by_id(user_id))
            self._redis.delete(self._index_by_username(user.username))
            # 從角色索引移除
            self._redis.srem(self._role_users_key(user.role), str(user_id))
            # 從全部使用者索引移除
            self._redis.srem(self._all_key(), str(user_id))

    def _role_users_key(self, role: str | UserRole) -> str:
        """角色使用者索引 key"""
        role_value = role.value if hasattr(role, 'value') else role
        return f"users:role:{role_value}"

    def _all_key(self) -> str:
        """所有使用者索引 key"""
        return "users:all"

    def _association_users_key(self, association_id: str | UUID) -> str:
        """商圈使用者索引 key"""
        return f"association:{association_id}:users"

    def create(self, user: User) -> User:
        """建立使用者"""
        # 儲存使用者資料
        self.save(user)
        # 加入角色索引
        self._redis.sadd(self._role_users_key(user.role), str(user.id))
        # 加入全部使用者索引
        self._redis.sadd(self._all_key(), str(user.id))
        # 如果有 association_id，加入商圈使用者索引
        if user.association_id:
            self._redis.sadd(self._association_users_key(user.association_id), str(user.id))
        return user

    def list_by_role(
        self,
        role: UserRole,
        page: int = 1,
        limit: int = 20,
        status_filter: Optional[Status] = None,
        association_id: Optional[UUID] = None,
    ) -> Tuple[List[User], int]:
        """
        列出指定角色的使用者。

        Args:
            role: 使用者角色
            page: 頁碼
            limit: 每頁數量
            status_filter: 狀態篩選
            association_id: 商圈 ID 篩選（用於商圈管理員）
        """
        # 取得該角色的所有使用者 ID
        user_ids = self._redis.smembers(self._role_users_key(role))

        users: List[User] = []
        for user_id in user_ids:
            if isinstance(user_id, bytes):
                user_id = user_id.decode()
            user = self.get_by_id(user_id)
            if user:
                # 狀態篩選
                if status_filter and user.status != status_filter:
                    continue
                # 商圈篩選
                if association_id and user.association_id != association_id:
                    continue
                users.append(user)

        # 排序（按建立時間倒序）
        users.sort(key=lambda x: x.created_at, reverse=True)

        # 分頁
        total = len(users)
        start = (page - 1) * limit
        end = start + limit
        return users[start:end], total


# ─────────────────────────────────────────────────────────
# HomelessPerson Repository
# ─────────────────────────────────────────────────────────
class HomelessPersonRepository(BaseRepository):
    """
    街友資料存取層。

    Redis 結構：
      - homeless:{id} => Hash（街友資料）
      - homeless:qr:{qr_code} => String（homeless_id）
      - homeless:id_number:{id_number} => String（homeless_id）
      - homeless:all => Set（所有 homeless_id）
    """

    def _key_by_id(self, homeless_id: str | UUID) -> str:
        return f"homeless:{homeless_id}"

    def _index_by_qr(self, qr_code: str) -> str:
        return f"homeless:qr:{qr_code}"

    def _index_by_id_number(self, id_number: str) -> str:
        return f"homeless:id_number:{id_number}"

    def _all_key(self) -> str:
        return "homeless:all"

    def _transactions_key(self, homeless_id: str | UUID) -> str:
        return f"homeless:{homeless_id}:transactions"

    def _allocations_key(self, homeless_id: str | UUID) -> str:
        return f"homeless:{homeless_id}:allocations"

    def _parse_homeless(self, data: Dict[str, str]) -> HomelessPerson:
        """解析 Redis 資料為 HomelessPerson"""
        if "id" in data:
            data["id"] = UUID(data["id"])
        if "balance" in data:
            data["balance"] = int(data["balance"])
        if "created_at" in data:
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if "updated_at" in data:
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        # 處理 status 欄位（可能是 'Status.ACTIVE' 或 'active'）
        if "status" in data:
            status_val = data["status"]
            if status_val.startswith("Status."):
                # 舊格式：'Status.ACTIVE' -> 'active'
                data["status"] = status_val.split(".")[-1].lower()
        return HomelessPerson(**data)

    def get_by_id(self, homeless_id: str | UUID) -> Optional[HomelessPerson]:
        """透過 ID 取得街友"""
        key = self._key_by_id(homeless_id)
        data = self._redis.hgetall(key)
        if not data:
            return None
        return self._parse_homeless(self._hash_to_dict(data))

    def get_by_qr_code(self, qr_code: str) -> Optional[HomelessPerson]:
        """透過 QR Code 取得街友"""
        index_key = self._index_by_qr(qr_code)
        homeless_id = self._redis.get(index_key)
        if not homeless_id:
            return None
        if isinstance(homeless_id, bytes):
            homeless_id = homeless_id.decode()
        return self.get_by_id(homeless_id)

    def get_by_id_number(self, id_number: str) -> Optional[HomelessPerson]:
        """透過身分證字號取得街友"""
        index_key = self._index_by_id_number(id_number.upper())
        homeless_id = self._redis.get(index_key)
        if not homeless_id:
            return None
        if isinstance(homeless_id, bytes):
            homeless_id = homeless_id.decode()
        return self.get_by_id(homeless_id)

    def create(self, homeless_id: UUID, data: HomelessPersonCreate) -> HomelessPerson:
        """建立街友"""
        now = self._get_now()
        qr_code = generate_homeless_qr_code()

        homeless = HomelessPerson(
            id=homeless_id,
            qr_code=qr_code,
            balance=0,
            status=Status.ACTIVE,
            created_at=now,
            updated_at=now,
            **data.model_dump(),
        )

        # 儲存主資料
        key = self._key_by_id(homeless_id)
        self._redis.hset(key, mapping=self._model_to_hash(homeless))

        # 建立索引
        self._redis.set(self._index_by_qr(qr_code), str(homeless_id))
        self._redis.set(self._index_by_id_number(data.id_number.upper()), str(homeless_id))
        self._redis.sadd(self._all_key(), str(homeless_id))

        return homeless

    def update(self, homeless_id: str | UUID, updates: Dict[str, Any]) -> Optional[HomelessPerson]:
        """更新街友資料"""
        homeless = self.get_by_id(homeless_id)
        if not homeless:
            return None

        key = self._key_by_id(homeless_id)
        now = self._get_now()
        updates["updated_at"] = str(now)

        for field, value in updates.items():
            if value is None:
                # 將 None 值存為空字串（允許清空欄位）
                self._redis.hset(key, field, "")
            else:
                self._redis.hset(key, field, self._serialize_value(value))

        return self.get_by_id(homeless_id)

    def update_balance(self, homeless_id: str | UUID, new_balance: int) -> bool:
        """更新餘額"""
        key = self._key_by_id(homeless_id)
        if not self._redis.exists(key):
            return False
        now = self._get_now()
        self._redis.hset(key, "balance", str(new_balance))
        self._redis.hset(key, "updated_at", str(now))
        return True

    def delete(self, homeless_id: str | UUID) -> bool:
        """刪除街友（軟刪除：設為 inactive）"""
        return self.update(homeless_id, {"status": Status.INACTIVE.value}) is not None

    def list_all(
        self,
        page: int = 1,
        limit: int = 20,
        status_filter: Optional[Status] = None,
        search: Optional[str] = None,
    ) -> Tuple[List[HomelessPerson], int]:
        """列出所有街友（支援分頁、狀態篩選、搜尋）"""
        all_ids = self._redis.smembers(self._all_key())
        all_homeless: List[HomelessPerson] = []

        for homeless_id in all_ids:
            if isinstance(homeless_id, bytes):
                homeless_id = homeless_id.decode()
            homeless = self.get_by_id(homeless_id)
            if homeless:
                # 狀態篩選
                if status_filter and homeless.status != status_filter:
                    continue
                # 搜尋（姓名或身分證字號）
                if search:
                    search_lower = search.lower()
                    if (
                        search_lower not in homeless.name.lower()
                        and search_lower not in homeless.id_number.lower()
                    ):
                        continue
                all_homeless.append(homeless)

        # 排序（按建立時間倒序）
        all_homeless.sort(key=lambda x: x.created_at, reverse=True)

        # 分頁
        total = len(all_homeless)
        start = (page - 1) * limit
        end = start + limit
        return all_homeless[start:end], total

    def reissue_qr_code(self, homeless_id: str | UUID) -> Optional[str]:
        """重新發放 QR Code"""
        homeless = self.get_by_id(homeless_id)
        if not homeless:
            return None

        # 刪除舊索引
        self._redis.delete(self._index_by_qr(homeless.qr_code))

        # 生成新 QR Code
        new_qr_code = generate_homeless_qr_code()

        # 更新資料
        key = self._key_by_id(homeless_id)
        now = self._get_now()
        self._redis.hset(key, "qr_code", new_qr_code)
        self._redis.hset(key, "updated_at", str(now))

        # 建立新索引
        self._redis.set(self._index_by_qr(new_qr_code), str(homeless_id))

        return new_qr_code

    def acquire_lock(self, homeless_id: str | UUID, timeout: int = 30) -> bool:
        """取得街友帳戶鎖定（用於交易）"""
        lock_key = f"lock:homeless:{homeless_id}"
        return self._redis.set(lock_key, "locked", nx=True, ex=timeout)

    def release_lock(self, homeless_id: str | UUID) -> None:
        """釋放街友帳戶鎖定"""
        lock_key = f"lock:homeless:{homeless_id}"
        self._redis.delete(lock_key)


# ─────────────────────────────────────────────────────────
# Store Repository
# ─────────────────────────────────────────────────────────
class StoreRepository(BaseRepository):
    """
    商店資料存取層。

    Redis 結構：
      - store:{id} => Hash（商店資料）
      - store:qr:{qr_code} => String（store_id）
      - store:all => Set（所有 store_id）
      - association:{association_id}:stores => Set（商圈下的商店）
    """

    def _key_by_id(self, store_id: str | UUID) -> str:
        return f"store:{store_id}"

    def _index_by_qr(self, qr_code: str) -> str:
        return f"store:qr:{qr_code}"

    def _all_key(self) -> str:
        return "store:all"

    def _association_stores_key(self, association_id: str | UUID) -> str:
        return f"association:{association_id}:stores"

    def _products_key(self, store_id: str | UUID) -> str:
        return f"store:{store_id}:products"

    def _transactions_key(self, store_id: str | UUID) -> str:
        return f"store:{store_id}:transactions"

    def _parse_store(self, data: Dict[str, str]) -> Store:
        """解析 Redis 資料為 Store"""
        if "id" in data:
            data["id"] = UUID(data["id"])
        if "total_income" in data:
            data["total_income"] = int(data["total_income"])
        if "association_id" in data and data["association_id"]:
            data["association_id"] = UUID(data["association_id"])
        if "created_at" in data:
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if "updated_at" in data:
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        return Store(**data)

    def get_by_id(self, store_id: str | UUID) -> Optional[Store]:
        """透過 ID 取得商店"""
        key = self._key_by_id(store_id)
        data = self._redis.hgetall(key)
        if not data:
            return None
        return self._parse_store(self._hash_to_dict(data))

    def get_by_qr_code(self, qr_code: str) -> Optional[Store]:
        """透過 QR Code 取得商店"""
        index_key = self._index_by_qr(qr_code)
        store_id = self._redis.get(index_key)
        if not store_id:
            return None
        if isinstance(store_id, bytes):
            store_id = store_id.decode()
        return self.get_by_id(store_id)

    def create(self, store_id: UUID, data: StoreCreate) -> Store:
        """建立商店"""
        now = self._get_now()
        qr_code = generate_store_qr_code()

        store = Store(
            id=store_id,
            qr_code=qr_code,
            total_income=0,
            status=Status.ACTIVE,
            created_at=now,
            updated_at=now,
            **data.model_dump(),
        )

        # 儲存主資料
        key = self._key_by_id(store_id)
        self._redis.hset(key, mapping=self._model_to_hash(store))

        # 建立索引
        self._redis.set(self._index_by_qr(qr_code), str(store_id))
        self._redis.sadd(self._all_key(), str(store_id))

        # 如果有商圈，加入商圈索引
        if data.association_id:
            self._redis.sadd(self._association_stores_key(data.association_id), str(store_id))

        return store

    def update(self, store_id: str | UUID, updates: Dict[str, Any]) -> Optional[Store]:
        """更新商店資料"""
        store = self.get_by_id(store_id)
        if not store:
            return None

        key = self._key_by_id(store_id)
        now = self._get_now()
        updates["updated_at"] = str(now)

        for field, value in updates.items():
            if value is None:
                self._redis.hset(key, field, "")
            else:
                self._redis.hset(key, field, self._serialize_value(value))

        return self.get_by_id(store_id)

    def update_income(self, store_id: str | UUID, amount: int) -> bool:
        """增加商店收入"""
        key = self._key_by_id(store_id)
        if not self._redis.exists(key):
            return False
        self._redis.hincrby(key, "total_income", amount)
        self._redis.hset(key, "updated_at", str(self._get_now()))
        return True

    def list_all(
        self,
        page: int = 1,
        limit: int = 20,
        status_filter: Optional[Status] = None,
        association_id: Optional[UUID] = None,
    ) -> Tuple[List[Store], int]:
        """列出所有商店（支援分頁、狀態篩選、商圈篩選）"""
        if association_id:
            all_ids = self._redis.smembers(self._association_stores_key(association_id))
        else:
            all_ids = self._redis.smembers(self._all_key())

        all_stores: List[Store] = []

        for store_id in all_ids:
            if isinstance(store_id, bytes):
                store_id = store_id.decode()
            store = self.get_by_id(store_id)
            if store:
                if status_filter and store.status != status_filter:
                    continue
                all_stores.append(store)

        # 排序
        all_stores.sort(key=lambda x: x.created_at, reverse=True)

        # 分頁
        total = len(all_stores)
        start = (page - 1) * limit
        end = start + limit
        return all_stores[start:end], total


# ─────────────────────────────────────────────────────────
# Product Repository
# ─────────────────────────────────────────────────────────
class ProductRepository(BaseRepository):
    """
    產品資料存取層。

    Redis 結構：
      - product:{id} => Hash（產品資料）
      - store:{store_id}:products => Set（商店下的產品 ID）
    """

    def _key_by_id(self, product_id: str | UUID) -> str:
        return f"product:{product_id}"

    def _store_products_key(self, store_id: str | UUID) -> str:
        return f"store:{store_id}:products"

    def _parse_product(self, data: Dict[str, str]) -> Product:
        """解析 Redis 資料為 Product"""
        if "id" in data:
            data["id"] = UUID(data["id"])
        if "store_id" in data:
            data["store_id"] = UUID(data["store_id"])
        if "points" in data:
            data["points"] = int(data["points"])
        if "created_at" in data:
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if "updated_at" in data:
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        return Product(**data)

    def get_by_id(self, product_id: str | UUID) -> Optional[Product]:
        """透過 ID 取得產品"""
        key = self._key_by_id(product_id)
        data = self._redis.hgetall(key)
        if not data:
            return None
        return self._parse_product(self._hash_to_dict(data))

    def create(self, product_id: UUID, store_id: UUID, data: ProductCreate) -> Product:
        """建立產品"""
        now = self._get_now()

        product = Product(
            id=product_id,
            store_id=store_id,
            status=Status.ACTIVE,
            created_at=now,
            updated_at=now,
            **data.model_dump(),
        )

        # 儲存主資料
        key = self._key_by_id(product_id)
        self._redis.hset(key, mapping=self._model_to_hash(product))

        # 加入商店產品索引
        self._redis.sadd(self._store_products_key(store_id), str(product_id))

        return product

    def update(self, product_id: str | UUID, updates: Dict[str, Any]) -> Optional[Product]:
        """更新產品資料"""
        product = self.get_by_id(product_id)
        if not product:
            return None

        key = self._key_by_id(product_id)
        now = self._get_now()
        updates["updated_at"] = str(now)

        for field, value in updates.items():
            if value is None:
                self._redis.hset(key, field, "")
            else:
                self._redis.hset(key, field, self._serialize_value(value))

        return self.get_by_id(product_id)

    def delete(self, product_id: str | UUID) -> bool:
        """刪除產品（軟刪除）"""
        return self.update(product_id, {"status": Status.INACTIVE.value}) is not None

    def list_by_store(
        self,
        store_id: str | UUID,
        status_filter: Optional[Status] = None,
    ) -> List[Product]:
        """列出商店的所有產品"""
        product_ids = self._redis.smembers(self._store_products_key(store_id))
        products: List[Product] = []

        for product_id in product_ids:
            if isinstance(product_id, bytes):
                product_id = product_id.decode()
            product = self.get_by_id(product_id)
            if product:
                if status_filter and product.status != status_filter:
                    continue
                products.append(product)

        # 排序
        products.sort(key=lambda x: x.created_at, reverse=True)
        return products


# ─────────────────────────────────────────────────────────
# Transaction Repository
# ─────────────────────────────────────────────────────────
class TransactionRepository(BaseRepository):
    """
    交易資料存取層。

    Redis 結構：
      - transaction:{id} => Hash（交易資料）
      - homeless:{homeless_id}:transactions => Sorted Set（score=timestamp）
      - store:{store_id}:transactions => Sorted Set（score=timestamp）
      - transactions:daily:{YYYY-MM-DD} => Set（當日交易 ID）
    """

    def _key_by_id(self, tx_id: str | UUID) -> str:
        return f"transaction:{tx_id}"

    def _homeless_transactions_key(self, homeless_id: str | UUID) -> str:
        return f"homeless:{homeless_id}:transactions"

    def _store_transactions_key(self, store_id: str | UUID) -> str:
        return f"store:{store_id}:transactions"

    def _daily_transactions_key(self, date: str) -> str:
        return f"transactions:daily:{date}"

    def _parse_transaction(self, data: Dict[str, str]) -> Transaction:
        """解析 Redis 資料為 Transaction"""
        if "id" in data:
            data["id"] = UUID(data["id"])
        if "homeless_id" in data:
            data["homeless_id"] = UUID(data["homeless_id"])
        if "store_id" in data:
            data["store_id"] = UUID(data["store_id"])
        if "product_id" in data and data["product_id"]:
            data["product_id"] = UUID(data["product_id"])
        if "amount" in data:
            data["amount"] = int(data["amount"])
        if "balance_before" in data:
            data["balance_before"] = int(data["balance_before"])
        if "balance_after" in data:
            data["balance_after"] = int(data["balance_after"])
        if "created_at" in data:
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        return Transaction(**data)

    def get_by_id(self, tx_id: str | UUID) -> Optional[Transaction]:
        """透過 ID 取得交易"""
        key = self._key_by_id(tx_id)
        data = self._redis.hgetall(key)
        if not data:
            return None
        return self._parse_transaction(self._hash_to_dict(data))

    def create(
        self,
        tx_id: UUID,
        homeless_id: UUID,
        homeless_qr_code: str,
        store_id: UUID,
        store_qr_code: str,
        product_name: str,
        amount: int,
        balance_before: int,
        balance_after: int,
        status: TransactionStatus,
        product_id: Optional[UUID] = None,
    ) -> Transaction:
        """建立交易記錄"""
        now = self._get_now()
        timestamp = now.timestamp()

        tx = Transaction(
            id=tx_id,
            homeless_id=homeless_id,
            homeless_qr_code=homeless_qr_code,
            store_id=store_id,
            store_qr_code=store_qr_code,
            product_id=product_id,
            product_name=product_name,
            amount=amount,
            balance_before=balance_before,
            balance_after=balance_after,
            status=status,
            created_at=now,
        )

        # 儲存主資料
        key = self._key_by_id(tx_id)
        self._redis.hset(key, mapping=self._model_to_hash(tx))

        # 加入索引
        self._redis.zadd(self._homeless_transactions_key(homeless_id), {str(tx_id): timestamp})
        self._redis.zadd(self._store_transactions_key(store_id), {str(tx_id): timestamp})
        self._redis.sadd(self._daily_transactions_key(now.strftime("%Y-%m-%d")), str(tx_id))

        return tx

    def list_by_homeless(
        self,
        homeless_id: str | UUID,
        page: int = 1,
        limit: int = 20,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Tuple[List[Transaction], int]:
        """列出街友的交易記錄"""
        key = self._homeless_transactions_key(homeless_id)
        return self._list_transactions(key, page, limit, start_date, end_date)

    def list_by_store(
        self,
        store_id: str | UUID,
        page: int = 1,
        limit: int = 20,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Tuple[List[Transaction], int]:
        """列出商店的交易記錄"""
        key = self._store_transactions_key(store_id)
        return self._list_transactions(key, page, limit, start_date, end_date)

    def _list_transactions(
        self,
        key: str,
        page: int,
        limit: int,
        start_date: Optional[datetime],
        end_date: Optional[datetime],
    ) -> Tuple[List[Transaction], int]:
        """通用交易列表查詢"""
        min_score = start_date.timestamp() if start_date else "-inf"
        max_score = end_date.timestamp() if end_date else "+inf"

        # 取得符合時間範圍的所有交易 ID
        tx_ids = self._redis.zrevrangebyscore(key, max_score, min_score)

        transactions: List[Transaction] = []
        for tx_id in tx_ids:
            if isinstance(tx_id, bytes):
                tx_id = tx_id.decode()
            tx = self.get_by_id(tx_id)
            if tx:
                transactions.append(tx)

        # 分頁
        total = len(transactions)
        start = (page - 1) * limit
        end = start + limit
        return transactions[start:end], total

    def list_all(
        self,
        page: int = 1,
        limit: int = 20,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Tuple[List[Transaction], int]:
        """列出所有交易記錄（用於報表）"""
        # 取得日期範圍內的所有交易
        if start_date and end_date:
            all_tx_ids = set()
            current = start_date
            while current <= end_date:
                date_key = self._daily_transactions_key(current.strftime("%Y-%m-%d"))
                tx_ids = self._redis.smembers(date_key)
                for tx_id in tx_ids:
                    if isinstance(tx_id, bytes):
                        tx_id = tx_id.decode()
                    all_tx_ids.add(tx_id)
                current = datetime(current.year, current.month, current.day + 1)
        else:
            # 沒有日期範圍時，需要掃描所有交易（不建議在生產環境使用）
            all_tx_ids = set()
            keys = self._redis.keys("transaction:*")
            for key in keys:
                if isinstance(key, bytes):
                    key = key.decode()
                tx_id = key.replace("transaction:", "")
                all_tx_ids.add(tx_id)

        transactions: List[Transaction] = []
        for tx_id in all_tx_ids:
            tx = self.get_by_id(tx_id)
            if tx:
                transactions.append(tx)

        # 排序（按時間倒序）
        transactions.sort(key=lambda x: x.created_at, reverse=True)

        # 分頁
        total = len(transactions)
        start = (page - 1) * limit
        end = start + limit
        return transactions[start:end], total


# ─────────────────────────────────────────────────────────
# Allocation Repository
# ─────────────────────────────────────────────────────────
class AllocationRepository(BaseRepository):
    """
    點數配額資料存取層。

    Redis 結構：
      - allocation:{id} => Hash（配額資料）
      - homeless:{homeless_id}:allocations => Sorted Set（score=timestamp）
      - allocations:daily:{YYYY-MM-DD} => Set（當日配額 ID）
    """

    def _key_by_id(self, allocation_id: str | UUID) -> str:
        return f"allocation:{allocation_id}"

    def _homeless_allocations_key(self, homeless_id: str | UUID) -> str:
        return f"homeless:{homeless_id}:allocations"

    def _daily_allocations_key(self, date: str) -> str:
        return f"allocations:daily:{date}"

    def _parse_allocation(self, data: Dict[str, str]) -> Allocation:
        """解析 Redis 資料為 Allocation"""
        if "id" in data:
            data["id"] = UUID(data["id"])
        if "homeless_id" in data:
            data["homeless_id"] = UUID(data["homeless_id"])
        if "admin_id" in data:
            data["admin_id"] = UUID(data["admin_id"])
        if "amount" in data:
            data["amount"] = int(data["amount"])
        if "balance_before" in data:
            data["balance_before"] = int(data["balance_before"])
        if "balance_after" in data:
            data["balance_after"] = int(data["balance_after"])
        if "created_at" in data:
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        return Allocation(**data)

    def get_by_id(self, allocation_id: str | UUID) -> Optional[Allocation]:
        """透過 ID 取得配額記錄"""
        key = self._key_by_id(allocation_id)
        data = self._redis.hgetall(key)
        if not data:
            return None
        return self._parse_allocation(self._hash_to_dict(data))

    def create(
        self,
        allocation_id: UUID,
        homeless_id: UUID,
        admin_id: UUID,
        amount: int,
        balance_before: int,
        balance_after: int,
        notes: Optional[str] = None,
    ) -> Allocation:
        """建立配額記錄"""
        now = self._get_now()
        timestamp = now.timestamp()

        allocation = Allocation(
            id=allocation_id,
            homeless_id=homeless_id,
            admin_id=admin_id,
            amount=amount,
            balance_before=balance_before,
            balance_after=balance_after,
            notes=notes,
            created_at=now,
        )

        # 儲存主資料
        key = self._key_by_id(allocation_id)
        self._redis.hset(key, mapping=self._model_to_hash(allocation))

        # 加入索引
        self._redis.zadd(
            self._homeless_allocations_key(homeless_id),
            {str(allocation_id): timestamp},
        )
        self._redis.sadd(
            self._daily_allocations_key(now.strftime("%Y-%m-%d")),
            str(allocation_id),
        )

        return allocation

    def list_by_homeless(
        self,
        homeless_id: str | UUID,
        page: int = 1,
        limit: int = 20,
    ) -> Tuple[List[Allocation], int]:
        """列出街友的配額記錄"""
        key = self._homeless_allocations_key(homeless_id)
        allocation_ids = self._redis.zrevrange(key, 0, -1)

        allocations: List[Allocation] = []
        for allocation_id in allocation_ids:
            if isinstance(allocation_id, bytes):
                allocation_id = allocation_id.decode()
            allocation = self.get_by_id(allocation_id)
            if allocation:
                allocations.append(allocation)

        # 分頁
        total = len(allocations)
        start = (page - 1) * limit
        end = start + limit
        return allocations[start:end], total

    def list_all(
        self,
        page: int = 1,
        limit: int = 20,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Tuple[List[Allocation], int]:
        """列出所有配額記錄"""
        all_allocation_ids = set()

        if start_date and end_date:
            current = start_date
            while current <= end_date:
                date_key = self._daily_allocations_key(current.strftime("%Y-%m-%d"))
                ids = self._redis.smembers(date_key)
                for aid in ids:
                    if isinstance(aid, bytes):
                        aid = aid.decode()
                    all_allocation_ids.add(aid)
                current = datetime(current.year, current.month, current.day + 1)
        else:
            keys = self._redis.keys("allocation:*")
            for key in keys:
                if isinstance(key, bytes):
                    key = key.decode()
                allocation_id = key.replace("allocation:", "")
                all_allocation_ids.add(allocation_id)

        allocations: List[Allocation] = []
        for allocation_id in all_allocation_ids:
            allocation = self.get_by_id(allocation_id)
            if allocation:
                allocations.append(allocation)

        # 排序
        allocations.sort(key=lambda x: x.created_at, reverse=True)

        # 分頁
        total = len(allocations)
        start = (page - 1) * limit
        end = start + limit
        return allocations[start:end], total


# ─────────────────────────────────────────────────────────
# Association Repository
# ─────────────────────────────────────────────────────────
class AssociationRepository(BaseRepository):
    """
    商圈資料存取層。

    Redis 結構：
      - association:{id} => Hash（商圈資料）
      - associations:all => Set（所有 association_id）
    """

    def _key_by_id(self, association_id: str | UUID) -> str:
        return f"association:{association_id}"

    def _all_key(self) -> str:
        return "associations:all"

    def _stores_key(self, association_id: str | UUID) -> str:
        return f"association:{association_id}:stores"

    def _parse_association(self, data: Dict[str, str]) -> Association:
        """解析 Redis 資料為 Association"""
        if "id" in data:
            data["id"] = UUID(data["id"])
        if "created_at" in data:
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if "updated_at" in data:
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        return Association(**data)

    def get_by_id(self, association_id: str | UUID) -> Optional[Association]:
        """透過 ID 取得商圈"""
        key = self._key_by_id(association_id)
        data = self._redis.hgetall(key)
        if not data:
            return None
        return self._parse_association(self._hash_to_dict(data))

    def create(self, association_id: UUID, data: AssociationCreate) -> Association:
        """建立商圈"""
        now = self._get_now()

        association = Association(
            id=association_id,
            status=Status.ACTIVE,
            created_at=now,
            updated_at=now,
            **data.model_dump(),
        )

        # 儲存主資料
        key = self._key_by_id(association_id)
        self._redis.hset(key, mapping=self._model_to_hash(association))

        # 加入索引
        self._redis.sadd(self._all_key(), str(association_id))

        return association

    def update(
        self, association_id: str | UUID, updates: Dict[str, Any]
    ) -> Optional[Association]:
        """更新商圈資料"""
        association = self.get_by_id(association_id)
        if not association:
            return None

        key = self._key_by_id(association_id)
        now = self._get_now()
        updates["updated_at"] = str(now)

        for field, value in updates.items():
            if value is None:
                self._redis.hset(key, field, "")
            else:
                self._redis.hset(key, field, self._serialize_value(value))

        return self.get_by_id(association_id)

    def list_all(
        self,
        page: int = 1,
        limit: int = 20,
        status_filter: Optional[Status] = None,
    ) -> Tuple[List[Association], int]:
        """列出所有商圈"""
        all_ids = self._redis.smembers(self._all_key())
        associations: List[Association] = []

        for association_id in all_ids:
            if isinstance(association_id, bytes):
                association_id = association_id.decode()
            association = self.get_by_id(association_id)
            if association:
                if status_filter and association.status != status_filter:
                    continue
                associations.append(association)

        # 排序
        associations.sort(key=lambda x: x.created_at, reverse=True)

        # 分頁
        total = len(associations)
        start = (page - 1) * limit
        end = start + limit
        return associations[start:end], total

    def get_stores(self, association_id: str | UUID) -> List[str]:
        """取得商圈下的所有商店 ID"""
        store_ids = self._redis.smembers(self._stores_key(association_id))
        result = []
        for store_id in store_ids:
            if isinstance(store_id, bytes):
                store_id = store_id.decode()
            result.append(store_id)
        return result


# ─────────────────────────────────────────────────────────
# SystemConfig Repository
# ─────────────────────────────────────────────────────────
class SystemConfigRepository(BaseRepository):
    """
    系統設定資料存取層。

    Redis 結構：
      - config:{key} => Hash（設定資料）
    """

    # 預設設定值
    DEFAULT_CONFIGS = {
        "max_balance_limit": {"value": "10000", "description": "最大餘額上限"},
        "max_allocation_limit": {"value": "1000", "description": "單次配額上限"},
        "default_page_size": {"value": "20", "description": "預設分頁大小"},
    }

    def _key(self, config_key: str) -> str:
        return f"config:{config_key}"

    def get(self, config_key: str) -> Optional[SystemConfig]:
        """取得系統設定"""
        key = self._key(config_key)
        data = self._redis.hgetall(key)

        if not data:
            # 如果沒有設定，返回預設值
            if config_key in self.DEFAULT_CONFIGS:
                default = self.DEFAULT_CONFIGS[config_key]
                return SystemConfig(
                    key=config_key,
                    value=default["value"],
                    description=default["description"],
                    updated_at=self._get_now(),
                )
            return None

        data = self._hash_to_dict(data)
        data["key"] = config_key
        if "updated_at" in data:
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        if "updated_by" in data and data["updated_by"]:
            data["updated_by"] = UUID(data["updated_by"])

        return SystemConfig(**data)

    def set(
        self,
        config_key: str,
        value: str,
        description: Optional[str] = None,
        updated_by: Optional[UUID] = None,
    ) -> SystemConfig:
        """設定系統設定"""
        now = self._get_now()
        key = self._key(config_key)

        config = SystemConfig(
            key=config_key,
            value=value,
            description=description,
            updated_by=updated_by,
            updated_at=now,
        )

        self._redis.hset(key, mapping=self._model_to_hash(config))
        return config

    def get_int(self, config_key: str, default: int = 0) -> int:
        """取得整數設定值"""
        config = self.get(config_key)
        if config:
            try:
                return int(config.value)
            except ValueError:
                pass
        return default

    def list_all(self) -> List[SystemConfig]:
        """列出所有系統設定"""
        configs: List[SystemConfig] = []

        # 取得所有設定 key
        keys = self._redis.keys("config:*")
        seen_keys = set()

        for key in keys:
            if isinstance(key, bytes):
                key = key.decode()
            config_key = key.replace("config:", "")
            seen_keys.add(config_key)
            config = self.get(config_key)
            if config:
                configs.append(config)

        # 加入未設定的預設值
        for default_key in self.DEFAULT_CONFIGS:
            if default_key not in seen_keys:
                config = self.get(default_key)
                if config:
                    configs.append(config)

        return configs
