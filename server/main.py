import os
import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Callable

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

# Reuse existing clients
from src.delta_client import DeltaExchangeClient
from src.ws_client import DeltaWSClient


load_dotenv()


# -------------------- Config --------------------
API_KEY = os.getenv("DELTA_API_KEY")
API_SECRET = os.getenv("DELTA_API_SECRET")
USE_TESTNET = os.getenv("USE_TESTNET", "false").lower() in ("1", "true", "yes")
BASE_URL = os.getenv(
    "DELTA_BASE_URL",
    "https://cdn-ind.testnet.deltaex.org" if USE_TESTNET else "https://api.india.delta.exchange",
)
MOCK_DELTA = os.getenv("MOCK_DELTA", "false").lower() in ("1", "true", "yes")


# -------------------- FastAPI app --------------------
app = FastAPI(title="Delta Exchange Bot - FastAPI")

static_dir = os.path.join(os.path.dirname(__file__), "static")
templates_dir = os.path.join(os.path.dirname(__file__), "templates")

app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=templates_dir)


# -------------------- Data Service --------------------
@dataclass
class Snapshot:
    balances: Dict[str, Any]
    positions: Dict[str, Any]
    orders: Dict[str, Any]
    marks: Dict[str, float]
    version: int = 0


class ConnectionManager:
    def __init__(self):
        self._mark: Set[WebSocket] = set()
        self._balances: Set[WebSocket] = set()
        self._positions: Set[WebSocket] = set()
        self._orders: Set[WebSocket] = set()

    def get_pool(self, topic: str) -> Set[WebSocket]:
        return {
            "mark": self._mark,
            "balances": self._balances,
            "positions": self._positions,
            "orders": self._orders,
        }[topic]

    async def connect(self, ws: WebSocket, topic: str):
        await ws.accept()
        self.get_pool(topic).add(ws)

    def disconnect(self, ws: WebSocket, topic: str):
        pool = self.get_pool(topic)
        if ws in pool:
            pool.remove(ws)

    async def broadcast(self, topic: str, html: str):
        pool = list(self.get_pool(topic))
        for ws in pool:
            try:
                await ws.send_text(html)
            except Exception:
                # Drop broken connections silently
                try:
                    self.disconnect(ws, topic)
                except Exception:
                    pass


manager = ConnectionManager()


class DataService:
    """Abstraction over Delta clients with optional mock mode."""

    def __init__(self):
        self.mock = MOCK_DELTA or not (API_KEY and API_SECRET)
        self.rest_client: Optional[DeltaExchangeClient] = None
        self.ws_client: Optional[DeltaWSClient] = None
        self.snapshot = Snapshot(balances={}, positions={}, orders={}, marks={}, version=0)
        self._lock = asyncio.Lock()
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

    async def start(self):
        if self.mock:
            # Start mock data generator
            self._task = asyncio.create_task(self._mock_loop())
            return
        # Real clients
        self.rest_client = DeltaExchangeClient(API_KEY, API_SECRET, base_url=BASE_URL)
        self.ws_client = DeltaWSClient(use_testnet=USE_TESTNET)
        self.ws_client.configure_auth(API_KEY, API_SECRET)
        self.ws_client.connect()
        # Subscribe channels
        self.ws_client.subscribe_mark(["BTCUSD"])  # default symbol for UI
        # Background loop to capture WS snapshots and REST balances
        self._task = asyncio.create_task(self._real_loop())

    async def stop(self):
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=2)
            except Exception:
                pass

    async def _real_loop(self):
        assert self.rest_client is not None and self.ws_client is not None
        prev = None
        last_bal_pull = 0.0
        while not self._stop.is_set():
            try:
                # Mark price from WS
                marks: Dict[str, float] = {}
                price = self.ws_client.get_latest_mark("BTCUSD")
                if price is not None:
                    marks["BTCUSD"] = float(price)

                # Private snapshots from WS (preferred)
                positions = self.ws_client.get_positions() if hasattr(self.ws_client, "get_positions") else {}
                orders = self.ws_client.get_orders() if hasattr(self.ws_client, "get_orders") else {}

                # If empty, fallback to REST briefly to hydrate
                if not positions:
                    try:
                        pos_resp = self.rest_client.get_positions()
                        if isinstance(pos_resp, dict) and pos_resp.get("success"):
                            pos_list = pos_resp.get("result") or []
                            positions = {p.get("product_symbol"): p for p in pos_list if p.get("product_symbol")}
                    except Exception:
                        pass

                if not orders:
                    try:
                        ord_resp = self.rest_client.get_orders()
                        if isinstance(ord_resp, dict) and ord_resp.get("success"):
                            ord_list = ord_resp.get("result") or []
                            orders = {str(o.get("id")): o for o in ord_list if o.get("id") is not None}
                    except Exception:
                        pass

                # Pull balances every 30s
                now = asyncio.get_running_loop().time()
                balances = self.snapshot.balances
                if now - last_bal_pull > 30:
                    last_bal_pull = now
                    try:
                        bal_resp = self.rest_client.get_account_balance()
                        if isinstance(bal_resp, dict) and bal_resp.get("success"):
                            # Transform list to dict keyed by asset symbol
                            result = bal_resp.get("result") or []
                            if isinstance(result, list):
                                transformed = {
                                    (row.get("asset_symbol") or row.get("symbol") or ""): {
                                        "available_balance": row.get("available_balance"),
                                        "total_balance": row.get("balance") or row.get("total_balance"),
                                    }
                                    for row in result
                                    if (row.get("asset_symbol") or row.get("symbol"))
                                }
                                balances = transformed
                    except Exception:
                        pass

                snap = {
                    "marks": marks,
                    "positions": positions,
                    "orders": orders,
                    # keep last balances if empty
                    "balances": balances or self.snapshot.balances,
                }
                if snap != prev:
                    async with self._lock:
                        self.snapshot.marks = marks
                        self.snapshot.positions = positions
                        self.snapshot.orders = orders
                        self.snapshot.balances = snap["balances"]
                        self.snapshot.version += 1
                    prev = snap
                    # Schedule broadcasts
                    await self._broadcast_all()
            except Exception:
                # Avoid tight error loops
                await asyncio.sleep(0.5)
            await asyncio.sleep(1.0)

    async def _mock_loop(self):
        import random
        # Start with deterministic values
        price = 60000.0
        t = 0
        while not self._stop.is_set():
            # simple random walk
            price += random.uniform(-5, 5)
            t += 1
            positions = {
                "BTCUSD": {
                    "product_symbol": "BTCUSD",
                    "size": 1,
                    "entry_price": 60000.0,
                    "direction": "buy",
                }
            }
            orders = {
                "1": {
                    "id": 1,
                    "product_symbol": "BTCUSD",
                    "price": round(price + 100, 2),
                    "size": 1,
                    "side": "sell",
                    "state": "open",
                }
            }
            balances = {"BTC": {"available_balance": 0.1, "total_balance": 0.1}}
            async with self._lock:
                self.snapshot.marks = {"BTCUSD": round(price, 2)}
                self.snapshot.positions = positions
                self.snapshot.orders = orders
                self.snapshot.balances = balances
                self.snapshot.version += 1
            await self._broadcast_all()
            await asyncio.sleep(0.75)

    async def _broadcast_all(self):
        # Render and broadcast separate sections
        html_mark = templates.get_template("_mark.html").render(mark=self.snapshot.marks.get("BTCUSD"))
        html_bal = templates.get_template("_balances.html").render(balances=self.snapshot.balances)
        html_pos = templates.get_template("_positions.html").render(positions=self.snapshot.positions, marks=self.snapshot.marks)
        html_ord = templates.get_template("_orders.html").render(orders=self.snapshot.orders)
        await manager.broadcast("mark", html_mark)
        await manager.broadcast("balances", html_bal)
        await manager.broadcast("positions", html_pos)
        await manager.broadcast("orders", html_ord)


