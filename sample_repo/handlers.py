from order_service import OrderService


class CancelOrderHandler:
    def __init__(self, orders: OrderService) -> None:
        self._orders = orders

    def handle(self, payload: dict[str, str]) -> dict[str, str]:
        order_id = payload.get("order_id")
        if not order_id:
            raise ValueError("order_id is required")

        order = self._orders.cancel_order(order_id)
        return {"order_id": order.order_id, "status": order.status}
