from models import Order
from repositories import CouponRepository


class CouponService:
    def __init__(self, coupons: CouponRepository) -> None:
        self._coupons = coupons

    def apply(self, order: Order, code: str) -> None:
        self._coupons.mark_used(code)
        order.coupon_code = code

    def release(self, order: Order) -> None:
        if order.coupon_code is not None:
            self._coupons.release(order.coupon_code)
