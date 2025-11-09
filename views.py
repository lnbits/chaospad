from http import HTTPStatus

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from lnbits.core.models import User
from lnbits.decorators import check_user_exists
from lnbits.helpers import template_renderer

from .crud import get_pads_by_id

chaospad_generic_router = APIRouter()


def chaospad_renderer():
    return template_renderer(["chaospad/templates"])


# Backend admin page
@chaospad_generic_router.get("/", response_class=HTMLResponse)
async def index(req: Request, user: User = Depends(check_user_exists)):
    return chaospad_renderer().TemplateResponse("chaospad/index.html", {"request": req, "user": user.json()})


# Frontend shareable page
@chaospad_generic_router.get("/{pads_id}")
async def pads_public_page(req: Request, pads_id: str):
    pads = await get_pads_by_id(pads_id)
    if not pads:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Pads does not exist.")

    public_page_name = getattr(pads, "name", "") or ""
    public_page_description = ""
    initial_content = getattr(pads, "content", "") or ""

    max_words = 500
    max_room_peers = 10

    return chaospad_renderer().TemplateResponse(
        "chaospad/public_page.html",
        {
            "request": req,
            "pads_id": pads_id,
            "public_page_name": public_page_name,
            "public_page_description": public_page_description,
            "initial_content": initial_content,
            "max_words": max_words,
            "room_cap": max_room_peers,
        },
    )
