# BYTEARENA — Execution Roadmap

Companion to `README.md` and `ARCHITECTURE.md`. This is the "what do I actually do Monday morning" document — a linear build order, not a feature wishlist. Each stage has a concrete Definition of Done (DoD); don't move to the next stage until the current one's DoD is met. Keep the stack as simple as each stage allows — don't reach for Redis, Docker, or Postgres until the stage that actually needs them.

---

## Start here

**Sprint 0, Day 1 task:** stand up a bare FastAPI app with one endpoint (`GET /health`) and a SQLite file next to it. Nothing else. Get that running on your laptop, then get a second laptop on the same Wi-Fi hitting it by IP. That one round-trip — browser on device B, response from device A over LAN, no internet involved — proves the entire premise of the project before a single line of judge logic exists. Everything below builds on top of that.

---

## Sprint 0 — Skeleton (2–3 days)
**Goal:** prove the LAN round-trip and lock the schema.

- [ ] FastAPI app + `/health` endpoint, reachable from a second device on the same LAN
- [ ] SQLite DB created with the full schema from `ARCHITECTURE.md` §2 (empty tables, but the shape is final)
- [ ] `PRAGMA journal_mode=WAL` set
- [ ] Repo structure matches the `Contest/` layout in the README

**DoD:** two laptops, one router, one FastAPI response. No cloud services touched.

---

## Sprint 1 — Contest & Problem CRUD (1 week)
**Goal:** an organizer can create a contest and load problems, no participants yet.

- [ ] `contests` and `problems`/`testcases` REST endpoints (create, list, get)
- [ ] Problem loading from the `Problems/<code>/statement.md` + `tests/` + `config.json` file layout
- [ ] Minimal organizer-only frontend screen: create contest, upload a problem folder, see it listed

**DoD:** you can create a contest and add 2–3 real problems through the UI, and see them stored correctly in SQLite.

---

## Sprint 2 — Judge Worker, MVP Sandbox (1–1.5 weeks)
**Goal:** the core value proposition — code goes in, a correct verdict comes out, safely.

- [ ] `compile()` / `run()` interface from `ARCHITECTURE.md` §3, one language first (pick whichever your contest problems are actually in — likely C++ or Python)
- [ ] OS-level sandbox: dedicated low-priv user, `rlimit` CPU/memory caps, wall-clock timeout that kills the whole process group
- [ ] DB-backed queue (a `status` column on `submissions`, polled — no Redis yet)
- [ ] Verdict states: `AC / WA / TLE / MLE / RE / CE`

**DoD:** submit a known-correct solution and a known-infinite-loop solution from a script (not the UI yet) — the correct one returns `AC`, the infinite loop gets killed and returns `TLE`, and your laptop is still responsive afterward. This is the single most important checkpoint in the whole roadmap — don't let UI work pull you away before this is solid.

---

## Sprint 3 — Participant Flow (1 week)
**Goal:** an actual participant can log in, read a problem, submit, and see a verdict.

- [ ] Pre-provisioned accounts (CSV upload → `participants` table, no self-registration)
- [ ] Session tokens, login screen
- [ ] Problem view + Monaco editor (vendored, not CDN-loaded) + submit button
- [ ] Submission → queue → judge → verdict shown to the participant (polling is fine here; WebSocket comes next sprint)

**DoD:** a second device, logged in as a fake participant, submits code and sees a verdict without you touching the DB directly.

---

## Sprint 4 — Realtime Leaderboard (3–5 days)
**Goal:** live standings, the feature that makes it feel like a contest.

- [ ] WebSocket channel per contest
- [ ] Leaderboard computed from ICPC-style rule (`ARCHITECTURE.md` §4): solved count, then penalty time
- [ ] Delta pushes on verdict, not full re-sends
- [ ] Freeze window (config flag, hides updates from participants in the last N minutes; organizer still sees live)

**DoD:** three simulated participants submitting concurrently see rank changes update live, without a page refresh, and the leaderboard visibly freezes/unfreezes on schedule.

---

## Sprint 5 — Anti-Cheat Signals + Rate Limiting (3–5 days)
**Goal:** the organizer dashboard actually shows what's happening.

