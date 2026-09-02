"""
banana.client - Canonical Zero-Dependency Turn-Claim Mutex Client.
Interacts with the Banana API to ensure only one agent speaks in shared channels at a time.
"""

import json
import urllib.request
import urllib.error
from contextlib import contextmanager
from typing import Optional, Dict, Any

DEFAULT_ENDPOINT = "https://banana.mikecarmody.net/api"
DEFAULT_LEASE_TTL_SECONDS = 120  # Ratified 2-minute floor lease ceiling

class BananaError(Exception):
    """Base exception for all Banana protocol errors."""
    pass

class BananaBlockedError(BananaError):
    """Raised on 409 Conflict when another agent holds the floor."""
    def __init__(self, current_holder: str, state: Dict[str, Any]):
        super().__init__(f"Floor is currently held by '{current_holder}'")
        self.current_holder = current_holder
        self.state = state

class BananaRoundLimitExceededError(BananaError):
    """Raised on HTTP 429 when a subject has exceeded the server's hard round limit."""
    def __init__(self, round: int, hard_limit: int, subject: str = ""):
        super().__init__(f"Round limit exceeded for subject '{subject}': reached round {round} (hard limit: {hard_limit})")
        self.round = round
        self.hard_limit = hard_limit
        self.subject = subject

class SubjectCache:
    """Client-side cache for conversation subjects, preserving topic continuity across turns."""
    def __init__(self):
        self._cache: Dict[str, str] = {}
        self._last_subject: Optional[str] = None

    def get(self, key: str = "default") -> Optional[str]:
        if key in self._cache:
            return self._cache[key]
        if key == "default":
            return self._last_subject
        return None

    def set(self, subject: str, key: str = "default") -> None:
        if subject:
            self._cache[key] = subject
            self._last_subject = subject

    def clear(self, key: Optional[str] = None) -> None:
        if key:
            removed = self._cache.pop(key, None)
            if self._last_subject == removed:
                self._last_subject = None
        else:
            self._cache.clear()
            self._last_subject = None

    @property
    def last_subject(self) -> Optional[str]:
        return self._last_subject

