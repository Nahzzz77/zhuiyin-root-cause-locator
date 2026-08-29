from models import Order


class OrderRepository:
    def __init__(self) -> None:
        self._orders: dict[str, Order] = {}

    def save(self, order: Order) -> None:
        self._orders[order.order_id] = order

    def get(self, order_id: str) -> Order:
        try:
            return self._orders[order_id]
        except KeyError as error:
            raise ValueError(f"order not found: {order_id}") from error


class CouponRepository:
    def __init__(self) -> None:
        self._statuses: dict[str, str] = {}

    def add(self, code: str) -> None:
        self._statuses[code] = "available"

    def mark_used(self, code: str) -> None:
        if self.status(code) != "available":
            raise ValueError(f"coupon is not available: {code}")
        self._statuses[code] = "used"

    def release(self, code: str) -> None:
        if code not in self._statuses:
            raise ValueError(f"coupon not found: {code}")
        self._statuses[code] = "available"

    def status(self, code: str) -> str:
        try:
            return self._statuses[code]
        except KeyError as error:
            raise ValueError(f"coupon not found: {code}") from error
