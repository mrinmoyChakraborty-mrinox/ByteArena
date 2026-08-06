# BYTEARENA — MVP Task List

Every task needed to go from empty repo to a real, runnable contest platform (the "Milestone: MVP Complete" point in `ROADMAP.md`). Organized by build area rather than sprint number, so you can see everything a given piece of the system needs in one place. Checkbox per atomic task — most should take under an hour; if one doesn't, it's probably actually 2–3 tasks.

**Scope note:** this is MVP only — no mDNS, no captive portal, no plagiarism detection, no Docker sandbox. Those are Phase 2/3, tracked separately in `ROADMAP.md`.

**Status as of 2026-08-01 (per project audit, head `aa1aef7`):** Sections 0–6 below are functionally complete (11/11 judge DoD tests pass). Actual repo paths differ slightly from the plan (`server/database.py` not `db.py`, single-file `server/static/index.html` instead of a React app so far, no `server/services/` yet) — noted inline. Section 5b is new: three security gaps from the audit that should close before Sprint 3, not drift into backlog.

---

## 0. Environment & Repo Setup ✅ done (paths differ — see note)

- [ ] Create repo, `python -m venv .venv`, activate it
- [ ] `pip install fastapi "uvicorn[standard]" sqlalchemy pydantic python-multipart passlib[bcrypt] python-jose`
- [x] Create repo layout — **actual:** `server/{main.py, database.py, models.py, schemas.py, problem_loader.py, routers/, static/}`, `judge/{interface.py, languages.py, sandbox.py, compare.py, worker.py}`, `scripts/test_judge.py`, `Contest/{Problems/, Submissions/, Database/, Runs/, Logs/, Config/}`. `services/`, `ws/`, `middleware/`, and a real `frontend/` don't exist yet — organizer UI is currently a single vendored `server/static/index.html` (447 lines, vanilla JS). Fine for now; Sprint 3+ (Monaco, WebSocket leaderboard) is where a real frontend build becomes necessary.
- [x] `.gitignore`: `.venv/`, `__pycache__/`, `Contest/Database/*.db*`, `Contest/Submissions/`, `Contest/Runs/`
- [ ] `node -v` / `npm -v` check, then scaffold a real frontend (Vite/React) — deferred until Sprint 3 needs Monaco + WebSockets; vanilla JS has been sufficient through Sprint 1
- [x] Confirm `uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload` boots — `GET /health` returns `{"status":"ok","service":"bytearena"}`, verified 2026-08-01

---

## 1. Prove the LAN Premise (do this before anything else)

- [x] `GET /health` returning `{"status": "ok"}` — confirmed working on `:8000`
- [ ] Find organizer laptop's LAN IP — **not yet re-verified from a second physical device.** Audit only confirms `localhost:8000`; the actual cross-device Wi-Fi round-trip from Sprint 0's DoD hasn't been re-checked on the current dev machine.
- [ ] Hit `http://<lan-ip>:8000/health` from a second physical device on the same Wi-Fi
- [ ] Disable/unplug the router's WAN uplink and repeat the request — must still succeed
- [ ] Write the result down somewhere (which devices, which router) for future reference

> **Note:** dev environment is Windows 11. Decide now whether the actual contest-day organizer laptop will be Linux or Windows — it changes how much hardening the sandbox's Windows fallback path (§5) needs. See §5b.

---

## 2. Database Schema ✅ done

- [x] `server/database.py` (named differently than planned, same job) — SQLite engine at `Contest/Database/bytearena.db`, WAL + `foreign_keys=ON` + `busy_timeout=10000` pragma set on connect (busy_timeout added mid-Sprint-2 so the judge worker and API never deadlock — good addition beyond the original plan)
- [x] `server/models.py` — all 11 tables implemented as SQLAlchemy models, plus 7 enums (`ContestState`, `SubmissionStatus`, `Verdict`, `TestcaseStatus`, `EventType`, `ReviewDecision`, `ComplexityDecision`) matching `ARCHITECTURE.md` §2
- [x] `status`/`verdict` kept as separate columns as specified (pipeline stage vs. judging outcome)
- [x] `source_path` points to a file under `Contest/Submissions/<participant>/` — source stays out of the DB, matches manual-review design intent
- [x] `Base.metadata.create_all(bind=engine)` wired into FastAPI `lifespan`
- [x] Verified: all 11 tables present via `.schema`, FKs confirmed
- [x] Verified: `PRAGMA journal_mode` reports `wal`