data_service = DataService()


# -------------------- Dependencies --------------------
async def get_service() -> DataService:
    return data_service


@app.on_event("startup")
async def _on_startup():
    await data_service.start()


@app.on_event("shutdown")
async def _on_shutdown():
    await data_service.stop()


# -------------------- Routes --------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "use_testnet": USE_TESTNET,
        },
    )


@app.post("/orders/place")
async def place_order(
    product_symbol: str = Form(...),
    size: int = Form(...),
    side: str = Form(...),
    limit_price: Optional[float] = Form(None),
    service: DataService = Depends(get_service),
):
    # In mock mode, just acknowledge
    if service.mock:
        return RedirectResponse("/", status_code=303)
    # Find product id via REST
    assert service.rest_client is not None
    pid = None
    try:
        prod = service.rest_client.get_product_by_symbol(product_symbol)
        if isinstance(prod, dict) and prod.get("success"):
            result = prod.get("result") or {}
            pid = result.get("id")
    except Exception:
        pass
    if pid is None:
        return RedirectResponse("/", status_code=303)
    service.rest_client.place_order(
        product_id=int(pid),
        size=size,
        side=side,
        order_type="limit_order" if limit_price is not None else "market_order",
        limit_price=str(limit_price) if limit_price is not None else None,
        time_in_force="gtc",
        post_only=True,
    )
    return RedirectResponse("/", status_code=303)


@app.post("/orders/cancel")
async def cancel_order(
    order_id: str = Form(...),
    service: DataService = Depends(get_service),
):
    if service.mock:
        return RedirectResponse("/", status_code=303)
    assert service.rest_client is not None
    try:
        service.rest_client.cancel_order(order_id=int(order_id))
    except Exception:
        pass
    return RedirectResponse("/", status_code=303)


# -------------------- WebSockets for HTMX --------------------
@app.websocket("/ws/mark")
async def ws_mark(ws: WebSocket):
    await manager.connect(ws, "mark")
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws, "mark")


@app.websocket("/ws/balances")
async def ws_balances(ws: WebSocket):
    await manager.connect(ws, "balances")
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws, "balances")


@app.websocket("/ws/positions")
async def ws_positions(ws: WebSocket):
    await manager.connect(ws, "positions")
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws, "positions")


@app.websocket("/ws/orders")
async def ws_orders(ws: WebSocket):
    await manager.connect(ws, "orders")
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws, "orders")

