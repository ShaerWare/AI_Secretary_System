# AI Secretary System — Consolidated Improvement Plan

> **Version:** 1.0 | **Date:** 2026-01-28 | **Author:** Claude + ShaerWare

---

## Overview

| Parameter | Value |
|-----------|-------|
| Current project score | 7.5/10 |
| Target | 9/10 (production-ready) |
| Developer rate | 50,000₽/week |
| Risk buffer | +20% to estimates |
| Target ROI | < 6 months |
| Strategic goal | 500k+/month revenue |

---

## Strategic Priorities

```
P0 (Blocking)     → Cannot launch to production without this
P1 (High)         → Critical for monetization and scaling
P2 (Medium)       → Improves quality but doesn't block
P3 (Nice-to-have) → After achieving PMF
```

---

## Phase 0: Foundation (BEFORE everything else)
**Timeline: 2 weeks | Budget: 120,000₽**

### 0.1 CI/CD Pipeline [P0]
**Why first:** Without automation, every PR risks breaking production

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  lint-backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'
      - run: |
          pip install ruff mypy
          ruff check .
          ruff format --check .
          # mypy with gradual adoption
          mypy orchestrator.py --ignore-missing-imports

  lint-frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: admin/package-lock.json
      - working-directory: admin
        run: |
          npm ci
          npm run lint
          npm run type-check
          npm run build

  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run Trivy vulnerability scanner
        uses: aquasecurity/trivy-action@master
        with:
          scan-type: 'fs'
          severity: 'CRITICAL,HIGH'
```

**Checklist:**
- [ ] Create `.github/workflows/ci.yml`
- [ ] Add badge to README
- [ ] Configure branch protection (require CI pass)
- [ ] Add Dependabot for Python and npm

### 0.2 Code Restructuring [P0]
**Why:** orchestrator.py is too large (~60 endpoints), hard to maintain

```
AI_Secretary_System/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app factory
│   ├── config.py               # Pydantic Settings
│   ├── dependencies.py         # DI container
│   │
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── auth.py             # 4 endpoints
│   │   ├── services.py         # 6 endpoints
│   │   ├── llm.py              # 12 endpoints (including providers)
│   │   ├── tts.py              # 8 endpoints
│   │   ├── stt.py              # 4 endpoints
│   │   ├── faq.py              # 5 endpoints
│   │   ├── finetune.py         # 10 endpoints
│   │   ├── monitoring.py       # 6 endpoints
│   │   ├── widget.py           # 4 endpoints
│   │   ├── telegram.py         # 8 endpoints
│   │   └── telephony.py        # stub for future
│   │
│   ├── services/
│   │   ├── llm_service.py
│   │   ├── tts_service.py
│   │   ├── stt_service.py
│   │   └── telephony_service.py
│   │
│   └── models/
│       ├── schemas.py          # Pydantic models
│       └── enums.py
│
├── db/                         # ✓ already exists
├── admin/                      # ✓ already exists
├── tests/                      # NEW
│   ├── conftest.py
│   ├── test_llm.py
│   ├── test_tts.py
│   └── test_api.py
│
├── orchestrator.py             # DEPRECATED → app/main.py
└── ...
```

**Migration (step by step):**
```python
# Step 1: app/main.py
from fastapi import FastAPI
from app.routers import auth, llm, tts, stt, faq, finetune, monitoring, widget, telegram

def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Secretary System",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc"
    )

    # Middleware
    app.add_middleware(CORSMiddleware, ...)

    # Routers
    app.include_router(auth.router, prefix="/admin/auth", tags=["auth"])
    app.include_router(llm.router, prefix="/admin/llm", tags=["llm"])
    app.include_router(tts.router, prefix="/admin/tts", tags=["tts"])
    # ... rest

    return app

app = create_app()
```

**Checklist:**
- [ ] Create folder structure
- [ ] Extract auth endpoints to `routers/auth.py`
- [ ] Extract llm endpoints to `routers/llm.py`
- [ ] Add `__init__.py` with versioning
- [ ] Update Dockerfile (WORKDIR /app)
- [ ] Maintain backward compatibility (orchestrator.py → import app)

### 0.3 Basic Security [P0]
**Why:** Cannot accept payments without this

```python
# app/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Secrets (NEVER in code)
    jwt_secret: str
    gemini_api_key: str | None = None
    stripe_secret_key: str | None = None

    # Security
    cors_origins: list[str] = ["http://localhost:5173"]
    rate_limit_requests: int = 100
    rate_limit_period: int = 60  # seconds

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/secretary.db"
    redis_url: str | None = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
