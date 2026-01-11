# src/db/models.py
# 資料模型定義 - Homeless Donation Management Platform

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator
import re


# ─────────────────────────────────────────────────────────
# Enums（列舉類型）
# ─────────────────────────────────────────────────────────
class UserRole(str, Enum):
    """使用者角色"""
    SYSTEM_ADMIN = "system_admin"
    NGO_ADMIN = "ngo_admin"
    NGO_PARTNER = "ngo_partner"
    STORE = "store"
    HOMELESS = "homeless"
    ASSOCIATION_ADMIN = "association_admin"
    ASSOCIATION_PARTNER = "association_partner"


class Status(str, Enum):
    """通用狀態"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class ProductCategory(str, Enum):
    """產品類別"""
    MEALS = "meals"                       # 餐點
    SERVICES = "services"                 # 服務
    DAILY_NECESSITIES = "daily_necessities"  # 生活用品
    MEDICAL = "medical"                   # 醫療
    OTHER = "other"                       # 其他


class TransactionStatus(str, Enum):
    """交易狀態"""
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ─────────────────────────────────────────────────────────
# User Models（使用者）
# ─────────────────────────────────────────────────────────
class UserBase(BaseModel):
    """使用者基礎欄位"""
    username: str = Field(..., min_length=3, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    role: UserRole
    email: Optional[str] = None
    phone: Optional[str] = None


class UserCreate(UserBase):
    """建立使用者請求"""
    password: str = Field(..., min_length=6)
    store_id: Optional[UUID] = None
    homeless_id: Optional[UUID] = None
    association_id: Optional[UUID] = None


class User(UserBase):
    """完整使用者資料"""
    id: UUID
    password: str  # bcrypt 雜湊後的密碼
    status: Status = Status.ACTIVE
    store_id: Optional[UUID] = None
    homeless_id: Optional[UUID] = None
    association_id: Optional[UUID] = None
    last_login_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserResponse(BaseModel):
    """使用者回應（不含密碼）"""
    id: UUID
    username: str
    name: str
    role: UserRole
    email: Optional[str] = None
    phone: Optional[str] = None
    status: Status
    store_id: Optional[UUID] = None
    homeless_id: Optional[UUID] = None
    association_id: Optional[UUID] = None
    last_login_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


# ─────────────────────────────────────────────────────────
# HomelessPerson Models（街友）
# ─────────────────────────────────────────────────────────
class HomelessPersonBase(BaseModel):
    """街友基礎欄位"""
    name: str = Field(..., min_length=1, max_length=100)
    id_number: str = Field(..., pattern=r"^[A-Z][12]\d{8}$")
    phone: Optional[str] = None
    address: Optional[str] = None
    emergency_contact: Optional[str] = None
    emergency_phone: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("id_number")
    @classmethod
    def validate_taiwan_id(cls, v: str) -> str:
        """驗證台灣身分證字號格式"""
        if not re.match(r"^[A-Z][12]\d{8}$", v):
            raise ValueError("身分證字號格式不正確")
        return v.upper()

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        """驗證手機號碼格式（台灣手機 09 開頭 10 位數）"""
        if v is not None and v != "" and not re.match(r"^09\d{8}$", v):
            raise ValueError("手機號碼格式不正確（需為 09 開頭的 10 位數字）")
        return v if v else None

    @field_validator("emergency_phone")
    @classmethod
    def validate_emergency_phone(cls, v: Optional[str]) -> Optional[str]:
        """驗證緊急聯絡電話格式（8-10 位數字）"""
        if v is not None and v != "" and not re.match(r"^\d{8,10}$", v):
            raise ValueError("緊急聯絡電話格式不正確（需為 8-10 位數字）")
        return v if v else None


class HomelessPersonCreate(HomelessPersonBase):
    """建立街友請求"""
    pass


class HomelessPersonUpdate(BaseModel):
    """更新街友請求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    id_number: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    emergency_contact: Optional[str] = None
    emergency_phone: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[Status] = None

    @field_validator("id_number")
    @classmethod
    def validate_id_number(cls, v: Optional[str]) -> Optional[str]:
        """驗證台灣身分證字號格式"""
        if v is not None and v != "" and not re.match(r"^[A-Z][12]\d{8}$", v):
            raise ValueError("身分證字號格式不正確")
        return v.upper() if v else None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        """驗證手機號碼格式"""
        if v is not None and v != "" and not re.match(r"^09\d{8}$", v):
            raise ValueError("手機號碼格式不正確（需為 09 開頭的 10 位數字）")
        return v if v else None

    @field_validator("emergency_phone")
    @classmethod
    def validate_emergency_phone(cls, v: Optional[str]) -> Optional[str]:
        """驗證緊急聯絡電話格式"""
        if v is not None and v != "" and not re.match(r"^\d{8,10}$", v):
            raise ValueError("緊急聯絡電話格式不正確（需為 8-10 位數字）")
        return v if v else None