> **Watch item (not blocking):** SQLAlchemy's enum column stores the member **name**, not the value — raw SQL in `worker.py`'s claim query has to pass `.name` explicitly. Documented in-code, but worth a comment reminder anywhere else raw SQL touches an enum column later.

---

## 3. Contest & Problem CRUD (Organizer Backend) ✅ done, plus extras

- [x] `server/schemas.py` — Pydantic (v1-style) request/response models
- [x] Full CRUD, beyond the original scope: `POST/GET/PUT/DELETE /api/contests`, including state-transition coercion back to `ContestState`
- [x] `server/routers/problems.py` — beyond the plan, also shipped `PUT/DELETE /api/problems/{id}` and full testcase management (`GET/POST /api/problems/{id}/testcases`, `DELETE /api/testcases/{id}`), plus duplicate-`code` → `409`
- [x] `server/problem_loader.py` (top-level, not under `services/`):
  - [x] Reads `statement.md` + optional `config.json` with documented defaults
  - [x] Walks `tests/`, pairs by basename across `inputN/outputN`, `inN/outN`, `inN/ansN`
  - [x] Stores testcases as on-disk **paths**, not contents — hidden tests stay off the wire
  - [x] `POST /api/contests/{id}/problems/load?code=X`
- [x] Sample problems `Contest/Problems/A|B|C` built and used as fixtures (A = Hello BYTEARENA, sum of two ints, 3 testcase pairs, matches `PROBLEMS_GUIDE.md` exactly)
- [ ] Loader hasn't been formally unit-tested in isolation — it's been exercised indirectly through the DoD script and manual UI use. Worth a standalone unit test before treating it as regression-safe.

---

## 4. Organizer Frontend — Contest & Problems ✅ done (vanilla JS, not React — reconsider for Sprint 3+)

- [x] **Deviation from plan:** single-file `server/static/index.html`, vanilla JS, no build step, no CDN — arguably *more* aligned with the zero-internet-tooling promise than a Vite build would've been, but Sprint 3's Monaco Editor + WebSocket client will likely force a real bundler. Decide before Sprint 3 whether to keep growing the vanilla-JS file or cut over to a proper frontend build then.
- [x] Contests tab — create/list/delete, state dropdown
- [x] Problems tab — list per contest, Add Problem with Manual + Load from Disk modes
- [x] Testcases tab — view/delete
- [x] Both Manual and Load-from-Disk flows verified end-to-end against the live server

**Checkpoint met:** contest created, 3 problems added (mix of manual + disk-loaded), confirmed correctly stored in SQLite.

---

## 5. Judge Worker — Interface & Sandbox ✅ core done — 3 items deliberately deferred, see §5b

