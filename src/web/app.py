import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.agent.chat import create_chat_session

app = FastAPI(title="Pundit AI Chat API")

STATIC_DIR = Path(__file__).parent / "static"

# In-memory session store: session_id -> (client, chat). Both must be kept alive together -
# the Chat object depends on its parent Client's underlying HTTP client internally but
# doesn't hold a strong reference to it itself, so storing only `chat` would let `client`
# get garbage-collected and close the connection under it (confirmed directly - see
# create_chat_session()'s docstring). Per-process only - not persisted across server
# restarts and not shared across multiple worker processes. Fine for local testing/a
# single-process demo; a real multi-worker deployment would need an external session store
# (e.g. Redis) instead, since each worker would otherwise have its own separate dict.
sessions: dict[str, tuple] = {}


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ToolCallTrace(BaseModel):
    tool: str
    args: dict
    result: dict | None = None


class ChatResponse(BaseModel):
    session_id: str
    response: str
    debug_trace: list[ToolCallTrace] = []


def _extract_debug_trace(response) -> list[ToolCallTrace]:
    """Pull the tool-call trace out of a Gemini response's automatic_function_calling_history -
    same source agent.py's ask() prints to the terminal (call name/args, then the matching
    result), just structured here instead of printed.

    Calls and their responses are paired by FIFO order, not by matching a single "most recent
    call" - Gemini can (and does, e.g. when asked to compare two players) issue multiple
    function_call parts within a single model turn before any results come back (parallel tool
    calling), so the naive "attach the next response to whichever call I saw last" approach
    silently drops results for every call but the last one in a batch. function_response parts
    don't carry a usable 'id' to pair on either (empirically None in this SDK version) - but
    call order and response order both follow the order the calls were issued in, so a FIFO
    queue pairs them correctly regardless of whether calls are sequential or parallel.
    """
    trace: list[ToolCallTrace] = []
    pending_queue: list[ToolCallTrace] = []
    for content in response.automatic_function_calling_history or []:
        for part in content.parts:
            if part.function_call:
                entry = ToolCallTrace(
                    tool=part.function_call.name,
                    args=dict(part.function_call.args) if part.function_call.args else {},
                )
                trace.append(entry)
                pending_queue.append(entry)
            if part.function_response and pending_queue:
                pending_queue.pop(0).result = part.function_response.response
    return trace


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest) -> ChatResponse:
    """Send a message through the same multi-turn Gemini chat session used by the terminal
    chat (src/agent/chat.py) - full tool set, same SYSTEM_PROMPT, same conversation-memory
    behavior. Conversation state is kept server-side per session_id, so the client only ever
    sends the new message, not the full history each time - pass back the session_id from
    the previous response to continue a conversation; omit it (or send an unknown one) to
    start a new one.
    """
    session_id = request.session_id
    if session_id is None or session_id not in sessions:
        session_id = str(uuid.uuid4())
        sessions[session_id] = create_chat_session()

    _client, chat = sessions[session_id]
    response = chat.send_message(request.message)

    return ChatResponse(
        session_id=session_id,
        response=response.text,
        debug_trace=_extract_debug_trace(response),
    )
