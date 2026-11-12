from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, StrictInt, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InterpretIn(_Strict):
    text: str = Field(min_length=3, max_length=500)


class IntentIn(_Strict):
    instruction: str = Field(min_length=3, max_length=500)
    constraints: dict[str, Any]  # re-validated field by field by core.validation
    source: Literal["gemini", "fallback_rules", "user_edited"]


class CartLineIn(_Strict):
    item_id: str
    qty: StrictInt
    unit_price: StrictInt


class TransactionIn(_Strict):
    intent_id: str
    offer_id: str
    cart: list[CartLineIn]


class ThreatIn(_Strict):
    text: str = Field(min_length=1, max_length=5000)


class CaptureIn(_Strict):
    order_id: str = Field(min_length=1, max_length=64)