- [x] `judge/interface.py` — `compile()`/`run()` stable interface, exactly as specified. Interpreted-language subtlety handled correctly: artifact path stays the source file (not a binary) for languages that only syntax-check at compile time.
- [x] `judge/languages.py` — `python` and `cpp` both implemented, config-only (no new code paths). `run_env_for()` correctly prepends the compiler's bin dir to `PATH` so MSYS2-built C++ binaries find `libstdc++-6.dll` at runtime.
- [ ] Dedicated low-privilege OS user (`judgerunner`) — **code supports it** (`BYTEARENA_SANDBOX_USER` env var → `_drop_privileges`), **but it's not provisioned on any actual machine yet.** POSIX runs currently execute as the worker's own user. See §5b — this is a real gap, not just an unchecked box.
- [x] `judge/sandbox.py` — per-run scratch dir under `Contest/Runs/`, wiped in `finally`, verified zero leftover dirs across all 11 DoD cases
- [x] CPU/memory caps — `RLIMIT_AS` (enforcement cap, generously above the problem limit so MLE can be *measured* rather than instantly killed) + `RLIMIT_CPU` on POSIX; Windows Job Object (`JOB_OBJECT_LIMIT_JOB_MEMORY`) with a poll-based fallback when job assignment fails
- [x] Wall-clock timeout — POSIX: `setsid()` + `killpg(SIGKILL)` on `TimeoutExpired`. Windows: `taskkill /F /T /PID` tree-kill. Both verified to leave zero stray processes after a TLE case.
- [ ] Block outbound network for the sandboxed process — **explicitly deferred this sprint, not forgotten.** See §5b — treat as blocking before any real contest, not backlog.

---

## 5b. Security Gaps to Close Before Sprint 3 / Before Any Real Contest

Pulled directly from the 2026-08-01 audit's "Known Gaps" section — these are the three items where "the code path exists but isn't actually protecting anything yet" is true, as opposed to features that simply haven't been built. Treat this section as a gate, not a nice-to-have backlog.

- [ ] **Block outbound network for the judge sandbox.** This is the one guarantee the entire "no internet, no AI" pitch depends on, and it's currently unimplemented. POSIX: scope an `iptables`/`nftables` rule to the sandbox UID, or run in a network namespace with loopback only. Verify with a testcase that calls `socket.connect()` and confirm it fails — this test doesn't exist yet either; write it alongside the fix.
- [ ] **Provision the low-privilege `judgerunner` OS user** on whichever machine will actually run the contest, and confirm `BYTEARENA_SANDBOX_USER` is set so `_drop_privileges` actually engages (verify by checking the *effective* UID of a running sandboxed process, not just that the env var is set).
- [ ] **Add a stale-claim reaper.** A worker crash between claiming a submission (`status → COMPILING`/`RUNNING`) and finishing leaves it stuck forever with no self-healing. A simple periodic sweep (`UPDATE submissions SET status='queued' WHERE status IN ('compiling','running') AND claimed_at < now() - interval`) closes this. Low-probability, but on contest day a silently stuck submission with no automatic recovery is a real support problem, not a theoretical one.

**Decide, don't just note:** is the contest-day organizer laptop Linux or Windows? The POSIX sandbox path (hard rlimits, real process-group kill) and the Windows path (softer poll-based fallback, job-assignment can fail in restrictive shells) are not equally strong guarantees. If it's Windows, the fallback path needs the same level of scrutiny as the POSIX path is getting here — right now it's only been proven correct in a dev shell, not hardened for adversarial input.

---

## 6. Judge Worker — Queue & Verdict Pipeline ✅ done — 11/11 DoD, the checkpoint is met

- [x] `submissions.status` — `QUEUED/COMPILING/RUNNING/JUDGED/COMPILE_ERROR/JUDGE_ERROR` enum
- [x] Atomic claim via `UPDATE ... WHERE id = (SELECT ... ORDER BY submitted_at, id LIMIT 1) RETURNING id` — correct pattern for multi-worker safety, though only single-worker has actually been exercised so far (see watch item below)
- [x] `judge/worker.py` main loop, short-circuits remaining testcases as `SKIPPED` on first failure
- [x] Per-testcase → `verdicts`, aggregate → `submissions.verdict` (max runtime/mem over testcases)
- [x] All six verdict states implemented and exercised
- [x] `JUDGE_ERROR` kept distinct from `RE`, scratch dir wiped in `finally` even on exception
- [x] `scripts/test_judge.py` — **11/11 cases pass**, not just the 4 minimum: AC/WA/TLE/MLE/RE/CE × {python, cpp}
- [x] Laptop responsiveness confirmed after TLE cases — zero stray processes, zero leftover scratch dirs