class BananaClient:
    """Zero-dependency client for the Banana turn-claim API."""

    def __init__(self, holder: str, token: Optional[str] = None, endpoint: str = DEFAULT_ENDPOINT, timeout: float = 10.0, lease_ttl: int = DEFAULT_LEASE_TTL_SECONDS):
        self.token = token
        self.holder = holder
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout
        self.lease_ttl = lease_ttl
        self.subject_cache = SubjectCache()
        # Fencing token (Kleppmann's Redlock critique: a TTL alone can't
        # distinguish "paused" from "dead", so a late-recovering holder that
        # never noticed it lost the lock can still stomp whoever claimed it
        # next). Captured from the claim response's `state.id`, echoed back
        # on release so the server has what it needs to reject a stale
        # release once it validates this field. Purely additive until then —
        # a server that ignores `generation` behaves exactly as before.
        self._generation: Optional[int] = None

    def get_status(self) -> Dict[str, Any]:
        """
        Check current floor status without authentication.
        Returns dict with 'holder' (str or None) and 'state'.
        """
        req = urllib.request.Request(f"{self.endpoint}/status")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def is_free(self) -> bool:
        """Return True if the floor is free to be claimed."""
        try:
            status = self.get_status()
            return status.get("holder") is None
        except Exception:
            return False

    @staticmethod
    def _extract_generation(body: Dict[str, Any]) -> Optional[int]:
        """Pull the fencing token out of a claim response. Checks `state.id`
        (the shape `/api/status` and `/api/claim` already document) and falls
        back to a top-level `generation`/`id`, since the exact key a given
        server version returns isn't guaranteed. None on any miss — a server
        with no concept of this yet just means fencing stays a no-op."""
        state = body.get("state") if isinstance(body.get("state"), dict) else {}
        for key, source in (("generation", body), ("id", state), ("id", body)):
            val = source.get(key)
            if isinstance(val, int):
                return val
        return None

    @staticmethod
    def is_lease_expired(state: Dict[str, Any], ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS, current_time: Optional[float] = None) -> bool:
        """Check whether a lock state has exceeded the lease duration (default 120s / 2min)."""
        import time
        now = current_time if current_time is not None else time.time()
        claimed_at = state.get("last_active_ts") or state.get("claimed_at")
        if not claimed_at or not isinstance(claimed_at, (int, float)):
            return False
        return (now - float(claimed_at)) > ttl_seconds

    def get_cached_subject(self, key: str = "default") -> Optional[str]:
        return self.subject_cache.get(key)

    def set_cached_subject(self, subject: str, key: str = "default") -> None:
        self.subject_cache.set(subject, key)

    def clear_subject_cache(self, key: Optional[str] = None) -> None:
        self.subject_cache.clear(key)

    def claim(self, subject: str = "", preflight: bool = True, cache_key: str = "default") -> Dict[str, Any]:
        """
        Claim the floor before posting to a shared channel.
        If preflight is True, verifies status before attempting claim.
        If subject is empty, falls back to subject_cache if available.
        Raises BananaBlockedError on 409 if floor is already claimed.
        """
        if not self.token:
            raise BananaError("Bearer token required to claim the floor.")

        if preflight:
            status = self.get_status()
            current_holder = status.get("holder")
            if current_holder and current_holder != self.holder:
                raise BananaBlockedError(current_holder, status.get("state", {}))

        effective_subject = subject or self.subject_cache.get(cache_key) or ""
        data = json.dumps({"holder": self.holder, "subject": effective_subject}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.endpoint}/claim",
            data=data,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                self._generation = self._extract_generation(result)
                returned_subject = result.get("subject") or effective_subject
                if returned_subject:
                    self.subject_cache.set(returned_subject, cache_key)
                return result
        except urllib.error.HTTPError as e:
            body = {}
            if (hasattr(e.headers, "get_content_type") and e.headers.get_content_type() == "application/json") or (isinstance(e.headers, dict) and "json" in str(e.headers.get("Content-Type", ""))):
                try:
                    body = json.loads(e.read().decode("utf-8"))
                except Exception:
                    pass
            err = body.get("error") if isinstance(body.get("error"), dict) else {}
            code = body.get("code") or err.get("code")
            if e.code == 409 and code == "blocked":
                holder = body.get("holder") or err.get("holder") or (body.get("state") or {}).get("holder") or "unknown"
                raise BananaBlockedError(holder, body.get("state", {}))
            if e.code == 429 and code == "round_limit_exceeded":
                raise BananaRoundLimitExceededError(
                    round=body.get("round") or err.get("round", 0),
                    hard_limit=body.get("hard_limit") or err.get("hard_limit", 10),
                    subject=body.get("subject") or err.get("subject", effective_subject)
                )
            raise BananaError(f"HTTP {e.code}: {err.get('message') or body.get('error') or body.get('code') or e.reason}")

    def release(self) -> Dict[str, Any]:
        """
        Release the floor after posting.

        Echoes back the fencing token captured on claim(), if any, so a
        server that validates it can reject a stale release from a holder
        that lost the lock without ever finding out. Omitted entirely when
        there is nothing to echo (no prior claim(), or a server that never
        returned one) — same request shape as before in that case.
        """
        if not self.token:
            raise BananaError("Bearer token required to release the floor.")

        payload: Dict[str, Any] = {"holder": self.holder}
        if self._generation is not None:
            payload["generation"] = self._generation
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.endpoint}/release",
            data=data,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                self._generation = None
                return result
        except urllib.error.HTTPError as e:
            body = {}
            if e.headers.get_content_type() == "application/json":
                try:
                    body = json.loads(e.read().decode("utf-8"))
                except Exception:
                    pass
            raise BananaError(f"HTTP {e.code}: {body.get('error') or body.get('code') or e.reason}")

    @contextmanager
    def hold(self, subject: str = "", preflight: bool = True):
        """
        Atomic context manager:
        with client.hold("task description"):
            # send to discord
        """
        self.claim(subject=subject, preflight=preflight)
        try:
            yield
        finally:
            try:
                self.release()
            except Exception:
                pass

