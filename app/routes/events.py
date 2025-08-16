# ✅ app/routes/events.py
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
from bson import ObjectId
from app.models.event import EventCreate, EventOut, ExpenseOut, EventSummary
from app.db import db
from app.auth import get_current_user
from typing import List
from pydantic import BaseModel

router = APIRouter()
users_collection = db["users"]
events_collection = db["events"]

# מודל למשתתף עם חלק מותאם אישית
class ParticipantShare(BaseModel):
    email: str
    share: float  # כמה הוא משלם (לא אחוז!)

# מודל פשוט יותר להוספת הוצאה - עם אימיילים
class SimpleExpense(BaseModel):
    amount: float
    currency: str
    participants: List[str]  # רשימת אימיילים - חלוקה שווה
    note: str = ""

# מודל חדש להוצאה עם חלוקה מותאמת אישית
class CustomExpense(BaseModel):
    amount: float
    currency: str
    participants: List[ParticipantShare]  # רשימת משתתפים עם חלק מותאם אישית
    note: str = ""

# מודל לתשלום בין חברים
class Payment(BaseModel):
    from_user_id: str
    to_user_id: str
    amount: float
    currency: str

@router.post("/", response_model=EventOut)
def create_event(event: EventCreate, current_user: dict = Depends(get_current_user)):
    event_dict = {
        "name": event.name,
        "currency": None,  # יקבע לפי ההוצאה הראשונה
        "created_by": current_user["user_id"],
        "created_at": datetime.utcnow(),
        "expenses": [],
        "members": []
    }

    # 1. הוספת המשתמש שיוצר האירוע אוטומטית
    creator = users_collection.find_one({"_id": ObjectId(current_user["user_id"])})
    if creator:
        event_dict["members"].append({
            "user_id": current_user["user_id"],
            "email": creator["email"],
            "balance": 0.0,
            "currency_balances": {}
        })

    # 2. הוספת משתמשים נוספים לפי אימייל
    for member in event.members:
        user = users_collection.find_one({"email": member.email})
        if not user:
            raise HTTPException(status_code=404, detail=f"User {member.email} not found")

        # בדיקה שלא מוסיפים את היוצר פעמיים
        if str(user["_id"]) != current_user["user_id"]:
            event_dict["members"].append({
                "user_id": str(user["_id"]),
                "email": user["email"],
                "balance": 0.0,
                "currency_balances": {}
            })

    result = events_collection.insert_one(event_dict)
    event_dict["_id"] = str(result.inserted_id)

    return EventOut(id=event_dict["_id"], **event_dict)

