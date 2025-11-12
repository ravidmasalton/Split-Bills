# ✅ app/routes/events.py - גרסה מתקדמת עם תשלומים + אחראיות + שערי חליפין אוטומטיים
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
from bson import ObjectId
from app.models.event import (
    FlexibleEventCreate, 
    EventOut, 
    ExpenseOut, 
    EventSummary,
    FlexibleExpense,
    Payment
)
from app.services.db import db
from app.services.auth import get_current_user
from app.services.simple_exchange_rates import exchange_service
from typing import List, Dict

router = APIRouter()
users_collection = db["users"]
events_collection = db["events"]

@router.post("/", response_model=EventOut)
def create_event(event: FlexibleEventCreate, current_user: dict = Depends(get_current_user)):
    """יצירת אירוע גמיש - בלי מטבע קבוע כלל"""
    
    # יצירת האירוע בלי מטבע
    event_dict = {
        "name": event.name,
        "base_currency": None,  # לא קובעים מטבע!
        "created_by": current_user["user_id"],
        "created_at": datetime.utcnow(),
        "expenses": [],
        "members": [],
        "currency_balances": {},  # יתרות לפי מטבעות: {"USD": {"user1": 10}, "EUR": {"user2": -5}}
        "total_expenses_by_currency": {}  # סכומים לפי מטבע: {"USD": 100, "EUR": 50}
    }

    # 1. הוספת המשתמש שיוצר האירוע
    creator = users_collection.find_one({"_id": ObjectId(current_user["user_id"])})
    if not creator:
        raise HTTPException(status_code=404, detail="Creator user not found")
        
    event_dict["members"].append({
        "user_id": current_user["user_id"],
        "email": creator["email"]
    })

    # 2. הוספת משתמשים נוספים
    for member in event.members:
        user = users_collection.find_one({"email": member["email"]})
        if not user:
            raise HTTPException(status_code=404, detail=f"User {member['email']} not found")

        if str(user["_id"]) != current_user["user_id"]:
            event_dict["members"].append({
                "user_id": str(user["_id"]),
                "email": user["email"]
            })

    try:
        result = events_collection.insert_one(event_dict)
        event_dict["_id"] = str(result.inserted_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    # החזרת האירוע
    return EventOut(
        id=event_dict["_id"],
        name=event_dict["name"],
        base_currency="FLEXIBLE",  # סימן שזה גמיש
        created_by=event_dict["created_by"],
        created_at=event_dict["created_at"],
        members=[{"user_id": m["user_id"], "email": m["email"], "balance": 0.0} for m in event_dict["members"]],
        expenses=[],
        total_expenses=0.0
    )

@router.post("/{event_id}/expenses", response_model=EventOut)
def add_flexible_expense(event_id: str, expense: FlexibleExpense, current_user: dict = Depends(get_current_user)):
    """הוספת הוצאה מתקדמת - מי שילם בפועל VS מי אחראי על מה"""
    
    try:
        event = events_collection.find_one({"_id": ObjectId(event_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid ID format")

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # בדיקה שהמשתמש חבר באירוע
    if current_user["user_id"] not in [m["user_id"] for m in event["members"]]:
        raise HTTPException(status_code=403, detail="You are not a member of this event")

    # בדיקת תקינות 1: סכום האחראיות = הסכום הכללי
    total_responsibility = sum(p.responsible_for for p in expense.participants)
    if abs(total_responsibility - expense.amount) > 0.01:
        raise HTTPException(
            status_code=400,
            detail=f"Sum of responsibilities ({total_responsibility}) must equal total amount ({expense.amount})"
        )
    
    # בדיקת תקינות 2: סכום התשלומים = הסכום הכללי
    total_paid = sum(p.paid for p in expense.participants)
    if abs(total_paid - expense.amount) > 0.01:
        raise HTTPException(
            status_code=400,
            detail=f"Sum of payments ({total_paid}) must equal total amount ({expense.amount})"
        )

    # המרת אימיילים ל-user_ids ובדיקת חברות
    participant_data = []
    event_member_emails = {m["email"]: m["user_id"] for m in event["members"]}
    
    current_user_included = False
    for participant in expense.participants:
        if participant.email not in event_member_emails:
            raise HTTPException(status_code=400, detail=f"User {participant.email} is not a member of this event")
        
        user_id = event_member_emails[participant.email]
        participant_data.append({
            "user_id": user_id,
            "email": participant.email,
            "responsible_for": participant.responsible_for,
            "paid": participant.paid
        })
        
        if user_id == current_user["user_id"]:
            current_user_included = True

    if not current_user_included:
        raise HTTPException(status_code=400, detail="You must include yourself in the participants list")

    # עדכון יתרות לפי מטבע
    if "currency_balances" not in event:
        event["currency_balances"] = {}
    
    if expense.currency not in event["currency_balances"]:
        event["currency_balances"][expense.currency] = {}

    # חישוב ועדכון יתרות
    for participant in participant_data:
        user_id = participant["user_id"]
        responsible_for = participant["responsible_for"]
        paid = participant["paid"]
        
        if user_id not in event["currency_balances"][expense.currency]:
            event["currency_balances"][expense.currency][user_id] = 0.0
        
        # יתרה = מה ששילם - מה שהוא אחראי עליו
        balance_change = paid - responsible_for
        event["currency_balances"][expense.currency][user_id] += balance_change

    # עדכון סך הוצאות לפי מטבע
    if "total_expenses_by_currency" not in event:
        event["total_expenses_by_currency"] = {}
    
    if expense.currency not in event["total_expenses_by_currency"]:
        event["total_expenses_by_currency"][expense.currency] = 0.0
    
    event["total_expenses_by_currency"][expense.currency] += expense.amount

    # הוספת ההוצאה עם כל המידע
    expense_record = {
        "created_by": current_user["user_id"],
        "amount": expense.amount,
        "currency": expense.currency,
        "participants": participant_data,
        "note": expense.note,
        "expense_type": "advanced",  # סימון שזו הוצאה מתקדמת
        "created_at": datetime.utcnow()
    }
    
    event["expenses"].append(expense_record)

    # עדכון המסד נתונים
    events_collection.update_one(
        {"_id": ObjectId(event_id)},
        {"$set": {
            "currency_balances": event["currency_balances"],
            "total_expenses_by_currency": event["total_expenses_by_currency"],
            "expenses": event["expenses"]
        }}
    )

    # החזרת האירוע המעודכן
    event["_id"] = str(event["_id"])
    
    expenses_out = []
    for exp in event["expenses"]:
        # התאמה למבנה ExpenseOut
        participants_for_output = []
        for p in exp["participants"]:
            if "paid" in p and "responsible_for" in p:
                # הוצאה מתקדמת - שמור את כל הנתונים
                participants_for_output.append({
                    "user_id": p["user_id"],
                    "share": p["paid"],
                    "responsible_for": p["responsible_for"],
                    "paid": p["paid"]
                })
            elif "share" in p:
                # הוצאה ישנה
                participants_for_output.append({
                    "user_id": p["user_id"],
                    "share": p["share"]
                })
            else:
                # fallback
                participants_for_output.append({
                    "user_id": p.get("user_id", ""),
                    "share": 0.0
                })
        
        expenses_out.append(ExpenseOut(
            payer_id=exp.get("created_by", exp.get("payer_id", "")),
            amount=exp["amount"],
            currency=exp["currency"],
            amount_in_base_currency=exp["amount"],
            participants=participants_for_output,
            note=exp.get("note", ""),
            exchange_rate=None,
            created_at=exp["created_at"]
        ))
    
    return EventOut(
        id=event["_id"],
        name=event["name"],
        base_currency="FLEXIBLE",
        created_by=event["created_by"],
        created_at=event["created_at"],
        members=[{"user_id": m["user_id"], "email": m["email"], "balance": 0.0} for m in event["members"]],
        expenses=expenses_out,
        total_expenses=0.0
    )



@router.get("/my-events")
def get_my_events(current_user: dict = Depends(get_current_user)):
    try:
        user_id = current_user["user_id"]
        conds = [
            {"created_by": user_id},
            {"members.user_id": user_id},
        ]

        # אם ה-user_id נראה כמו ObjectId תקף, נצרף תנאים גם ל-ObjectId
        if ObjectId.is_valid(user_id):
            user_oid = ObjectId(user_id)
            conds.extend([
                {"created_by": user_oid},
                {"members.user_id": user_oid},
            ])

        events_cursor = events_collection.find({"$or": conds}).sort("created_at", -1)

        events_list = []
        for event in events_cursor:
            events_list.append({
                "id": str(event["_id"]),
                "name": event.get("name", "Unknown"),
                # הפוך ל-str אם יושב כ-ObjectId באירועים ישנים
                "created_by": str(event.get("created_by")) if event.get("created_by") is not None else None,
                "created_at": str(event.get("created_at")),
                "members": event.get("members", []),
                "expenses_count": len(event.get("expenses", [])),
                # היזהר מערך None – אם יש סיכוי ל-None, אפשר לעשות or "FLEXIBLE"
                "base_currency": (event.get("base_currency") or "FLEXIBLE"),
            })

        return {
            "user_id": user_id,
            "events_count": len(events_list),
            "events": events_list
        }

    except Exception as e:
        import traceback
        return {
            "error": str(e),
            "traceback": traceback.format_exc()[:1000],
            "user_id": current_user.get("user_id", "NO_USER_ID")
        }
    


@router.get("/{event_id}", response_model=EventOut)
def get_event(event_id: str, current_user: dict = Depends(get_current_user)):
    try:
        event = events_collection.find_one({"_id": ObjectId(event_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid ID format")

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    event["_id"] = str(event["_id"])

    expenses_out = []
    for expense in event.get("expenses", []):
        participants_for_output = []
        for p in expense.get("participants", []):
            if "paid" in p and "responsible_for" in p:
                participants_for_output.append({
                    "user_id": p["user_id"],
                    "share": p["paid"],
                    "responsible_for": p["responsible_for"],
                    "paid": p["paid"]
                })
            elif "share" in p:
                participants_for_output.append({"user_id": p["user_id"], "share": p["share"]})
            else:
                participants_for_output.append({"user_id": p.get("user_id", ""), "share": 0.0})

        expenses_out.append(ExpenseOut(
            payer_id=expense.get("created_by", expense.get("payer_id", "")),
            amount=expense["amount"],
            currency=expense["currency"],
            amount_in_base_currency=expense["amount"],
            participants=participants_for_output,
            note=expense.get("note", ""),
            exchange_rate=None,
            created_at=expense.get("created_at", datetime.utcnow())
        ))

    base_currency = event.get("base_currency") or "FLEXIBLE"

    return EventOut(
        id=event["_id"],
        name=event["name"],
        base_currency=base_currency,
        created_by=event["created_by"],
        created_at=event["created_at"],
        members=[{"user_id": m["user_id"], "email": m["email"], "balance": 0.0} for m in event["members"]],
        expenses=expenses_out,
        total_expenses=0.0
    )


@router.post("/{event_id}/finalize", response_model=EventSummary)
def finalize_event(event_id: str, final_currency: str, current_user: dict = Depends(get_current_user)):
    """סיום האירוע עם שערי חליפין אוטומטיים"""
    
    try:
        event = events_collection.find_one({"_id": ObjectId(event_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid ID format")

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    if current_user["user_id"] not in [m["user_id"] for m in event["members"]]:
        raise HTTPException(status_code=403, detail="You are not a member of this event")

    # קבלת שערים אוטומטית
    try:
        current_rates = exchange_service.get_rates()
        print(f"Got rates: {current_rates}")
        
        # חישוב שערי המרה לפי המטבע הסופי הנבחר
        exchange_rates = {}
        
        for currency in event.get("total_expenses_by_currency", {}).keys():
            if currency != final_currency:
                if final_currency == "USD":
                    # המרה למטבע היעד USD
                    if currency in current_rates:
                        exchange_rates[currency] = 1 / current_rates[currency]
                    else:
                        raise HTTPException(status_code=400, detail=f"Currency {currency} not supported")
                        
                elif currency == "USD":
                    # המרה מ-USD למטבע היעד
                    if final_currency in current_rates:
                        exchange_rates[currency] = current_rates[final_currency]
                    else:
                        raise HTTPException(status_code=400, detail=f"Target currency {final_currency} not supported")
                        
                else:
                    # המרה בין שני מטבעות זרים דרך USD
                    if currency in current_rates and final_currency in current_rates:
                        usd_rate = 1 / current_rates[currency]
                        target_rate = current_rates[final_currency]
                        exchange_rates[currency] = usd_rate * target_rate
                    else:
                        raise HTTPException(status_code=400, detail=f"Currency conversion not supported: {currency} -> {final_currency}")
        
        print(f"Calculated exchange rates: {exchange_rates}")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get exchange rates: {str(e)}")

    # חישוב יתרות סופיות במטבע הנבחר
    final_balances = {}
    total_expenses_final = 0.0

    # איתחול יתרות
    for member in event["members"]:
        final_balances[member["user_id"]] = 0.0

    # המרת יתרות מכל מטבע למטבע הסופי
    for currency, balances in event.get("currency_balances", {}).items():
        rate = 1.0  # אם זה אותו מטבע
        
        if currency != final_currency:
            if currency not in exchange_rates:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Missing exchange rate for {currency} to {final_currency}"
                )
            rate = exchange_rates[currency]

        for user_id, balance in balances.items():
            converted_balance = balance * rate
            final_balances[user_id] += converted_balance

    # חישוב סך הוצאות במטבע הסופי
    for currency, total in event.get("total_expenses_by_currency", {}).items():
        rate = 1.0 if currency == final_currency else exchange_rates.get(currency, 1.0)
        total_expenses_final += total * rate

    # חישוב תשלומים נדרשים
    payments = []
    debtors = [(uid, abs(balance)) for uid, balance in final_balances.items() if balance < -0.01]
    creditors = [(uid, balance) for uid, balance in final_balances.items() if balance > 0.01]
    
    for debtor_id, debt in debtors:
        for creditor_id, credit in creditors:
            if debt > 0.01 and credit > 0.01:
                payment_amount = min(debt, credit)
                payments.append(Payment(
                    from_user_id=debtor_id,
                    to_user_id=creditor_id,
                    amount=round(payment_amount, 2),
                    currency=final_currency
                ))
                debt -= payment_amount
                credit -= payment_amount

    # שמירת התוצאות הסופיות
    events_collection.update_one(
        {"_id": ObjectId(event_id)},
        {"$set": {
            "base_currency": final_currency,
            "final_balances": final_balances,
            "final_payments": [p.dict() for p in payments],
            "exchange_rates_used": exchange_rates,
            "finalized_at": datetime.utcnow()
        }}
    )

    return EventSummary(
        event_id=str(event["_id"]),
        event_name=event["name"],
        base_currency=final_currency,
        member_balances=final_balances,
        payments_needed=payments,
        total_expenses=round(total_expenses_final, 2)
    )

@router.delete("/{event_id}")
def delete_event(event_id: str, current_user: dict = Depends(get_current_user)):
    """Delete an event if the current user is the creator"""
    
    try:
        event = events_collection.find_one({"_id": ObjectId(event_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid ID format")

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    if event["created_by"] != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Only the creator can delete this event")

    events_collection.delete_one({"_id": ObjectId(event_id)})

    return {"message": "Event deleted successfully", "event_id": event_id}


@router.delete("/{event_id}/expenses/{expense_index}")
def delete_expense(
    event_id: str, 
    expense_index: int, 
    current_user: dict = Depends(get_current_user)
):
    """Delete an expense and reverse its balance changes"""
    
    try:
        event = events_collection.find_one({"_id": ObjectId(event_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid ID format")

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Check user is a member
    if current_user["user_id"] not in [m["user_id"] for m in event["members"]]:
        raise HTTPException(status_code=403, detail="You are not a member of this event")

    # Check expense exists
    if expense_index < 0 or expense_index >= len(event.get("expenses", [])):
        raise HTTPException(status_code=404, detail="Expense not found")

    expense = event["expenses"][expense_index]

    # Reverse the balance changes
    currency = expense["currency"]
    
    if "currency_balances" in event and currency in event["currency_balances"]:
        for participant in expense.get("participants", []):
            user_id = participant["user_id"]
            
            # Reverse the balance change
            if "paid" in participant and "responsible_for" in participant:
                # Advanced expense
                balance_change = participant["paid"] - participant["responsible_for"]
                if user_id in event["currency_balances"][currency]:
                    event["currency_balances"][currency][user_id] -= balance_change
            elif "share" in participant:
                # Old-style expense - might need different logic
                pass

    # Reverse total expenses
    if "total_expenses_by_currency" in event and currency in event["total_expenses_by_currency"]:
        event["total_expenses_by_currency"][currency] -= expense["amount"]
        
        # Remove currency if total is zero
        if abs(event["total_expenses_by_currency"][currency]) < 0.01:
            del event["total_expenses_by_currency"][currency]
            if currency in event.get("currency_balances", {}):
                del event["currency_balances"][currency]

    # Remove the expense
    event["expenses"].pop(expense_index)

    # Update database
    events_collection.update_one(
        {"_id": ObjectId(event_id)},
        {"$set": {
            "currency_balances": event.get("currency_balances", {}),
            "total_expenses_by_currency": event.get("total_expenses_by_currency", {}),
            "expenses": event["expenses"]
        }}
    )

    return {"message": "Expense deleted successfully", "expense_index": expense_index}


@router.put("/{event_id}/expenses/{expense_index}", response_model=EventOut)
def update_expense(
    event_id: str,
    expense_index: int,
    expense: FlexibleExpense,
    current_user: dict = Depends(get_current_user)
):
    """Update an expense - reverses old calculations and applies new ones"""
    
    try:
        event = events_collection.find_one({"_id": ObjectId(event_id)})
    except:
        raise HTTPException(status_code=400, detail="Invalid ID format")

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Check user is a member
    if current_user["user_id"] not in [m["user_id"] for m in event["members"]]:
        raise HTTPException(status_code=403, detail="You are not a member of this event")

    # Check expense exists
    if expense_index < 0 or expense_index >= len(event.get("expenses", [])):
        raise HTTPException(status_code=404, detail="Expense not found")

    old_expense = event["expenses"][expense_index]

    # Validate new expense
    total_responsibility = sum(p.responsible_for for p in expense.participants)
    if abs(total_responsibility - expense.amount) > 0.01:
        raise HTTPException(
            status_code=400,
            detail=f"Sum of responsibilities ({total_responsibility}) must equal total amount ({expense.amount})"
        )
    
    total_paid = sum(p.paid for p in expense.participants)
    if abs(total_paid - expense.amount) > 0.01:
        raise HTTPException(
            status_code=400,
            detail=f"Sum of payments ({total_paid}) must equal total amount ({expense.amount})"
        )

    # Convert emails to user_ids
    participant_data = []
    event_member_emails = {m["email"]: m["user_id"] for m in event["members"]}
    
    for participant in expense.participants:
        if participant.email not in event_member_emails:
            raise HTTPException(status_code=400, detail=f"User {participant.email} is not a member of this event")
        
        user_id = event_member_emails[participant.email]
        participant_data.append({
            "user_id": user_id,
            "email": participant.email,
            "responsible_for": participant.responsible_for,
            "paid": participant.paid
        })

    # Initialize if needed
    if "currency_balances" not in event:
        event["currency_balances"] = {}
    if "total_expenses_by_currency" not in event:
        event["total_expenses_by_currency"] = {}

    # STEP 1: Reverse old expense calculations
    old_currency = old_expense["currency"]
    
    if old_currency in event["currency_balances"]:
        for participant in old_expense.get("participants", []):
            user_id = participant["user_id"]
            if "paid" in participant and "responsible_for" in participant:
                balance_change = participant["paid"] - participant["responsible_for"]
                if user_id in event["currency_balances"][old_currency]:
                    event["currency_balances"][old_currency][user_id] -= balance_change

    if old_currency in event["total_expenses_by_currency"]:
        event["total_expenses_by_currency"][old_currency] -= old_expense["amount"]
        
        # Clean up if zero
        if abs(event["total_expenses_by_currency"][old_currency]) < 0.01:
            del event["total_expenses_by_currency"][old_currency]
            if old_currency in event["currency_balances"]:
                # Check if all balances are zero
                all_zero = all(abs(b) < 0.01 for b in event["currency_balances"][old_currency].values())
                if all_zero:
                    del event["currency_balances"][old_currency]

    # STEP 2: Apply new expense calculations
    new_currency = expense.currency
    
    if new_currency not in event["currency_balances"]:
        event["currency_balances"][new_currency] = {}

    for participant in participant_data:
        user_id = participant["user_id"]
        responsible_for = participant["responsible_for"]
        paid = participant["paid"]
        
        if user_id not in event["currency_balances"][new_currency]:
            event["currency_balances"][new_currency][user_id] = 0.0
        
        balance_change = paid - responsible_for
        event["currency_balances"][new_currency][user_id] += balance_change

    if new_currency not in event["total_expenses_by_currency"]:
        event["total_expenses_by_currency"][new_currency] = 0.0
    
    event["total_expenses_by_currency"][new_currency] += expense.amount

    # STEP 3: Update the expense record
    expense_record = {
        "created_by": old_expense.get("created_by", current_user["user_id"]),
        "amount": expense.amount,
        "currency": expense.currency,
        "participants": participant_data,
        "note": expense.note,
        "expense_type": "advanced",
        "created_at": old_expense.get("created_at", datetime.utcnow()),
        "updated_at": datetime.utcnow()
    }
    
    event["expenses"][expense_index] = expense_record

    # Update database
    events_collection.update_one(
        {"_id": ObjectId(event_id)},
        {"$set": {
            "currency_balances": event["currency_balances"],
            "total_expenses_by_currency": event["total_expenses_by_currency"],
            "expenses": event["expenses"]
        }}
    )

    # Return updated event
    event["_id"] = str(event["_id"])
    
    expenses_out = []
    for exp in event["expenses"]:
        participants_for_output = []
        for p in exp["participants"]:
            if "paid" in p and "responsible_for" in p:
                participants_for_output.append({
                    "user_id": p["user_id"],
                    "share": p["paid"],
                    "responsible_for": p["responsible_for"],
                    "paid": p["paid"]
                })
            elif "share" in p:
                participants_for_output.append({
                    "user_id": p["user_id"],
                    "share": p["share"]
                })
            else:
                participants_for_output.append({
                    "user_id": p.get("user_id", ""),
                    "share": 0.0
                })
        
        expenses_out.append(ExpenseOut(
            payer_id=exp.get("created_by", exp.get("payer_id", "")),
            amount=exp["amount"],
            currency=exp["currency"],
            amount_in_base_currency=exp["amount"],
            participants=participants_for_output,
            note=exp.get("note", ""),
            exchange_rate=None,
            created_at=exp["created_at"]
        ))
    
    return EventOut(
        id=event["_id"],
        name=event["name"],
        base_currency="FLEXIBLE",
        created_by=event["created_by"],
        created_at=event["created_at"],
        members=[{"user_id": m["user_id"], "email": m["email"], "balance": 0.0} for m in event["members"]],
        expenses=expenses_out,
        total_expenses=0.0
    )