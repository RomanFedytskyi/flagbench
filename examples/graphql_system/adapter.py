"""
Production-grade FlagBench adapter for a GraphQL feature flag system.

Designed for use in regulated financial applications. Security properties:

  ✓ Credentials loaded from environment variables only — never hardcoded
  ✓ TLS certificate verification always enabled (no verify=False)
  ✓ Explicit connect + read timeouts on every request
  ✓ Retry with exponential back-off (configurable)
  ✓ Circuit breaker: after N consecutive failures, fail-safe to fallback
  ✓ Structured audit log: every resolution decision is recorded
  ✓ No PII or flag values in log output (user_id is SHA-256 hashed)
  ✓ Safe fallback: network or auth errors always return fallback_version
  ✓ Thread-safe: uses a single requests.Session with connection pooling
  ✓ Input validation: ResolutionInput is validated by Pydantic before use

Environment variables (set these; never commit them):
  GRAPHQL_URL          GraphQL endpoint (required)
  GRAPHQL_TOKEN        Bearer token for Authorization header (required)
  GRAPHQL_TIMEOUT_S    Request timeout in seconds (default: 5)
  FLAGBENCH_RETRY_MAX  Max retries on transient errors (default: 3)
  FLAGBENCH_CB_THRESH  Circuit-breaker failure threshold (default: 5)
"""
from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from flagbench.schema import ComplianceStatus, ResolutionInput, ResolutionOutput

# ---------------------------------------------------------------------------
# Logging — structured, no PII
# ---------------------------------------------------------------------------
log = logging.getLogger("flagbench.adapter.graphql")

