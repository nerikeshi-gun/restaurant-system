from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self.kitchen: set[WebSocket] = set()
        self.customers: dict[int, set[WebSocket]] = {}

    async def connect_kitchen(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.kitchen.add(websocket)

    async def connect_customer(self, session_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self.customers.setdefault(session_id, set()).add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self.kitchen.discard(websocket)
        for connections in self.customers.values():
            connections.discard(websocket)

    async def broadcast_kitchen(self, event: dict) -> None:
        dead: list[WebSocket] = []
        for websocket in self.kitchen:
            try:
                await websocket.send_json(event)
            except Exception:
                dead.append(websocket)
        for websocket in dead:
            self.disconnect(websocket)

    async def broadcast_customer(self, session_id: int, event: dict) -> None:
        dead: list[WebSocket] = []
        for websocket in self.customers.get(session_id, set()):
            try:
                await websocket.send_json(event)
            except Exception:
                dead.append(websocket)
        for websocket in dead:
            self.disconnect(websocket)

    async def broadcast_all_customers(self, event: dict) -> None:
        for session_id in list(self.customers):
            await self.broadcast_customer(session_id, event)


manager = ConnectionManager()
