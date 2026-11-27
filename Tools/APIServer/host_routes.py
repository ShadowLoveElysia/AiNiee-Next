"""Hosting and capability metadata for clients replacing the interactive menu."""
from fastapi import APIRouter, HTTPException
from .host_contracts import WebHostingRequest, WebHostingResponse, ParityResponse
from .responses import ERROR_RESPONSES

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/web", response_model=WebHostingResponse, responses=ERROR_RESPONSES)
def web_hosting_status():
    from .server import web_status
    return web_status()


@router.put("/web", response_model=WebHostingResponse, responses=ERROR_RESPONSES)
def configure_web_hosting(payload: WebHostingRequest):
    from .server import configure_web
    if not payload.confirmed:
        raise HTTPException(409, "Confirm changing Web hosting")
    try:
        return configure_web(payload.enabled)
    except FileNotFoundError as exc:
        raise HTTPException(404, "Build or install Web assets before enabling hosting") from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/tui-capabilities", response_model=ParityResponse, responses=ERROR_RESPONSES)
def tui_capabilities():
    from .parity import capability_matrix
    return {"features": capability_matrix()}