```

**Checklist:**
- [ ] Remove `.env.docker` from repository → `.env.docker.example`
- [ ] Add `slowapi` for rate limiting
- [ ] Configure CORS whitelist via env
- [ ] Add `python-dotenv` to requirements
- [ ] Security headers (X-Content-Type-Options, X-Frame-Options)

### 0.4 Release Management [P0]

**Checklist:**
- [ ] Create `CHANGELOG.md` (Keep a Changelog format)
- [ ] Create GitHub Release v1.0.0
- [ ] Add `CONTRIBUTING.md`
- [ ] Add `CODE_OF_CONDUCT.md`
- [ ] Configure semantic versioning

---

## Phase 1: Monetization (MVP for revenue)
**Timeline: 3 weeks | Budget: 180,000₽**

### 1.1 Stripe/YooKassa Integration [P1]
**ROI: High — blocker for any revenue**

```python
# app/routers/billing.py
from fastapi import APIRouter, Depends, HTTPException
from stripe import Subscription, Customer, checkout

router = APIRouter()

PLANS = {
    "basic": {"price_id": "price_xxx", "minutes": 100, "voices": 2},
    "pro": {"price_id": "price_yyy", "minutes": 500, "voices": 5},
    "enterprise": {"price_id": "price_zzz", "minutes": -1, "voices": -1},  # unlimited
}

@router.post("/checkout")
async def create_checkout_session(plan: str, user_id: str):
    """Create payment session"""
    if plan not in PLANS:
        raise HTTPException(400, "Invalid plan")

    session = checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{"price": PLANS[plan]["price_id"], "quantity": 1}],
        mode="subscription",
        success_url=f"{settings.frontend_url}/billing/success",
        cancel_url=f"{settings.frontend_url}/billing/cancel",
        metadata={"user_id": user_id, "plan": plan}
    )
    return {"checkout_url": session.url}

@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe events"""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    event = stripe.Webhook.construct_event(
        payload, sig_header, settings.stripe_webhook_secret
    )

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        await activate_subscription(
            user_id=session["metadata"]["user_id"],
            plan=session["metadata"]["plan"]
        )
    elif event["type"] == "invoice.payment_failed":
        await suspend_subscription(...)

    return {"status": "ok"}
```

**Subscription Model:**

| Plan | Price | Minutes/month | Voices | Fine-tuning | Integrations |
|------|-------|---------------|--------|-------------|--------------|
| Basic | 990₽ | 100 | 2 | No | Widget |
| Pro | 2,990₽ | 500 | 5 | 1/month | Widget + Telegram |
| Enterprise | 9,990₽ | Unlimited | Unlimited | Unlimited | All + API + SLA |

**Checklist:**
- [ ] Register Stripe/YooKassa account
- [ ] Create products and prices
- [ ] Implement `routers/billing.py`
- [ ] Add `subscriptions` table to DB
- [ ] Middleware for limit checks
- [ ] UI: pricing page in admin
- [ ] Webhook endpoint with signature verification

### 1.2 Usage Limits [P1]

```python
# app/middleware/usage.py
from fastapi import Request, HTTPException
from db.repositories.usage import UsageRepository

class UsageLimitMiddleware:
    async def __call__(self, request: Request, call_next):
        user = request.state.user

        # Check only for billing-sensitive endpoints
        if request.url.path.startswith("/v1/audio/speech"):
            usage = await UsageRepository.get_current_month(user.id)
            plan = await SubscriptionRepository.get_plan(user.id)

            if usage.minutes >= plan.minutes_limit and plan.minutes_limit != -1:
                raise HTTPException(
                    status_code=402,
                    detail={
                        "error": "usage_limit_exceeded",
                        "limit": plan.minutes_limit,
                        "used": usage.minutes,
                        "upgrade_url": "/billing/upgrade"
                    }
                )

        response = await call_next(request)
        return response
```

**Checklist:**
- [ ] Table `usage_logs` (user_id, type, amount, timestamp)
- [ ] Middleware for counting TTS/STT minutes
- [ ] API endpoint `/admin/usage/stats`
- [ ] UI: dashboard with usage graphs
- [ ] Email notifications at 80% and 100% limit

### 1.3 Legal Compliance [P1]
**CRITICAL for Russia: 152-FZ on Personal Data**

**Checklist:**
- [ ] Privacy Policy
- [ ] Voice processing consent (checkbox at registration)
- [ ] Call recording consent (IVR message)
- [ ] Right to deletion (GDPR Article 17)
- [ ] Encryption of voice recordings at rest (AES-256)
- [ ] Disclaimer in README about voice ethics

```python
# Example consent
VOICE_CONSENT_TEXT = """
By clicking "Agree", you consent to:
1. Recording and storing samples of your voice
2. Using your voice for speech synthesis within the service
3. Processing voice data on Russian Federation territory

