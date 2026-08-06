# BYTEARENA — Project Audit Report

**Date:** 2026-08-01
**Status:** Sprints 0, 1, 2 complete · Sprint 3 (Participant Flow) not started
**Branch:** `main` (up to date with `origin/main`)
**Head commit:** `aa1aef7` — "feat: add FastAPI server skeleton, contest/problem CRUD, and sample problems"

---

## 1. What the Project Is

BYTEARENA is an **offline-first LAN competitive-programming platform** by BYTEMONK. One organizer laptop + a Wi-Fi router (no internet WAN) is enough to run a secure contest: participants join the LAN, read problems, submit code, get a sandboxed verdict, and see a live leaderboard.

Guiding constraints baked into the design:

- **Zero internet at runtime** — no CDN fonts, frameworks, or editor bundles; no cloud API calls.
- **Untrusted code runs only inside a sandbox** on the organizer laptop (day-one requirement, not a Phase-3 nice-to-have).
- **Single-laptop deploy** — SQLite (WAL) for MVP, no Redis; the DB itself is the judge queue.
- **Sandbox backend is swappable** — everything outside the worker talks only to `compile()` / `run()`, so a Docker/gVisor backend can replace the MVP OS-level sandbox without a rewrite.

---

## 2. Repository Layout (as-built)

```
ByteArena/
├── server/                       # Sprint 0 + 1
│   ├── __init__.py
│   ├── main.py                   # FastAPI app, /health, static mount
│   ├── database.py               # engine + WAL/foreign_keys/busy_timeout pragmas
│   ├── models.py                 # all 11 SQLAlchemy models + 7 enums
│   ├── schemas.py                # Pydantic (v1-style) request/response schemas
│   ├── problem_loader.py         # loads problems from Contest/Problems/<code>/
│   ├── routers/
│   │   ├── contests.py           # /api/contests CRUD
│   │   └── problems.py           # /api/contests/{id}/problems..., testcases
│   └── static/
│       └── index.html            # single-file organizer dashboard (447 lines, vanilla JS)
├── judge/                        # Sprint 2
│   ├── __init__.py
│   ├── interface.py              # compile() / run() stable interface
│   ├── languages.py              # language config table (python, cpp)
│   ├── sandbox.py                # cross-platform sandbox (POSIX + Windows)
│   ├── compare.py                # exact_match output comparison
│   └── worker.py                 # DB-backed queue worker, verdict aggregation
├── scripts/
│   └── test_judge.py             # Sprint 2 DoD test (11 cases)
├── Contest/                      # runtime data (per README layout)
│   ├── Problems/{A,B,C}/         # sample problems (statement.md, config.json, tests/)
│   ├── Submissions/              # participant source files (gitignored)
│   ├── Database/bytearena.db     # SQLite DB (gitignored)
│   ├── Runs/                     # judge scratch dir (gitignored, auto-wiped)
│   ├── Logs/                     # empty
│   └── Config/                   # empty
├── README.md                     # product + architecture overview
├── ARCHITECTURE.md               # full technical design (§1–§3a)
├── ROADMAP.md                    # sprint-by-sprint execution plan with DoDs
├── PROBLEMS_GUIDE.md             # how to add problems/testcases
├── requirements.txt
├── LICENSE
└── .gitignore
```

**Installed stack (verified `pip list`):** Python 3.13 (miniforge) · FastAPI 0.108.0 · Uvicorn 0.49.0 · SQLAlchemy 2.0.51 · Pydantic 1.10.26 · g++ 15.2.0 (MSYS2). Host: Windows 11.

---

## 3. Sprint 0 — Skeleton & Schema  ✅

**Goal:** prove the LAN round-trip and lock the schema. Nothing here touches judging, auth, or UI.

### 3.1 App entry — `server/main.py`

```python
from .database import engine, Base
from .models import *
from .routers import contests, problems

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)     # create tables on startup
    yield

app = FastAPI(title="BYTEARENA", version="0.1.0", lifespan=lifespan)
app.include_router(contests.router)
app.include_router(problems.router)

@app.get("/health")
def health():
    return {"status": "ok", "service": "bytearena"}

if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
```

### 3.2 Database — `server/database.py`

SQLite at `Contest/Database/bytearena.db`, WAL mode, FK enforcement, and a 10 s busy timeout (added in Sprint 2 so the judge worker and API never deadlock):

