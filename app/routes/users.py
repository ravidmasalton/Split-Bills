# ✅ app/routes/users.py - ללא bcrypt
from fastapi import APIRouter, HTTPException, Depends
from app.models.user import UserCreate, UserLogin, UserOut
from app.services.db import db
from datetime import datetime
from app.services.auth import create_access_token, get_current_user
from bson import ObjectId
from typing import List
import hashlib
import secrets

router = APIRouter()

users_collection = db["users"]

def hash_password(password: str) -> str:
    """Hash password - פשוט ובטוח"""
    salt = secrets.token_hex(16)
    password_hash = hashlib.sha256((password + salt).encode()).hexdigest()
    return f"{password_hash}:{salt}"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password"""
    try:
        password_hash, salt = hashed_password.split(":")
        test_hash = hashlib.sha256((plain_password + salt).encode()).hexdigest()
        return password_hash == test_hash
    except:
        return False

@router.post("/register", response_model=UserOut)
def register(user: UserCreate):
    # בדיקה אם המשתמש קיים
    if users_collection.find_one({"email": user.email}):
        raise HTTPException(status_code=400, detail="Email already registered")

    # Hash password
    hashed_password = hash_password(user.password)
    
    user_dict = {
        "name": user.name,
        "email": user.email,
        "password_hash": hashed_password,
        "created_at": datetime.utcnow()
    }
    
    result = users_collection.insert_one(user_dict)
    
    return UserOut(
        id=str(result.inserted_id),
        name=user.name,
        email=user.email,
        created_at=user_dict["created_at"]
    )

@router.post("/login")
def login(user: UserLogin):
    # מצא משתמש
    db_user = users_collection.find_one({"email": user.email})
    
    # בדוק סיסמה
    if not db_user or not verify_password(user.password, db_user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # צור token
    token = create_access_token(
        data={"user_id": str(db_user["_id"]), "email": db_user["email"]}
    )
    
    return {"access_token": token, "token_type": "bearer"}

@router.get("/me", response_model=UserOut)
def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """קבלת פרטי המשתמש המחובר"""
    try:
        user = users_collection.find_one({"_id": ObjectId(current_user["user_id"])})
    except:
        raise HTTPException(status_code=400, detail="Invalid user ID")
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return UserOut(
        id=str(user["_id"]),
        name=user["name"],
        email=user["email"],
        created_at=user["created_at"]
    )

@router.get("/", response_model=List[UserOut])
def get_all_users(current_user: dict = Depends(get_current_user)):
    """קבלת כל המשתמשים (לבחירה באירועים)"""
    users = []
    for user in users_collection.find({}, {"password_hash": 0}):  # בלי החזרת הסיסמה
        users.append(UserOut(
            id=str(user["_id"]),
            name=user["name"],
            email=user["email"],
            created_at=user["created_at"]
        ))
    return users