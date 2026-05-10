"""
StudySync Backend - PDC Assignment 2
Author: Abdullah Asim | BSCS23064
"""

from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
from typing import Optional
import asyncio
import time
import random
import httpx

# ─────────────────────────────────────────────
#  Custom Middleware → adds X-Student-ID header
# ─────────────────────────────────────────────
class StudentIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Student-ID"] = "BSCS23064"
        return response


app = FastAPI(title="StudySync API - BSCS23064")

app.add_middleware(StudentIDMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
#  In-memory "database" (simulates a real DB)
# ─────────────────────────────────────────────
documents_db: dict = {}          # { doc_id: { content, version } }
users_db: dict = {}              # { user_id: { is_premium } }
processed_webhooks: set = set()  # idempotency store


# ─────────────────────────────────────────────
#  Pydantic Models
# ─────────────────────────────────────────────
class DocumentUpdate(BaseModel):
    content: str
    version: int          # client must send the version it last read


class WebhookPayload(BaseModel):
    event_id: str         # idempotency key
    user_id: str
    event_type: str       # e.g. "subscription.cancelled"


class LLMRequest(BaseModel):
    prompt: str


# ─────────────────────────────────────────────
#  Root
# ─────────────────────────────────────────────
@app.get("/")
def root():
    return {"message": "StudySync API is running", "student_id": "BSCS23064"}


# ═══════════════════════════════════════════════════════════════
#  PART 3 CHOICE: CIRCUIT BREAKER for the LLM API
# ═══════════════════════════════════════════════════════════════

class CircuitBreaker:
    """
    A simple Circuit Breaker with three states:
      CLOSED  → requests flow normally
      OPEN    → requests are immediately rejected (fail-fast)
      HALF-OPEN → one probe request is allowed through to test recovery
    """

    CLOSED    = "CLOSED"
    OPEN      = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    def __init__(self, failure_threshold=3, recovery_timeout=15):
        self.state            = self.CLOSED
        self.failure_count    = 0
        self.failure_threshold = failure_threshold   # failures before opening
        self.recovery_timeout = recovery_timeout     # seconds before trying again
        self.last_failure_time: Optional[float] = None

    def record_success(self):
        self.failure_count = 0
        self.state = self.CLOSED
        print("[Circuit Breaker] ✅ Success — state reset to CLOSED")

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        print(f"[Circuit Breaker] ❌ Failure #{self.failure_count}")
        if self.failure_count >= self.failure_threshold:
            self.state = self.OPEN
            print(f"[Circuit Breaker] ⚡ OPEN — blocking requests for {self.recovery_timeout}s")

    def can_attempt(self) -> bool:
        if self.state == self.CLOSED:
            return True
        if self.state == self.OPEN:
            elapsed = time.time() - (self.last_failure_time or 0)
            if elapsed >= self.recovery_timeout:
                self.state = self.HALF_OPEN
                print("[Circuit Breaker] 🔄 HALF-OPEN — probing...")
                return True
            return False
        if self.state == self.HALF_OPEN:
            return True
        return False


# Single shared circuit breaker instance
llm_circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=15)


async def call_llm_api(prompt: str) -> str:
    """
    Simulates calling an external LLM API.
    - 40% chance of failure (simulates a flaky/down LLM)
    - Times out after 3 seconds (instead of hanging forever)
    """
    await asyncio.sleep(0.5)   # simulate network latency

    # Simulate the LLM being unreliable
    if random.random() < 0.4:
        raise httpx.TimeoutException("LLM API timed out")

    return f"[LLM Response] Here is a study summary for: '{prompt}'"


