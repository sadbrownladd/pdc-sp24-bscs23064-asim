Abdullah Asim | BSCS23064

# PDC Assignment 2  "Building Resilient Distributed Systems"

## How to Run

### 1. Install Python (if not installed)
Download from https://www.python.org/downloads/  install version 3.11 or higher.

### 2. Install dependencies
Open a terminal in VS Code (Terminal → New Terminal) and run:

```bash
pip install -r requirements.txt
```

### 3. Start the API server
```bash
uvicorn backend.main:app --reload
```

The server will start at http://127.0.0.1:8000

You can visit http://127.0.0.1:8000/docs for the interactive API documentation.

### 4. Run the tests (open a second terminal)
```bash
python tests/test_circuit_breaker.py
```

---

## What the Code Does

### Problem Solved: Fault Tolerance (Circuit Breaker Pattern)

The `/api/llm/generate` endpoint is protected by a Circuit Breaker.

- **CLOSED state**: All requests pass through normally
- **OPEN state**: After 3 failures, the breaker opens. Instead of waiting 60 seconds for a timeout, every request immediately gets a helpful fallback response
- **HALF-OPEN state**: After 15 seconds, one probe request goes through to test if the LLM is back

### Bonus: Optimistic Locking (`/api/documents/{id}`)
Prevents the Lost Update problem. Clients send a version number; if it doesn't match, the update is rejected with a 409 Conflict.

### Bonus: Idempotent Webhooks (`/api/webhooks/clerk`)
Every webhook has an `event_id`. Duplicate events are detected and safely ignored, preventing double-processing.

### Custom Header
Every response includes `X-Student-ID: BSCS23064` (injected by FastAPI middleware).

---

## Repository Naming
`PDC-Sp24-BSCS23064-Asim`
