import asyncio
from http import HTTPStatus
from time import time

from fastapi import APIRouter, Depends, Request, WebSocket
from fastapi.exceptions import HTTPException
from lnbits.core.models import SimpleStatus, User
from lnbits.db import Filters, Page
from lnbits.decorators import check_user_exists, parse_filters
from lnbits.helpers import generate_filter_params_openapi
from starlette.requests import ClientDisconnect
from starlette.websockets import WebSocketDisconnect, WebSocketState

from .crud import (
    create_pads,
    create_snapshot,
    delete_pads,
    get_latest_snapshot,
    get_pads,
    get_pads_by_id,
    get_pads_paginated,
    prune_old_snapshots,
    update_pads,
)
from .models import (
    CreatePads,
    Pads,
    PadsFilters,
    SnapshotResponse,
    SnapshotWriteResult,
)
from .views import chaospad_generic_router

pads_filters = parse_filters(PadsFilters)
chaospad_api_router = APIRouter()

MAX_ROOM_PEERS = 10
SNAPSHOT_MIN_INTERVAL = 3.0
MAX_CHARS = 6000

_SNAPSHOT_LAST_AT: dict[str, float] = {}
_SNAPSHOT_LOCKS: dict[str, asyncio.Lock] = {}


def _pad_lock(pads_id: str) -> asyncio.Lock:
    lock = _SNAPSHOT_LOCKS.get(pads_id)
    if lock is None:
        lock = asyncio.Lock()
        _SNAPSHOT_LOCKS[pads_id] = lock
    return lock


def _count_chars(s: str | None) -> int:
    return len(s or "")


############################# Pads #############################
@chaospad_api_router.post("/api/v1/pads", status_code=HTTPStatus.CREATED)
async def api_create_pads(
    data: CreatePads,
    user: User = Depends(check_user_exists),
) -> Pads:
    if _count_chars(data.content) > MAX_CHARS:
        raise HTTPException(HTTPStatus.BAD_REQUEST, f"Content exceeds {MAX_CHARS} characters.")
    pads = await create_pads(user.id, data)
    return pads


@chaospad_api_router.put("/api/v1/pads/{pads_id}", status_code=HTTPStatus.CREATED)
async def api_update_pads(
    pads_id: str,
    data: CreatePads,
    user: User = Depends(check_user_exists),
) -> Pads:
    pads = await get_pads(user.id, pads_id)
    if not pads:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Pads not found.")
    if pads.user_id != user.id:
        raise HTTPException(HTTPStatus.FORBIDDEN, "You do not own this pads.")

    if _count_chars(data.content) > MAX_CHARS:
        raise HTTPException(HTTPStatus.BAD_REQUEST, f"Content exceeds {MAX_CHARS} characters.")

    pads = await update_pads(Pads(**{**pads.dict(), **data.dict()}))
    return pads


@chaospad_api_router.get(
    "/api/v1/pads/paginated",
    name="Pads List",
    summary="get paginated list of pads",
    response_description="list of pads",
    openapi_extra=generate_filter_params_openapi(PadsFilters),
    response_model=Page[Pads],
)
async def api_get_pads_paginated(
    user: User = Depends(check_user_exists),
    filters: Filters = Depends(pads_filters),
) -> Page[Pads]:
    return await get_pads_paginated(user_id=user.id, filters=filters)


@chaospad_api_router.get(
    "/api/v1/pads/{pads_id}",
    name="Get Pads",
    summary="Get the pads with this id.",
    response_description="An pads or 404 if not found",
    response_model=Pads,
)
async def api_get_pads(
    pads_id: str,
    user: User = Depends(check_user_exists),
) -> Pads:
    pads = await get_pads(user.id, pads_id)
    if not pads:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Pads not found.")
    return pads


@chaospad_api_router.delete(
    "/api/v1/pads/{pads_id}",
    name="Delete Pads",
    summary="Delete the pads and optionally all its associated client_data.",
    response_description="The status of the deletion.",
    response_model=SimpleStatus,
)
async def api_delete_pads(
    pads_id: str,
    clear_client_data: bool | None = False,
    user: User = Depends(check_user_exists),
) -> SimpleStatus:
    await delete_pads(user.id, pads_id)
    if clear_client_data is True:
        pass
    return SimpleStatus(success=True, message="Pads Deleted")


######################### Realtime & Snapshots ############################

FRAME_YUPDATE = bytes([0x01])
FRAME_PING = bytes([0x02])
ROOMS: dict[str, set[WebSocket]] = {}