You can revoke consent at any time through account settings.
"""
```

---

## Phase 2: SIM7600G-H Telephony
**Timeline: 4 weeks | Budget: 240,000₽**

### 2.1 Hardware Abstraction [P1]

```python
# app/services/modem_service.py
import serial
import asyncio
from enum import Enum
from typing import AsyncIterator

class ATCommand(str, Enum):
    """Whitelist of allowed commands"""
    # Informational (safe)
    SIGNAL = "AT+CSQ"
    OPERATOR = "AT+COPS?"
    IMEI = "AT+GSN"
    SIM_STATUS = "AT+CPIN?"

    # Calls (require authorization)
    DIAL = "ATD"      # ATD+79001234567;
    ANSWER = "ATA"
    HANGUP = "ATH"

    # SMS (require authorization)
    SMS_MODE = "AT+CMGF=1"
    SMS_SEND = "AT+CMGS"

class ModemService:
    def __init__(self, port: str = "/dev/ttyUSB0"):
        self.port = port
        self.serial: serial.Serial | None = None
        self.lock = asyncio.Lock()
        self._call_whitelist: set[str] = set()  # Allowed numbers

    async def connect(self) -> bool:
        """Connect to modem with verification"""
        try:
            self.serial = serial.Serial(
                self.port,
                baudrate=115200,
                timeout=1,
                write_timeout=1
            )
            # Connection test
            response = await self._send_raw("AT")
            return "OK" in response
        except serial.SerialException as e:
            logger.error(f"Modem connection failed: {e}")
            return False

    async def _send_raw(self, command: str) -> str:
        """Low-level send (internal use only)"""
        async with self.lock:
            self.serial.write(f"{command}\r\n".encode())
            await asyncio.sleep(0.1)
            return self.serial.read(1024).decode(errors='ignore')

    async def send_command(self, cmd: ATCommand, params: str = "") -> str:
        """Safe send with whitelist"""
        full_command = f"{cmd.value}{params}"

        # Additional check for calls
        if cmd == ATCommand.DIAL:
            phone = params.rstrip(';')
            if not self._validate_phone(phone):
                raise SecurityError(f"Phone not in whitelist: {phone}")

        return await self._send_raw(full_command)

    def _validate_phone(self, phone: str) -> bool:
        """Phone number validation"""
        # Basic format validation
        import re
        if not re.match(r'^\+?[0-9]{10,15}$', phone):
            return False

        # Whitelist check (if enabled)
        if self._call_whitelist and phone not in self._call_whitelist:
            return False

        # Block premium numbers (8-900, 8-809, etc.)
        blocked_prefixes = ['900', '809', '803', '806', '807']
        normalized = phone.lstrip('+').lstrip('7').lstrip('8')
        return not any(normalized.startswith(p) for p in blocked_prefixes)

    async def get_signal_strength(self) -> dict:
        """Signal level in dBm"""
        response = await self.send_command(ATCommand.SIGNAL)
        # Parse: +CSQ: 18,0 → rssi=18, ber=0
        match = re.search(r'\+CSQ:\s*(\d+),(\d+)', response)
        if match:
            rssi = int(match.group(1))
            # Convert to dBm: -113 + rssi*2
            dbm = -113 + rssi * 2 if rssi < 99 else None
            return {"rssi": rssi, "dbm": dbm, "quality": self._rssi_to_quality(rssi)}
        return {"error": "Failed to parse signal"}

    @staticmethod
    def _rssi_to_quality(rssi: int) -> str:
        if rssi >= 20: return "excellent"
        if rssi >= 15: return "good"
        if rssi >= 10: return "fair"
        if rssi >= 5: return "poor"
        return "no_signal"
```

### 2.2 Call Manager [P1]

```python
# app/services/call_manager.py
from enum import Enum
from dataclasses import dataclass
from datetime import datetime

class CallState(str, Enum):
    IDLE = "idle"
    RINGING = "ringing"
    ACTIVE = "active"
    HOLD = "hold"
    ENDED = "ended"

@dataclass
class Call:
    id: str
    phone_number: str
    direction: str  # "inbound" | "outbound"
    state: CallState
    started_at: datetime
    ended_at: datetime | None = None
    recording_path: str | None = None
    transcript: str | None = None

class CallManager:
    def __init__(
        self,
        modem: ModemService,
        stt: STTService,
        llm: LLMService,
        tts: TTSService
    ):
        self.modem = modem
        self.stt = stt
        self.llm = llm
        self.tts = tts
        self.active_calls: dict[str, Call] = {}

    async def handle_incoming_call(self, phone: str) -> Call:
        """Handle incoming call"""
        call_id = str(uuid.uuid4())
        call = Call(
            id=call_id,
            phone_number=phone,
            direction="inbound",
            state=CallState.RINGING,
            started_at=datetime.utcnow()
        )
        self.active_calls[call_id] = call

        # Auto-answer after 2 seconds
        await asyncio.sleep(2)
        await self.modem.send_command(ATCommand.ANSWER)
        call.state = CallState.ACTIVE

        # Greeting
        greeting = await self.tts.synthesize(
            "Hello! You've reached ShaerWare. How can I help you?"
        )
        await self._play_audio(greeting)

        # Start pipeline
        await self._run_conversation_loop(call)

        return call

    async def _run_conversation_loop(self, call: Call):
        """Main conversation loop"""
        while call.state == CallState.ACTIVE:
            # 1. Listen to user (STT)
            user_speech = await self.stt.listen_from_modem(timeout=10)

            if not user_speech:
                # Silence — clarify
                await self._say("Are you still there?")
                continue

            if self._is_goodbye(user_speech):
                await self._say("Goodbye! Have a nice day!")
                await self.hangup(call.id)
                break

            # 2. Generate response (LLM)
            response = await self.llm.generate(
                prompt=user_speech,
                context={"phone": call.phone_number, "call_id": call.id}
            )

            # 3. Speak (TTS)
            await self._say(response)

    async def hangup(self, call_id: str):
        """End call"""
        if call_id not in self.active_calls:
            return

        call = self.active_calls[call_id]
        await self.modem.send_command(ATCommand.HANGUP)
        call.state = CallState.ENDED
        call.ended_at = datetime.utcnow()

        # Save to DB
        await CallRepository.save(call)
        del self.active_calls[call_id]
```

### 2.3 Admin Panel Endpoints [P1]

```python
# app/routers/telephony.py
from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse

router = APIRouter()

@router.get("/modem/status")
async def get_modem_status(modem: ModemService = Depends(get_modem)):
    """Modem status"""
    return {
        "connected": modem.is_connected,
        "signal": await modem.get_signal_strength(),
        "operator": await modem.get_operator(),
        "sim_status": await modem.get_sim_status()
    }

@router.get("/calls/active")
async def get_active_calls(manager: CallManager = Depends(get_call_manager)):
    """List of active calls"""
    return [
        {
            "id": call.id,
            "phone": mask_phone(call.phone_number),
            "direction": call.direction,
            "state": call.state,
            "duration": (datetime.utcnow() - call.started_at).seconds
        }
        for call in manager.active_calls.values()
    ]

@router.post("/calls/{call_id}/hangup")
async def hangup_call(call_id: str, manager: CallManager = Depends(get_call_manager)):
    """End call"""
    if call_id not in manager.active_calls:
        raise HTTPException(404, "Call not found")
    await manager.hangup(call_id)
    return {"status": "ended"}

@router.get("/calls/stream")
async def stream_calls(manager: CallManager = Depends(get_call_manager)):
    """SSE call status stream"""
    async def event_generator():
        while True:
            for call in manager.active_calls.values():
                yield {
                    "event": "call_status",
                    "data": json.dumps({
                        "id": call.id,
                        "state": call.state,
                        "duration": (datetime.utcnow() - call.started_at).seconds
                    })
                }
            await asyncio.sleep(1)

    return EventSourceResponse(event_generator())

@router.get("/calls/history")
async def get_call_history(
    limit: int = 50,
    offset: int = 0,
    repo: CallRepository = Depends(get_call_repo)
):
    """Call history"""
    calls = await repo.get_paginated(limit=limit, offset=offset)
    return {
        "calls": calls,
        "total": await repo.count()
    }
```

### 2.4 Circuit Breaker [P1]

```python
# app/services/resilience.py
from circuitbreaker import circuit
from tenacity import retry, stop_after_attempt, wait_exponential

class ResilientLLMService:
    def __init__(self, vllm: VLLMService, cloud: CloudLLMService):
        self.vllm = vllm
        self.cloud = cloud
        self._use_local = True

    @circuit(failure_threshold=3, recovery_timeout=60)
    async def _query_cloud(self, prompt: str) -> str:
        """Cloud LLM with circuit breaker"""
        return await self.cloud.generate(prompt)

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=4))
    async def _query_local(self, prompt: str) -> str:
        """Local vLLM with retry"""
        return await self.vllm.generate(prompt)

    async def generate(self, prompt: str) -> str:
        """Smart fallback: local → cloud"""
        if self._use_local:
            try:
                return await self._query_local(prompt)
            except Exception as e:
                logger.warning(f"vLLM failed, falling back to cloud: {e}")
                self._use_local = False

        try:
            return await self._query_cloud(prompt)
        except CircuitBreakerError:
            logger.error("Both LLM backends unavailable")
            return "Sorry, the service is temporarily unavailable. Please try again later."
```

---

## Phase 3: Observability & Quality
**Timeline: 2 weeks | Budget: 120,000₽**

### 3.1 Structured Logging [P2]

```python
# app/logging_config.py
import structlog
from structlog.typing import FilteringBoundLogger

def configure_logging():
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer()
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )

logger: FilteringBoundLogger = structlog.get_logger()

# Usage in code
async def handle_call(call_id: str, phone: str):
    structlog.contextvars.bind_contextvars(
        call_id=call_id,
        phone=mask_phone(phone)
    )
    logger.info("call_started")
    # ... all logs inside will contain call_id
    logger.info("call_ended", duration=120)
```

### 3.2 Prometheus Metrics [P2]

```python
# app/metrics.py
from prometheus_client import Counter, Histogram, Gauge, generate_latest

# Business metrics
CALLS_TOTAL = Counter(
    'secretary_calls_total',
    'Total calls processed',
    ['direction', 'status', 'persona']
)
CALL_DURATION = Histogram(
    'secretary_call_duration_seconds',
    'Call duration in seconds',
    buckets=[10, 30, 60, 120, 300, 600]
)
SUBSCRIPTION_REVENUE = Gauge(
    'secretary_subscription_revenue_rub',
    'Monthly recurring revenue'
)

# Technical metrics
LLM_LATENCY = Histogram(
    'secretary_llm_latency_seconds',
    'LLM response time',
    ['backend']
)
TTS_LATENCY = Histogram(
    'secretary_tts_latency_seconds',
    'TTS synthesis time',
    ['voice']
)
GPU_MEMORY = Gauge(
    'secretary_gpu_memory_mb',
    'GPU memory usage',
    ['gpu_id']
)
MODEM_SIGNAL = Gauge(
    'secretary_modem_signal_dbm',
    'Modem signal strength in dBm'
)

# Prometheus endpoint
@router.get("/metrics")
async def metrics():
    return Response(
        content=generate_latest(),
        media_type="text/plain"
    )
```

### 3.3 Testing [P1]

```python
# tests/conftest.py
import pytest
from httpx import AsyncClient
from app.main import create_app
from db.database import get_test_database

@pytest.fixture
async def app():
    """Test application"""
    app = create_app()
    app.dependency_overrides[get_database] = get_test_database
    yield app

@pytest.fixture
async def client(app):
    """Test client"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

