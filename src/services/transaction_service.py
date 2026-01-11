# src/services/transaction_service.py
# 交易業務邏輯服務

from typing import Optional, Tuple
from uuid import UUID, uuid4

from src.db.models import (
    Transaction,
    TransactionCreate,
    TransactionStatus,
    HomelessPerson,
    Store,
    Status,
)
from src.db.repositories import (
    HomelessPersonRepository,
    StoreRepository,
    TransactionRepository,
    SystemConfigRepository,
    ProductRepository,
)


class TransactionError(Exception):
    """交易錯誤基礎類別"""

    def __init__(self, code: str, message: str, details: Optional[dict] = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


class InsufficientBalanceError(TransactionError):
    """餘額不足錯誤"""

    def __init__(self, current_balance: int, required: int):
        super().__init__(
            code="INSUFFICIENT_BALANCE",
            message="餘額不足",
            details={"current_balance": current_balance, "required": required},
        )


class HomelessNotFoundError(TransactionError):
    """找不到街友錯誤"""

    def __init__(self, qr_code: str):
        super().__init__(
            code="HOMELESS_NOT_FOUND",
            message="找不到該街友",
            details={"qr_code": qr_code},
        )


class StoreNotFoundError(TransactionError):
    """找不到商店錯誤"""

    def __init__(self, qr_code: str):
        super().__init__(
            code="STORE_NOT_FOUND",
            message="找不到該商店",
            details={"qr_code": qr_code},
        )


class HomelessInactiveError(TransactionError):
    """街友帳戶未啟用錯誤"""

    def __init__(self, homeless_id: str):
        super().__init__(
            code="HOMELESS_INACTIVE",
            message="街友帳戶已停用",
            details={"homeless_id": homeless_id},
        )


class StoreInactiveError(TransactionError):
    """商店未啟用錯誤"""

    def __init__(self, store_id: str):
        super().__init__(
            code="STORE_INACTIVE",
            message="商店已停用",
            details={"store_id": store_id},
        )


class ProductInactiveError(TransactionError):
    """商品已下架錯誤"""

    def __init__(self, product_id: str):
        super().__init__(
            code="PRODUCT_INACTIVE",
            message="該商品已下架",
            details={"product_id": product_id},
        )


class TransactionLockError(TransactionError):
    """交易鎖定錯誤（並發交易）"""

    def __init__(self, homeless_id: str):
        super().__init__(
            code="TRANSACTION_LOCKED",
            message="該帳戶正在進行其他交易，請稍後再試",
            details={"homeless_id": homeless_id},
        )


class TransactionService:
    """
    交易服務。

    負責處理街友與商店間的點數交易，包含：
    - 悲觀鎖定（防止並發交易）
    - 餘額驗證
    - 原子性扣款與商店收入增加
    """

    def __init__(self):
        self.homeless_repo = HomelessPersonRepository()
        self.store_repo = StoreRepository()
        self.transaction_repo = TransactionRepository()
        self.config_repo = SystemConfigRepository()
        self.product_repo = ProductRepository()

    def create_transaction(self, data: TransactionCreate) -> Transaction:
        """
        建立交易。

        流程：
        1. 驗證街友 QR Code
        2. 驗證商店 QR Code
        3. 取得街友帳戶鎖定（悲觀鎖定）
        4. 驗證餘額
        5. 扣除餘額
        6. 增加商店收入
        7. 建立交易記錄
        8. 釋放鎖定

        Args:
            data: 交易建立請求

        Returns:
            完成的交易記錄

        Raises:
            HomelessNotFoundError: 找不到街友
            StoreNotFoundError: 找不到商店
            HomelessInactiveError: 街友帳戶已停用
            StoreInactiveError: 商店已停用
            InsufficientBalanceError: 餘額不足
            TransactionLockError: 無法取得鎖定
        """
        # 1. 驗證街友
        homeless = self.homeless_repo.get_by_qr_code(data.homeless_qr_code)
        if not homeless:
            raise HomelessNotFoundError(data.homeless_qr_code)
        if homeless.status != Status.ACTIVE:
            raise HomelessInactiveError(str(homeless.id))

        # 2. 驗證商店
        store = self.store_repo.get_by_qr_code(data.store_qr_code)
        if not store:
            raise StoreNotFoundError(data.store_qr_code)
        if store.status != Status.ACTIVE:
            raise StoreInactiveError(str(store.id))

        # 3. 驗證商品狀態（如果有指定商品）
        if data.product_id:
            product = self.product_repo.get_by_id(data.product_id)
            if product and product.status != Status.ACTIVE:
                raise ProductInactiveError(str(data.product_id))

        # 4. 取得鎖定
        if not self.homeless_repo.acquire_lock(homeless.id, timeout=30):
            raise TransactionLockError(str(homeless.id))

        try:
            # 重新讀取最新餘額（鎖定後）
            homeless = self.homeless_repo.get_by_id(homeless.id)
            if not homeless:
                raise HomelessNotFoundError(data.homeless_qr_code)

            balance_before = homeless.balance
            balance_after = balance_before - data.amount

            # 4. 驗證餘額
            if balance_after < 0:
                raise InsufficientBalanceError(
                    current_balance=balance_before,
                    required=data.amount,
                )

            # 5. 扣除餘額
            self.homeless_repo.update_balance(homeless.id, balance_after)

            # 6. 增加商店收入
            self.store_repo.update_income(store.id, data.amount)

            # 7. 建立交易記錄
            tx_id = uuid4()
            transaction = self.transaction_repo.create(
                tx_id=tx_id,
                homeless_id=homeless.id,
                homeless_qr_code=data.homeless_qr_code,
                store_id=store.id,
                store_qr_code=data.store_qr_code,
                product_id=data.product_id,
                product_name=data.product_name,
                amount=data.amount,
                balance_before=balance_before,
                balance_after=balance_after,
                status=TransactionStatus.COMPLETED,
            )

            return transaction

        except Exception as e:
            # 如果發生錯誤，建立失敗的交易記錄（如果可能）
            if isinstance(e, TransactionError):
                raise
            # 其他未預期的錯誤
            raise
        finally:
            # 8. 釋放鎖定
            self.homeless_repo.release_lock(homeless.id)

    def get_transaction(self, tx_id: UUID) -> Optional[Transaction]:
        """取得交易記錄"""
        return self.transaction_repo.get_by_id(tx_id)

    def validate_homeless(self, qr_code: str) -> Tuple[HomelessPerson, bool]:
        """
        驗證街友 QR Code。

        Returns:
            (街友資料, 是否可交易)
        """
        homeless = self.homeless_repo.get_by_qr_code(qr_code)
        if not homeless:
            raise HomelessNotFoundError(qr_code)
        can_transact = homeless.status == Status.ACTIVE
        return homeless, can_transact

    def validate_store(self, qr_code: str) -> Tuple[Store, bool]:
        """
        驗證商店 QR Code。

        Returns:
            (商店資料, 是否可交易)
        """
        store = self.store_repo.get_by_qr_code(qr_code)
        if not store:
            raise StoreNotFoundError(qr_code)
        can_transact = store.status == Status.ACTIVE
        return store, can_transact
