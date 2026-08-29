from dataclasses import dataclass


@dataclass
class Order:
    order_id: str
    status: str = "created"
    coupon_code: str | None = None