def _get_room(peers_map: dict[str, set[WebSocket]], room_id: str) -> set[WebSocket]:
    return peers_map.setdefault(room_id, set())


async def _ensure_pad_or_close(ws: WebSocket, pads_id: str) -> bool:
    pads = await get_pads_by_id(pads_id)
    if not pads:
        await ws.close(code=1008, reason="Pad not found")
        return False
    return True


def _over_capacity(peers: set[WebSocket]) -> bool:
    return len(peers) >= MAX_ROOM_PEERS


def _prune_disconnected(peers: set[WebSocket]) -> None:
    for peer in list(peers):
        if peer.application_state != WebSocketState.CONNECTED:
            peers.discard(peer)


async def _fanout(peers: set[WebSocket], sender: WebSocket, mtype: int, payload: bytes) -> None:
    dead: list[WebSocket] = []
    for peer in list(peers):
        if peer is sender:
            continue
        if peer.application_state != WebSocketState.CONNECTED:
            dead.append(peer)
            continue
        try:
            await peer.send_bytes(bytes([mtype]) + payload)
        except Exception:
            dead.append(peer)
    for d in dead:
        peers.discard(d)


@chaospad_generic_router.websocket("/ws/{pads_id}")
async def ws_room(ws: WebSocket, pads_id: str):
    if not await _ensure_pad_or_close(ws, pads_id):
        return

    peers = _get_room(ROOMS, pads_id)
    if _over_capacity(peers):
        await ws.close(code=1008, reason="Room full")
        return

    await ws.accept()
    peers.add(ws)
    try:
        while True:
            data = await ws.receive_bytes()
            if not data:
                continue
            mtype, payload = data[0], data[1:]
            if mtype == 0x02:
                continue
            await _fanout(peers, ws, mtype, payload)
            _prune_disconnected(peers)
    except WebSocketDisconnect:
        pass
    finally:
        peers.discard(ws)
        if not ROOMS.get(pads_id):
            ROOMS.pop(pads_id, None)


@chaospad_api_router.get(
    "/api/v1/snapshot/{pads_id}",
    response_model=SnapshotResponse,
)
async def api_get_snapshot(pads_id: str) -> SnapshotResponse:
    pads = await get_pads_by_id(pads_id)
    if not pads:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Pads not found.")

    blob = await get_latest_snapshot(pads_id)
    return SnapshotResponse.from_bytes(blob)


@chaospad_api_router.post(
    "/api/v1/snapshot/{pads_id}",
    response_model=SnapshotWriteResult,
    status_code=HTTPStatus.CREATED,
)
async def api_post_snapshot(pads_id: str, request: Request) -> SnapshotWriteResult:
    pads = await get_pads_by_id(pads_id)
    if not pads:
        raise HTTPException(HTTPStatus.NOT_FOUND, "Pads not found.")

    is_final = request.headers.get("x-final") == "1"

    try:
        body = await request.body()
    except ClientDisconnect:
        return SnapshotWriteResult(ok=False, final=is_final, rate_limited=False)

    if not body:
        return SnapshotWriteResult(ok=False, final=is_final, rate_limited=False)

    ch_header = request.headers.get("x-char-count")
    wc_header = request.headers.get("x-word-count")

    try:
        if ch_header is not None:
            ch = int(ch_header)
            if ch > MAX_CHARS:
                raise HTTPException(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, f"Content exceeds {MAX_CHARS} characters.")
        elif wc_header is not None:
            wc = int(wc_header)
            approx_chars = wc * 6
            if approx_chars > MAX_CHARS:
                raise HTTPException(
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE, f"Content exceeds {MAX_CHARS} characters (approx from words)."
                )
    except ValueError:
        pass

    async with _pad_lock(pads_id):
        now = time()
        last = _SNAPSHOT_LAST_AT.get(pads_id, 0.0)
        over_limit = (now - last) < SNAPSHOT_MIN_INTERVAL

        if over_limit and not is_final:
            raise HTTPException(
                HTTPStatus.TOO_MANY_REQUESTS, f"Snapshots limited to one every {int(SNAPSHOT_MIN_INTERVAL)}s."
            )

        _SNAPSHOT_LAST_AT[pads_id] = now

        await create_snapshot(pads_id, body)
        await prune_old_snapshots(pads_id)

    return SnapshotWriteResult(ok=True, final=is_final, rate_limited=over_limit)