# tests/test_llm.py
@pytest.mark.asyncio
async def test_llm_generate(client: AsyncClient):
    """Test response generation"""
    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "gulya-secretary-qwen",
            "messages": [{"role": "user", "content": "Hello!"}]
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "choices" in data
    assert len(data["choices"]) > 0

# tests/test_billing.py
@pytest.mark.asyncio
async def test_usage_limit(client: AsyncClient, mock_user_at_limit):
    """Test limit exceeded"""
    response = await client.post(
        "/v1/audio/speech",
        json={"input": "Test", "voice": "gulya"},
        headers={"Authorization": f"Bearer {mock_user_at_limit.token}"}
    )
    assert response.status_code == 402
    assert response.json()["error"] == "usage_limit_exceeded"

# tests/test_telephony.py
@pytest.mark.asyncio
async def test_phone_validation():
    """Test phone number validation"""
    modem = ModemService.__new__(ModemService)
    modem._call_whitelist = set()

    # Valid numbers
    assert modem._validate_phone("+79001234567") == True
    assert modem._validate_phone("89001234567") == True

    # Premium numbers (blocked)
    assert modem._validate_phone("+79001234567") == True
    assert modem._validate_phone("89091234567") == False  # 8-909 - not premium
    assert modem._validate_phone("89001234567") == False  # 8-900 - premium