from contextlib import asynccontextmanager

class AsyncBananaClient:
    """Async client using aiohttp for asyncio/aiohttp native stacks (e.g. Marvin/Amos)."""

    def __init__(self, holder: str, token: Optional[str] = None, endpoint: str = DEFAULT_ENDPOINT, timeout: float = 10.0, lease_ttl: int = DEFAULT_LEASE_TTL_SECONDS):
        self.token = token
        self.holder = holder
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout
        self.lease_ttl = lease_ttl
        self.subject_cache = SubjectCache()
        # See BananaClient._generation above — same fencing-token rationale,
        # sync and async clients kept in lockstep.
        self._generation: Optional[int] = None

    def get_cached_subject(self, key: str = "default") -> Optional[str]:
        return self.subject_cache.get(key)

    def set_cached_subject(self, subject: str, key: str = "default") -> None:
        self.subject_cache.set(subject, key)

    def clear_subject_cache(self, key: Optional[str] = None) -> None:
        self.subject_cache.clear(key)

    async def get_status(self) -> Dict[str, Any]:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.endpoint}/status", timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                return await resp.json()

    async def is_free(self) -> bool:
        try:
            status = await self.get_status()
            return status.get("holder") is None
        except Exception:
            return False

    async def claim(self, subject: str = "", preflight: bool = True, cache_key: str = "default") -> Dict[str, Any]:
        import aiohttp
        if not self.token:
            raise BananaError("Bearer token required to claim the floor.")

        if preflight:
            status = await self.get_status()
            current_holder = status.get("holder")
            if current_holder and current_holder != self.holder:
                raise BananaBlockedError(current_holder, status.get("state", {}))

        effective_subject = subject or self.subject_cache.get(cache_key) or ""
        data = {"holder": self.holder, "subject": effective_subject}
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.endpoint}/claim", json=data, headers=headers, timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                body = await resp.json()
                err = body.get("error") if isinstance(body.get("error"), dict) else {}
                code = body.get("code") or err.get("code")
                if resp.status == 409 and code == "blocked":
                    holder = body.get("holder") or err.get("holder") or (body.get("state") or {}).get("holder") or "unknown"
                    raise BananaBlockedError(holder, body.get("state", {}))
                if resp.status == 429 and code == "round_limit_exceeded":
                    raise BananaRoundLimitExceededError(
                        round=body.get("round") or err.get("round", 0),
                        hard_limit=body.get("hard_limit") or err.get("hard_limit", 10),
                        subject=body.get("subject") or err.get("subject", effective_subject)
                    )
                if resp.status != 200:
                    raise BananaError(f"HTTP {resp.status}: {err.get('message') or body.get('error') or body.get('code')}")
                self._generation = BananaClient._extract_generation(body)
                returned_subject = body.get("subject") or effective_subject
                if returned_subject:
                    self.subject_cache.set(returned_subject, cache_key)
                return body

    async def release(self) -> Dict[str, Any]:
        """Same fencing-token echo as the sync client's release() — see there
        for the rationale."""
        import aiohttp
        if not self.token:
            raise BananaError("Bearer token required to release the floor.")

        data: Dict[str, Any] = {"holder": self.holder}
        if self._generation is not None:
            data["generation"] = self._generation
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.endpoint}/release", json=data, headers=headers, timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                body = await resp.json()
                if resp.status != 200:
                    raise BananaError(f"HTTP {resp.status}: {body.get('error') or body.get('code')}")
                self._generation = None
                return body

    @asynccontextmanager
    async def hold(self, subject: str = "", preflight: bool = True):
        await self.claim(subject=subject, preflight=preflight)
        try:
            yield
        finally:
            try:
                await self.release()
            except Exception:
                pass