**Checkpoint met — this was correctly treated as the most important gate in the build**, and it's been proven with a broader test matrix than originally scoped (11 cases vs. the planned 4).

> **Watch item:** N-worker concurrency hasn't actually been exercised yet — correctness currently rests on SQLite's single-writer semantics plus the atomic `RETURNING` claim, which is sound in theory but untested under real concurrent load. Worth a deliberate 2–3 worker stress test before assuming Sprint 2's queue design scales past one worker.

---

## 7. Auth & Participant Accounts

- [ ] `passlib` bcrypt hashing helper
- [ ] `POST /contests/{id}/participants/import` — CSV upload → `participants` rows with hashed passwords
- [ ] `POST /login` — `{username, password, contest_id}` → session token (JWT with `contest_id` + `participant_id` claims, or server-side session)
- [ ] Auth dependency/middleware that validates the token on protected routes
- [ ] Token doesn't require heartbeats to stay valid (heartbeat logic is separate, added later)

---

## 8. Participant Flow — Problem View & Submission

- [ ] `frontend/src/pages/ProblemView.tsx` — renders `statement_md` as sanitized HTML, shows sample I/O and limits
- [ ] Monaco Editor vendored into the build (npm package, not CDN script tag)
- [ ] Language selector matching `judge/languages.py`
- [ ] `POST /submissions` — `{problem_id, lang, source}`:
  - [ ] Writes source to `Contest/Submissions/<username>/<problem_code>/<timestamp>.<ext>`
  - [ ] Inserts `submissions` row, `status="queued"`
- [ ] `GET /submissions/{id}` — returns current status/verdict
- [ ] Frontend polling (1–2s interval) while status isn't terminal, then renders a verdict badge (distinct color per verdict)

**Checkpoint:** from a second physical device, log in as a real participant, submit a correct solution, watch it reach `AC` without touching the DB directly.

---

## 9. Realtime Leaderboard

- [ ] `server/services/scoring.py`:
  - [ ] Solved/not-solved per problem based on first `AC`
  - [ ] Rank: `(problems_solved DESC, penalty_time ASC)`
  - [ ] Penalty time = minutes-to-first-AC + (penalty_minutes × wrong attempts before it)
- [ ] `server/ws/leaderboard.py` — one WebSocket channel per contest
- [ ] Delta-only broadcast on new verdicts (not full table re-sends)
- [ ] Freeze window: participant connections stop receiving rank/solve updates in the last `freeze_minutes`; organizer connection unaffected
- [ ] `frontend/src/pages/Leaderboard.tsx` — subscribes, applies deltas, shows a frozen-standings banner during freeze
- [ ] Test: 3 simulated participants submitting concurrently (script is fine) → confirm live rank updates with no refresh
- [ ] Test: force a freeze window, confirm participant view stalls while organizer view keeps moving

---

## 10. Anti-Cheat Signals & Rate Limiting

- [ ] `POST /heartbeat` — updates `participants.last_heartbeat`, writes `events` row
- [ ] Background job marking `disconnected` after ~20s of silence
- [ ] Client-side listeners: `visibilitychange`, `blur`/`focus`, `fullscreenchange`
- [ ] Client-side batching — flush accumulated events every few seconds, not one request per event
- [ ] `POST /events/batch` — inserts into shared `events` table
- [ ] Internet-probe client script — background fetch every 30–60s to a public endpoint; **success** triggers a warning event
- [ ] `POST /events` (single) or reuse batch endpoint for probe results
- [ ] Token-bucket rate limiter middleware on `POST /submissions`, returns `429` when exhausted
- [ ] `frontend/src/pages/OrganizerDashboard.tsx`:
  - [ ] Unified per-participant event timeline from `events`
  - [ ] Judge queue depth
  - [ ] Worker health (last-seen heartbeat per judge process)
- [ ] Test: switch tabs on participant device mid-test, confirm it appears on dashboard within seconds, correctly timestamped
- [ ] Test: exceed rate limit deliberately, confirm `429`s without judge queue corruption

