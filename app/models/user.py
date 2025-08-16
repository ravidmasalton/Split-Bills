from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime

# מודל להרשמה
class UserCreate(BaseModel):
    name: str = Field(..., min_length=2)
    email: EmailStr
    password: str = Field(..., min_length=6)

# מודל שמחזירים החוצה (בלי סיסמה)
class UserOut(BaseModel):
    id: str
    name: str
    email: EmailStr
    created_at: datetime

# מודל להתחברות
class UserLogin(BaseModel):
    email: EmailStr
    password: str