class HomelessPerson(HomelessPersonBase):
    """完整街友資料"""
    id: UUID
    qr_code: str
    balance: int = 0
    photo_url: Optional[str] = None
    status: Status = Status.ACTIVE
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────
# Store Models（商店）
# ─────────────────────────────────────────────────────────
class StoreBase(BaseModel):
    """商店基礎欄位"""
    name: str = Field(..., min_length=1, max_length=100)
    category: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    association_id: Optional[UUID] = None


class StoreCreate(StoreBase):
    """建立商店請求"""
    pass


class StoreUpdate(BaseModel):
    """更新商店請求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    category: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    association_id: Optional[UUID] = None
    status: Optional[Status] = None


class Store(StoreBase):
    """完整商店資料"""
    id: UUID
    qr_code: str
    total_income: int = 0
    status: Status = Status.ACTIVE
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────
# Product Models（產品）
# ─────────────────────────────────────────────────────────
class ProductBase(BaseModel):
    """產品基礎欄位"""
    name: str = Field(..., min_length=1, max_length=100)
    points: int = Field(..., gt=0)
    category: ProductCategory
    description: Optional[str] = None


class ProductCreate(ProductBase):
    """建立產品請求（store_id 從路徑取得）"""
    pass


class ProductUpdate(BaseModel):
    """更新產品請求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    points: Optional[int] = Field(None, gt=0)
    category: Optional[ProductCategory] = None
    description: Optional[str] = None
    status: Optional[Status] = None


class Product(ProductBase):
    """完整產品資料"""
    id: UUID
    store_id: UUID
    status: Status = Status.ACTIVE
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────
# Transaction Models（交易）
# ─────────────────────────────────────────────────────────
class TransactionCreate(BaseModel):
    """建立交易請求"""
    homeless_qr_code: str
    store_qr_code: str
    product_id: Optional[UUID] = None
    product_name: str
    amount: int = Field(..., gt=0)


class Transaction(BaseModel):
    """完整交易資料"""
    id: UUID
    homeless_id: UUID
    homeless_qr_code: str
    store_id: UUID
    store_qr_code: str
    product_id: Optional[UUID] = None
    product_name: str
    amount: int
    balance_before: int
    balance_after: int
    status: TransactionStatus
    created_at: datetime

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────
# Allocation Models（點數配額）
# ─────────────────────────────────────────────────────────
class AllocationCreate(BaseModel):
    """建立配額請求"""
    homeless_id: UUID
    amount: int = Field(..., gt=0)
    notes: Optional[str] = None


class Allocation(BaseModel):
    """完整配額資料"""
    id: UUID
    homeless_id: UUID
    admin_id: UUID
    amount: int
    balance_before: int
    balance_after: int
    notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────
# Association Models（商圈）
# ─────────────────────────────────────────────────────────
class AssociationBase(BaseModel):
    """商圈基礎欄位"""
    name: str = Field(..., min_length=1, max_length=100)
    district: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None


class AssociationCreate(AssociationBase):
    """建立商圈請求"""
    pass


class AssociationUpdate(BaseModel):
    """更新商圈請求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    district: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    status: Optional[Status] = None


class Association(AssociationBase):
    """完整商圈資料"""
    id: UUID
    status: Status = Status.ACTIVE
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────
# SystemConfig Models（系統設定）
# ─────────────────────────────────────────────────────────
class SystemConfigUpdate(BaseModel):
    """更新系統設定請求"""
    value: str
    description: Optional[str] = None


class SystemConfig(BaseModel):
    """完整系統設定資料"""
    key: str
    value: str
    description: Optional[str] = None
    updated_by: Optional[UUID] = None
    updated_at: datetime

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────
# API Response Models（API 回應）
# ─────────────────────────────────────────────────────────
class PaginationMeta(BaseModel):
    """分頁資訊"""
    page: int
    limit: int
    total: int
    total_pages: int


class PaginatedResponse(BaseModel):
    """分頁回應"""
    success: bool = True
    data: list
    meta: PaginationMeta
