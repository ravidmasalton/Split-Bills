from pydantic import BaseModel, EmailStr
from typing import List, Optional, Dict
from datetime import datetime

class MemberInput(BaseModel):
    email: EmailStr

# מודל יצירת אירוע בלי מטבע
class EventCreate(BaseModel):
    name: str
    members: List[MemberInput]

# מודל מעודכן לחבר עם תמיכה במטבעות מרובים
class MemberOut(BaseModel):
    user_id: str
    email: EmailStr
    balance: float  # יתרה במטבע הבסיסי (לתאימות לאחור)
    currency_balances: Optional[Dict[str, float]] = {}  # יתרות לפי מטבע

# מודל מעודכן למשתתף בהוצאה
class ExpenseParticipant(BaseModel):
    user_id: str
    share: float

# מודל ישן להוצאה (לתאימות לאחור)
class Expense(BaseModel):
    payer_id: str
    amount: float
    note: Optional[str]
    participants: List[ExpenseParticipant]

# מודל חדש פשוט להוספת הוצאה
class SimpleExpense(BaseModel):
    amount: float
    currency: str
    participants: List[str]  # רשימת user_ids של המשתתפים
    payer_id: str  # מי שילם
    note: str = ""

# מודל להוצאה שמוחזרת מהמסד נתונים
class ExpenseOut(BaseModel):
    payer_id: str
    amount: float
    currency: str
    participants: List[ExpenseParticipant]
    note: Optional[str] = ""
    created_at: datetime

# מודל מעודכן לאירוע
class EventOut(BaseModel):
    id: str
    name: str
    currency: Optional[str] = None  
    created_by: str
    created_at: datetime
    members: List[MemberOut]
    expenses: List[ExpenseOut]

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
    currency_balances: Dict[str, Dict[str, float]]  # {user_id: {currency: balance}}
    payments_needed: List[Payment]  # תשלומים נדרשים
    total_expenses_by_currency: Dict[str, float]  # סך הוצאות לפי מטבע