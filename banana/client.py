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
        self._heartbeat_thread = None
        self._heartbeat_stop = None

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

        self.stop_heartbeat()

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
            if (hasattr(e.headers, "get_content_type") and e.headers.get_content_type() == "application/json") or (isinstance(e.headers, dict) and "json" in str(e.headers.get("Content-Type", ""))):
                try:
                    body = json.loads(e.read().decode("utf-8"))
                except Exception:
                    pass
            raise BananaError(f"HTTP {e.code}: {body.get('error') or body.get('code') or e.reason}")

    def heartbeat(self) -> Dict[str, Any]:
        """
        Renew the current claim's liveness without re-claiming it.

        The server (api/heartbeat.js) evicts a claim after EVICTION_SEC
        (120s as of 2026-09-02) of silence on last_active_ts — a
        heartbeat is what refreshes that clock for a turn that is
        legitimately still running, decoupling "still working" from
        "actually dead" (see specs/banana-turn-claim-api.md §7). Call
        this on your own timer well under 120s; 30-40s leaves comfortable
        margin for one missed beat. Prefer start_heartbeat() over calling
        this by hand on a loop — it manages the timer thread for you.

        Echoes the captured fencing token the same way release() does, so
        a heartbeat from a superseded claim instance is rejected (409
        stale_generation) rather than silently reviving state that has
        already moved on.
        """
        if not self.token:
            raise BananaError("Bearer token required to heartbeat the floor.")

        payload: Dict[str, Any] = {"holder": self.holder}
        if self._generation is not None:
            payload["generation"] = self._generation
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.endpoint}/heartbeat",
            data=data,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = {}
            if (hasattr(e.headers, "get_content_type") and e.headers.get_content_type() == "application/json") or (isinstance(e.headers, dict) and "json" in str(e.headers.get("Content-Type", ""))):
                try:
                    body = json.loads(e.read().decode("utf-8"))
                except Exception:
                    pass
            err = body.get("error") if isinstance(body.get("error"), dict) else {}
            raise BananaError(f"HTTP {e.code}: {err.get('message') or body.get('error') or body.get('code') or e.reason}")

    def start_heartbeat(self, interval: float = 30.0) -> None:
        """
        Start a daemon thread that calls heartbeat() every `interval`
        seconds (default 30s, comfortably under the server's 120s
        eviction ceiling) until stop_heartbeat() runs or the process
        exits. Safe to call again to change the interval — it stops any
        existing timer first.

        Best-effort: a failed heartbeat (e.g. you're no longer the
        current holder) is swallowed in the background thread rather
        than raised, since nothing is positioned to catch it there — the
        next claim()/release()/heartbeat() call you make directly is
        where you would find out your floor state changed.
        """
        import threading
        self.stop_heartbeat()
        stop_event = threading.Event()

        def _loop():
            while not stop_event.wait(interval):
                try:
                    self.heartbeat()
                except Exception:
                    pass

        self._heartbeat_stop = stop_event
        self._heartbeat_thread = threading.Thread(target=_loop, daemon=True)
        self._heartbeat_thread.start()

    def stop_heartbeat(self) -> None:
        """Stop the background heartbeat thread started by start_heartbeat(),
        if one is running. Safe to call even if none was ever started."""
        stop_event = self._heartbeat_stop
        if stop_event is not None:
            stop_event.set()
        thread = self._heartbeat_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)
        self._heartbeat_stop = None
        self._heartbeat_thread = None

    @contextmanager
    def hold(self, subject: str = "", preflight: bool = True, heartbeat_interval: Optional[float] = None):
        """
        Atomic context manager:
        with client.hold("task description"):
            # send to discord

        Pass heartbeat_interval (seconds) to automatically run
        start_heartbeat() for the duration of the block — useful for a
        turn whose length isn't known up front. Omitted by default: most
        callers hold the floor briefly and don't need it.
        """
        self.claim(subject=subject, preflight=preflight)
        if heartbeat_interval is not None:
            self.start_heartbeat(heartbeat_interval)
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
        self._heartbeat_task = None

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

        await self.stop_heartbeat()

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

    async def heartbeat(self) -> Dict[str, Any]:
        """Async counterpart to BananaClient.heartbeat() — see there for the
        full rationale. Renews last_active_ts on the current claim without
        re-claiming it; echoes the fencing token so a stale/superseded claim
        instance gets 409 stale_generation instead of silently reviving."""
        import aiohttp
        if not self.token:
            raise BananaError("Bearer token required to heartbeat the floor.")

        data: Dict[str, Any] = {"holder": self.holder}
        if self._generation is not None:
            data["generation"] = self._generation
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.endpoint}/heartbeat", json=data, headers=headers, timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                body = await resp.json()
                if resp.status != 200:
                    err = body.get("error") if isinstance(body.get("error"), dict) else {}
                    raise BananaError(f"HTTP {resp.status}: {err.get('message') or body.get('error') or body.get('code')}")
                return body

    def start_heartbeat(self, interval: float = 30.0) -> None:
        """Start an asyncio background task calling heartbeat() every
        `interval` seconds (default 30s, under the server's 120s eviction
        ceiling). Must be called from a running event loop. Best-effort:
        a failed heartbeat is swallowed in the task, not raised — the next
        direct claim()/release()/heartbeat() call is where a caller finds
        out its floor state changed."""
        import asyncio
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()

        async def _loop():
            try:
                while True:
                    await asyncio.sleep(interval)
                    try:
                        await self.heartbeat()
                    except Exception:
                        pass
            except asyncio.CancelledError:
                pass

        self._heartbeat_task = asyncio.ensure_future(_loop())

    async def stop_heartbeat(self) -> None:
        """Stop the background task started by start_heartbeat(), if one is
        running. Safe to call even if none was ever started."""
        import asyncio
        task = self._heartbeat_task
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                # asyncio.CancelledError is a BaseException (3.8+), not an
                # Exception — a task cancelled before its first run throws
                # this at the throw()/await point itself rather than inside
                # _loop()'s own try/except, so this is the real backstop,
                # not a redundant one.
                pass
            except Exception:
                pass
        self._heartbeat_task = None

    @asynccontextmanager
    async def hold(self, subject: str = "", preflight: bool = True, heartbeat_interval: Optional[float] = None):
        """See BananaClient.hold() — same heartbeat_interval convenience,
        async flavor."""
        await self.claim(subject=subject, preflight=preflight)
        if heartbeat_interval is not None:
            self.start_heartbeat(heartbeat_interval)
        try:
            yield
        finally:
            try:
                await self.release()
            except Exception:
                pass