```

---

## Summary Timeline

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Week   │  1  │  2  │  3  │  4  │  5  │  6  │  7  │  8  │  9  │ 10  │ 11 │
├─────────────────────────────────────────────────────────────────────────┤
│ Phase 0│ ███████████ │                                                  │
│ CI/CD  │ ████        │                                                  │
│ Refact │     ████████│                                                  │
├─────────────────────────────────────────────────────────────────────────┤
│ Phase 1│             │████████████████████│                             │
│ Stripe │             │████████            │                             │
│ Usage  │             │        ████████    │                             │
│ Legal  │             │            ████████│                             │
├─────────────────────────────────────────────────────────────────────────┤
│ Phase 2│                                  │████████████████████████████│
│ Modem  │                                  │████████                    │
│ Calls  │                                  │        ████████████        │
│ UI     │                                  │                    ████████│
├─────────────────────────────────────────────────────────────────────────┤
│ Phase 3│                                              │████████████████│
│ (paral)│                                              │ Logs │ Tests  │
└─────────────────────────────────────────────────────────────────────────┘

Total: 11 weeks
Budget: 660,000₽ (with 20% buffer → 792,000₽)
```

---

## ROI Calculation

| Item | Investment | Expected Revenue/Savings |
|------|------------|--------------------------|
| Subscriptions (100 clients × 2000₽) | 180,000₽ development | 200,000₽/month |
| Telephony (secretary replacement) | 240,000₽ development | 80,000₽/month savings |
| Quality (fewer bugs) | 120,000₽ development | 50,000₽/month savings |
| **Total** | **540,000₽** | **330,000₽/month** |

