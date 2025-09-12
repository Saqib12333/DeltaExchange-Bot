import os
import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Callable
import logging

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
BASE_URL = os.getenv("DELTA_BASE_URL", "https://api.india.delta.exchange")


# -------------------- FastAPI app --------------------
app = FastAPI(title="Delta Exchange Bot - FastAPI")
logger = logging.getLogger("delta.app")
logging.basicConfig(level=logging.INFO)

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
    """Abstraction over Delta clients (real-only; mock removed)."""

    def __init__(self):
        self.mock = False  # mock removed
        self.rest_client: Optional[DeltaExchangeClient] = None
        self.ws_client: Optional[DeltaWSClient] = None
        self.snapshot = Snapshot(balances={}, positions={}, orders={}, marks={}, version=0)
        self._lock = asyncio.Lock()
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

    async def start(self):
        # Real clients only
        if not API_KEY or not API_SECRET:
            raise RuntimeError("DELTA_API_KEY / DELTA_API_SECRET must be set (mock mode removed)")

        self.rest_client = DeltaExchangeClient(API_KEY, API_SECRET, base_url=BASE_URL)
        self.ws_client = DeltaWSClient()
        self.ws_client.configure_auth(API_KEY, API_SECRET)
        self.ws_client.connect()
        # Subscribe channels
        self.ws_client.subscribe_mark(["BTCUSD"])  # default symbol for UI

        # Startup auth sanity check (balances endpoint requires valid key)
        try:
            bal_probe = self.rest_client.get_account_balance()
            if not (isinstance(bal_probe, dict) and bal_probe.get("success")):
                code = None
                if isinstance(bal_probe, dict):
                    code = (bal_probe.get("error") or {}).get("code") if isinstance(bal_probe.get("error"), dict) else None
                masked = API_KEY[:4] + "***" + API_KEY[-4:]
                logger.warning(f"Startup auth check failed (code={code}) for key {masked} base_url={BASE_URL}")
        except Exception as e:
            masked = API_KEY[:4] + "***" + API_KEY[-4:]
            logger.error(f"Startup auth exception for key {masked}: {e}")

        # Launch background loop
        self._task = asyncio.create_task(self._real_loop())
        logger.info("DataService.start() scheduled _real_loop task id=%s", id(self._task))

    async def stop(self):
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=2)
            except Exception:
                pass

    async def _real_loop(self):
        assert self.rest_client is not None and self.ws_client is not None
        prev: Optional[Dict[str, Any]] = None
        last_bal_pull = 0.0
        last_rest_mark_pull = -10.0
        ws_mark_seen = False
        first_broadcast_done = False
        tick = 0

        logger.info("_real_loop entered: starting main data aggregation loop")

        while not self._stop.is_set():
            try:
                if prev is None:
                    logger.info("Loop first iteration starting (tick=%s)", tick)

                # Mark price
                marks: Dict[str, float] = {}
                price = self.ws_client.get_latest_mark("BTCUSD")
                if price is not None:
                    marks["BTCUSD"] = float(price)
                    ws_mark_seen = True
                elif os.getenv("DELTA_WS_DEBUG", "false").lower() in ("1", "true", "yes"):
                    logger.info("No WS price yet")

                loop_now = asyncio.get_running_loop().time()
                if not ws_mark_seen and loop_now - last_rest_mark_pull > 5:
                    last_rest_mark_pull = loop_now
                    try:
                        rest_mark = self.rest_client.get_mark_price("BTCUSD")
                        if isinstance(rest_mark, dict) and rest_mark.get("success") and rest_mark.get("mark_price"):
                            marks["BTCUSD"] = float(rest_mark["mark_price"])
                            logger.info("REST mark fallback pulled price=%s", marks["BTCUSD"])
                    except Exception:
                        pass

                # Positions / Orders
                positions = self.ws_client.get_positions() if hasattr(self.ws_client, "get_positions") else {}
                orders = self.ws_client.get_orders() if hasattr(self.ws_client, "get_orders") else {}
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

                # Balances
                now = asyncio.get_running_loop().time()
                balances = self.snapshot.balances
                if prev is None or now - last_bal_pull > 30:
                    last_bal_pull = now
                    try:
                        bal_resp = self.rest_client.get_account_balance()
                        if isinstance(bal_resp, dict) and bal_resp.get("success"):
                            result = bal_resp.get("result") or []
                            if isinstance(result, list):
                                balances = {
                                    (row.get("asset_symbol") or row.get("symbol") or ""): {
                                        "available_balance": row.get("available_balance"),
                                        "total_balance": row.get("balance") or row.get("total_balance"),
                                    }
                                    for row in result
                                    if (row.get("asset_symbol") or row.get("symbol"))
                                }
                                logger.info("Pulled balances count=%s", len(balances))
                    except Exception:
                        pass

                snap = {
                    "marks": marks,
                    "positions": positions,
                    "orders": orders,
                    "balances": balances or self.snapshot.balances,
                }

                if prev is None:
                    await self._broadcast_all()
                    first_broadcast_done = True
                    logger.info("Initial forced broadcast executed (may be empty) tick=%s", tick)

                if snap != prev:
                    async with self._lock:
                        self.snapshot.marks = marks
                        self.snapshot.positions = positions
                        self.snapshot.orders = orders
                        self.snapshot.balances = snap["balances"]
                        self.snapshot.version += 1
                    prev = snap
                    await self._broadcast_all()
                    first_broadcast_done = True
                    logger.info(
                        "Broadcast v%s tick=%s marks=%d positions=%d orders=%d balances=%d ws_mark=%s",
                        self.snapshot.version,
                        tick,
                        len(self.snapshot.marks),
                        len(self.snapshot.positions),
                        len(self.snapshot.orders),
                        len(self.snapshot.balances),
                        ws_mark_seen,
                    )
                else:
                    if os.getenv("DELTA_WS_DEBUG", "false").lower() in ("1", "true", "yes") and not ws_mark_seen:
                        try:
                            print("[DEBUG] Waiting for first mark price... snapshot version", self.snapshot.version)
                        except Exception:
                            pass
                    if not first_broadcast_done and self.snapshot.version == 0:
                        try:
                            await self._broadcast_all()
                            first_broadcast_done = True
                            logger.info("Forced initial broadcast with empty snapshot to populate UI placeholders tick=%s", tick)
                        except Exception:
                            pass
                tick += 1
            except Exception as e:
                try:
                    import traceback
                    tb = traceback.format_exc()
                    logger.error("_real_loop iteration error: %s\n%s", e, tb)
                except Exception:
                    pass
                await asyncio.sleep(0.5)
            await asyncio.sleep(1.0)
    async def _broadcast_all(self):
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
    {"request": request},
    )


