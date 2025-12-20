"""
Shared authentication models and utilities
This module prevents circular imports between server.py and route modules
"""

from pydantic import BaseModel, Field, EmailStr
from enum import Enum
from typing import Optional, List
from datetime import datetime, timezone
import uuid

class UserRole(str, Enum):
    BUYER = "buyer"
    SELLER = "seller"
    ADMIN = "admin"

class UserStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    BANNED = "banned"

class User(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: EmailStr
    full_name: str
    phone: Optional[str] = None
    business_name: Optional[str] = None
    profile_picture: Optional[str] = None
    roles: List[UserRole] = Field(default_factory=list)
    status: UserStatus = UserStatus.PENDING
    province: Optional[str] = None
    city: Optional[str] = None
    farm_size: Optional[float] = None
    specialization: Optional[List[str]] = Field(default_factory=list)
    years_experience: Optional[int] = None
    certifications: Optional[List[str]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_login: Optional[datetime] = None
    is_verified: bool = False
    verification_token: Optional[str] = None

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    phone: Optional[str] = None
    role: Optional[UserRole] = None
    user_type: Optional[str] = "buyer"

class UserLogin(BaseModel):
    email: EmailStr
    password: str