- [ ] Heartbeat (`POST /heartbeat`, 5–10s interval, `disconnected` after ~20s silence)
- [ ] Browser event listeners (`visibilitychange`, `blur`, `fullscreenchange`), batched client-side
- [ ] Internet-probe check, dashboard + participant warning on success
- [ ] Submission rate limiting (token bucket per participant)
- [ ] Organizer dashboard: unified per-participant event timeline, queue depth, worker health

**DoD:** switch tabs on the participant device mid-contest and see it show up on the organizer dashboard within a few seconds, with a timestamp.

---

## Sprint 6 — Manual Review + Contest State Machine (1 week)
**Goal:** the organizer can run a contest end-to-end, including pausing it.

- [ ] `scheduled → running → paused → frozen → ended` state machine, organizer-triggered
- [ ] Pause/extend controls
- [ ] Manual review screen: view source, approve/reject/flag, see it reflected in final standings
- [ ] Judge complexity review screen: per accepted submission, judge marks complexity valid/invalid (plain form for now — no AI yet, see Sprint 6b) — invalid demotes that solve, valid feeds tiebreaking only; live standings otherwise stay authoritative
- [ ] Periodic DB backup during a live contest (copy the SQLite file every N minutes)

**DoD:** run a full mock contest start-to-finish, including pausing it once, extending the timer, and manually setting complexity classes that visibly change the final ranking — without restarting any process.

---

## Sprint 6b — AI-Assisted Complexity Review (3–5 days, fast-follow)
**Goal:** speed up the judge review screen from Sprint 6 with an AI suggestion, without changing who decides.

- [ ] Local LLM (Ollama or similar) running on the organizer laptop, or a cloud API call if the team accepts a brief post-contest reconnect (`ARCHITECTURE.md` §4 has the tradeoff)
- [ ] Batch job: for each accepted submission, send source + problem constraints, get back a suggested class + reasoning
- [ ] Review screen shows the AI suggestion inline next to the judge's manual field from Sprint 6, with one-click accept
- [ ] Overrides logged (`judge_note`) so there's a record when a judge disagrees with the AI

**DoD:** the judge review screen for a mock contest shows an AI suggestion for every accepted submission, and a judge can accept or override each one in under a few seconds per submission — this is explicitly a speed-up for the judge, not a replacement decision-maker.

---

## Milestone: MVP Complete
At this point you have a real, runnable contest platform. This is a legitimate stopping point to demo, get feedback, and decide what Phase 2 items actually matter based on real usage — don't build Phase 2 speculatively before running at least one real or realistic mock contest on this.

---

## Sprint 7+ — Phase 2 (Enhancement, pick based on real feedback)
Roughly in priority order, but reorder based on what your first mock contest actually needed:

- [ ] mDNS auto-discovery (`contest.local`) — do this early, it removes real day-of friction
- [ ] Multi-language support (add config entries per `ARCHITECTURE.md` §3, not new code paths)
- [ ] Captive portal
- [ ] Practice mode
- [ ] Clarification requests (participant ↔ organizer)
- [ ] Contest templates

---

## Sprint N — Phase 3 (Advanced, only once Phase 2 is stable and used)
- [ ] Swap sandbox backend to Docker/gVisor behind the existing `compile()`/`run()` interface — no rewrite, just a new backend
- [ ] Plagiarism detection, bundled into the existing post-contest batch job alongside time-complexity analysis
- [ ] Contest import/export
- [ ] Analytics dashboard

---

## Team split (if running this as a 4-person build)

A workable division of labor once Sprint 0 skeleton exists:

| Track | Owns |
|---|---|
| Backend/judge (you) | Contest server, judge worker, sandboxing, scoring engine, schema |
| Frontend | Participant UI, Monaco integration, WebSocket client, leaderboard rendering |
| Tooling/infra | mDNS, rate limiting, dashboard event pipeline, deployment scripting |
| Design/docs | Organizer dashboard UI, problem statement formatting, README/setup docs, the landing page |

Backend and frontend tracks can run in parallel from Sprint 1 onward once the API contract for that sprint is agreed — write the request/response shape for each sprint's endpoints before building both sides, so nobody's blocked waiting on the other.

---

## The one rule that keeps this from sprawling

Every sprint above has a DoD you can literally demo in one sentence. If a task doesn't move you toward that sentence, it's not this sprint's problem — park it in Phase 2/3 and keep going.
