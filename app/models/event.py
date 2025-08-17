from pydantic import BaseModel, EmailStr
from typing import List, Optional, Dict
from datetime import datetime

class MemberInput(BaseModel):
    email: EmailStr

# מודל יצירת אירוע עם מטבע בסיסי
class EventCreate(BaseModel):
    name: str
    base_currency: str  # מטבע בסיסי של האירוע
    members: List[MemberInput]

# מודל עדכון מטבע האירוע
class EventCurrencyUpdate(BaseModel):
    base_currency: str

class MemberOut(BaseModel):
    user_id: str
    email: EmailStr
    balance: float

# מודל למשתתף בהוצאה
class ExpenseParticipant(BaseModel):
    user_id: str
    share: float

# מודל פשוט להוספת הוצאה
class SimpleExpense(BaseModel):
    amount: float
    currency: str  # המטבע שבו שולמה ההוצאה
    participants: List[str]  # רשימת אימיילים של המשתתפים
    note: str = ""
    exchange_rate: Optional[float] = None  # שער חליפין (אם השתמש במטבע שונה מהבסיסי)

# מודל להוצאה עם חלוקה מותאמת אישית
class ParticipantShare(BaseModel):
    email: str
    share: float  # כמה הוא משלם במטבע המקורי

class CustomExpense(BaseModel):
    amount: float
    currency: str
    participants: List[ParticipantShare]
    note: str = ""
    exchange_rate: Optional[float] = None

# מודל להוצאה שמוחזרת מהמסד נתונים
class ExpenseOut(BaseModel):
    payer_id: str
    amount: float
    currency: str  # המטבע המקורי
    amount_in_base_currency: float  # הסכום במטבע הבסיסי
    participants: List[ExpenseParticipant]
    note: Optional[str] = ""
    exchange_rate: Optional[float] = None
    created_at: datetime

# מודל מעודכן לאירוע
class EventOut(BaseModel):
    id: str
    name: str
    base_currency: str  # מטבע בסיסי של האירוע
    created_by: str
    created_at: datetime
    members: List[MemberOut]
    expenses: List[ExpenseOut]
    total_expenses: float  # סך הוצאות במטבע הבסיסי

# מודל לתשלום בין חברים
class Payment(BaseModel):
    from_user_id: str
    to_user_id: str
    amount: float
    currency: str  # תמיד במטבע הבסיסי

# מודל לתוצאת סיום אירוע - פשוט יותר
class EventSummary(BaseModel):
    event_id: str
    event_name: str
    base_currency: str
    member_balances: Dict[str, float]  # {user_id: balance} במטבע הבסיסי
    payments_needed: List[Payment]  # תשלומים נדרשים
    total_expenses: float  # סך הוצאות במטבע הבסיסי

# מודל לקבלת שער חליפין
class ExchangeRateRequest(BaseModel):
    from_currency: str
    to_currency: str
    amount: float

class ExchangeRateResponse(BaseModel):
    from_currency: str
    to_currency: str
    rate: float
    converted_amount: float