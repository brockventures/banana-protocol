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

class BananaClient:
    """Zero-dependency client for the Banana turn-claim API."""

    def __init__(self, token: Optional[str] = None, holder: str = "zero", endpoint: str = DEFAULT_ENDPOINT, timeout: float = 10.0):
        self.token = token
        self.holder = holder
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout

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
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = {}
            if e.headers.get_content_type() == "application/json":
                try:
                    body = json.loads(e.read().decode("utf-8"))
                except Exception:
                    pass
            if e.code == 409 and body.get("code") == "blocked":
                raise BananaBlockedError(body.get("holder", "unknown"), body.get("state", {}))
            raise BananaError(f"HTTP {e.code}: {body.get('error') or body.get('code') or e.reason}")

    def release(self) -> Dict[str, Any]:
        """
        Release the floor after posting.
        """
        if not self.token:
            raise BananaError("Bearer token required to release the floor.")

        data = json.dumps({"holder": self.holder}).encode("utf-8")
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
                return json.loads(resp.read().decode("utf-8"))
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
