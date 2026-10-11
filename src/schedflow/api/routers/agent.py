"""Actor scoped assistant API. Only authenticated JWT users can confirm writes."""

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from schedflow.api.schemas import APIResponse

router = APIRouter(prefix="/agent", tags=["agent"])


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SessionRequest(StrictRequest):
    title: str | None = Field(default=None, max_length=200)


class TurnRequest(StrictRequest):
    message: str = Field(min_length=1, max_length=16000)
    job_id: str | None = Field(default=None, max_length=128)


class ApprovalRequest(StrictRequest):
    proposal_version: int = Field(ge=1)


class RevisionRequest(StrictRequest):
    enabled: bool


def _service(request: Request):
    service = getattr(request.app.state, "agent", None)
    if service is None:
        raise HTTPException(503, "Agent service unavailable")
    return service


def _actor(request: Request):
    auth = getattr(request.state, "auth", None)
    if auth is None or not auth.success or not auth.user_id:
        raise HTTPException(403, "Authentication required")
    return auth.user_id


def _human(request: Request, actor=Depends(_actor)):
    if request.state.auth.method != "jwt":
        raise HTTPException(403, "Confirm proposals using a logged-in user session")
    return actor


def _call(service, function, *args, **kwargs):
    try:
        return APIResponse(data=service._safe(function(*args, **kwargs)))
    except KeyError:
        raise HTTPException(404, "Agent resource not found") from None
    except ValueError as exc:
        raise HTTPException(409, service._safe(str(exc))) from exc


@router.get("/config-status")
def config_status(service=Depends(_service)):
    return APIResponse(data=service.config.public_status())


@router.get("/sessions")
def list_sessions(actor=Depends(_actor), service=Depends(_service)):
    return _call(service, service.repository.list, "session", actor)


@router.post("/sessions")
def create_session(
    body: SessionRequest, actor=Depends(_actor), service=Depends(_service)
):
    return _call(service, service.repository.create_session, actor, body.title)


@router.get("/sessions/{session_id}")
def get_session(session_id: str, actor=Depends(_actor), service=Depends(_service)):
    data = service.repository.get_session(actor, session_id)
    if data is None:
        raise HTTPException(404, "Session not found")
    return APIResponse(data=service._safe(data))


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, actor=Depends(_actor), service=Depends(_service)):
    if service.repository.get("session", actor, session_id) is None:
        raise HTTPException(404, "Session not found")
    active = [
        t
        for t in service.repository.list("turn", actor, session_id)
        if t["status"] in {"queued", "running"}
    ]
    if active:
        raise HTTPException(409, "Cancel the active turn before deleting this session")
    operations = service.repository.list("operation", actor, session_id)
    if any(
        op["status"] in {"prepared", "committing", "accepted", "running", "unknown"}
        for op in operations
    ):
        raise HTTPException(409, "Session has an active or uncertain operation")
    return _call(service, service.repository.delete_session, actor, session_id)


@router.post("/sessions/{session_id}/turns")
async def submit_turn(
    session_id: str, body: TurnRequest, actor=Depends(_actor), service=Depends(_service)
):
    try:
        data = await service.submit_turn(actor, session_id, body.message, body.job_id)
        return APIResponse(data=data)
    except KeyError:
        raise HTTPException(404, "Session not found") from None
    except ValueError as exc:
        raise HTTPException(409, service._safe(str(exc))) from exc


@router.get("/turns/{turn_id}")
def get_turn(turn_id: str, actor=Depends(_actor), service=Depends(_service)):
    def detail():
        turn = service._require("turn", actor, turn_id)
        turn["last_seq"] = service.repository.last_seq(actor, turn["session_id"])
        return turn

    return _call(service, detail)


@router.post("/turns/{turn_id}/cancel")
async def cancel_turn(turn_id: str, actor=Depends(_actor), service=Depends(_service)):
    return _call(service, service.cancel, actor, turn_id)


@router.get("/sessions/{session_id}/events")
async def events(
    request: Request,
    session_id: str,
    after: int = Query(default=0, ge=0),
    actor=Depends(_actor),
    service=Depends(_service),
):
    if service.repository.get("session", actor, session_id) is None:
        raise HTTPException(404, "Session not found")
    last_event = request.headers.get("last-event-id")
    if last_event:
        try:
            after = max(after, int(last_event))
        except ValueError:
            raise HTTPException(422, "Invalid Last-Event-ID") from None

    async def stream():
        cursor = after
        while not await request.is_disconnected() and not service.closed:
            batch = service.repository.events(actor, session_id, cursor)
            for event in batch:
                cursor = event["seq"]
                yield (
                    "id: "
                    + str(cursor)
                    + "\ndata: "
                    + json.dumps(service._safe(event), ensure_ascii=False)
                    + "\n\n"
                )
            if not batch:
                yield ": keepalive\n\n"
                await asyncio.sleep(1)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/turns/{turn_id}/events")
async def turn_events(
    request: Request,
    turn_id: str,
    after: int = Query(default=0, ge=0),
    actor=Depends(_actor),
    service=Depends(_service),
):
    try:
        turn = service._require("turn", actor, turn_id)
    except KeyError:
        raise HTTPException(404, "Turn not found") from None
    last_event = request.headers.get("last-event-id")
    if last_event:
        try:
            after = max(after, int(last_event))
        except ValueError:
            raise HTTPException(422, "Invalid Last-Event-ID") from None

    async def stream():
        cursor = after
        while not await request.is_disconnected() and not service.closed:
            batch = service.repository.events(actor, turn["session_id"], cursor)
            for event in batch:
                cursor = event["seq"]
                if event["turn_id"] != turn_id:
                    continue
                yield (
                    "id: "
                    + str(cursor)
                    + "\ndata: "
                    + json.dumps(service._safe(event), ensure_ascii=False)
                    + "\n\n"
                )
                if event["type"] in {"turn.completed", "turn.failed"}:
                    return
            latest = service.repository.get("turn", actor, turn_id)
            if latest is None or (
                latest["status"] not in {"queued", "running"} and not batch
            ):
                return
            if not batch:
                yield ": keepalive\n\n"
                await asyncio.sleep(0.2)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/proposals/{proposal_id}")
def get_proposal(proposal_id: str, actor=Depends(_actor), service=Depends(_service)):
    return _call(service, service._require, "proposal", actor, proposal_id)


@router.post("/proposals/{proposal_id}/approve")
def approve(
    proposal_id: str,
    body: ApprovalRequest,
    actor=Depends(_human),
    service=Depends(_service),
):
    return _call(service, service.approve, actor, proposal_id, body.proposal_version)


@router.post("/proposals/{proposal_id}/reject")
def reject(
    proposal_id: str,
    body: StrictRequest,
    actor=Depends(_actor),
    service=Depends(_service),
):
    return _call(service, service.reject, actor, proposal_id)


@router.post("/proposals/{proposal_id}/revise")
def revise(
    proposal_id: str,
    body: RevisionRequest,
    actor=Depends(_actor),
    service=Depends(_service),
):
    return _call(service, service.revise, actor, proposal_id, enabled=body.enabled)


@router.get("/operations/{operation_id}")
def operation(operation_id: str, actor=Depends(_actor), service=Depends(_service)):
    return _call(service, service.get_operation, actor, operation_id)
