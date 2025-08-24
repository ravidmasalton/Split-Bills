# ✅ app/models/event.py - מודלים מעודכנים עם שערי חליפין אוטומטיים
from pydantic import BaseModel, EmailStr, validator
from typing import List, Optional, Dict
from datetime import datetime

class MemberInput(BaseModel):
    email: EmailStr

# מודל יצירת אירוع רגיל עם מטבע בסיסי (לתאימות לאחור)
class EventCreate(BaseModel):
    name: str
    base_currency: str  # מטבע בסיסי של האירוע
    members: List[MemberInput]

# מודל פשוט ליצירת אירוע גמיש - רק שם וחברים
class FlexibleEventCreate(BaseModel):
    name: str
    members: List[dict]  # [{"email": "user@example.com"}]

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

# מודל למשתתף בהוצאה מתקדמת
class ParticipantExpense(BaseModel):
    email: str
    responsible_for: float  # על כמה הוא אחראי מהעלות הכוללת
    paid: float  # כמה הוא שילם בפועל

# מודל להוצאה מתקדמת - המודל הראשי
class FlexibleExpense(BaseModel):
    amount: float  # סך העלות הכוללת
    currency: str
    participants: List[ParticipantExpense]  # מי אחראי על כמה ומי שילם כמה
    note: str = ""
    
    @validator('currency')
    def validate_currency(cls, v):
        """בדיקת תקינות בסיסית למטבע"""
        v = v.upper().strip()
        
        if len(v) < 2 or len(v) > 4:
            raise ValueError("Currency code must be 2-4 characters")
            
        if not v.isalpha():
            raise ValueError("Currency code must contain only letters")
            
        return v

# מודל להוצאה עם חלוקה מותאמת אישית (תאימות לאחור)
class ParticipantShare(BaseModel):
    email: str
    share: float  # כמה הוא משלם במטבע המקורי

# מודל פשוט להוספת הוצאה עם חלוקה שווה (תאימות לאחור)
class SimpleExpense(BaseModel):
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
    base_currency: str  # מטבע בסיסי של האירוע או "FLEXIBLE"
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
    currency: str

# מודל לתוצאת סיום אירוע
class EventSummary(BaseModel):
    event_id: str
    event_name: str
    base_currency: str
    member_balances: Dict[str, float]  # {user_id: balance} במטבע הבסיסי
    payments_needed: List[Payment]  # תשלומים נדרשים
    total_expenses: float  # סך הוצאות במטבע הבסיסי

# מודלים חדשים לשערי חליפין אוטומטיים

class ExchangeRatesResponse(BaseModel):
    """תגובה לקבלת שערי חליפין"""
    base_currency: str
    rates: Dict[str, float]
    supported_currencies: List[str]
    last_updated: str

class EventCurrencyInfo(BaseModel):
    """מידע על מטבעות באירוע"""
    event_id: str
    event_name: str
    currencies_in_event: List[str]
    suggested_rates: Dict[str, float]
    base_currency: str
    total_expenses_by_currency: Dict[str, float]

class CurrencyConversionRequest(BaseModel):
    """בקשה להמרת מטבע"""
    amount: float
    from_currency: str
    to_currency: str

class CurrencyConversionResponse(BaseModel):
    """תגובה להמרת מטבע"""
    original_amount: float
    from_currency: str
    to_currency: str
    converted_amount: float
    exchange_rate: float
    last_updated: str

# מודלים ישנים שנשמרו לתאימות לאחור (אבל לא נשתמש בהם יותר)

class FinalCurrencyChoice(BaseModel):
    """מודל ישן - כעת לא נשתמש בו כי השערים אוטומטיים"""
    final_currency: str  # המטבע לחישוב החובות הסופיים
    exchange_rates: Dict[str, float]  # {"USD": 3.7, "EUR": 4.1} - שערי חליפין

class ExchangeRateRequest(BaseModel):
    """מודל ישן לבקשת שער חליפין"""
    from_currency: str
    to_currency: str
    amount: float

class ExchangeRateResponse(BaseModel):
    """מודל ישן לתגובת שער חליפין"""
    from_currency: str
    to_currency: str
    rate: float
    converted_amount: float