**Breakeven: ~2 months after monetization launch**

---

## Production Readiness Checklist

### Infrastructure
- [ ] CI/CD passes on all PRs
- [ ] Docker Compose starts from scratch in < 5 minutes
- [ ] Healthcheck endpoints work
- [ ] Graceful shutdown implemented

### Security
- [ ] All secrets in `.env`, not in code
- [ ] Rate limiting on public endpoints
- [ ] CORS configured via whitelist
- [ ] HTTPS configured (Let's Encrypt)
- [ ] AT commands go through whitelist

### Quality
- [ ] Test coverage > 60%
- [ ] All critical paths covered by tests
- [ ] No critical/high Trivy alerts
- [ ] README is up to date

### Business
- [ ] Subscriptions work end-to-end
- [ ] Privacy policy on website
- [ ] Voice processing consent form
- [ ] Email support configured

### Monitoring
- [ ] Prometheus metrics exported
- [ ] Logs in JSON format
- [ ] Alerting on critical errors

---

## Anti-patterns (What NOT to do)

1. **Don't start with Kubernetes** — Docker Compose is enough until 1000 users
2. **Don't do everything at once** — one feature per sprint
3. **Don't ignore legal** — 152-FZ can cost you your business
4. **Don't store secrets in code** — even "temporarily"
5. **Don't skip tests** — one bug in telephony = lost customer
6. **Don't complicate AT commands** — whitelist is simpler and safer

---

## Resources

- [SIM7600 AT Commands Manual](https://www.simcom.com/product/SIM7600G-H.html)
- [Stripe Python SDK](https://stripe.com/docs/api/python)
- [FastAPI Best Practices](https://fastapi.tiangolo.com/tutorial/)
- [152-FZ on Personal Data](http://www.consultant.ru/document/cons_doc_LAW_61801/)
- [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)

---

> **Next step:** Create GitHub Issue for Phase 0.1 (CI/CD Pipeline)
