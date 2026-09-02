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

class BananaClient:
    """Zero-dependency client for the Banana turn-claim API."""

    def __init__(self, holder: str, token: Optional[str] = None, endpoint: str = DEFAULT_ENDPOINT, timeout: float = 10.0):
        self.token = token
        self.holder = holder
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout
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

    def claim(self, subject: str = "", preflight: bool = True) -> Dict[str, Any]:
        """
        Claim the floor before posting to a shared channel.
        If preflight is True, verifies status before attempting claim.
        Raises BananaBlockedError on 409 if floor is already claimed.
        """
        if not self.token:
            raise BananaError("Bearer token required to claim the floor.")

        if preflight:
            status = self.get_status()
            current_holder = status.get("holder")
            if current_holder and current_holder != self.holder:
                raise BananaBlockedError(current_holder, status.get("state", {}))

        data = json.dumps({"holder": self.holder, "subject": subject}).encode("utf-8")
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
                    subject=body.get("subject") or err.get("subject", subject)
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

    def __init__(self, holder: str, token: Optional[str] = None, endpoint: str = DEFAULT_ENDPOINT, timeout: float = 10.0):
        self.token = token
        self.holder = holder
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout
        # See BananaClient._generation above — same fencing-token rationale,
        # sync and async clients kept in lockstep.
        self._generation: Optional[int] = None

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

    async def claim(self, subject: str = "", preflight: bool = True) -> Dict[str, Any]:
        import aiohttp
        if not self.token:
            raise BananaError("Bearer token required to claim the floor.")

        if preflight:
            status = await self.get_status()
            current_holder = status.get("holder")
            if current_holder and current_holder != self.holder:
                raise BananaBlockedError(current_holder, status.get("state", {}))

        data = {"holder": self.holder, "subject": subject}
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
                        subject=body.get("subject") or err.get("subject", subject)
                    )
                if resp.status != 200:
                    raise BananaError(f"HTTP {resp.status}: {err.get('message') or body.get('error') or body.get('code')}")
                self._generation = BananaClient._extract_generation(body)
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
