from abc import ABC, abstractmethod

from app.models import Order


class PosAdapter(ABC):
    @abstractmethod
    def export_confirmed_order(self, order: Order) -> dict:
        raise NotImplementedError


class JsonMockPosAdapter(PosAdapter):
    """APIキーなしで確認できるLoyverse等への将来接続用JSONアダプター。"""

    def export_confirmed_order(self, order: Order) -> dict:
        return {
            "adapter": "json_mock",
            "transaction_id": order.transaction_id,
            "display_number": order.display_number,
            "business_date": order.business_date,
            "items": [
                {
                    "menu_item_id": item.menu_item_id,
                    "name": item.menu_name_snapshot,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price_snapshot,
                    "line_total": item.line_total,
                }
                for item in order.items
                if item.status == "confirmed"
            ],
        }


pos_adapter: PosAdapter = JsonMockPosAdapter()
