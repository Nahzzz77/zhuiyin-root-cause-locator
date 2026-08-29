from coupon_service import CouponService
from handlers import CancelOrderHandler
from models import Order
from order_service import OrderService
from repositories import CouponRepository, OrderRepository


def test_cancelled_order_returns_coupon() -> None:
    orders = OrderRepository()
    coupons = CouponRepository()
    coupons.add("NEWUSER20")
    service = OrderService(orders, CouponService(coupons))

    service.place_order(Order("ORD-1001"), "NEWUSER20")
    response = CancelOrderHandler(service).handle({"order_id": "ORD-1001"})

    assert response["status"] == "cancelled"
    assert coupons.status("NEWUSER20") == "available"
