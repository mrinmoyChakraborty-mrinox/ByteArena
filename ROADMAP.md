# BYTEARENA — Detailed Execution Roadmap

Companion to `README.md` and `ARCHITECTURE.md`, and an expansion of `ROADMAP.md`. Where `ROADMAP.md` gives the sprint-by-sprint order and Definition of Done (DoD), this document breaks each sprint down into **concrete tasks** — exact files to create, endpoints to write, commands to run, and things to test — so there's no ambiguity about what "Monday morning" actually looks like at any point in the build.

**How to use this doc:** work top to bottom. Every task has a checkbox. Don't skip ahead — later sprints assume earlier interfaces exist exactly as built. If a task references a file, that's the actual path it should live at in the repo.

**Status as of 2026-08-01 (per project audit, head `aa1aef7`):** Sprints 0–2 are done — 11/11 judge DoD cases pass, not just the 4 minimum this doc originally asked for. Sprint 3 hasn't started. Actual file paths differ slightly from what's below (`server/database.py` not `db.py`, no `server/services/` yet, organizer UI is a vendored single-file `server/static/index.html` rather than a React app so far) — flagged inline rather than rewritten, since the differences don't matter functionally. A new **Sprint 2.5 — Security Gate** has been inserted before Sprint 3: three protections that were deliberately scoped out of Sprint 2 and need to close before this goes anywhere near a real contest.

---

## Table of Contents

