from typing import Optional

from uuid import UUID
from pydantic import BaseModel


class User(BaseModel):
    id: UUID
    username: str
    password: str  # 建議存 hash
    role: str
    email: Optional[str] = None
