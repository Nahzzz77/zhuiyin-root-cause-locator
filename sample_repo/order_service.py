from coupon_service import CouponService
from models import Order
from repositories import OrderRepository


class OrderService:
    def __init__(
        self,
        orders: OrderRepository,
        coupons: CouponService,
    ) -> None:
        self._orders = orders
        self._coupons = coupons

    def place_order(self, order: Order, coupon_code: str | None = None) -> Order:
        if coupon_code is not None:
            self._coupons.apply(order, coupon_code)
        order.status = "paid"
        self._orders.save(order)
        return order

    def cancel_order(self, order_id: str) -> Order:
        order = self._orders.get(order_id)
        if order.status != "paid":
            raise ValueError(f"order cannot be cancelled: {order.status}")
        order.status = "cancelled"
        self._orders.save(order)
        return order