@router.get("/{event_id}", response_model=EventOut)
def get_event(event_id: str, current_user: dict = Depends(get_current_user)):
    try:
        event = events_collection.find_one({"_id": ObjectId(event_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid ID format")

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # המרת ההוצאות לפורמט ExpenseOut
    expenses_out = []
    for expense in event.get("expenses", []):
        expenses_out.append(ExpenseOut(
            payer_id=expense["payer_id"],
            amount=expense["amount"],
            currency=expense.get("currency", event["currency"]),
            participants=expense["participants"],
            note=expense.get("note", ""),
            created_at=expense["created_at"]
        ))

    event["_id"] = str(event["_id"])
    event["expenses"] = expenses_out
    return EventOut(id=event["_id"], **event)

@router.post("/{event_id}/expenses/custom", response_model=EventOut)
def add_custom_expense(event_id: str, expense: CustomExpense, current_user: dict = Depends(get_current_user)):
    """הוספת הוצאה עם חלוקה מותאמת אישית"""
    try:
        event = events_collection.find_one({"_id": ObjectId(event_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid ID format")

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # בדיקה שהמשתמש הנוכחי חבר באירוע
    if current_user["user_id"] not in [m["user_id"] for m in event["members"]]:
        raise HTTPException(status_code=403, detail="You are not a member of this event")

    # המשתמש המחובר הוא המשלם אוטומטית
    payer_id = current_user["user_id"]

    # המרת אימיילים ל-user_ids ובדיקה שהם חברים באירוע
    participant_data = []
    event_member_emails = {m["email"]: m["user_id"] for m in event["members"]}
    total_shares = 0.0
    
    for participant in expense.participants:
        if participant.email not in event_member_emails:
            # בדיקה אם המשתמש קיים במערכת בכלל
            user = users_collection.find_one({"email": participant.email})
            if not user:
                raise HTTPException(
                    status_code=404, 
                    detail=f"User with email {participant.email} not found in system"
                )
            else:
                raise HTTPException(
                    status_code=400, 
                    detail=f"User {participant.email} is not a member of this event"
                )
        
        participant_data.append({
            "user_id": event_member_emails[participant.email],
            "email": participant.email,
            "share": participant.share
        })
        total_shares += participant.share

    # בדיקה שסכום החלקים שווה לסכום הכולל
    if abs(total_shares - expense.amount) > 0.01:  # מעט סובלנות לטעויות עגול
        raise HTTPException(
            status_code=400, 
            detail=f"Total shares ({total_shares}) must equal expense amount ({expense.amount})"
        )

    # וידוא שהמשלם (המשתמש המחובר) נכלל במשתתפים
    payer_found = any(p["user_id"] == payer_id for p in participant_data)
    if not payer_found:
        raise HTTPException(
            status_code=400, 
            detail="You must include yourself in the participants list"
        )

    # אם זו ההוצאה הראשונה, עדכן את מטבע האירוע
    if not event["expenses"] and event.get("currency") is None:
        event["currency"] = expense.currency

    # עדכון יתרות לפי החלוקה המותאמת אישית
    for participant in participant_data:
        user_id = participant["user_id"]
        share = participant["share"]
        
        for member in event["members"]:
            if member["user_id"] == user_id:
                if "currency_balances" not in member:
                    member["currency_balances"] = {}
                if expense.currency not in member["currency_balances"]:
                    member["currency_balances"][expense.currency] = 0.0
                
                member["currency_balances"][expense.currency] -= share
                if expense.currency == event["currency"]:
                    member["balance"] -= share
                break

    # המשלם (המשתמש המחובר) מקבל את כל הסכום
    for member in event["members"]:
        if member["user_id"] == payer_id:
            if "currency_balances" not in member:
                member["currency_balances"] = {}
            if expense.currency not in member["currency_balances"]:
                member["currency_balances"][expense.currency] = 0.0
                
            member["currency_balances"][expense.currency] += expense.amount
            if expense.currency == event["currency"]:
                member["balance"] += expense.amount
            break

    # הוספת ההוצאה לרשימה
    expense_record = {
        "payer_id": payer_id,
        "amount": expense.amount,
        "currency": expense.currency,
        "participants": [{"user_id": p["user_id"], "share": p["share"]} for p in participant_data],
        "note": expense.note,
        "created_at": datetime.utcnow()
    }
    
    event["expenses"].append(expense_record)

    # עדכון המסד נתונים
    events_collection.update_one(
        {"_id": ObjectId(event_id)},
        {"$set": {
            "currency": event["currency"],
            "members": event["members"],
            "expenses": event["expenses"]
        }}
    )

    event["_id"] = str(event["_id"])
    
    # המרת ההוצאות לפורמט ExpenseOut
    expenses_out = []
    for expense in event.get("expenses", []):
        expenses_out.append(ExpenseOut(
            payer_id=expense["payer_id"],
            amount=expense["amount"],
            currency=expense.get("currency", event["currency"]),
            participants=expense["participants"],
            note=expense.get("note", ""),
            created_at=expense["created_at"]
        ))
    
    event["expenses"] = expenses_out
    return EventOut(id=event["_id"], **event)

@router.post("/{event_id}/expenses", response_model=EventOut)
def add_expense(event_id: str, expense: SimpleExpense, current_user: dict = Depends(get_current_user)):
    try:
        event = events_collection.find_one({"_id": ObjectId(event_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid ID format")

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # בדיקה שהמשתמש הנוכחי חבר באירוع
    if current_user["user_id"] not in [m["user_id"] for m in event["members"]]:
        raise HTTPException(status_code=403, detail="You are not a member of this event")

    # המשתמש המחובר הוא המשלם אוטומטית
    payer_id = current_user["user_id"]

    # המרת אימיילים ל-user_ids ובדיקה שהם חברים באירוע
    participant_ids = []
    event_member_emails = {m["email"]: m["user_id"] for m in event["members"]}
    
    for email in expense.participants:
        if email not in event_member_emails:
            # בדיקה אם המשתמש קיים במערכת בכלל
            user = users_collection.find_one({"email": email})
            if not user:
                raise HTTPException(
                    status_code=404, 
                    detail=f"User with email {email} not found in system"
                )
            else:
                raise HTTPException(
                    status_code=400, 
                    detail=f"User {email} is not a member of this event"
                )
        
        participant_ids.append(event_member_emails[email])

    # וידוא שהמשלם (המשתמש המחובר) נכלל במשתתפים
    if payer_id not in participant_ids:
        raise HTTPException(
            status_code=400, 
            detail="You must include yourself in the participants list"
        )

    # אם זו ההוצאה הראשונה, עדכן את מטבע האירוע
    if not event["expenses"] and event.get("currency") is None:
        event["currency"] = expense.currency

    # חישוב כמה כל משתתף צריך לשלם (חלוקה שווה)
    share_per_person = expense.amount / len(participant_ids)

    # עדכון יתרות לפי מטבע - כל משתתף חייב את חלקו
    for participant_id in participant_ids:
        for member in event["members"]:
            if member["user_id"] == participant_id:
                if "currency_balances" not in member:
                    member["currency_balances"] = {}
                if expense.currency not in member["currency_balances"]:
                    member["currency_balances"][expense.currency] = 0.0
                
                member["currency_balances"][expense.currency] -= share_per_person
                if expense.currency == event["currency"]:
                    member["balance"] -= share_per_person
                break

    # המשלם (המשתמש המחובר) מקבל את כל הסכום
    for member in event["members"]:
        if member["user_id"] == payer_id:
            if "currency_balances" not in member:
                member["currency_balances"] = {}
            if expense.currency not in member["currency_balances"]:
                member["currency_balances"][expense.currency] = 0.0
                
            member["currency_balances"][expense.currency] += expense.amount
            if expense.currency == event["currency"]:
                member["balance"] += expense.amount
            break

    # הוספת ההוצאה לרשימה
    expense_record = {
        "payer_id": payer_id,
        "amount": expense.amount,
        "currency": expense.currency,
        "participants": [{"user_id": pid, "share": share_per_person} for pid in participant_ids],
        "note": expense.note,
        "created_at": datetime.utcnow()
    }
    
    event["expenses"].append(expense_record)

    # עדכון המסד נתונים
    events_collection.update_one(
        {"_id": ObjectId(event_id)},
        {"$set": {
            "currency": event["currency"],
            "members": event["members"],
            "expenses": event["expenses"]
        }}
    )

    event["_id"] = str(event["_id"])
    
    # המרת ההוצאות לפורמט ExpenseOut
    expenses_out = []
    for expense in event.get("expenses", []):
        expenses_out.append(ExpenseOut(
            payer_id=expense["payer_id"],
            amount=expense["amount"],
            currency=expense.get("currency", event["currency"]),
            participants=expense["participants"],
            note=expense.get("note", ""),
            created_at=expense["created_at"]
        ))
    
    event["expenses"] = expenses_out
    return EventOut(id=event["_id"], **event)

@router.get("/", response_model=List[EventOut])
def get_user_events(current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]

    events_cursor = events_collection.find({
        "$or": [
            {"created_by": user_id},
            {"members.user_id": user_id}
        ]
    })

    events = []
    for event in events_cursor:
        event["_id"] = str(event["_id"])
        
        # המרת ההוצאות לפורמט ExpenseOut
        expenses_out = []
        for expense in event.get("expenses", []):
            expenses_out.append(ExpenseOut(
                payer_id=expense["payer_id"],
                amount=expense["amount"],
                currency=expense.get("currency", event["currency"]),
                participants=expense["participants"],
                note=expense.get("note", ""),
                created_at=expense["created_at"]
            ))
        
        event["expenses"] = expenses_out
        events.append(EventOut(**event))

    return events

def calculate_payments_for_currency(members_balances: dict, currency: str) -> List[Payment]:
    """חישוב תשלומים נדרשים עבור מטבע ספציפי"""
    payments = []
    
    # יצירת רשימות חייבים ונושים
    debtors = []
    creditors = []
    
    for user_id, balance in members_balances.items():
        if balance < 0:
            debtors.append({"user_id": user_id, "amount": abs(balance)})
        elif balance > 0:
            creditors.append({"user_id": user_id, "amount": balance})
    
    # אלגוריתם פשוט לחישוב תשלומים מינימליים
    i, j = 0, 0
    while i < len(debtors) and j < len(creditors):
        debt_amount = debtors[i]["amount"]
        credit_amount = creditors[j]["amount"]
        
        payment_amount = min(debt_amount, credit_amount)
        
        payments.append(Payment(
            from_user_id=debtors[i]["user_id"],
            to_user_id=creditors[j]["user_id"],
            amount=round(payment_amount, 2),
            currency=currency
        ))
        
        debtors[i]["amount"] -= payment_amount
        creditors[j]["amount"] -= payment_amount
        
        if debtors[i]["amount"] == 0:
            i += 1
        if creditors[j]["amount"] == 0:
            j += 1
    
    return payments

@router.get("/{event_id}/summary", response_model=EventSummary)
def get_event_summary(event_id: str, current_user: dict = Depends(get_current_user)):
    """סיום אירוע - חישוב חובות וזכויות לפי מטבעות"""
    try:
        event = events_collection.find_one({"_id": ObjectId(event_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid ID format")

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # בדיקה שהמשתמש חבר באירוע
    if current_user["user_id"] not in [m["user_id"] for m in event["members"]]:
        raise HTTPException(status_code=403, detail="You are not a member of this event")

    # איסוף כל המטבעות והיתרות
    all_currencies = set()
    currency_balances = {}
    total_expenses_by_currency = {}

    # איסוף מטבעות מההוצאות
    for expense in event["expenses"]:
        currency = expense.get("currency", event["currency"])
        all_currencies.add(currency)
        
        if currency not in total_expenses_by_currency:
            total_expenses_by_currency[currency] = 0.0
        total_expenses_by_currency[currency] += expense["amount"]

    # איסוף יתרות החברים לפי מטבעות
    for member in event["members"]:
        user_id = member["user_id"]
        currency_balances[user_id] = {}
        
        if "currency_balances" in member:
            for currency in all_currencies:
                balance = member["currency_balances"].get(currency, 0.0)
                currency_balances[user_id][currency] = balance
        else:
            # תאימות לאחור
            for currency in all_currencies:
                if currency == event["currency"]:
                    currency_balances[user_id][currency] = member.get("balance", 0.0)
                else:
                    currency_balances[user_id][currency] = 0.0

    # חישוב תשלומים נדרשים לכל מטבע
    all_payments = []
    for currency in all_currencies:
        members_for_currency = {
            user_id: balances[currency] 
            for user_id, balances in currency_balances.items()
            if balances[currency] != 0
        }
        
        if members_for_currency:
            payments = calculate_payments_for_currency(members_for_currency, currency)
            all_payments.extend(payments)

    return EventSummary(
        event_id=str(event["_id"]),
        event_name=event["name"],
        currency_balances=currency_balances,
        payments_needed=all_payments,
        total_expenses_by_currency=total_expenses_by_currency
    )