---

## 11. Contest State Machine & Pause/Extend

- [ ] `server/services/contest_state.py` — `scheduled → running → paused → frozen → ended`
- [ ] `POST /contests/{id}/state` — `{action: start|pause|resume|extend|end, ...}`
- [ ] Pause: stop timer, `POST /submissions` returns `409` while paused
- [ ] Extend: push `end_at` forward, broadcast new end time over dashboard WS
- [ ] Log every transition (who, when, from/to) — reuse `events` or a small dedicated table
- [ ] Test: pause a running mock contest, confirm submissions blocked, resume, confirm they work again

---

## 12. Manual Review

- [ ] `GET /contests/{id}/submissions?status=judged` — review queue
- [ ] `frontend/src/pages/Review.tsx` — read-only source view, execution stats, per-testcase verdict breakdown
- [ ] `POST /submissions/{id}/review` — `{decision: approved|rejected|flagged, note}` → `review_flags` row
- [ ] `POST /submissions/{id}/complexity` — `{decision: valid|invalid, judge_class, note}` → `complexity_reviews` row (plain form — AI suggestion comes next)
- [ ] Wire gate/tiebreaker logic into `scoring.py`:
  - [ ] `invalid` → problem no longer counts as solved, standings recompute
  - [ ] `judge_class` only breaks ties among participants equal on `(solved, penalty_time)`
- [ ] Test: mark one submission invalid, confirm standings recompute correctly; mark a tie-break, confirm only tied participants reorder

---

## 13. AI-Assisted Complexity Review

- [ ] Decide local (Ollama, recommended default) vs. cloud-API-with-brief-reconnect, document the choice
- [ ] If local: install Ollama, pull a code-capable model, sanity-check runtime on the actual organizer laptop hardware
- [ ] `judge/complexity_review.py` — batch job over every `AC` submission with no existing `complexity_reviews` row:
  - [ ] Prompt includes source, time/mem limits, constraint bounds from `config.json`/`statement.md`
  - [ ] Store `ai_suggested_class` + `ai_reasoning`
- [ ] Update Review screen: show AI suggestion inline, one-click "accept" pre-filling judge fields
- [ ] Auto-log `judge_note` whenever the judge's final decision differs from the AI's suggestion
- [ ] Test: run batch job over a mock contest's accepted submissions, confirm every one gets a suggestion, time the accept/override flow per submission

---

## 14. Backups & Resilience

- [ ] `scripts/backup_db.py` — copies `bytearena.db` + WAL/SHM files to `Contest/Database/backups/<timestamp>/`
- [ ] Scheduled execution (background thread or OS scheduler) every N minutes during a live contest
- [ ] Confirm contest state (timer, standings, queue) is fully reconstructable from the DB — kill and restart the server process mid-mock-contest, confirm nothing is lost
- [ ] Confirm client reconnect flow: drop Wi-Fi on a participant device mid-submission, reconnect, confirm it resyncs against server state rather than trusting stale local state

---

## 15. Full MVP Dry Run

- [ ] Seed a full mock contest: 3+ problems (mixed manual/disk-loaded), 5+ fake participant accounts
- [ ] Run start-to-finish on real LAN hardware (not localhost):
  - [ ] Start contest
  - [ ] Multiple participants log in and submit (mix of correct/incorrect/TLE solutions)
  - [ ] Leaderboard updates live, freezes on schedule
  - [ ] Trigger tab-switch and internet-probe warnings on purpose, confirm dashboard shows them
  - [ ] Pause the contest, resume, extend the timer
  - [ ] Run manual review + AI-assisted complexity pass, override at least one AI suggestion
  - [ ] End contest, confirm final leaderboard matches expectations given the review decisions
- [ ] Confirm at least one automatic backup fired during the run
- [ ] Write down every friction point encountered (this feeds Phase 2 prioritization per `ROADMAP.md`)

**MVP is done when this dry run completes without you touching the database directly at any point.**
