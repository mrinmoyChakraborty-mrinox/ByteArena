# BYTEARENA — Detailed Execution Roadmap

Companion to `README.md` and `ARCHITECTURE.md`, and an expansion of `ROADMAP.md`. Where `ROADMAP.md` gives the sprint-by-sprint order and Definition of Done (DoD), this document breaks each sprint down into **concrete tasks** — exact files to create, endpoints to write, commands to run, and things to test — so there's no ambiguity about what "Monday morning" actually looks like at any point in the build.

**How to use this doc:** work top to bottom. Every task has a checkbox. Don't skip ahead — later sprints assume earlier interfaces exist exactly as built. If a task references a file, that's the actual path it should live at in the repo.

---

## Table of Contents

- [Sprint 0 — Skeleton](#sprint-0--skeleton-2–3-days)
- [Sprint 1 — Contest & Problem CRUD](#sprint-1--contest--problem-crud-1-week)
- [Sprint 2 — Judge Worker, MVP Sandbox](#sprint-2--judge-worker-mvp-sandbox-1–15-weeks)
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

## Sprint 0 — Skeleton (2–3 days)

**Goal:** prove the LAN round-trip and lock the schema. Nothing in this sprint touches judging, auth, or UI.

### Day 1 — the one round-trip that proves the whole premise

- [ ] `mkdir bytearena && cd bytearena && python -m venv .venv && source .venv/bin/activate`
- [ ] `pip install fastapi uvicorn[standard] sqlalchemy`
- [ ] Create `server/main.py`:
  ```python
  from fastapi import FastAPI
  app = FastAPI()

  @app.get("/health")
  def health():
      return {"status": "ok"}
  ```
- [ ] Run it bound to all interfaces (not just localhost) so a second device can reach it:
  `uvicorn server.main:app --host 0.0.0.0 --port 8000`
- [ ] Find the organizer laptop's LAN IP (`ip addr` / `ipconfig`), open `http://<that-ip>:8000/health` from a phone or second laptop on the **same Wi-Fi**, confirm `{"status":"ok"}`.
- [ ] Turn off the router's WAN/internet uplink (or just unplug it) and repeat the request — it must still work. This is the actual test of the "no cloud" premise, not just a nice-to-have.

**Checkpoint:** if this doesn't work, nothing downstream matters — don't move on until two physical devices have done a real HTTP round-trip with zero internet in the path.

### Day 2 — schema and repo shape

- [ ] Create the repo layout matching the README's `Contest/` structure:
  ```
  bytearena/
  ├── server/
  │   ├── main.py
  │   ├── models.py          # SQLAlchemy models, one per ARCHITECTURE.md §2 table
  │   ├── db.py               # engine + session, WAL pragma
  │   └── routers/            # empty for now, filled in Sprint 1+
  ├── judge/                  # empty for now, filled in Sprint 2
  ├── frontend/                # empty for now, filled in Sprint 3
  Contest/
  ├── Problems/
  ├── Submissions/
  ├── Database/
  ├── Logs/
  └── Config/
  ```
- [ ] `server/db.py` — engine pointed at `Contest/Database/bytearena.db`, and set WAL mode on connect:
  ```python
  from sqlalchemy import create_engine, event

  engine = create_engine("sqlite:///Contest/Database/bytearena.db")

  @event.listens_for(engine, "connect")
  def set_wal(dbapi_conn, _):
      dbapi_conn.execute("PRAGMA journal_mode=WAL")
  ```
- [ ] `server/models.py` — every table from `ARCHITECTURE.md` §2 as a SQLAlchemy model: `Contest`, `Problem`, `Testcase`, `Participant`, `Submission`, `Verdict`, `Event`, `Warning`, `ReviewFlag`, `ComplexityReview`, `PlagiarismMatch`. Tables can be empty of data but the columns must match §2 exactly — Sprint 1+ assumes this shape is final.
- [ ] `Base.metadata.create_all(engine)` on startup, confirm all 11 tables exist: `sqlite3 Contest/Database/bytearena.db ".tables"`.

### Day 2–3 — verify and freeze

- [ ] `.gitignore`: `Contest/Database/*.db*`, `Contest/Submissions/`, `.venv/`, `__pycache__/`
- [ ] Write down the LAN test result (which router, which two devices, screenshot or note) somewhere in `Logs/` or the repo README — you'll want this as a reference once things get more complex and something breaks.
- [ ] Confirm `PRAGMA journal_mode` actually reports `wal` (`sqlite3 Contest/Database/bytearena.db "PRAGMA journal_mode;"`), not just that you set it.

**DoD:** two laptops, one router, one FastAPI response, zero cloud services touched, schema exists with correct columns, WAL confirmed on disk.

---

## Sprint 1 — Contest & Problem CRUD (1 week)

**Goal:** an organizer can create a contest and load problems, no participants yet.

### Contest endpoints

- [ ] `server/routers/contests.py`:
  - `POST /contests` — body: `name, start_at, end_at, freeze_minutes, penalty_minutes` → creates row, `state="scheduled"`
  - `GET /contests` — list all
  - `GET /contests/{id}` — single contest detail
- [ ] Pydantic schemas in `server/schemas.py` for request/response validation — don't pass raw dicts around.

### Problem endpoints + disk loader

- [ ] `server/routers/problems.py`:
  - `POST /contests/{id}/problems` — manual entry: `code, title, statement_md, time_limit_ms, mem_limit_mb, points`
  - `POST /contests/{id}/problems/load` — body: `{"code": "A"}`, triggers the disk loader below
  - `GET /contests/{id}/problems` — list
  - `GET /problems/{id}` — detail, including testcases
- [ ] `server/services/problem_loader.py` — implements the logic from `PROBLEMS_GUIDE.md`:
  - Reads `Contest/Problems/<code>/statement.md` → `problems.statement_md`
  - Reads `Contest/Problems/<code>/config.json` if present, else defaults (`title=<code>`, `time_limit_ms=1000`, `mem_limit_mb=256`, `points=100`)
  - Walks `Contest/Problems/<code>/tests/`, matches pairs by the three supported naming conventions (`input<N>/output<N>`, `in<N>/out<N>`, `in<N>/ans<N>`), inserts one `testcases` row per matched pair with `input_path`/`output_path` set to the file paths (not file contents — keep testcases on disk, per `ARCHITECTURE.md` design notes)
  - Raise a clear error if a code directory doesn't exist, or if an `input<N>` has no matching output file — surface this to the organizer UI rather than silently skipping.
- [ ] Unit test the loader against the sample problem in `PROBLEMS_GUIDE.md` (`Contest/Problems/A/` with 3 testcase pairs) — assert 3 `testcases` rows, correct `title`/`points` from `config.json`.

### Minimal organizer frontend

- [ ] `frontend/` — bootstrap React app (Vite is fine), no CDN dependencies — vendor everything per the README's offline promise from day one, don't leave this for later.
- [ ] Screen 1: Create Contest form (`name`, `start_at`, `end_at`) → `POST /contests`
- [ ] Screen 2: Problem list for a contest, with an "Add Problem" flow:
  - Manual tab: the 5 fields from `PROBLEMS_GUIDE.md` Method 2
  - Load from Disk tab: single `code` input → `POST /contests/{id}/problems/load`
- [ ] Confirm both flows actually persist to SQLite by inspecting the DB directly (`sqlite3 ... "SELECT * FROM problems;"`), not just trusting the UI.

**DoD:** create a contest and add 2–3 real problems (at least one via disk load, one manual) through the UI, and see them stored correctly in SQLite.

---

## Sprint 2 — Judge Worker, MVP Sandbox (1–1.5 weeks)

**Goal:** the core value proposition — code goes in, a correct verdict comes out, safely. This is called out in `README.md` and `ARCHITECTURE.md` as the single most important checkpoint in the whole build — don't let UI work pull you away before this is solid.

### The stable interface (build this first, exactly as specified)

- [ ] `judge/interface.py`:
  ```python
  def compile(source_path: str, lang: str) -> CompiledArtifact | CompileError: ...
  def run(artifact: CompiledArtifact, input: str, limits: Limits) -> RunResult: ...
  ```
  Everything downstream (Phase 3's Docker swap) depends on nothing outside the worker calling anything but these two functions.

### Language config

- [ ] `judge/languages.py` — start with **one** language end-to-end before adding more (pick whatever your actual contest problems are in — likely Python or C++):
  ```python
  LANGUAGES = {
      "cpp":    {"compile": "g++ -O2 -o {out} {src}", "run": "{out}"},
      "python": {"compile": None,                      "run": "python3 {src}"},
  }
  ```
- [ ] Get one language fully working (compile/CE, run/AC/WA/TLE) before adding the second — don't parallelize language support until the pipeline itself is proven.

### MVP sandbox (OS-level isolation)

- [ ] Create a dedicated low-privilege OS user (`useradd -M -s /usr/sbin/nologin judgerunner`) with no write access outside a per-run scratch dir.
- [ ] Per-run scratch directory: `judge/run_sandbox.py` creates `/tmp/bytearena-run-<uuid>/`, copies the compiled artifact in, runs as `judgerunner`, wipes the directory after — every run, no exceptions, even on crash (use `try/finally`).
- [ ] CPU/memory caps via `resource.setrlimit`:
  ```python
  import resource
  resource.setrlimit(resource.RLIMIT_CPU, (time_limit_s, time_limit_s))
  resource.setrlimit(resource.RLIMIT_AS, (mem_limit_bytes, mem_limit_bytes))
  ```
- [ ] Wall-clock timeout that kills the **process group**, not just the parent (catches fork bombs):
  ```python
  proc = subprocess.Popen(cmd, preexec_fn=os.setsid, ...)
  try:
      stdout, stderr = proc.communicate(timeout=wall_clock_s)
  except subprocess.TimeoutExpired:
      os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
  ```
- [ ] Block outbound network for the sandboxed user (restrictive `iptables` rule scoped to `judgerunner`'s UID, or a network namespace with loopback only) — verify with a testcase that does `socket.connect()` and confirm it fails.

### Queue + verdict pipeline

- [ ] DB-backed queue: `submissions.status` column, worker polls `WHERE status='queued' ORDER BY submitted_at LIMIT 1` (add `SELECT ... FOR UPDATE SKIP LOCKED`-equivalent locking once past a single worker — a simple `UPDATE ... WHERE status='queued' AND id=? RETURNING *` claim pattern works fine on SQLite for now).
- [ ] `judge/worker.py` — main loop: claim job → compile → run against every testcase for the problem → compare stdout to expected output → aggregate verdict → write `verdicts` rows (per-testcase) and update `submissions.verdict`.
- [ ] Verdict states implemented exactly: `AC`, `WA`, `TLE`, `MLE`, `RE`, `CE`, plus internal `JUDGE_ERROR` for infra failures (keep this distinct from `RE` in the code — a judge bug should never display as a participant fault).

### Prove it

- [ ] Write a throwaway script `scripts/test_judge.py` that inserts a submission row directly (bypassing the API, since it doesn't exist yet) for:
  - A known-correct solution to the sample problem → expect `AC`
  - A known infinite loop (`while True: pass`) → expect `TLE`, and confirm the process is actually killed (`ps aux` shows nothing lingering)
  - A program that allocates way past the memory cap → expect `MLE`
  - A program with a syntax error → expect `CE`
- [ ] After running the infinite-loop case, confirm the laptop is still responsive — this is explicitly part of the DoD, not just "the verdict was TLE."

**DoD:** submit a known-correct solution and a known-infinite-loop solution from a script — the correct one returns `AC`, the infinite loop gets killed and returns `TLE`, and your laptop is still responsive afterward.

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

Things worth deciding on paper before they become a live-contest surprise:

| Risk | Mitigation | Where it's handled |
|---|---|---|
| Judge worker's sandbox has a gap, untrusted code escapes | OS-level isolation from day one (Sprint 2), not deferred to Phase 3 | `ARCHITECTURE.md` §3 |
| Organizer laptop crashes mid-contest | Periodic DB backup + DB-derived (not memory-only) contest state | Sprint 6, `ARCHITECTURE.md` §8 |
| WebSocket full re-sends saturate Wi-Fi at scale | Delta-only leaderboard pushes, batched anti-cheat events | Sprint 4, Sprint 5 |
| Participant on a second device (phone, mobile data) bypasses all anti-cheat layers | Structural limitation — state it plainly to organizers rather than implying it's solved | README's Anti-Cheating section, `ARCHITECTURE.md` §7 |
| AI complexity review breaks the "zero internet" promise | Default to local model (Ollama); if using cloud API, document the brief post-judging reconnect explicitly | Sprint 6b, `ARCHITECTURE.md` §4 |
| Weak testcases let an inefficient/wrong-complexity solution pass as AC | Post-contest complexity review can demote, but only as an audit — never silently changes what participants saw live | `ARCHITECTURE.md` §4 gate/tiebreaker model |