@app.post("/api/llm/generate")
async def generate_with_circuit_breaker(req: LLMRequest):
    """
    Protected LLM endpoint.
    - If the circuit is OPEN, returns a fallback immediately (no waiting)
    - If the LLM fails too many times, the breaker opens
    """
    if not llm_circuit_breaker.can_attempt():
        # FAST FAIL: do not even try calling the LLM
        print("[Circuit Breaker] 🚫 Request blocked — circuit is OPEN")
        return JSONResponse(
            status_code=503,
            content={
                "source": "fallback",
                "circuit_state": llm_circuit_breaker.state,
                "response": (
                    "Our AI assistant is temporarily unavailable. "
                    "Please try again in a few seconds. "
                    "In the meantime, check our pre-written study guides!"
                ),
            },
        )

    try:
        result = await asyncio.wait_for(call_llm_api(req.prompt), timeout=3.0)
        llm_circuit_breaker.record_success()
        return {
            "source": "llm",
            "circuit_state": llm_circuit_breaker.state,
            "response": result,
        }

    except (httpx.TimeoutException, asyncio.TimeoutError) as e:
        llm_circuit_breaker.record_failure()
        raise HTTPException(
            status_code=503,
            detail={
                "error": "LLM call failed",
                "circuit_state": llm_circuit_breaker.state,
                "message": str(e),
            },
        )


@app.get("/api/llm/status")
def circuit_breaker_status():
    """Inspect the current circuit breaker state."""
    return {
        "state": llm_circuit_breaker.state,
        "failure_count": llm_circuit_breaker.failure_count,
        "failure_threshold": llm_circuit_breaker.failure_threshold,
        "recovery_timeout_seconds": llm_circuit_breaker.recovery_timeout,
    }

@app.post("/api/llm/reset")
def reset_circuit_breaker():
    """Manually reset the circuit breaker (for testing)."""
    llm_circuit_breaker.state = CircuitBreaker.CLOSED
    llm_circuit_breaker.failure_count = 0
    llm_circuit_breaker.last_failure_time = None
    return {"message": "Circuit breaker reset to CLOSED"}


# ═══════════════════════════════════════════════════════════════
#  BONUS: Optimistic Locking for Documents (Problem 1)
# ═══════════════════════════════════════════════════════════════

@app.post("/api/documents/{doc_id}/create")
def create_document(doc_id: str, content: str = ""):
    if doc_id in documents_db:
        raise HTTPException(status_code=409, detail="Document already exists")
    documents_db[doc_id] = {"content": content, "version": 1}
    return {"doc_id": doc_id, "version": 1, "content": content}


@app.get("/api/documents/{doc_id}")
def get_document(doc_id: str):
    if doc_id not in documents_db:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"doc_id": doc_id, **documents_db[doc_id]}


@app.put("/api/documents/{doc_id}")
def update_document(doc_id: str, update: DocumentUpdate):
    """
    Optimistic Locking:
    Client sends the version it last read. If it doesn't match
    the current version, we reject the update — someone else edited first.
    """
    if doc_id not in documents_db:
        raise HTTPException(status_code=404, detail="Document not found")

    current = documents_db[doc_id]

    if update.version != current["version"]:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "Version conflict — document was modified by another user.",
                "your_version": update.version,
                "current_version": current["version"],
                "hint": "Fetch the latest version and re-apply your changes.",
            },
        )

    documents_db[doc_id] = {
        "content": update.content,
        "version": current["version"] + 1,
    }
    return {"doc_id": doc_id, **documents_db[doc_id]}


# ═══════════════════════════════════════════════════════════════
#  BONUS: Idempotent Webhook Handler (Problem 2)
# ═══════════════════════════════════════════════════════════════

@app.post("/api/webhooks/clerk")
def handle_webhook(payload: WebhookPayload):
    """
    Idempotent webhook handler.
    Uses event_id as an idempotency key — duplicate events are safely ignored.
    """
    if payload.event_id in processed_webhooks:
        print(f"[Webhook] ♻️  Duplicate event {payload.event_id} — ignoring")
        return {"status": "already_processed", "event_id": payload.event_id}

    # Process the event
    if payload.event_type == "subscription.cancelled":
        users_db[payload.user_id] = {"is_premium": False}
        print(f"[Webhook] ✅ User {payload.user_id} downgraded from premium")

    elif payload.event_type == "subscription.created":
        users_db[payload.user_id] = {"is_premium": True}
        print(f"[Webhook] ✅ User {payload.user_id} upgraded to premium")

    # Mark as processed AFTER successful handling
    processed_webhooks.add(payload.event_id)

    return {
        "status": "processed",
        "event_id": payload.event_id,
        "user_id": payload.user_id,
        "event_type": payload.event_type,
    }


@app.get("/api/users/{user_id}")
def get_user(user_id: str):
    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user_id": user_id, **users_db[user_id]}
