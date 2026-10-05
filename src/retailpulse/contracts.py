from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EventType = Literal[
    "product_view",
    "search",
    "add_to_cart",
    "checkout",
    "purchase",
    "payment",
    "inventory_update",
]

TOPIC_BY_EVENT: dict[str, str] = {
    "product_view": "customer-events",
    "search": "customer-events",
    "add_to_cart": "customer-events",
    "checkout": "order-events",
    "purchase": "order-events",
    "payment": "order-events",
    "inventory_update": "inventory-events",
}


class RetailEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    event_type: EventType
    customer_id: str | None = None
    product_id: str | None = None
    order_id: str | None = None
    quantity: int | None = Field(default=None, strict=True, ge=-(2**31), le=2**31 - 1)
    price: Decimal | None = None
    country: str | None = None
    query: str | None = None
    event_timestamp: datetime
    schema_version: Literal[1]

    @field_validator("schema_version", mode="before")
    @classmethod
    def version_must_be_integer(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("schema_version must be the integer 1")
        return value

    @field_validator("event_timestamp", mode="before")
    @classmethod
    def timestamp_must_be_iso(cls, value: object) -> object:
        if not isinstance(value, (str, datetime)):
            raise ValueError("event_timestamp must be an ISO timestamp with a timezone")
        if isinstance(value, str):
            datetime.fromisoformat(value)
        return value

    @field_validator("event_timestamp")
    @classmethod
    def timestamp_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("event_timestamp must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_business_fields(self) -> RetailEvent:
        product_events = {"product_view", "add_to_cart", "purchase", "inventory_update"}
        if self.event_type in product_events and (
            not self.product_id or not self.product_id.strip()
        ):
            raise ValueError(f"product_id is required for {self.event_type}")
        if self.event_type in {"purchase", "inventory_update"} and (
            self.quantity is None or self.quantity <= 0
        ):
            raise ValueError("quantity must be positive")
        if self.price is not None and self.price < 0:
            raise ValueError("price must be non-negative")
        if self.event_type == "purchase":
            if not self.order_id or not self.order_id.strip():
                raise ValueError("order_id is required for purchase")
            if self.price is None:
                raise ValueError("price is required for purchase")
        return self


class QuarantineRecord(BaseModel):
    event_id: str | None
    raw_payload: str
    error_type: str
    error_message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