@app.post("/orders/place")
async def place_order(
    product_symbol: str = Form(...),
    size: int = Form(...),
    side: str = Form(...),
    limit_price: Optional[float] = Form(None),
    service: DataService = Depends(get_service),
):
    # Real mode only
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
    request: Request,
    order_id: str = Form(...),
    service: DataService = Depends(get_service),
):
    # Real mode only
    assert service.rest_client is not None
    headers_snapshot = {}
    try:
        headers_snapshot = dict(request.headers)
        logger.info("/orders/cancel headers=%s", headers_snapshot)
    except Exception:
        pass

    prior_ids = list(service.snapshot.orders.keys())
    product_id: Optional[int] = None
    order_obj = service.snapshot.orders.get(order_id)
    if isinstance(order_obj, dict):
        product_id = order_obj.get("product_id") or (order_obj.get("product") or {}).get("id") if isinstance(order_obj.get("product"), dict) else None
        product_symbol = order_obj.get("product_symbol") or order_obj.get("symbol")
    else:
        product_symbol = None

    try:
        logger.info(f"/orders/cancel resolve order_id={order_id} product_id={product_id} product_symbol={product_symbol}")
    except Exception:
        pass

    cancel_resp: Dict[str, Any] = {}
    cancel_success = False
    try:
        cancel_resp = service.rest_client.cancel_order(order_id=int(order_id), product_id=product_id, product_symbol=product_symbol)
        cancel_success = bool(cancel_resp.get("success"))
    except Exception as e:
        logger.warning("Cancel order exception order_id=%s err=%s", order_id, e)

    # Only remove locally if API reported success
    if cancel_success:
        try:
            async with service._lock:  # type: ignore[attr-defined]
                service.snapshot.orders.pop(order_id, None)
                service.snapshot.version += 1
        except Exception:
            pass
    else:
        try:
            logger.warning(
                "Cancel order API reported failure order_id=%s resp=%s order_obj=%s prior_ids=%s", 
                order_id, cancel_resp, order_obj, prior_ids
            )
        except Exception:
            logger.warning("Cancel order API reported failure order_id=%s resp=%s (order_obj log failed)", order_id, cancel_resp)

    # Refresh from REST to ensure authoritative state
    refreshed_ids: List[str] = []
    try:
        ord_resp = service.rest_client.get_orders()
        orders: Dict[str, Any] = {}
        if isinstance(ord_resp, dict) and ord_resp.get("success"):
            for o in (ord_resp.get("result") or []):
                if o.get("id") is not None:
                    orders[str(o.get("id"))] = o
            refreshed_ids = list(orders.keys())
        async with service._lock:  # type: ignore[attr-defined]
            service.snapshot.orders = orders
            service.snapshot.version += 1
    except Exception as e:
        logger.error("Failed to refresh orders after cancel order_id=%s err=%s", order_id, e)

    removed = set(prior_ids) - set(refreshed_ids)
    logger.info("Cancel result order_id=%s success=%s removed_now=%s remaining=%d", order_id, cancel_success, order_id in removed, len(refreshed_ids))

    html_ord = templates.get_template("_orders.html").render(orders=service.snapshot.orders)
    # Broadcast to others
    try:
        await manager.broadcast("orders", html_ord)
    except Exception:
        pass

    # Return partial for HX or fetch fallback
    if request.headers.get("hx-request") == "true" or request.headers.get("x-fetch-cancel") == "1":
        return HTMLResponse(html_ord)
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

