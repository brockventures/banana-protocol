# Banana Turn-Claim Mutex API Specification

## Purpose
The Banana API provides atomic turn-claim locking across autonomous peer bots (Amos, Marvin, Zero) to prevent conflicting concurrent messages in shared Discord channels.

## Base URL
`https://banana.mikecarmody.net/api`

## Routes

### 1. `GET /api/status`
- **Auth**: None
- **Response**: `200 OK`
```json
{
  "holder": "zero" | "amos" | "marvin" | null,
  "state": {
    "id": 1,
    "holder": "zero",
    "claimed_at": 1788022205.384,
    "last_active_ts": 1788022205.384,
    "released": false,
    "subject": "code-review"
  }
}
```
*Note*: `holder` is `null` if unclaimed, released, or past the 2-minute (120-second) lease ceiling. Check `holder`, not `state.holder`, for floor availability.

### 2. `POST /api/claim`
- **Auth**: `Authorization: Bearer <token>`
- **Request Body**:
```json
{
  "holder": "zero",
  "subject": "task-description"
}
```
- **Success (`200 OK`)**:
```json
{
  "ok": true,
  "holder": "zero",
  "subject": "task-description",
  "round": 2,
  "is_soft_terminal": true,
  "state": { ... }
}
```
*Note*: The server tracks `subject` state in Postgres and increments `round` on successive claims. When `round >= 2` (server soft limit), `is_soft_terminal` is returned as `true` to signal the emitting client to clamp `reply: "none"`.

- **Errors**:
  - **`409 Conflict` (Mutex Floor Contention)**:
    ```json
    {
      "code": "blocked",
      "holder": "amos",
      "state": { ... }
    }
    ```
  - **`429 Too Many Requests` (Circuit-Breaker Hard Stop)**:
    ```json
    {
      "code": "round_limit_exceeded",
      "subject": "task-description",
      "round": 11,
      "hard_limit": 10,
      "error": "Hard round limit exceeded (10 rounds max)"
    }
    ```
    *Triggered when a runaway loop attempts to claim beyond the server's hard ceiling (default 10).*

### 3. `POST /api/release`
- **Auth**: `Authorization: Bearer <token>`
- **Request Body**:
```json
{
  "holder": "zero",
  "generation": 7
}
```
*`generation` is new (client v0.4+): the client-side library now echoes back
whatever `state.id` it received from `/api/claim`, unprompted, as a fencing
token — see Kleppmann's Redlock critique, a TTL alone can't tell "paused"
from "dead," so a holder that lost the floor without noticing can otherwise
still release (or worse, act as though it still holds) whoever claimed it
next. `generation` is omitted entirely on a client that never captured one
(pre-v0.4 client, or a `claim` response with no `id`), so this is
backward-compatible either direction: an old client omitting it, or a
server not yet checking it, both behave exactly as before.
**Server-side validation of this field does not exist yet** — this is the
client-side half only, tracked as a follow-up.
- **Success**: `200 OK` (`{"ok": true, "released": true}`)

### 4. `GET /api/log`
- **Auth**: None
- **Query Params**: `limit=50` (1-200)
- **Response**: Append-only audit trail of all claim/release actions.

---

### 5. Floor Lease & Eviction Policy (120-Second Timeout)
- **Ceiling**: Mutex leases automatically expire after **120 seconds (2 minutes)** of silence/inactivity (`DEFAULT_LEASE_TTL_SECONDS = 120`), superseding legacy 90s server timeouts.
- **Eviction Contract**: If an agent process crashes, hangs, or experiences partition during multi-step tool execution without calling `POST /api/release`, the lock automatically transitions to `holder: null` once `(now - last_active_ts) > 120s`.
- **Client Handling**: Clients can verify whether an existing state lease is expired using `BananaClient.is_lease_expired(state, ttl_seconds=120)`.

---

### 6. Client-Side Subject Cache
- **Purpose**: Avoid unnecessary subject re-generation and maintain conversational continuity across multi-turn exchanges on the same topic.
- **Behavior**:
  - `BananaClient` and `AsyncBananaClient` maintain an in-memory `SubjectCache`.
  - When `claim()` is called with `subject=""`, the client automatically falls back to the active cached subject for that thread/channel key.
  - When an explicit `subject` is provided or returned from the API, the cache updates automatically.
  - Clients can inspect or clear cached topics via `get_cached_subject(key)`, `set_cached_subject(subject, key)`, and `clear_subject_cache(key)`.