- [Sprint 0 — Skeleton](#sprint-0--skeleton-2–3-days)
- [Sprint 1 — Contest & Problem CRUD](#sprint-1--contest--problem-crud-1-week)
- [Sprint 2 — Judge Worker, MVP Sandbox](#sprint-2--judge-worker-mvp-sandbox-1–15-weeks)
- [Sprint 2.5 — Security Gate](#sprint-25--security-gate-before-sprint-3-1–2-days)
- [Sprint 3 — Participant Flow](#sprint-3--participant-flow-1-week)
- [Sprint 4 — Realtime Leaderboard](#sprint-4--realtime-leaderboard-3–5-days)
- [Sprint 5 — Anti-Cheat Signals + Rate Limiting](#sprint-5--anti-cheat-signals--rate-limiting-3–5-days)
- [Sprint 6 — Manual Review + Contest State Machine](#sprint-6--manual-review--contest-state-machine-1-week)
- [Sprint 6b — AI-Assisted Complexity Review](#sprint-6b--ai-assisted-complexity-review-3–5-days-fast-follow)
- [Milestone: MVP Complete](#milestone-mvp-complete)
- [Sprint 7+ — Phase 2](#sprint-7--phase-2-enhancement-pick-based-on-real-feedback)
- [Sprint N — Phase 3](#sprint-n--phase-3-advanced-only-once-phase-2-is-stable-and-used)
- [Pre-Contest Day-Of Checklist](#pre-contest-day-of-checklist)
- [Risk Register](#risk-register)

---

## Sprint 0 — Skeleton (2–3 days) ✅ done

### Day 1 — the one round-trip that proves the whole premise

- [x] Env + deps installed (Python 3.13 miniforge, FastAPI 0.108.0, Uvicorn 0.49.0, SQLAlchemy 2.0.51, Pydantic 1.10.26)
- [x] `GET /health` implemented — returns `{"status": "ok", "service": "bytearena"}`, wired into `server/main.py`'s `lifespan`
- [x] `uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload` confirmed booting, `/health` verified locally on `:8000`
- [ ] **Not yet re-confirmed:** hitting `/health` from a second physical device on the same Wi-Fi, and repeating with the router's WAN uplink disabled. This was proven once during original Sprint 0 per commit history, but the 2026-08-01 audit only re-verified `localhost` — redo this specific check before trusting it going into Sprint 3's participant-flow testing, especially since dev has since moved to a Windows machine.

**Checkpoint:** don't move deeper into Sprint 3 until this cross-device, no-internet round-trip has been redone on the actual current dev/contest hardware — it's cheap to re-check and expensive to discover it's broken later.

### Day 2 — schema and repo shape

- [x] Repo layout — **actual paths:** `server/{main.py, database.py, models.py, schemas.py, problem_loader.py, routers/, static/}`, `judge/{interface.py, languages.py, sandbox.py, compare.py, worker.py}`, `scripts/test_judge.py`. No `frontend/` yet (organizer UI is `server/static/index.html`, vanilla JS) — fine through Sprint 2, revisit before Sprint 3's Monaco/WebSocket needs.
- [x] `server/database.py` — WAL pragma **plus** `foreign_keys=ON` and `busy_timeout=10000` (the last one added mid-Sprint-2 specifically so the judge worker and API don't deadlock against each other — a real fix, not speculative hardening)
- [x] `server/models.py` — all 11 tables from `ARCHITECTURE.md` §2, plus 7 enums (`ContestState`, `SubmissionStatus`, `Verdict`, `TestcaseStatus`, `EventType`, `ReviewDecision`, `ComplexityDecision`)
- [x] `Base.metadata.create_all()` on startup, all 11 tables confirmed via `.schema`

### Day 2–3 — verify and freeze

- [x] `.gitignore` covers `Contest/Database/*.db*`, `Contest/Submissions/`, `Contest/Runs/`
- [ ] LAN test result from Day 1 not yet written down anywhere durable — do this once the re-check above is redone
- [x] `PRAGMA journal_mode` confirmed reporting `wal`, not just set

**DoD:** ~~two laptops, one router, one FastAPI response~~ — schema and WAL are solid; the actual cross-device round-trip needs a fresh re-check per the note above before calling Sprint 0 fully closed.

---

## Sprint 1 — Contest & Problem CRUD (1 week) ✅ done, exceeded scope

**Goal:** an organizer can create a contest and load problems, no participants yet.

### Contest endpoints

- [x] Full CRUD shipped, beyond the original `POST/GET` scope — `PUT/DELETE /api/contests` also implemented, plus state-transition coercion back to the `ContestState` enum
- [x] Pydantic schemas in `server/schemas.py`

### Problem endpoints + disk loader

- [x] `server/routers/problems.py` — beyond plan: also shipped `PUT/DELETE /api/problems/{id}` and full testcase CRUD (`GET/POST /api/problems/{id}/testcases`, `DELETE /api/testcases/{id}`), plus duplicate-`code` detection → `409`
- [x] `server/problem_loader.py` (top-level file, not under a `services/` package — functionally identical):
  - Reads `statement.md` → `problems.statement_md` ✓
  - Reads `config.json` with documented defaults ✓
  - Pairs `tests/` files across all three naming conventions ✓ — implementation does the pairing via basename substitution (`input→output`, `in→out`, `in→ans`) rather than a lookup table, same result
  - Stores paths, not contents ✓
  - Clear errors on missing directory / unmatched input ✓
- [ ] **Not done as a standalone unit test** — the loader's correctness has only been exercised indirectly (via the DoD script and manual UI use against the real `Contest/Problems/A|B|C` fixtures), not via an isolated test asserting row counts/field values. Worth adding before the loader logic changes again.

### Minimal organizer frontend

- [x] **Deviation:** vanilla JS single-file `server/static/index.html` (447 lines) instead of a Vite/React build — no CDN dependencies either way, so the offline promise holds. Revisit this choice before Sprint 3 forces Monaco + WebSockets into the picture.
- [x] Contest create/list/delete, Problems list + Add (Manual/Load from Disk), Testcases view/delete — all three tabs built and verified end-to-end
- [x] Both flows confirmed persisting correctly to SQLite by direct inspection

**DoD met:** contest created, 3 problems added (mix of manual + disk-loaded), verified in SQLite.

---

## Sprint 2 — Judge Worker, MVP Sandbox (1–1.5 weeks) ✅ done — 11/11 DoD cases, exceeded the 4-case minimum

**Goal:** the core value proposition — code goes in, a correct verdict comes out, safely. This is called out in `README.md` and `ARCHITECTURE.md` as the single most important checkpoint in the whole build — and it held up under the broader test matrix that actually got run.

### The stable interface (build this first, exactly as specified)

- [x] `judge/interface.py` — `compile()`/`run()` implemented exactly as specified. One subtlety handled correctly that this doc didn't originally call out: for interpreted languages (only syntax-checked, not compiled to a binary), the "artifact" path has to stay the source file, not a nonexistent binary — `uses_bin = any("{bin}" in token for token in cfg["run"])` gates this.

### Language config

- [x] `judge/languages.py` — Python and C++ both fully working, config-only additions as designed
- [x] `run_env_for()` (not in the original plan, added out of necessity) — prepends the compiler's bin dir to `PATH` so MSYS2-built C++ binaries can find `libstdc++-6.dll` at runtime. Worth keeping in mind if the eventual production machine is Linux — this specific fix is Windows-only and won't be needed there, but the pattern (making sure the runtime env is correct, not just the compile command) generalizes.

### MVP sandbox (OS-level isolation)

- [ ] **Low-privilege OS user — code supports it, not actually provisioned.** `BYTEARENA_SANDBOX_USER` env var exists and `_drop_privileges` implements the `setgid`/`setuid` drop, but no `judgerunner` user has been created on any real machine yet, so POSIX runs currently execute as the worker's own user. Moved to Sprint 2.5 below — this is a real gap, not a checked box.
- [x] Per-run scratch dir under `Contest/Runs/run_<id>_*/`, wiped in `finally` — verified zero leftover directories across all 11 DoD cases
- [x] CPU/memory caps — implemented with a documented enforcement/verdict split: the *enforcement* rlimit is set generously above the problem's limit (`max(limit*2, limit+256)`) so an over-limit process survives long enough to be **measured** rather than killed instantly; the *verdict* threshold is applied separately by the worker comparing peak memory to the problem's actual limit. This is a real design decision beyond what this doc originally specified, and it's the right one — makes MLE deterministic instead of racy.
- [x] Wall-clock timeout, process-group kill — POSIX: `setsid()` + `killpg(SIGKILL)` on `TimeoutExpired`. **Windows wasn't in the original plan at all**, but the dev machine is Windows, so a second backend was built: Job Object with `JOB_OBJECT_LIMIT_JOB_MEMORY` + `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, with a poll-based (`taskkill /F /T`) fallback for when job assignment fails (which it does in this dev shell — see finding below). Both paths verified to leave zero stray processes after a TLE case.
- [ ] **Outbound network blocking — deliberately deferred, not forgotten.** Documented as a TODO in `judge/sandbox.py`. Moved to Sprint 2.5 below — this is the single guarantee the "no internet" pitch actually depends on, so treat it as blocking, not backlog.

### Queue + verdict pipeline

- [x] Atomic claim via `UPDATE ... WHERE id = (SELECT ... ORDER BY submitted_at, id LIMIT 1) RETURNING id` — correct pattern, though only single-worker execution has actually been exercised so far; multi-worker correctness rests on SQLite's single-writer semantics plus this atomic claim, untested under real concurrent load
- [x] `judge/worker.py` main loop — claim → compile → run each testcase in id order → **short-circuit on first failure**, remaining testcases marked `SKIPPED` (a refinement beyond "run every testcase" — faster judging, and it matches how most real judges behave)
- [x] All six verdict states implemented, plus `JUDGE_ERROR` kept distinct from `RE` for infra failures as specified

### Prove it — actual results, broader than planned

- [x] `scripts/test_judge.py` ran **11 cases** (AC/WA/TLE/MLE/RE/CE × {python, cpp}, one extra WA) instead of the 4 originally scoped — **11/11 PASS**
- [x] Laptop responsiveness confirmed after every TLE/MLE case — zero stray processes, zero leftover scratch dirs

**Two real bugs found and fixed during this sprint** (worth keeping visible, not just "tests passed"):
1. Job Object assignment fails with error 6 in this dev shell (parent process already lives inside a job with no breakaway) → the poll+taskkill fallback exists because of this, not speculatively.
2. `-O2` silently elided the C++ MLE test's dead `vector` allocation, and Python was originally producing `RE` instead of `CE` for syntax errors, and the artifact-path bug caused the Python runner to try executing a nonexistent `main.exe`. All three fixed; the MLE test now actually uses the allocation (`printf(v.back())`) so `-O2` can't optimize it away again.

**DoD met, exceeded:** correct → AC, infinite loop → TLE (both languages), laptop stayed responsive throughout, plus WA/MLE/RE/CE all separately verified rather than just the two required cases.

---

## Sprint 2.5 — Security Gate (before Sprint 3, 1–2 days)

**Goal:** close the three protections that were correctly identified in Sprint 2 as deferred, before building anything that assumes the judge worker is contest-safe. Pulled directly from the 2026-08-01 audit's gap list — these aren't new scope, they're scope that was explicitly pushed here rather than skipped, and shouldn't be allowed to drift further.

- [ ] **Block outbound network for the sandboxed process.** POSIX: scope an `iptables`/`nftables` DROP rule to the sandbox UID (works cleanly once the low-priv user below exists — block by UID rather than trying to sandbox the worker's own user), or run under a network namespace with loopback only. Write the missing test alongside the fix: a testcase that calls `socket.connect()` and asserts it fails.
- [ ] **Provision the low-privilege `judgerunner` OS user** on the actual target machine (`useradd -M -s /usr/sbin/nologin judgerunner` on Linux), set `BYTEARENA_SANDBOX_USER`, and verify by checking the sandboxed process's *effective* UID at runtime — not just that the env var is set.
- [ ] **Add a stale-claim reaper.** A worker crash between claim (`status → COMPILING`/`RUNNING`) and finish currently leaves a submission stuck forever with no self-healing. A periodic sweep (`UPDATE submissions SET status='queued' WHERE status IN ('compiling','running') AND claimed_at < now() - interval '2 minutes'`) closes this — small enough to build in an afternoon.

**Decide explicitly, don't let it default:** is the contest-day organizer laptop going to be Linux or Windows? The POSIX sandbox path (hard rlimits, real `killpg`) is a stronger guarantee than the Windows fallback (10ms-granularity polling, job assignment can fail as already observed in this dev shell). If Windows is the real target, the fallback path needs the same adversarial scrutiny the POSIX path is getting here — right now it's only been proven correct in a cooperative dev shell, not tested against code trying to evade it.

**DoD:** a testcase that attempts an outbound network call fails; a sandboxed process's effective UID is confirmed as the low-priv user, not the worker's own; killing the worker process mid-`RUNNING` and restarting it results in the stuck submission self-recovering within one reaper cycle, not requiring manual DB intervention.

---

## Sprint 3 — Participant Flow (1 week)

**Goal:** an actual participant can log in, read a problem, submit, and see a verdict.

### Accounts + sessions

- [ ] `server/routers/participants.py`:
  - `POST /contests/{id}/participants/import` — CSV upload (`username, password` or auto-generated passwords), inserts `participants` rows with `password_hash` (bcrypt/argon2, not plaintext)
  - `POST /login` — body `{username, password, contest_id}` → session token
- [ ] Session tokens scoped to a single contest, stored server-side or as a signed JWT with `contest_id` + `participant_id` claims; short-lived but tied to heartbeat state (heartbeat logic lands in Sprint 5 — for now just make sure the token doesn't need heartbeats to remain valid).

### Problem view + editor

- [ ] `frontend/src/pages/ProblemView.tsx` — renders `statement_md` (Markdown → HTML, sanitize it), shows sample input/output, time/memory limits.
- [ ] Vendor Monaco Editor into the frontend build (`npm install monaco-editor`, bundle it — do **not** load it from a CDN, per the README's zero-internet requirement) with a language selector matching `judge/languages.py`.
- [ ] Submit button → `POST /submissions` with `{problem_id, lang, source}` → server writes source to `Contest/Submissions/<username>/<problem_code>/<timestamp>.<ext>`, inserts a `submissions` row with `status="queued"`.

### Verdict display

- [ ] `GET /submissions/{id}` — poll endpoint (WebSocket comes in Sprint 4), returns current `status`/`verdict`.
- [ ] Frontend polls every 1–2s while `status != "judged"`, then shows the verdict badge (AC green, WA/TLE/MLE/RE/CE in a distinct color each).

### Prove it

- [ ] From a **second physical device** on the LAN, logged in as a real (non-organizer) participant account: read a problem, submit a correct solution, watch it go `queued → compiling → running → judged` and land on `AC`, without you touching the DB directly at any point.

**DoD:** a second device, logged in as a fake participant, submits code and sees a verdict without you touching the DB directly.

---

## Sprint 4 — Realtime Leaderboard (3–5 days)

**Goal:** live standings, the feature that makes it feel like a contest.

- [ ] `server/ws/leaderboard.py` — one WebSocket channel per contest (`/ws/contests/{id}`), participants and organizer both connect to it.
- [ ] Leaderboard computation (`server/services/scoring.py`), matching `ARCHITECTURE.md` §4 exactly:
  - Per problem: solved (first `AC`) or not.
  - Rank: `(problems_solved DESC, penalty_time ASC)`.
  - Penalty time = sum over solved problems of (minutes from contest start to first `AC`) + (`penalty_minutes` config × wrong attempts before that `AC`).
- [ ] **Delta pushes, not full re-sends** — on a new verdict, compute what changed (one participant's row, maybe a rank shift) and broadcast only that, not the whole table. This matters concretely once you have 50+ participants on shared Wi-Fi.
- [ ] Freeze window: `contests.freeze_minutes` config — in the last N minutes, participant-facing WebSocket messages stop including rank/solve updates (organizer's channel keeps getting everything, gated by an `is_organizer` flag on the connection).
- [ ] Frontend: `frontend/src/pages/Leaderboard.tsx` subscribes to the WS channel, applies deltas to local state, shows a "standings frozen" banner during the freeze window.

### Prove it

- [ ] Simulate 3 concurrent participants submitting (a script hitting `/submissions` from 3 fake accounts works fine — doesn't need 3 physical devices) and confirm rank changes appear live without a page refresh.
- [ ] Manually trigger the freeze window (set `freeze_minutes` high enough to hit immediately in a test contest) and confirm participant view stops updating while the organizer view keeps moving.

**DoD:** three simulated participants submitting concurrently see rank changes update live, without a page refresh, and the leaderboard visibly freezes/unfreezes on schedule.

---

## Sprint 5 — Anti-Cheat Signals + Rate Limiting (3–5 days)

**Goal:** the organizer dashboard actually shows what's happening.

- [ ] `POST /heartbeat` — participant client fires every 5–10s; server updates `participants.last_heartbeat` and writes an `events` row (`type="heartbeat"`). Background job marks `disconnected` after ~20s of silence.
- [ ] Browser event listeners (`frontend/src/lib/eventTracker.ts`): `visibilitychange`, `blur`/`focus`, `fullscreenchange` — **batch client-side, flush every few seconds** in one request, not one HTTP call per event (chatty at 100+ concurrent participants on shared Wi-Fi).
- [ ] `POST /events/batch` — accepts an array of `{type, ts, payload}`, inserts rows into the shared `events` table (same table as heartbeats — this is what lets the dashboard render one unified timeline instead of three widgets).
- [ ] Internet-probe check: `frontend/src/lib/internetProbe.ts` — background `fetch` with a short timeout to a public endpoint every 30–60s. Success (not failure) is the anomaly — triggers `POST /events` with `type="internet_detected"`, surfaces as a warning on both the organizer dashboard and the participant's own screen.
- [ ] Submission rate limiting: token bucket per participant (`server/middleware/rate_limit.py`), applied to `POST /submissions` — reject with `429` once the bucket's empty, refill on a timer.
- [ ] `frontend/src/pages/OrganizerDashboard.tsx` — per-participant unified event timeline (pulls from `events`), queue depth (`SELECT COUNT(*) WHERE status='queued'`), worker health (last-seen heartbeat per judge worker process).

### Prove it

- [ ] From the participant device, switch tabs mid-contest and confirm it shows up on the organizer dashboard within a few seconds, with a correct timestamp.
- [ ] Hammer `POST /submissions` faster than the rate limit allows and confirm `429`s start appearing without crashing the queue.

**DoD:** switch tabs on the participant device mid-contest and see it show up on the organizer dashboard within a few seconds, with a timestamp.

---

## Sprint 6 — Manual Review + Contest State Machine (1 week)

**Goal:** the organizer can run a contest end-to-end, including pausing it.

### State machine

- [ ] `server/services/contest_state.py` — `scheduled → running → paused → frozen → ended`, transitions organizer-triggered via `POST /contests/{id}/state` (`{action: "start"|"pause"|"resume"|"extend"|"end", ...}`).
- [ ] Pause: stop the timer, freeze submission acceptance (`POST /submissions` returns `409` while `state="paused"`).
- [ ] Extend: push `contests.end_at` forward by the requested amount; broadcast the new end time over the dashboard WS so every connected client's countdown updates.
- [ ] Log every transition (who, when, from/to state) — reuse the `events` table with `type="state_change"` or a small dedicated log, organizer's call.

### Manual review screen

- [ ] `GET /contests/{id}/submissions?status=judged` — list for review.
- [ ] `frontend/src/pages/Review.tsx` — per submission: source code (syntax-highlighted, read-only Monaco), execution stats (`runtime_ms`, `mem_kb`), full per-testcase `verdicts` breakdown.
- [ ] `POST /submissions/{id}/review` — `{decision: "approved"|"rejected"|"flagged", note}` → inserts `review_flags` row.
- [ ] Complexity review (plain form for now, AI suggestion is Sprint 6b): `POST /submissions/{id}/complexity` — `{decision: "valid"|"invalid", judge_class, note}` → inserts `complexity_reviews` row.
- [ ] Wire the gate/tiebreaker logic from `ARCHITECTURE.md` §4 into `scoring.py`:
  - `judge_decision="invalid"` → that problem no longer counts as solved for that participant, standings recompute.
  - Otherwise, `judge_class` only breaks ties among participants equal on `(solved, penalty_time)` — never reorders anyone otherwise ahead.

### Backups

- [ ] `scripts/backup_db.py` — copies `Contest/Database/bytearena.db*` (include WAL/SHM files) to `Contest/Database/backups/<timestamp>/` every N minutes via a scheduled task or a simple background thread in the server process. Cheap insurance, not full recovery tooling — just make sure the habit exists from day one.

### Prove it

- [ ] Run a full mock contest start-to-finish: start it, pause it once, resume, extend the timer, manually mark one submission's complexity as invalid and confirm the leaderboard recomputes correctly, mark a tie-breaking complexity class and confirm rank order changes only for the tied pair — all without restarting any process.

**DoD:** run a full mock contest start-to-finish, including pausing it once, extending the timer, and manually setting complexity classes that visibly change the final ranking — without restarting any process.

---

## Sprint 6b — AI-Assisted Complexity Review (3–5 days, fast-follow)

**Goal:** speed up the Sprint 6 review screen with an AI suggestion, without changing who decides.

- [ ] Decide offline-vs-reconnect per `ARCHITECTURE.md` §4's tradeoff (recommended default: local model):
  - **Local (recommended):** install Ollama, pull a small-but-capable code model, confirm it runs acceptably on the organizer laptop's hardware *before* committing to this path for the actual event.
  - **Cloud reconnect (simpler to build):** if going this route, document it explicitly for organizers — the "no internet, ever" claim gets a stated exception, not a silent one.
- [ ] `judge/complexity_review.py` — batch job, one pass over every `submissions` row with `verdict="AC"` and no existing `complexity_reviews` entry:
  - Prompt includes: source code, problem's `time_limit_ms`/`mem_limit_mb`, and any constraint bounds parseable from `statement.md` or `config.json`.
  - Ask for a suggested complexity class + short reasoning, store as `ai_suggested_class` / `ai_reasoning`.
- [ ] Update `frontend/src/pages/Review.tsx`: show the AI suggestion inline next to the judge's manual field, with a one-click "accept" button that pre-fills `judge_decision`/`judge_class` from the AI's suggestion (judge can still edit before submitting).
- [ ] Every override (judge's final decision differs from the AI's suggestion) gets logged to `judge_note` automatically — don't rely on the judge to remember to write it down.

### Prove it

- [ ] Run the batch job over a mock contest's ~10–20 accepted submissions, confirm every one gets an AI suggestion, and time how long a judge takes to accept/override each on the review screen — should be a few seconds per submission, not a re-read of the whole solution from scratch.

**DoD:** the judge review screen for a mock contest shows an AI suggestion for every accepted submission, and a judge can accept or override each one in under a few seconds per submission.

---

## Milestone: MVP Complete

At this point you have a real, runnable contest platform. Before writing a line of Phase 2 code:

- [ ] Run at least one **real or realistic mock contest** end-to-end — ideally with actual people on actual laptops, not just scripted participants.
- [ ] Collect specific friction points from that run (not vague impressions) — what did organizers reach for that wasn't there, what did participants get confused by, what broke.
- [ ] Re-prioritize the Phase 2 list below based on that feedback, rather than building it in the order listed — the order below is a reasonable default, not a commitment.

---

## Sprint 7+ — Phase 2 (Enhancement, pick based on real feedback)

Roughly in priority order:

- [ ] **mDNS auto-discovery** (`contest.local`) — `zeroconf`/`python-zeroconf` on the server side advertising the service; do this early, it removes real day-of friction (participants typing a raw IP is a common failure point).
- [ ] **Multi-language support** — add entries to `judge/languages.py` (e.g. `java`, `c`) rather than new code paths; test each new language against the same known-correct/known-TLE/known-CE trio from Sprint 2 before trusting it in a real contest.
- [ ] **Captive portal** — router/DNS-level redirect so any device joining the Wi-Fi lands on the contest login page automatically.
- [ ] **Practice mode** — a contest flagged `is_practice=true`: no leaderboard, no penalty scoring, testcases visible, submissions still go through the same judge pipeline.
- [ ] **Clarification requests** — new `clarifications` table (`participant_id, problem_id, question, answer, ts`), participant-facing "ask a question" UI, organizer-facing inbox with reply.
- [ ] **Contest templates** — save a contest's problem set + config as a reusable template (`Contest/Templates/<name>/`), "create from template" option on the New Contest screen.

---

## Sprint N — Phase 3 (Advanced, only once Phase 2 is stable and used)

- [ ] **Container sandbox swap** — implement `judge/sandbox_docker.py` behind the exact same `compile()`/`run()` interface from Sprint 2; A/B it against the OS-level backend on the same test trio before switching over in production.
- [ ] **Plagiarism detection** — token/AST similarity (e.g. via a library like `pygments` for tokenization + a similarity metric), bundled into the same post-contest batch pass as the complexity review since submissions are already being opened for that.
- [ ] **Contest import/export** — serialize a full contest (problems, testcases, config, **not** participant PII) to a portable archive and back.
- [ ] **Analytics dashboard** — aggregate stats across contests: solve-rate per problem, submission-language breakdown, time-to-first-AC distributions.

---

## Pre-Contest Day-Of Checklist

Separate from the build roadmap — this is what to physically do on the day of a real contest, once the platform is built:

- [ ] Charge/plug in the organizer laptop — it's now a server, treat it like one.
- [ ] Router set up with WAN uplink physically disconnected or disabled, Wi-Fi SSID/password ready to hand out.
- [ ] Organizer laptop on Ethernet (RJ45) to the router, not Wi-Fi — keep the one reliable link reliable.
- [ ] Run the Sprint 0 LAN round-trip test again, fresh, on the actual venue network — venue Wi-Fi/router behavior can differ from your dev setup.
- [ ] Confirm `contest.local` resolves from a random participant-type device before doors open.
- [ ] Kick off a DB backup manually right before the contest starts, then confirm the scheduled backups are actually firing during a short dry run.
- [ ] Seed a couple of real accounts from the participant CSV and do one full login → submit → verdict → leaderboard pass yourself, on Wi-Fi, not localhost.
- [ ] Have the mock-contest friction list from the MVP milestone handy — if something breaks, check that list first; it's often already a known issue with a workaround.

---

## Risk Register

Things worth deciding on paper before they become a live-contest surprise. Status column added post-audit (2026-08-01) so this reflects reality, not just intent.

| Risk | Mitigation | Where it's handled | Status |
|---|---|---|---|
| Judge worker's sandbox has a gap, untrusted code escapes | OS-level isolation from day one (Sprint 2), not deferred to Phase 3 | `ARCHITECTURE.md` §3 | ⚠️ Partial — rlimits/timeout/kill work; low-priv user + network block still open, see Sprint 2.5 |
| Untrusted code reaches the internet | Block outbound network for the sandbox UID | Sprint 2.5 (moved from Sprint 2, was deferred) | 🔴 Open — unimplemented, treat as blocking before any real contest |
| Sandbox escape isn't actually contained | Dedicated low-priv `judgerunner` OS user | Sprint 2.5 | 🔴 Open — code path exists, nothing provisioned yet |
| Worker crash leaves a submission stuck forever | Stale-claim reaper | Sprint 2.5 | 🔴 Open — no reaper exists yet |
| Organizer laptop crashes mid-contest | Periodic DB backup + DB-derived (not memory-only) contest state | Sprint 6, `ARCHITECTURE.md` §8 | Not started (Sprint 6 not reached) |
| WebSocket full re-sends saturate Wi-Fi at scale | Delta-only leaderboard pushes, batched anti-cheat events | Sprint 4, Sprint 5 | Not started |
| Participant on a second device (phone, mobile data) bypasses all anti-cheat layers | Structural limitation — state it plainly to organizers rather than implying it's solved | README's Anti-Cheating section, `ARCHITECTURE.md` §7 | Accepted, documented |
| AI complexity review breaks the "zero internet" promise | Default to local model (Ollama); if using cloud API, document the brief post-judging reconnect explicitly | Sprint 6b, `ARCHITECTURE.md` §4 | Not started |
| Weak testcases let an inefficient/wrong-complexity solution pass as AC | Post-contest complexity review can demote, but only as an audit — never silently changes what participants saw live | `ARCHITECTURE.md` §4 gate/tiebreaker model | Not started |
| Windows sandbox fallback is a softer guarantee than the POSIX path | Decide contest-day OS explicitly; harden whichever path is actually used | Sprint 2.5 note | 🔴 Open decision — currently defaulting to whatever the dev machine happens to be |