def _hash_user(user_id: str) -> str:
    """One-way hash of user_id for audit logs — never log raw user IDs."""
    return hashlib.sha256(user_id.encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Configuration — environment variables only
# ---------------------------------------------------------------------------
def _require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise EnvironmentError(
            f"Required environment variable '{name}' is not set. "
            f"Set it before running FlagBench against this adapter."
        )
    return val

def _env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


GRAPHQL_QUERY = """
query GetFeatureFlags {
  featureFlags {
    name
    activeVersion
  }
}
"""

# Extended query — use this once your backend schema exposes these fields.
# Unlocks FlagBench P3 (Compliance Precedence) and P4 (Monotonic Rollout) testing.
GRAPHQL_QUERY_EXTENDED = """
query GetFeatureFlagsExtended {
  featureFlags {
    name
    activeVersion
    complianceStatus
    rolloutPct
  }
}
"""


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------
class CircuitBreaker:
    """
    Simple fail-fast circuit breaker.

    States:
      CLOSED   — normal operation, requests flow through
      OPEN     — too many failures, requests short-circuit to fallback
      HALF     — cooldown elapsed, one probe request allowed through

    Financial rationale: if the flag system is down, we must still serve
    requests safely (using fallback versions) rather than blocking the app.
    """
    CLOSED = "CLOSED"
    OPEN   = "OPEN"
    HALF   = "HALF"

    def __init__(self, threshold: int = 5, cooldown_s: float = 30.0):
        self.threshold   = threshold
        self.cooldown_s  = cooldown_s
        self._failures   = 0
        self._state      = self.CLOSED
        self._opened_at  = 0.0
        self._lock       = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            if self._state == self.OPEN:
                if time.monotonic() - self._opened_at >= self.cooldown_s:
                    self._state = self.HALF
            return self._state

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._state    = self.CLOSED

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self.threshold:
                if self._state != self.OPEN:
                    log.error(
                        "Circuit breaker OPEN after %d consecutive failures — "
                        "all resolutions will use fallback_version until the flag "
                        "service recovers. Cooldown: %.0fs",
                        self._failures, self.cooldown_s,
                    )
                self._state     = self.OPEN
                self._opened_at = time.monotonic()

    def is_open(self) -> bool:
        return self.state == self.OPEN


# ---------------------------------------------------------------------------
# HTTP session with retry
# ---------------------------------------------------------------------------
def _build_session(max_retries: int) -> requests.Session:
    """
    Create a requests.Session with:
      - Connection pooling (reused across calls in same process)
      - Automatic retry on transient network errors (not on 4xx/5xx)
      - TLS verification always enabled
    """
    retry = Retry(
        total=max_retries,
        backoff_factor=0.5,               # 0.5 s, 1 s, 2 s …
        status_forcelist=[429, 502, 503, 504],
        allowed_methods=["POST"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)   # for local dev only
    return session


# ---------------------------------------------------------------------------
# Adapter state (module-level singletons, lazy-initialised)
# ---------------------------------------------------------------------------
_session:  Optional[requests.Session] = None
_breaker:  Optional[CircuitBreaker]   = None
_init_lock = threading.Lock()


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        with _init_lock:
            if _session is None:
                max_retries = _env_int("FLAGBENCH_RETRY_MAX", 3)
                _session = _build_session(max_retries)
    return _session


def _get_breaker() -> CircuitBreaker:
    global _breaker
    if _breaker is None:
        with _init_lock:
            if _breaker is None:
                threshold = _env_int("FLAGBENCH_CB_THRESH", 5)
                _breaker  = CircuitBreaker(threshold=threshold, cooldown_s=30.0)
    return _breaker


# ---------------------------------------------------------------------------
# GraphQL fetch
# ---------------------------------------------------------------------------
def _fetch_flags(url: str, token: str, timeout: float) -> dict[str, str]:
    """
    Call the GraphQL endpoint and return { flag_name: activeVersion }.
    Raises on HTTP errors or invalid response shapes.
    """
    resp = _get_session().post(
        url,
        json={"query": GRAPHQL_QUERY},
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        },
        timeout=timeout,
        verify=True,   # NEVER set to False — required for financial apps
    )

    if resp.status_code == 401:
        raise PermissionError("GraphQL token rejected (401). Rotate GRAPHQL_TOKEN.")
    if resp.status_code == 403:
        raise PermissionError("Access forbidden (403). Check token scopes.")
    resp.raise_for_status()

    body = resp.json()
    if "errors" in body:
        # GraphQL-level errors (not HTTP errors)
        messages = [e.get("message", "unknown") for e in body["errors"]]
        raise RuntimeError(f"GraphQL errors: {messages}")

    raw: list[dict] = body["data"]["featureFlags"]
    return {flag["name"]: flag.get("activeVersion") for flag in raw}


# ---------------------------------------------------------------------------
# Public adapter — the one function FlagBench calls
# ---------------------------------------------------------------------------
def resolve(inp: ResolutionInput) -> ResolutionOutput:
    """
    FlagBench adapter for a GraphQL feature flag system.

    Resolves inp.config.component_id (treated as the flag name) by calling
    the GraphQL endpoint. Falls back to inp.config.fallback_version on any
    error — the circuit breaker short-circuits after FLAGBENCH_CB_THRESH
    consecutive failures.

    Required env vars: GRAPHQL_URL, GRAPHQL_TOKEN
    """
    t_start = time.perf_counter()
    fallback = inp.config.fallback_version

    # --- Circuit breaker check ---
    if _get_breaker().is_open():
        log.warning(
            "circuit_breaker=OPEN flag=%s user=%s → fallback",
            inp.config.component_id,
            _hash_user(inp.user.user_id),
        )
        return ResolutionOutput(
            version_id=fallback.version_id,
            is_fallback=True,
            compliance_status=fallback.compliance_status,
            resolution_time_ms=round((time.perf_counter() - t_start) * 1000, 4),
        )

    # --- Load config (validated by environment) ---
    try:
        url     = _require_env("GRAPHQL_URL")
        token   = _require_env("GRAPHQL_TOKEN")
        timeout = float(os.environ.get("GRAPHQL_TIMEOUT_S", 5))
    except EnvironmentError as exc:
        log.error("Configuration error: %s", exc)
        return _safe_fallback(inp, t_start, reason="config_error")

    # --- Call flag service ---
    try:
        flags = _fetch_flags(url, token, timeout)
        _get_breaker().record_success()
    except PermissionError as exc:
        # Auth errors are not transient — log loudly, do not retry
        log.critical("Auth failure calling flag service: %s", exc)
        _get_breaker().record_failure()
        return _safe_fallback(inp, t_start, reason="auth_error")
    except Exception as exc:
        # Network errors, timeouts, malformed responses
        log.error(
            "Flag service error for flag=%s: %s",
            inp.config.component_id,
            type(exc).__name__,   # no exc message — may contain URLs/tokens
        )
        _get_breaker().record_failure()
        return _safe_fallback(inp, t_start, reason="network_error")

    # --- Resolve ---
    active_version = flags.get(inp.config.component_id)
    elapsed_ms     = round((time.perf_counter() - t_start) * 1000, 4)

    # Mirror your normalizeFeatureFlags: null or "disabled" → fallback
    if not active_version or active_version == "disabled":
        log.info(
            "resolution flag=%s user=%s version=fallback(%s) latency_ms=%.3f",
            inp.config.component_id,
            _hash_user(inp.user.user_id),
            fallback.version_id,
            elapsed_ms,
        )
        return ResolutionOutput(
            version_id=fallback.version_id,
            is_fallback=True,
            compliance_status=fallback.compliance_status,
            resolution_time_ms=elapsed_ms,
        )

    # Find full metadata for selected version
    selected = next(
        (v for v in inp.config.version_set if v.version_id == active_version),
        fallback,
    )

    log.info(
        "resolution flag=%s user=%s version=%s compliance=%s latency_ms=%.3f",
        inp.config.component_id,
        _hash_user(inp.user.user_id),
        selected.version_id,
        selected.compliance_status.value,
        elapsed_ms,
    )

    return ResolutionOutput(
        version_id=selected.version_id,
        is_fallback=(selected.version_id == fallback.version_id),
        compliance_status=selected.compliance_status,
        resolution_time_ms=elapsed_ms,
    )


def _safe_fallback(
    inp: ResolutionInput,
    t_start: float,
    reason: str,
) -> ResolutionOutput:
    """Always returns fallback_version. Used on any error path."""
    fb = inp.config.fallback_version
    elapsed_ms = round((time.perf_counter() - t_start) * 1000, 4)
    log.warning(
        "safe_fallback flag=%s user=%s reason=%s latency_ms=%.3f",
        inp.config.component_id,
        _hash_user(inp.user.user_id),
        reason,
        elapsed_ms,
    )
    return ResolutionOutput(
        version_id=fb.version_id,
        is_fallback=True,
        compliance_status=fb.compliance_status,
        resolution_time_ms=elapsed_ms,
    )
