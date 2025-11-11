# app/models/event.py
# Updated models with automatic exchange rates
# Comments are in English, without emojis

from pydantic import BaseModel, EmailStr, validator
from typing import List, Optional, Dict
from datetime import datetime


# -----------------------------
# Member models
# -----------------------------

class MemberInput(BaseModel):
    """Input model for a member when creating an event"""
    email: EmailStr


class MemberOut(BaseModel):
    """Output model for a member including balance in base currency"""
    user_id: str
    email: EmailStr
    balance: float


# -----------------------------
# Event creation and update
# -----------------------------

class EventCreate(BaseModel):
    """Standard event creation model with a base currency"""
    name: str
    base_currency: str  # Base currency for the event
    members: List[MemberInput]


class FlexibleEventCreate(BaseModel):
    """
    Flexible event creation model (no base currency defined).
    Only requires name and members.
    """
    name: str
    members: List[dict]  # Example: [{"email": "user@example.com"}]


class EventCurrencyUpdate(BaseModel):
    """Update model for changing an event base currency"""
    base_currency: str


# -----------------------------
# Expense participant models
# -----------------------------

class ExpenseParticipant(BaseModel):
    """Represents a participant's share in an expense (output model)"""
    user_id: str
    share: float
    responsible_for: Optional[float] = None
    paid: Optional[float] = None


class ParticipantExpense(BaseModel):
    """
    Represents a participant in an advanced expense input.
    - responsible_for: amount they should cover
    - paid: amount they actually paid
    """
    email: str
    responsible_for: float
    paid: float


# -----------------------------
# Expense creation models
# -----------------------------

class FlexibleExpense(BaseModel):
    """
    Advanced expense model:
    - amount: total cost
    - currency: original currency of the expense
    - participants: list of participants with shares and payments
    """
    amount: float
    currency: str
    participants: List[ParticipantExpense]
    note: str = ""

    @validator("currency")
    def validate_currency(cls, v: str) -> str:
        """Basic validation for currency code"""
        v = v.upper().strip()
        if len(v) < 2 or len(v) > 4:
            raise ValueError("Currency code must be 2-4 characters")
        if not v.isalpha():
            raise ValueError("Currency code must contain only letters")
        return v


class ParticipantShare(BaseModel):
    """
    Backward-compatible model for custom split expenses.
    Represents how much each participant pays in the original currency.
    """
    email: str
    share: float


class SimpleExpense(BaseModel):
    """
    Backward-compatible model for simple equal split expenses.
    - exchange_rate is optional, used when converting to base currency
    """
    amount: float
    currency: str
    participants: List[ParticipantShare]
    note: str = ""
    exchange_rate: Optional[float] = None


# -----------------------------
# Expense output model
# -----------------------------

class ExpenseOut(BaseModel):
    """
    Expense as returned from database:
    - amount: in original currency
    - amount_in_base_currency: normalized to event base currency
    - exchange_rate: used for conversion (if applicable)
    """
    payer_id: str
    amount: float
    currency: str
    amount_in_base_currency: float
    participants: List[ExpenseParticipant]
    note: Optional[str] = ""
    exchange_rate: Optional[float] = None
    created_at: datetime


# -----------------------------
# Event output model
# -----------------------------

class EventOut(BaseModel):
    """
    Event output model with all details:
    - members
    - expenses
    - total_expenses in base currency
    """
    id: str
    name: str
    base_currency: str  # Either base currency code or "FLEXIBLE"
    created_by: str
    created_at: datetime
    members: List[MemberOut]
    expenses: List[ExpenseOut]
    total_expenses: float


# -----------------------------
# Settlement and summary models
# -----------------------------

class Payment(BaseModel):
    """Represents a settlement payment between two members"""
    from_user_id: str
    to_user_id: str
    amount: float
    currency: str


class EventSummary(BaseModel):
    """
    Event summary after settlement:
    - member_balances: user_id -> balance in base currency
    - payments_needed: list of suggested payments
    - total_expenses: total in base currency
    """
    event_id: str
    event_name: str
    base_currency: str
    member_balances: Dict[str, float]
    payments_needed: List[Payment]
    total_expenses: float


# -----------------------------
# Exchange rate related models
# -----------------------------

class ExchangeRatesResponse(BaseModel):
    """
    Response model for exchange rates:
    - base_currency: reference currency
    - rates: mapping target_currency -> rate
    - supported_currencies: list of supported codes
    - last_updated: timestamp string
    """
    base_currency: str
    rates: Dict[str, float]
    supported_currencies: List[str]
    last_updated: str


class EventCurrencyInfo(BaseModel):
    """
    Information model for currencies within an event:
    - currencies_in_event: list of distinct currencies used
    - suggested_rates: recommended conversion rates
    - total_expenses_by_currency: sum per currency
    """
    event_id: str
    event_name: str
    currencies_in_event: List[str]
    suggested_rates: Dict[str, float]
    base_currency: str
    total_expenses_by_currency: Dict[str, float]


class CurrencyConversionRequest(BaseModel):
    """Request model for converting currency"""
    amount: float
    from_currency: str
    to_currency: str


class CurrencyConversionResponse(BaseModel):
    """Response model for currency conversion"""
    original_amount: float
    from_currency: str
    to_currency: str
    converted_amount: float
    exchange_rate: float
    last_updated: str


# -----------------------------
# Legacy models (deprecated)
# -----------------------------

class FinalCurrencyChoice(BaseModel):
    """
    Legacy model for final currency selection and manual exchange rates.
    Deprecated because exchange rates are now automatic.
    """
    final_currency: str
    exchange_rates: Dict[str, float]


class ExchangeRateRequest(BaseModel):
    """Legacy model for requesting an exchange rate (deprecated)"""
    from_currency: str
    to_currency: str
    amount: float


class ExchangeRateResponse(BaseModel):
    """Legacy model for exchange rate response (deprecated)"""
    from_currency: str
    to_currency: str
    rate: float
    converted_amount: float