```python
DB_PATH = os.path.join(..., "Contest", "Database", "bytearena.db")
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})

@event.listens_for(engine, "connect")
def _set_wal(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=10000")
    cursor.close()
```

### 3.3 Schema — `server/models.py`

All 11 tables from ARCHITECTURE.md §2 are defined as SQLAlchemy models. The 7 enums:

```python
class ContestState(str, enum.Enum):      SCHEDULED / RUNNING / PAUSED / FROZEN / ENDED
class SubmissionStatus(str, enum.Enum):  QUEUED / COMPILING / RUNNING / JUDGED / COMPILE_ERROR / JUDGE_ERROR
class Verdict(str, enum.Enum):           AC / WA / TLE / MLE / RE / CE / PENDING
class TestcaseStatus(str, enum.Enum):    AC / WA / TLE / MLE / RE / SKIPPED
class EventType(str, enum.Enum):         HEARTBEAT / TAB_SWITCH / WINDOW_BLUR / FULLSCREEN_EXIT / INTERNET_DETECTED
class ReviewDecision(str, enum.Enum):    APPROVED / REJECTED / FLAGGED
class ComplexityDecision(str, enum.Enum):VALID / INVALID
```

Key design decisions implemented as specified:

- **`status` and `verdict` are separate columns** — status = pipeline stage, verdict = judging outcome.
- **`source_path` points to a file** under `Contest/Submissions/<participant>/` — source stays out of the DB.
- The `submissions` table (Sprint 2's queue) carries `runtime_ms` / `mem_kb` aggregates; `verdicts` carries one row per (submission, testcase).
- Anti-cheat signals all funnel into one `events` table; `warnings`, `review_flags`, `complexity_reviews`, `plagiarism_matches` are in place for later sprints.

Actual `.schema` in the live DB confirms all 11 tables created with FKs.

---

## 4. Sprint 1 — Contest & Problem CRUD  ✅

**Goal:** an organizer can create a contest and load problems, no participants yet.

### 4.1 Contest router — `server/routers/contests.py`

Full CRUD on `POST/GET/PUT/DELETE /api/contests`, including state transitions (`state="paused"` etc. are coerced back to the `ContestState` enum):

```python
@router.post("", response_model=ContestOut, status_code=201)
def create_contest(body: ContestCreate, db: Session = Depends(get_db)):
    contest = Contest(name=body.name, ..., state=ContestState.SCHEDULED, ...)
    db.add(contest); db.commit(); db.refresh(contest)
    return contest
```

### 4.2 Problem router — `server/routers/problems.py`

| Endpoint | Purpose |
|---|---|
| `GET /api/contests/{id}/problems` | list problems of a contest |
| `GET /api/problems/{id}` | problem detail (+testcase_count) |
| `PUT/DELETE /api/problems/{id}` | update / delete |
| `POST /api/contests/{id}/problems` | manual entry (validates duplicate `code` → 409) |
| `POST /api/contests/{id}/problems/load?code=X` | load from disk |
| `GET /api/problems/{id}/testcases` · `POST /api/problems/{id}/testcases` · `DELETE /api/testcases/{id}` | testcase management |

### 4.3 Disk loader — `server/problem_loader.py`

Reads `Contest/Problems/<code>/statement.md` + optional `config.json` (defaults: title=code, `time_limit_ms=1000`, `mem_limit_mb=256`, `points=100`), then walks `tests/` and **pairs input/output files by basename** across three naming conventions (`inputN/outputN`, `inN/outN`, `inN/ansN`):

```python
out_key = (base.replace("input", "output").replace("Input", "Output")
           .replace("in", "out").replace("In", "Out"))
out_path = (outputs.get(out_key)
            or outputs.get(base.replace("input", "output"))
            or outputs.get(base.replace("in", "out"))
            or outputs.get(base.replace("in", "ans")))
if out_path and os.path.isfile(out_path):
    testcases.append(Testcase(input_path=in_path, output_path=out_path, ...))
```

Testcases are stored as **paths to on-disk files**, not contents — keeps hidden tests off the wire and matches the manual-review design.

### 4.4 Organizer frontend — `server/static/index.html`

Single-file vanilla-JS dashboard (447 lines, no CDN). Three tabs: **Contests** (create/list/delete, state dropdown), **Problems** (list per contest; Add Problem with *Manual* and *Load from Disk* modes), **Testcases** (view/delete). Uses a small `api()` fetch wrapper. Verified end-to-end against the running server in Sprint 1.

### 4.5 Sample problems

`Contest/Problems/A|B|C` each have `statement.md`, `config.json`, and 3 testcase pairs. Example (`A` = Hello BYTEARENA, sum of two ints, 1000 ms / 256 MB):

```
input1.txt: 3 5      → output1.txt: 8
input2.txt: -10 20   → output2.txt: 10
input3.txt: 100 200  → output3.txt: 300
```

---

## 5. Sprint 2 — Judge Worker + MVP Sandbox  ✅ (11/11 DoD tests pass)

**Goal (the project's single most important checkpoint):** code goes in, a correct verdict comes out, safely.

### 5.1 Stable interface — `judge/interface.py`

Exactly the `compile()` / `run()` contract from ARCHITECTURE.md §3. Everything downstream (Phase-3 Docker swap) only sees these two functions.

```python
@dataclass
class Limits:            time_limit_ms: int; mem_limit_mb: int
@dataclass
class CompiledArtifact:  lang: str; path: str; workdir: str
@dataclass
class CompileError:      message: str; stderr: str = ""
@dataclass
class RunResult:         status: str; stdout: str; stderr: str
                         runtime_ms: int; mem_kb: int; exit_status: int
```

`compile()` dispatches through the language config; an important subtlety fixed during verification — interpreted languages only **syntax-check** at compile time, so the artifact path stays the source file, not a binary:

```python
uses_bin = any("{bin}" in token for token in cfg["run"])
artifact_path = bin_path if uses_bin else source_path
```

`run()` maps the sandbox's raw result to `status ∈ {"ok", "timeout", "error"}`.

### 5.2 Language config — `judge/languages.py`

Adding a language = adding one config entry, no new code paths:

```python
LANGUAGES = {
    "python": {
        "extension": "py",  "source_name": "main.py",
        "compile": [sys.executable, "-m", "py_compile", "{src}"],
        "run":     [sys.executable, "{src}"],
        "compile_timeout_ms": 10000,
    },
    "cpp": {
        "extension": "cpp", "source_name": "main.cpp",
        "compile": ["g++", "-O2", "-std=c++17", "-o", "{bin}", "{src}"],
        "run":     ["{bin}"],
        "compile_timeout_ms": 15000,
    },
}
```

`run_env_for()` prepends the compiler's bin dir to `PATH` so MSYS2-built C++ binaries find `libstdc++-6.dll` etc. at runtime (verified working).

### 5.3 Output comparison — `judge/compare.py`

Lenient exact match: strips trailing whitespace per line and trailing empty lines, so Windows `\r\n` and trailing-newline differences don't cause false WAs.

```python
def normalize(text: str) -> str:
    lines = text.split("\n")
    cleaned = [line.rstrip() for line in lines]
    while cleaned and cleaned[-1] == "":
        cleaned.pop()
    return "\n".join(cleaned) + "\n"

def compare(actual: str, expected: str) -> bool:
    return normalize(actual) == normalize(expected)
```

### 5.4 Sandbox — `judge/sandbox.py` (the security-critical piece)

One interface, two backends, selected at import time:

```python
IS_POSIX = os.name == "posix"
def run_sandboxed(cmd, cwd, stdin_bytes, time_limit_ms, mem_limit_mb, env=None):
    if IS_POSIX: return _run_posix(...)
    return _run_windows(...)
```

**Memory model (documented in the module docstring):** the *enforcement* cap (rlimit/job) is set generously above the problem's limit — `enforcement_mem_mb(limit) = max(limit*2, limit+256)` — so a process that merely exceeds the documented limit survives long enough to be **measured**; the *verdict* threshold (peak memory vs. the problem's limit) is applied by the worker. This keeps the laptop safe while making MLE deterministic on both platforms.

**POSIX backend** (`_run_posix`, used on the production Linux laptop):

- `preexec_fn` runs `os.setsid()` (new process group) so the whole tree can be killed on timeout — catches fork bombs, not just the parent.
- Optional privilege drop to a dedicated low-priv user via `BYTEARENA_SANDBOX_USER` (`_drop_privileges` → `setgid`/`setuid`).
- `RLIMIT_AS` (address space) at the enforcement cap and `RLIMIT_CPU` at the time limit.
- Wall-clock timeout kills the process group with `SIGKILL`:

```python
except subprocess.TimeoutExpired:
    timed_out = True
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    stdout, stderr = proc.communicate()
```

- Peak memory from `/proc/<pid>/status` `VmHWM` (fallback: `ru_maxrss` delta).

**Windows backend** (`_run_windows` + `_run_windows_fallback`): a **Job Object** is created with `JOB_OBJECT_LIMIT_JOB_MEMORY` (whole-tree memory cap) and `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` (nothing outlives the job), with peak memory read from `PeakJobMemoryUsed`. **Known environment finding:** in this dev shell the parent process already lives inside a job with no breakaway, so `AssignProcessToJobObject` fails (error 6). The code handles that by falling back to:

```python
job = None
try:
    job = _win_create_job(mem_limit_mb)
    if not _win_assign_process(job, int(proc.pid)):
        job = None
except SandboxError:
    job = None
if job:
    ...  # Job Object path (hard cap, TerminateJobObject on timeout)
else:
    stdout, stderr, elapsed_ms, timed_out, mem_kb = _run_windows_fallback(proc, ...)
```

`_run_windows_fallback` is a poll loop (10 ms) that:
- drains stdout/stderr on background threads (prevents pipe-buffer deadlock),
- tracks peak working set via `GetProcessMemoryInfo` (PSAPI) and also reads `PeakWorkingSetSize` after exit,
- kills the whole process tree with `taskkill /F /T /PID <pid>` on wall-clock timeout **or** when the enforcement memory cap is exceeded.

**Network blocking is intentionally NOT implemented this sprint** (per the agreed scope). The module docstring and ARCHITECTURE.md flag that production POSIX should block outbound sockets for the sandbox user via firewall/namespace.

### 5.5 Worker + verdict pipeline — `judge/worker.py`

**Queue = the DB itself.** No Redis. `claim_next` atomically claims the oldest queued row via `UPDATE … RETURNING`, so N workers can run without coordination:

```python
row = db.execute(text(
    "UPDATE submissions SET status = :compiling "
    "WHERE id = (SELECT id FROM submissions WHERE status = :queued "
    "ORDER BY submitted_at, id LIMIT 1) "
    "RETURNING id"
), {"compiling": SubmissionStatus.COMPILING.name,
    "queued":    SubmissionStatus.QUEUED.name}).fetchone()
db.commit()
```

> Note: SQLAlchemy's `SAEnum` stores the enum member **name**, not the value — the raw SQL must pass `.name`. A comment in the code documents this.

**`process_submission` flow:**

1. Copy source into a fresh scratch dir under `Contest/Runs/run_<id>_*/`.
2. `status = RUNNING` → `compile()`.
3. If `CompileError` → `status=COMPILE_ERROR`, `verdict=CE`.
4. Otherwise run each testcase in id order under the sandbox; **short-circuit on first failure** (remaining testcases recorded as `SKIPPED`).
5. `_classify` decides each testcase status; the submission's aggregate `runtime_ms`/`mem_kb` are the max over testcases.

```python
def _classify(run_res, expected, limits):
    mem_limit_kb = limits.mem_limit_mb * 1024
    if run_res.status == "timeout":                       return TestcaseStatus.TLE, Verdict.TLE
    if run_res.mem_kb and run_res.mem_kb > mem_limit_kb:  return TestcaseStatus.MLE, Verdict.MLE
    if run_res.status == "error":                         return TestcaseStatus.RE,  Verdict.RE
    if compare(run_res.stdout, expected):                 return TestcaseStatus.AC,  Verdict.AC
    return TestcaseStatus.WA, Verdict.WA
```

6. `status=JUDGED`, `verdict=<aggregate>`; per-testcase rows inserted into `verdicts`.
7. Exceptions → `status=JUDGE_ERROR` (distinct from `RE` — a judge bug must not look like the participant's fault), scratch dir wiped in a `finally`.

**How TLE works end-to-end (the detail you asked about):**

1. Problem A sets `time_limit_ms = 1000`.
2. Worker passes it to `interface.run` → `sandbox.run_sandboxed(..., time_limit_ms=1000, ...)`.
3. Windows fallback: poll loop every 10 ms; when `time.perf_counter() - start > 1.0s` it runs `taskkill /F /T /PID <pid>` (kills the whole process group) and sets `timed_out=True`. POSIX: `proc.communicate(timeout=1.0)` raises `TimeoutExpired` → `killpg(SIGKILL)`.
4. Sandbox returns `RawRunResult(timed_out=True, exit_status=-1, runtime_ms≈1160)`.
5. `interface.run` maps it to `status="timeout"`; `_classify` returns `TestcaseStatus.TLE, Verdict.TLE`.
6. Remaining testcases become `SKIPPED`; submission → `JUDGED / TLE`.
7. Because the kill is a whole-tree kill and scratch dirs are wiped, **the laptop stays responsive** — verified: zero stray processes and zero leftover `Contest/Runs/` entries after every TLE/MLE test.

### 5.6 DoD test — `scripts/test_judge.py`

Inserts submissions straight into the DB (the submission API intentionally doesn't exist until Sprint 3), claims + processes each, asserts the verdict:

| Case | Language | Source | Expected | Actual | Runtime | Peak mem |
|---|---|---|---|---|---|---|
| PY AC | python | `print(a+b)` | AC | AC | 43 ms | 11 724 KB |
| CPP AC | cpp | `cout<<a+b` | AC | AC | 21 ms | 5 252 KB |
| PY WA | python | `print(a+b+1)` | WA | WA | 31 ms | 11 748 KB |
| PY TLE | python | `while True: pass` | TLE | TLE | 1 194 ms | 11 600 KB |
| CPP TLE | cpp | `for(;;);` | TLE | TLE | 1 211 ms | 3 528 KB |
| PY CE | python | `def f(:` (syntax error) | CE | CE | — | — |
| CPP CE | cpp | `int main( {` | CE | CE | — | — |
| PY RE | python | `sys.exit(3)` | RE | RE | 32 ms | 11 632 KB |
| CPP RE | cpp | `return 3` | RE | RE | 10 ms | 3 956 KB |
| PY MLE | python | `bytearray(300 MB)` | MLE | MLE | 139 ms | 318 912 KB |
| CPP MLE | cpp | `vector<char>(300 MB)` | MLE | MLE | 75 ms | 312 072 KB |

**Result: 11/11 PASS.** The two bugs found and fixed during this sprint:

1. **Job Object assignment fails in agent shells** (error 6) → added the poll+taskkill fallback.
2. **`-O2` elided the C++ MLE test** (dead `vector` allocation) → test now uses the allocation (`printf(v.back())`); also `py_compile` was added so Python syntax errors produce `CE` instead of `RE`, and the artifact path bug (Python run executed `main.exe`) was fixed.

---

## 6. Runtime Verification (re-verification pass, 2026-08-01)

- **Standalone worker loop** (`python -m judge.worker`, poll mode): fresh queued submissions were picked up automatically — sub 48 → `JUDGED/AC` (42 ms), sub 49 → `JUDGED/TLE` (1 225 ms). Worker then stopped cleanly.
- **Per-testcase rows correct:** sub 48 → AC on all 3 testcases; sub 49 → TLE on #1, SKIPPED on #2/#3.
- **Cleanup:** 0 leftover scratch dirs; no stray `python`/`main.exe` processes after kills.
- **CLI:** `python -m judge.worker --once` exits 0 on an empty queue.
- **All modules import cleanly** (`judge.*`, `server.*`).
- **Server:** `GET /health` → `{"status":"ok","service":"bytearena"}` on `:8000` (uvicorn `--reload`).

### Current live DB state (`Contest/Database/bytearena.db`)

| Table | Rows | Notes |
|---|---|---|
| contests | 1 | "Sprint 1 Demo", state=RUNNING |
| participants | 1 | `judge_test` (used by the DoD script) |
| problems | 3 | A/B/C under contest 1 |
| testcases | 9 | 3 per problem |
| submissions | 49 | all in terminal state (JUDGED / COMPILE_ERROR) |
| verdicts | 126 | AC 27 · MLE 6 · RE 13 · TLE 7 · WA 5 · SKIPPED 62 |

(SKIPPED count is consistent: 31 failing submissions × 2 skipped testcases each.)

---

## 7. Git History

```
aa1aef7  feat: add FastAPI server skeleton, contest/problem CRUD, and sample problems   (HEAD)
6338dc9  feat: add detailed architecture documentation and execution roadmap
c4bb48e  fix: resolve Mermaid diagram rendering issues on GitHub
5b698ad  docs: add README with Mermaid architecture diagrams and MIT LICENSE
07fb877  Refactor code structure for improved readability and maintainability
```

`origin` = `https://github.com/mrinmoyChakraborty-mrinox/ByteArena.git`, branch `main`, ahead of `origin` by 0.

**Uncommitted working tree (Sprint 2 changes):**
```
 M .gitignore               # Contest/Runs/, Contest/Submissions/*, DB files
 M server/database.py       # +PRAGMA busy_timeout=10000
?? judge/                   # new package (5 modules)
?? scripts/                 # test_judge.py
```

---

## 8. Design Docs vs. Implementation (gap audit)

| ARCHITECTURE.md / ROADMAP.md spec | Status |
|---|---|
| 11-table SQLAlchemy schema matching §2 exactly | ✅ Implemented |
| WAL mode confirmed | ✅ (`PRAGMA journal_mode=wal`) |
| `compile()`/`run()` stable interface | ✅ `judge/interface.py` |
| Language config table, add-by-config | ✅ python + cpp (C/Java pending — config-only additions) |
| `status`/`verdict` split columns | ✅ |
| OS-level sandbox: low-priv user, rlimit, process-group kill, scratch wipe | ✅ POSIX path implemented; low-priv user is opt-in via env var, **not yet provisioned** (needs a `judgerunner` OS user on the prod laptop) |
| Block outbound network | ⛔ **Deferred** (documented TODO in `judge/sandbox.py`) |
| DB-backed queue, no Redis | ✅ `claim_next` via `UPDATE…RETURNING` |
| Verdicts AC/WA/TLE/MLE/RE/CE/JUDGE_ERROR | ✅ all present in worker |
| DoD: correct → AC, infinite loop → TLE, laptop responsive | ✅ proven 11/11 |
| Phase-3 Docker/gVisor backend swap | ⛔ not started (interface ready for it) |
| Contest/Problem CRUD + disk loader + organizer UI | ✅ Sprint 1 |
| Auth, participant flow, submission API, leaderboard, WebSockets, anti-cheat, manual review | ⛔ Sprint 3+ not started |

---

## 9. Known Gaps / Risks (honest list)

1. **Network blocking missing** — outbound sockets are not yet blocked for the sandbox. Low risk in the DoD (not tested), but must be done before a real contest.
2. **Low-privilege user not provisioned** on the production laptop — `BYTEARENA_SANDBOX_USER` defaults to None; POSIX runs currently execute as the worker's user.
3. **Windows fallback is a soft memory cap** (poll-based, 10 ms granularity) — fine for dev; the Job Object path (hard cap) engages only when the parent isn't inside another job.
4. **No stale-claim reaper** — a worker crash between claim and finish leaves a submission stuck in `COMPILING`/`RUNNING`. The DoD test cleans these up explicitly.
5. **Windows `CREATE_NEW_PROCESS_GROUP` + taskkill** is the tree-kill mechanism; a process that re-parents itself outside the tree could evade it (POSIX `setsid`+`killpg` has the same class of limitation). Acceptable for MVP threat model.
6. **No submission API yet** — judging is only reachable from scripts/DB until Sprint 3.
7. **Judge concurrency** is not exercised — single worker verified; N-worker claim correctness relies on SQLite's single-writer + the atomic `UPDATE…RETURNING`.
8. **`db.expire_all()`/refresh patterns** in the test script and `.get()` usage assume the ORM session stays in sync with raw-SQL writes — works, but a migration to ORM-only verdict writes would be cleaner.

---

## 10. How to Run (verified commands)

```powershell
# API server (dev)
uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload

# Judge worker (single pass or continuous)
python -m judge.worker --once
python -m judge.worker --poll-interval 1.0

# Sprint 2 DoD test
python scripts/test_judge.py          # → 11/11 passed

# Inspect the DB
sqlite3 Contest/Database/bytearena.db ".tables"
```

---

## 11. Summary

- **Sprint 0 ✅** skeleton + frozen schema (11 tables, WAL, enums) — no deviations.
- **Sprint 1 ✅** full contest/problem/testcase CRUD, deterministic disk loader, working organizer dashboard, 3 sample problems.
- **Sprint 2 ✅** the core value proposition works: `python` and `cpp` submissions are compiled, sandboxed (rlimit/Job-Object with a robust Windows fallback), run against hidden testcases with a 1 s wall-clock TLE kill, and produce `AC/WA/TLE/MLE/RE/CE` — **11/11 DoD cases pass**, laptop stays responsive, no orphan processes or scratch litter.
- **Not yet started:** participant flow/auth, submission API, realtime leaderboard, anti-cheat ingestion, manual review, network blocking, and Phase-3 container sandbox — all explicitly scoped to Sprints 3+ in `ROADMAP.md`.
- **Working tree:** Sprint 2 changes are uncommitted (`judge/`, `scripts/`, `.gitignore`, `server/database.py`); head is `aa1aef7` and `origin/main` is current.
