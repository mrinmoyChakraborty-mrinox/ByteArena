# Judge0 Implementation Guide

**Sprint 2.5 · Judge0 Migration** — implementation guide for the assignees.

**Primary owner:** A (Backend / Judge). **Read this before touching `judge/interface.py`.**
**Documented from:** the [Judge0 Python SDK docs (master)](https://python.docs.judge0.com/master/index.html), read page-by-page for this guide.

This guide maps every task in Sprint 2.5 (`a-25-1` → `a-25-8` of `bytearena_mvp_assignments.html`) to concrete SDK usage and code. The one non-negotiable constraint, straight from the assignment:

> **Keep the exact same function signatures and dataclasses** (`CompiledArtifact`, `CompileError`, `RunResult`, `Limits`) — nothing in `worker.py` should need to change beyond what calls into `interface.py`.

Everything below assumes the [Judge0 Python SDK](https://python.docs.judge0.com/master/index.html) (`pip install judge0`) driving a **self-hosted Judge0 CE** instance over the LAN.

---

## Table of Contents

1. [Box of Knowledge — abbreviations used everywhere](#1-box-of-knowledge--abbreviations-used-everywhere)
2. [How the pieces fit together (architecture)](#2-how-the-pieces-fit-together-architecture)
3. [TL;DR — the one-page plan](#3-tldr--the-one-page-plan)
4. [SDK concepts you actually need](#4-sdk-concepts-you-actually-need)
5. [Task-by-task implementation](#5-task-by-task-implementation)
6. [The one deliberate change to `worker.py`](#6-the-one-deliberate-change-to-workerpy)
7. [The 11-case suite, case by case](#7-the-11-case-suite-case-by-case)
8. [Verification checklist (the Sprint 2.5 gate)](#8-verification-checklist-the-sprint-25-gate)
9. [Troubleshooting](#9-troubleshooting)
10. [Suggested implementation order](#10-suggested-implementation-order)
11. [Gotchas & decisions log](#11-gotchas--decisions-log)
12. [References](#12-references)

---

## 1. Box of Knowledge — abbreviations used everywhere

Every abbreviation that appears in this guide, this repo, and the Judge0 docs — one place to look them up.

### 1.1 BYTEARENA verdicts & pipeline states

| Abbr | Stands for | Meaning here |
|---|---|---|
| AC | Accepted | Output matched expected output for the testcase / submission |
| WA | Wrong Answer | Output did **not** match expected (after `judge/compare.py` lenient normalization) |
| TLE | Time Limit Exceeded | Program ran past the problem's `time_limit_ms` |
| MLE | Memory Limit Exceeded | Program used more than the problem's `mem_limit_mb` |
| RE | Runtime Error | Program crashed (signal) or exited with a non-zero code |
| CE | Compilation Error | Source failed to compile / syntax-check |
| PENDING | — | Default `submissions.verdict` before a worker finishes judging |
| QUEUED | — | Row waiting for a worker to claim it |
| COMPILING | — | Row claimed; `compile()` in progress |
| RUNNING | — | Row in the per-testcase `run()` loop |
| JUDGED | — | Terminal: aggregate verdict computed |
| COMPILE_ERROR | — | Terminal: `compile()` returned a `CompileError` → verdict `CE` |
| JUDGE_ERROR | — | Terminal: judge infrastructure failed (not the participant's fault) |
| SKIPPED | — | Testcases after the first failure are marked SKIPPED, not run |

All of these map to the enums in `server/models.py:9-62` (`Verdict`, `SubmissionStatus`, `TestcaseStatus`).

### 1.2 Judge0 terms

| Abbr | Stands for | Meaning here |
|---|---|---|
| CE | Community Edition | The free, self-hostable Judge0 flavor (also see ambiguity alert below) |
| Extra CE | Extra Community Edition | Hub flavor with more languages; NOT used by this migration |
| SDK | Software Development Kit | The `judge0` Python package |
| REST | Representational State Transfer | The HTTP API style Judge0 exposes (`POST /submissions`, `GET /submissions/{token}`, …) |
| API | Application Programming Interface | The HTTP endpoints the SDK wraps |
| token | — | Per-submission UUID returned by `POST /submissions`; you poll with it |
| isolate | — | The sandbox tool Judge0 runs every submission inside (the containment that replaces the old iptables plan) |
| Flavor | — | SDK `Flavor` enum: `CE` vs `EXTRA_CE` ([Types](https://python.docs.judge0.com/master/api/types.html)) |
| IN_QUEUE / PROCESSING | — | SDK `Status` values meaning *still running* |
| ACCEPTED / WRONG_ANSWER / TIME_LIMIT_EXCEEDED / COMPILATION_ERROR | — | SDK `Status` terminal values (3, 4, 5, 6) |
| RUNTIME_ERROR_SIGSEGV / _SIGXFSZ / _SIGFPE / _SIGABRT / _NZEC / _OTHER | — | SDK `Status` values 7–12 — all collapse to BYTEARENA `RE` |
| INTERNAL_ERROR / EXEC_FORMAT_ERROR | — | SDK `Status` 13/14 — judge infrastructure failures → `JUDGE_ERROR` |
| ATD | AllThingsDev | One of the hub providers the SDK can talk to ([Clients](https://python.docs.judge0.com/master/api/clients.html)) |
| RapidAPI | — | Another hub provider the SDK supports |
| LanguageAlias | — | SDK enum of supported languages, resolved to the *latest version* on the connected client |

### 1.3 OS / processes / signals

| Abbr | Stands for | Meaning |
|---|---|---|
| SIGSEGV | signal 11 — segmentation fault | Invalid memory access |
| SIGXFSZ | signal 25 — file size limit exceeded | Output file grew past the max file size |
| SIGFPE | signal 8 — floating-point exception | Integer divide-by-zero, etc. |
| SIGABRT | signal 6 — abort | `abort()` called |
| SIGKILL | signal 9 — kill | Uncatchable; what the OOM killer sends |
| NZEC | Non-Zero Exit Code | Program finished but returned a code ≠ 0 |
| OOM | Out Of Memory | Memory-limit kill (see §6 — this is how MLE surfaces in Judge0) |
| EPERM | Operation not permitted | The typical `errno` you see when `ENABLE_NETWORK=false` blocks a socket call |
| exit code | process return value | `0` = success; Judge0 exposes it as `exit_code` |

### 1.4 Units & time

| Abbr | Stands for | Where |
|---|---|---|
| ms | millisecond | BYTEARENA time unit: `problems.time_limit_ms`, `submissions.runtime_ms` |
| s | second | Judge0 time unit: `cpu_time_limit`, `time`, `wall_time` |
| KB | kilobyte | Judge0 memory unit: `memory`, `memory_limit` |
| MB | megabyte | BYTEARENA memory unit: `problems.mem_limit_mb` (**1 MB = 1024 KB** — see §5 a-25-5) |
| CPU time | processor time | What Judge0 `time` reports — use it for `runtime_ms` |
| wall time | wall-clock time | Real elapsed time — Judge0 `wall_time`; do **not** score with it |

### 1.5 Web / infra / tooling

| Abbr | Stands for | Meaning |
|---|---|---|
| HTTP(S) | HyperText Transfer Protocol (Secure) | Transport for the Judge0 API |
| URL | Uniform Resource Locator | e.g. `http://localhost:2358` (Judge0 CE's API port) |
| JSON | JavaScript Object Notation | API request/response payload format |
| env var | environment variable | Configuration channel (`JUDGE0_ENDPOINT`, `JUDGE0_*`, `PATH`, …) |
| CVE | Common Vulnerabilities and Exposures | Public security advisories to review before pinning a Judge0 version |
| Docker | — | Container runtime Judge0 ships on (docker-compose) |
| compose | Docker Compose | Multi-container definition — Judge0 brings its own Postgres + Redis |
| Postgres | PostgreSQL | Judge0's **own** database — never touch it from BYTEARENA code |
| Redis | Remote Dictionary Server | Judge0's **own** queue — same rule |
| SQLite | — | BYTEARENA's database (`Contest/Database/bytearena.db`), WAL mode |
| WAL | Write-Ahead Logging | SQLite journal mode enabling concurrent reader/writer |
| ORM | Object-Relational Mapping | SQLAlchemy — BYTEARENA's model layer |
| SAEnum | SQLAlchemy `Enum` | Stores the enum **member name** in the DB column, not `.value` (Sprint-0 gotcha) |
| SQL | Structured Query Language | Raw queries in `claim_next` / the reaper |
| JWT | JSON Web Token | Participant login token (Sprint 3, `python-jose`) |
| WS | WebSocket | Live leaderboard channel (Sprint 4) |
| CRUD | Create / Read / Update / Delete | Sprint 1 contest & problem routers |
| CSV | Comma-Separated Values | Participant import (`POST /contests/{id}/participants/import`) |
| MVP | Minimum Viable Product | The milestone this whole plan builds |
| DoD | Definition of Done | Acceptance criteria per sprint (the checklist in §8) |
| LAN | Local Area Network | Contest network — "zero internet, ever" |
| CLI | Command Line Interface | e.g. `python scripts/test_judge.py` |
| IDE | Integrated Development Environment | [Judge0 IDE](https://ide.judge0.com/) — handy for manual probes |
| FIFO | First In, First Out | `claim_next()` claim order (`ORDER BY submitted_at, id`) |
| UTC | Coordinated Universal Time | Timestamps (`datetime.utcnow`) |

> **Ambiguity alert:** `CE` means **Compilation Error** (a BYTEARENA verdict) *and* **Community Edition** (a Judge0 flavor). Never write bare "CE" in a comment or log line without context. In this guide, "Judge0 CE" is the flavor; bare `CE` is the verdict.

---

## 2. How the pieces fit together (architecture)

```
                         BYTEARENA (your code, unchanged surfaces)
  ┌──────────────────────────────────────────────────────────────────────────┐
  │  server/ (FastAPI + SQLite)          judge/ (worker process)              │
  │    submissions table                  claim_next() -> claimed row         │
  │    verdicts table                     interface.compile()                 │
  │    problems/testcases tables          interface.run()   x N testcases     │
  └──────────────────┬───────────────────────────────────────────┬────────────┘
                     │  HTTP over LAN (port 2358)                 │  HTTP
                     ▼                                            ▼
  ┌──────────────────────────────────────────────────────────────────────────┐
  │  Judge0 CE  (docker-compose on the contest host)                          │
  │    Rails API server  ->  workers  ->  isolate sandbox per submission      │
  │    Postgres (Judge0's own DB)  +  Redis (Judge0's own queue)              │
  └──────────────────────────────────────────────────────────────────────────┘
```

**Data flow for one BYTEARENA submission:**

1. A row lands in `submissions` with `status=QUEUED` (Sprint 3's `POST /submissions` will do this; today `scripts/test_judge.py` does).
2. A worker calls `claim_next(db)` — an atomic `UPDATE … RETURNING` that sets `COMPILING` (`judge/worker.py:38-51`).
3. `interface.compile()` submits the source to Judge0 with a **tiny box** (2 s / 64 MB) and empty stdin (see §5 a-25-2 for why). Only a `COMPILATION_ERROR` returns a `CompileError`; everything else returns the source as the `CompiledArtifact`.
4. The worker sets `status=RUNNING`, then loops over the problem's testcases calling `interface.run()` — **one Judge0 submission per testcase** with the problem's real limits and the testcase's stdin.
5. Each `RunResult` is classified by `worker._classify` (TLE/MLE/RE/AC/WA) and written to `verdicts`. The first failure short-circuits the rest as `SKIPPED`.
6. The row becomes `JUDGED` with aggregate `verdict`, `runtime_ms`, `mem_kb`.
7. If Judge0 itself fails (status 13/14) or the HTTP call hangs past the retry budget, `interface` raises and the worker marks the row `JUDGE_ERROR`. A crashed worker mid-flight is healed by the stale-claim reaper (§5 a-25-8).

**What the SDK does under the hood** — the SDK is a thin wrapper over Judge0's REST API:

| SDK call | REST endpoint | Purpose |
|---|---|---|
| `judge0.execute(...)` / `judge0.run(...)` | `POST /submissions` then poll `GET /submissions/{token}` | Create **and wait** until terminal |
| `client.create_submission(sub)` | `POST /submissions` | Create; returns `sub` with `token` set |
| `client.get_submission(sub)` | `GET /submissions/{token}` | Poll status by token |
| `client.create_submissions([...])` | `POST /submissions/batch` | Batch create (deferred, §11) |
| `client.get_languages()` | `GET /languages` | List supported languages |
| `client.get_language_id(alias)` | derived from `GET /languages` | Resolve alias → numeric id on *this* server |
| `client.get_config_info()` | `GET /config_info` | Server config (limits, network flag, maintenance) |
| `client.get_statuses()` | `GET /statuses` | The 14-value status list |
| `client.get_about()` | `GET /about` | Health check |

All client methods are documented in the [Clients module](https://python.docs.judge0.com/master/api/clients.html).

---

## 3. TL;DR — the one-page plan

1. **Self-host Judge0 CE** on the contest host via docker-compose, **pinned to a release tag** (never `:latest` for something that executes untrusted code) — §5 a-25-1.
2. Point BYTEARENA's judge at `http://<host-ip>:2358` via a `JUDGE0_ENDPOINT` env var — §4.2.
3. **Build the language table** with `LanguageAlias` + `client.get_language_id()`, never hardcoded IDs — §5 a-25-3.
4. **`compile()`** becomes one Judge0 submission with a tiny CPU/memory box and empty stdin: **only status 6 (Compilation Error) is a `CompileError`**; everything else returns the source as the artifact — §5 a-25-2.
5. **`run()`** becomes one Judge0 submission per testcase with the problem's real limits; map the SDK `Status` to `RunResult.status`, convert seconds→ms and MB→KB — §5 a-25-2/4/5.
6. **Do NOT set `expected_output`.** BYTEARENA's lenient `judge/compare.py` stays the correctness check — §5 a-25-2.
7. Apply **one** deliberate line change in `worker._classify` (`>` → `>=` for the memory check) so Judge0 OOM kills surface as MLE — §6.
8. Re-run `python scripts/test_judge.py` → must pass **11/11** with zero changes to the test file — §7.

---

## 4. SDK concepts you actually need

### 4.1 Install + Hello World

[Getting started](https://python.docs.judge0.com/master/index.html#getting-started):

```bash
pip install judge0
```

```python
import judge0

sub = judge0.run(source_code="print('Hello Judge0!')")
print(sub.stdout)
```

To route that to your **self-hosted** instance instead of the preview client, either set the SDK's implicit-resolution env vars (see 4.2) or, in the worker, construct a `Client` explicitly (§5 a-25-2).

### 4.2 Clients and client resolution

See [Client Resolution](https://python.docs.judge0.com/master/in_depth/client_resolution.html) and [Clients module](https://python.docs.judge0.com/master/api/clients.html).

The SDK supports two flavors — **CE** and **Extra CE** (`judge0.Flavor`, [Types](https://python.docs.judge0.com/master/api/types.html)). When you call `judge0.run(...)` without a client, it **auto-resolves** one in this priority order:

| Priority | Client | Env vars that activate it |
|---|---|---|
| 1 | **Custom / self-hosted** | `JUDGE0_CE_ENDPOINT` + `JUDGE0_CE_AUTH_HEADERS` (JSON string) — or the `JUDGE0_EXTRA_CE_*` pair for Extra CE |
| 2 | **Judge0 Cloud** | `JUDGE0_CLOUD_CE_AUTH_HEADERS` / `JUDGE0_CLOUD_EXTRA_CE_AUTH_HEADERS` |
| 3 | **RapidAPI** | `JUDGE0_RAPID_API_KEY` |
| 4 | **AllThingsDev (ATD)** | `JUDGE0_ATD_API_KEY` |
| 5 | **Preview client** | (fallback) unauthenticated Judge0 Cloud — **rate-limited**, logs a warning |

Suppress the preview warning with `JUDGE0_SUPPRESS_PREVIEW_WARNING`. Errors `ClientResolutionError` and `PreviewClientLimitError` come from [Errors module](https://python.docs.judge0.com/master/api/errors.html).

**Trap for this project:** run the worker without configuration and it silently uses the **preview client** — rate-limited, cloud-hosted, and *not the instance you'll ship on*. Be explicit:

```python
from judge0.clients import Client
from judge0.retry import MaxWaitTime

client = Client(
    endpoint="http://localhost:2358",          # self-hosted CE worker port
    retry_strategy=MaxWaitTime(max_wait_time_sec=120),
)
```

Useful client methods for the migration (all in [Clients module](https://python.docs.judge0.com/master/api/clients.html)):

| Method | What it's for |
|---|---|
| `client.create_submission(sub)` | POST one submission; returns it with `token` set |
| `client.get_submission(sub, fields=...)` | poll by token (`fields` limits which attributes come back) |
| `client.get_languages()` / `get_language(id)` | build/verify the language table |
| `client.get_language_id(LanguageAlias.X)` | resolve alias → numeric id on *this* server |
| `client.is_language_supported(alias)` | guard before resolving |
| `client.get_config_info()` | returns `Config`; verify `enable_network`, max limits, `maintenance_mode` |
| `client.get_statuses()` / `get_about()` | verify server health / status list |

### 4.3 `Submission` — the fields that matter

The `Submission` constructor and helpers are in the [Submission module](https://python.docs.judge0.com/master/api/submission.html). **Set** on the way in:

| Constructor param | Unit / meaning |
|---|---|
| `source_code` | The source to execute |
| `language` | `LanguageAlias` **or** numeric id |
| `stdin` | Input fed via standard input during execution |
| `cpu_time_limit` | Max **CPU** seconds (Judge0 uses seconds — see §5 a-25-5) |
| `memory_limit` | Max memory in **KB** |
| `expected_output` | ⚠ Do **not** set this — see §11 item 1 |
| `additional_files` | base64 `.zip` for multi-file programs — **Phase 2, not MVP** |
| `compiler_options` / `command_line_arguments` / `enable_network` / `number_of_runs` / `callback_url` / … | Not used by this migration (full list in the docs) |

**Read** back after judging (Judge0 response fields the SDK stores on the same object):

| Field | Unit / meaning |
|---|---|
| `status` | `judge0.Status` enum (see §5 a-25-4) |
| `stdout` / `stderr` | program output |
| `compile_output` | compiler output (populated on Compilation Error) |
| `message` | human-readable status detail (e.g. exit code) |
| `time` | **CPU time, seconds** (float) |
| `wall_time` | wall-clock seconds — do not score with it |
| `memory` | **memory used, KB** (int) |
| `exit_code` | process exit code; `None` if killed by a signal |
| `token` | submission id used for polling |
| `is_done()` | `False` while `IN_QUEUE`/`PROCESSING`; `True` once terminal |

### 4.4 High-level vs low-level API + retry strategies

All functions are in the [API module](https://python.docs.judge0.com/master/api/api.html).

- **High level:** `judge0.run` / `judge0.execute` / `judge0.sync_execute` — create the submission(s) **and wait** until finished. Returns a single `Submission` when you pass `submissions=<one Submission>` or `source_code=...`; a list when you pass a list or `test_cases=`. `async_execute` is the non-blocking variant.
- **Low level:** `client.create_submission(s)` → `judge0.wait(client=..., submissions=...)` / `judge0.get_submissions(...)` — use when you need the token to persist or poll from another process.
- **Batch:** `create_submissions` / `create_submissions_from_test_cases` + `test_cases=` hit `/submissions/batch`. **Deferred** (see §11 item 7).

**Retry strategies** ([Retry module](https://python.docs.judge0.com/master/api/retry.html)) control polling while waiting:

| Strategy | Poll cadence | Stops when | Use for |
|---|---|---|---|
| `MaxRetries(20)` | every 0.1 s | 20 tries (~2 s) | quick smoke checks |
| `MaxWaitTime(300)` | every 0.1 s | 300 s elapsed | **judging** — TLE submissions legitimately run the full `cpu_time_limit` |
| `RegularPeriodRetry(0.1)` | every 0.1 s | never | watch loops |

Set the strategy on the `Client` at construction so `execute`/`run`/`wait` all inherit it.

### 4.5 Errors and logging

- `ClientResolutionError` — a client couldn't be resolved (env vars / endpoint wrong). [Errors](https://python.docs.judge0.com/master/api/errors.html)
- `PreviewClientLimitError` — preview-client rate limit hit (you forgot to point at your own instance).
- **Logging** — [Logging in-depth page](https://python.docs.judge0.com/master/in_depth/logging.html). Off by default. During the migration:
  ```bash
  set JUDGE0_ENABLE_LOGGING=1
  set JUDGE0_CONSOLE_LOG_LEVEL=debug      # DEBUG|INFO|WARNING|ERROR|CRITICAL
  set JUDGE0_FILE_LOG_LEVEL=warning
  python scripts/test_judge.py
  ```
  The console shows info/debug logs and where the file logs are written — the fastest way to confirm requests are hitting **your** endpoint.

---

## 5. Task-by-task implementation

### a-25-1 · Pin a Judge0 version + docker-compose

**DoD:** `docker-compose up` works on target hardware; the server responds.

- Clone the [Judge0 repo](https://github.com/judge0/judge0), **checkout a release tag** (latest stable `v1.x`), do **not** run `master`/`:latest` for something executing untrusted code. Review the release notes and any sandbox-escape-class **CVEs** before committing to it.
- Judge0's docker-compose starts its **own Postgres + Redis** — fully separate from BYTEARENA's SQLite. Docker becomes a stated prerequisite on the contest host.
- The CE REST API listens on **port 2358**. On the host itself: `http://localhost:2358`. From other LAN machines: `http://<host-ip>:2358`.
- The two settings that replace the old "low-priv user + iptables" plan:
  - `ENABLE_NETWORK=false` (default) — the containment property.
  - Server limit caps — Judge0 **clamps** submission limits to its configured maxima, so set them high enough to cover your problem configs.

Confirm against the live server early with `client.get_config_info()` — the returned `Config` model ([Types module](https://python.docs.judge0.com/master/api/types.html)) exposes exactly these fields:

| `Config` field | What to confirm |
|---|---|
| `enable_network` | `False` (network blocked) |
| `maintenance_mode` | `False` |
| `max_cpu_time_limit` / `max_wall_time_limit` | ≥ your largest `problems.time_limit_ms` in seconds |
| `max_memory_limit` | ≥ your largest `problems.mem_limit_mb` × 1024 (KB) |
| `max_submission_batch_size` | only relevant if you ever use `/submissions/batch` |
| `max_queue_size` | sanity check under load (C's concern, c-4-1) |

### a-25-3 · Language translation table

**DoD:** BYTEARENA keys `python`/`cpp` resolve to Judge0 language IDs via one mapping — no inline IDs in `interface.py`.

Judge0's numeric IDs drift between releases and don't correspond 1:1 to BYTEARENA's keys. The SDK's `LanguageAlias` enum ([Types](https://python.docs.judge0.com/master/api/types.html)) is version-agnostic: it always resolves to the **latest version of that language on the connected client**. Resolve once and cache:

```python
LANGUAGE_ALIASES = {
    "python": judge0.LanguageAlias.PYTHON3,
    "cpp":    judge0.LanguageAlias.CPP_GCC,
}

_language_ids = {}

def _language_id(lang: str) -> int:
    if lang not in LANGUAGE_ALIASES:
        raise UnsupportedLanguageError(f"unsupported language: {lang}")
    if lang not in _language_ids:
        client = _judge0_client()
        alias = LANGUAGE_ALIASES[lang]
        if not client.is_language_supported(alias):
            raise UnsupportedLanguageError(f"language {lang} not supported by the Judge0 server")
        _language_ids[lang] = client.get_language_id(alias)
    return _language_ids[lang]
```

If you'd rather use raw numeric IDs, build the table **once** from `client.get_languages()` and match on `name` (e.g. `"Python 3"`, `"C++ (GCC …)"`), never on hardcoded ids — they change between releases. Either way, the mapping lives in exactly one place. (`LanguageAlias.PYTHON3` = 56, `LanguageAlias.CPP_GCC` = 12 in the SDK enum; the *server-side* numeric ids those resolve to are typically 71 and 54 on current CE, but never rely on that.)

### a-25-4 · Judge0 Status → BYTEARENA Verdict mapping

**DoD:** a named function with documented reasoning, not an inline conditional.

The SDK `Status` enum ([Types module](https://python.docs.judge0.com/master/api/types.html)) has 14 values. BYTEARENA's verdict set is flat (`AC, WA, TLE, MLE, RE, CE`) plus `JUDGE_ERROR` for infra failures. Decide deliberately:

| Judge0 Status | SDK enum | BYTEARENA mapping | Reasoning |
|---|---|---|---|
| 1 In Queue | `Status.IN_QUEUE` | — | never terminal |
| 2 Processing | `Status.PROCESSING` | — | never terminal |
| 3 Accepted | `Status.ACCEPTED` | `"ok"` | stdout still goes through `compare.py` |
| 4 Wrong Answer | `Status.WRONG_ANSWER` | `"ok"` | defensive only — we never set `expected_output`, so Judge0 can't produce this |
| 5 Time Limit Exceeded | `Status.TIME_LIMIT_EXCEEDED` | `"timeout"` | → `TLE` in `worker._classify` |
| 6 Compilation Error | `Status.COMPILATION_ERROR` | `CompileError` in `compile()`; `"error"` defensively in `run()` | syntax check lives in the compile step |
| 7 Runtime Error (SIGSEGV) | `Status.RUNTIME_ERROR_SIGSEGV` | `"error"` → `RE` | |
| 8 Runtime Error (SIGXFSZ) | `Status.RUNTIME_ERROR_SIGXFSZ` | `"error"` → `RE` | output-too-big kills |
| 9 Runtime Error (SIGFPE) | `Status.RUNTIME_ERROR_SIGFPE` | `"error"` → `RE` | |
| 10 Runtime Error (SIGABRT) | `Status.RUNTIME_ERROR_SIGABRT` | `"error"` → `RE` | |
| 11 Runtime Error (NZEC) | `Status.RUNTIME_ERROR_NZEC` | `"error"` → `RE` | non-zero exit → RE, same as old `exit_status != 0` |
| 12 Runtime Error (Other) | `Status.RUNTIME_ERROR_OTHER` | `"error"` → `RE` | **but** see §6 — if `memory ≥ limit`, `_classify` turns this into MLE first |
| 13 Internal Error | `Status.INTERNAL_ERROR` | **raise** → `JUDGE_ERROR` | judge infrastructure, not the user's program |
| 14 Exec Format Error | `Status.EXEC_FORMAT_ERROR` | **raise** → `JUDGE_ERROR` | same |

All `RUNTIME_ERROR_*` subtypes collapse to BYTEARENA's flat `RE` — that mirrors the old behavior where any non-zero exit was `RE`. Statuses 13/14 raise so `worker.process_submission`'s catch path marks the row `JUDGE_ERROR` (the old code did the same for `sandbox.SandboxError`).

> Do **not** confuse this `Status` enum with BYTEARENA's `SubmissionStatus` (QUEUED/COMPILING/…). Different layers.

### a-25-5 · Unit conversion

**DoD:** confirmed explicitly, not assumed.

| BYTEARENA | Judge0 | Conversion |
|---|---|---|
| `limits.time_limit_ms` (problem `time_limit_ms`) | `cpu_time_limit` | `ms / 1000.0` seconds |
| `limits.mem_limit_mb` (problem `mem_limit_mb`) | `memory_limit` | `mb * 1024` KB |
| `sub.time` (CPU **seconds**, float) | `runtime_ms` | `int(round(sub.time * 1000))` |
| `sub.memory` (**KB**, int) | `mem_kb` | `int(sub.memory or 0)` |
| `sub.exit_code` (`None` if signal-killed) | `exit_status` | `exit_code if exit_code is not None else -1` |

**Worked example:** problem `time_limit_ms=1000`, `mem_limit_mb=256` → submit with `cpu_time_limit=1.0`, `memory_limit=262144`. A program that ran `1.5` CPU seconds and used `262144` KB reports back as `runtime_ms=1500`, `mem_kb=262144` → `_classify` sees `mem_kb ≥ 262144` → **MLE** (with the §6 tweak).

Use `time` (CPU), **not** `wall_time`, for `runtime_ms`.

### a-25-2 · Rewrite `compile()` / `run()`

**DoD:** same signatures and dataclasses; `worker.py` unchanged except the §6 tweak.

**Design decision (the important one):** Judge0 has no compile-only endpoint, but `worker.py` *requires* the CE verdict to come out of `compile()` — its `_classify` only knows `TLE/MLE/RE/AC/WA`, never `CE`. So:

- **`compile()`** runs **one submission** with a tiny CPU/memory box and empty stdin. Only `Status.COMPILATION_ERROR` is a `CompileError`; a TLE/RE/MLE from this check just means "the source parsed fine" — the real `run()` step measures those with the problem's actual limits.
- **`run()`** runs **one submission per testcase** with `stdin=input_data` and the problem's real limits, then maps the result.

The full replacement for `judge/interface.py`:

```python
import os
from dataclasses import dataclass

import judge0
from judge0.clients import Client
from judge0.retry import MaxWaitTime

from .languages import LANGUAGES


class UnsupportedLanguageError(Exception):
    pass


@dataclass
class Limits:
    time_limit_ms: int
    mem_limit_mb: int


@dataclass
class CompiledArtifact:
    lang: str
    path: str
    workdir: str


@dataclass
class CompileError:
    message: str
    stderr: str = ""


@dataclass
class RunResult:
    status: str            # "ok" | "timeout" | "error"
    stdout: str
    stderr: str
    runtime_ms: int
    mem_kb: int
    exit_status: int


# ---------------------------------------------------------------------------
# Judge0 client + language table (a-25-1, a-25-3)
# ---------------------------------------------------------------------------

JUDGE0_ENDPOINT = os.environ.get("JUDGE0_ENDPOINT", "http://localhost:2358")

LANGUAGE_ALIASES = {
    "python": judge0.LanguageAlias.PYTHON3,
    "cpp":    judge0.LanguageAlias.CPP_GCC,
}

_client = None
_language_ids = {}

COMPILE_CHECK_TIMEOUT_S = 2.0      # cheap syntax-check box
COMPILE_CHECK_MEM_KB = 64 * 1024   # 64 MB is plenty for a syntax check


def _judge0_client() -> Client:
    global _client
    if _client is None:
        _client = Client(endpoint=JUDGE0_ENDPOINT, retry_strategy=MaxWaitTime(max_wait_time_sec=120))
    return _client


def _language_id(lang: str) -> int:
    if lang not in LANGUAGE_ALIASES:
        raise UnsupportedLanguageError(f"unsupported language: {lang}")
    if lang not in _language_ids:
        client = _judge0_client()
        alias = LANGUAGE_ALIASES[lang]
        if not client.is_language_supported(alias):
            raise UnsupportedLanguageError(f"language {lang} not supported by the Judge0 server")
        _language_ids[lang] = client.get_language_id(alias)
    return _language_ids[lang]


def _submit(source: str, lang: str, stdin: str, time_limit_s: float, memory_limit_kb: int):
    sub = judge0.Submission(
        source_code=source,
        language=_language_id(lang),
        stdin=stdin,
        cpu_time_limit=time_limit_s,
        memory_limit=memory_limit_kb,
    )
    return judge0.execute(client=_judge0_client(), submissions=sub)


def compile(source_path: str, lang: str, compile_timeout_ms: int = 15000) -> "CompiledArtifact | CompileError":
    if lang not in LANGUAGES:
        return CompileError(f"unsupported language: {lang}")

    with open(source_path, "r", encoding="utf-8", errors="replace") as f:
        source = f.read()

    # Only status 6 (COMPILATION_ERROR) is a compile failure. TLE/RE/MLE from
    # this tiny box simply mean "it parsed fine"; run() re-measures with the
    # problem's real limits.
    sub = _submit(source, lang, stdin="", time_limit_s=COMPILE_CHECK_TIMEOUT_S, memory_limit_kb=COMPILE_CHECK_MEM_KB)

    if not sub.is_done():
        raise RuntimeError(f"Judge0 submission {sub.token} did not finish within the retry budget")

    if sub.status == judge0.Status.COMPILATION_ERROR:
        stderr = sub.stderr or sub.compile_output or ""
        message = sub.message or f"compilation error (status {sub.status.value})"
        return CompileError(message, stderr)

    return CompiledArtifact(lang=lang, path=source_path, workdir=os.path.dirname(source_path))


def run(artifact: CompiledArtifact, input_data: str, limits: Limits) -> RunResult:
    with open(artifact.path, "r", encoding="utf-8", errors="replace") as f:
        source = f.read()

    sub = _submit(
        source,
        artifact.lang,
        stdin=input_data,
        time_limit_s=limits.time_limit_ms / 1000.0,
        memory_limit_kb=limits.mem_limit_mb * 1024,
    )
    return _map_result(sub)


def _map_result(sub) -> RunResult:
    """Judge0 Status -> RunResult.status; seconds/KB -> ms/KB.

    Full reasoning in JUDGE0_GUIDE.md §5 (a-25-4/a-25-5). Statuses 13/14 are
    judge-infrastructure failures and raise so the worker marks JUDGE_ERROR.
    """
    if not sub.is_done():
        raise RuntimeError(f"Judge0 submission {sub.token} did not finish within the retry budget")

    status = sub.status
    if status in (judge0.Status.ACCEPTED, judge0.Status.WRONG_ANSWER):
        run_status = "ok"
    elif status == judge0.Status.TIME_LIMIT_EXCEEDED:
        run_status = "timeout"
    elif status in (judge0.Status.INTERNAL_ERROR, judge0.Status.EXEC_FORMAT_ERROR):
        raise RuntimeError(f"Judge0 failed to execute submission: status={status.value} message={sub.message}")
    else:
        run_status = "error"

    return RunResult(
        status=run_status,
        stdout=sub.stdout or "",
        stderr=sub.stderr or "",
        runtime_ms=int(round(sub.time * 1000)) if sub.time is not None else 0,
        mem_kb=int(sub.memory or 0),
        exit_status=sub.exit_code if sub.exit_code is not None else -1,
    )


def source_name(lang: str) -> str:
    return LANGUAGES[lang]["source_name"]
```

Notes:

- The old imports (`sandbox`, `format_cmd`, `run_env_for`, `binary_name_for`, `binary_path`) go away; `worker.py` only calls `interface.source_name`, `interface.compile`, `interface.run`, `interface.Limits` and the dataclasses — all preserved. (Dataclass signatures match the [Submission module](https://python.docs.judge0.com/master/api/submission.html) API shape; the SDK calls are documented in [API module](https://python.docs.judge0.com/master/api/api.html).)
- `CompiledArtifact.path` now points at the **source file** (Judge0 recompiles per submission; its compile cache makes the per-testcase submissions cheap). `workdir` is kept for shape compatibility.
- If `execute` ever returns while `is_done()` is still `False` (retry budget exhausted), we raise → `JUDGE_ERROR` row rather than hang the worker.

### a-25-6 · The 11-case regression suite

**DoD:** `python scripts/test_judge.py` passes **11/11** with **zero changes to the test file**. See §7 for the case-by-case walkthrough.

### a-25-7 · `sandbox.py` decision

**Recommended:** keep the old backend as an opt-in fallback behind a `JUDGE_BACKEND=judge0|local` selector, and record the decision in a comment at the top of `sandbox.py`. Rationale: the interface contract makes the swap a one-liner, dev machines without Docker still get a working judge, and it gives you a bisection tool if a verdict ever differs between backends. If you'd rather delete it, also fine — the half-orphaned state is the only unacceptable outcome.

### a-25-8 · Stale-claim reaper

**DoD:** a killed worker self-heals — its in-flight row returns to the queue and gets judged by the next worker.

This protects BYTEARENA's own `submissions` table (a crash between the atomic `claim_next` UPDATE and Judge0's response), independent of Judge0's internal queue.

`Submission` has **no `updated_at` column** (`server/models.py:127-145`), so compute the stale window from `submitted_at` + the problem's worst-case judging time (compile-check 2 s, then `time_limit_ms` per testcase, plus one extra testcase for the SKIPPED loop and a grace buffer):

```python
# judge/reaper.py — task a-25-8
from datetime import datetime, timedelta

from sqlalchemy import text

from server.models import SubmissionStatus, Verdict  # enum .name gotcha — see below

STALE_GRACE_S = 15.0
COMPILE_CHECK_BUDGET_MS = 2000


def reap_stale(db, now=None):
    rows = db.execute(
        text(
            "SELECT s.id, s.status, s.submitted_at, p.time_limit_ms, "
            "       (SELECT COUNT(*) FROM testcases t WHERE t.problem_id = s.problem_id) AS n_tc "
            "FROM submissions s JOIN problems p ON p.id = s.problem_id "
            "WHERE s.status IN (:compiling, :running)"
        ),
        {"compiling": SubmissionStatus.COMPILING.name, "running": SubmissionStatus.RUNNING.name},
    ).fetchall()

    now = now or datetime.utcnow()
    for row in rows:
        worst_ms = COMPILE_CHECK_BUDGET_MS + row.time_limit_ms * (row.n_tc + 1)
        deadline = row.submitted_at + timedelta(milliseconds=worst_ms) + timedelta(seconds=STALE_GRACE_S)
        if now > deadline:
            # WHERE status = :status keeps this race-safe with claim_next.
            db.execute(
                text(
                    "UPDATE submissions SET status = :queued, verdict = :pending "
                    "WHERE id = :id AND status = :old_status"
                ),
                {
                    "queued": SubmissionStatus.QUEUED.name,
                    "pending": Verdict.PENDING.name,
                    "id": row.id,
                    "old_status": row.status,
                },
            )
    db.commit()
```

Wire it into `run_worker` so it runs periodically (e.g. throttled to once per poll cycle) in `judge/worker.py`. **Remember the Sprint-0 gotcha:** SQLAlchemy's `SAEnum` stores the enum **member name** in the DB, so every raw-SQL value above uses `.name` — exactly how `claim_next` (`judge/worker.py:38-51`) already does it.

---

## 6. The one deliberate change to `worker.py`

In `judge/worker.py`, `_classify` (`judge/worker.py:138-148`):

```python
if run_res.mem_kb and run_res.mem_kb > mem_limit_kb:
```

becomes:

```python
# Judge0 kills the process AT the limit and reports memory == limit, so a
# strict ">" would misreport OOM kills as RE. (JUDGE0_GUIDE.md §6)
if run_res.mem_kb and run_res.mem_kb >= mem_limit_kb:
```

**Why it's required:** the old local sandbox measured usage slightly *above* the limit before killing, so `>` fired. Judge0's `isolate` kills the box when it hits the limit and reports `memory` at (or just under) the limit, so `>` misses and the OOM kill falls through to status-12 → `RE`. This is the only change `worker.py` needs, and it's why the MLE cases depend on `RunResult.mem_kb` being populated from Judge0's `memory` field. Add the comment verbatim; a strict reading of "don't touch worker.py" yields false `RE` verdicts on the two MLE cases.

---

## 7. The 11-case suite, case by case

`scripts/test_judge.py` drives the worker through the DB exactly like production. If the interface really stayed stable, every case lands on the same verdict with **zero changes to the test file**:

| # | Case | Source | Judge0 behavior | BYTEARENA sees |
|---|---|---|---|---|
| 1 | PY AC | `print(a + b)` | compile-check ok → run ACCEPTED, stdout `3` | `"ok"` → `compare` AC |
| 2 | CPP AC | `cout << a + b` | compile-check ok → run ACCEPTED | AC |
| 3 | PY WA | `print(a + b + 1)` | run ACCEPTED, stdout `4` | `"ok"` → `compare` fails → **WA** |
| 4 | PY TLE | `while True: pass` | compile-check box TLEs at 2 s (returns artifact) → run hits `cpu_time_limit` → status 5 | `"timeout"` → **TLE** |
| 5 | CPP TLE | `for(;;);` | same | **TLE** |
| 6 | PY CE | `def f(:` | compile-check submission → status 6, `compile_output` has the SyntaxError | `CompileError` → **CE** |
| 7 | CPP CE | `int main( {` | same | **CE** |
| 8 | PY RE | `sys.exit(3)` | compile-check ok → run exits 3 → status 11 NZEC | `"error"` → **RE** |
| 9 | CPP RE | `return 3;` | same | **RE** |
| 10 | PY MLE | `bytearray(300 MB)` | run OOM-killed at limit → status 12, `memory ≈ limit` | §6 tweak → **MLE** |
| 11 | CPP MLE | `vector<char>(300 MB)` | same | **MLE** |

The two TLE cases are the subtle ones: they **also TLE in the compile-check box** — that must *not* be treated as a compile failure (only status 6 is), which is exactly the `compile()` design in §5 a-25-2.

---

## 8. Verification checklist (the Sprint 2.5 gate)

Run in order on **target hardware**, not localhost.

- [ ] `docker-compose up` (pinned tag) healthy; `client.get_about()` responds; `client.get_config_info().maintenance_mode` is `False`.
- [ ] `client.get_config_info()` shows `enable_network`/`allow_enable_network` **False**.
- [ ] Problem time/memory limits fit within `max_cpu_time_limit` / `max_memory_limit` from `get_config_info()`.
- [ ] `python scripts/test_judge.py` → **11/11 passed** (unchanged test file).
- [ ] **Network blocked:** submit a probe that tries to reach the internet and observe it fail:
      ```python
      import urllib.request
      try:
          urllib.request.urlopen("http://example.com", timeout=5)
          print("NETWORK_OK")
      except Exception as e:
          print("NETWORK_BLOCKED", type(e).__name__)
      ```
      Expect `NETWORK_BLOCKED` (EPERM or timeout), never `NETWORK_OK`.
- [ ] **Reaper self-heal:** with a worker running, submit, kill the worker mid-judging, wait past the stale window, confirm the row returns to `queued` and the next worker judges it to a terminal verdict.
- [ ] `JUDGE0_ENABLE_LOGGING=1` shows requests going to **your** endpoint, not the preview client.
- [ ] The reaper's `WHERE status =` guard never races `claim_next` under a 2-worker smoke test.

---

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `PreviewClientLimitError` | Worker isn't pointed at your instance; implicit resolution fell back to the preview client | Set `JUDGE0_ENDPOINT` (used by `_judge0_client()`) or the SDK's `JUDGE0_CE_ENDPOINT`/`JUDGE0_CE_AUTH_HEADERS` env vars; confirm with logging on |
| `ClientResolutionError` | Env-var-based implicit resolution misconfigured | Construct the `Client` explicitly in `_judge0_client()` (the guide's code does) |
| Submission never reaches terminal; `MaxWaitTime` exhausted | Wrong endpoint (e.g. `http://localhost:2358` from another machine), server down, or limits exceed server caps | Check `client.get_about()`/`get_config_info()`; use `http://<host-ip>:2358` off-host |
| MLE cases report `RE` | The §6 `>=` change isn't applied | Apply it (see §6) |
| CE cases report `RE` | `compile()` isn't mapping status 6, or `_map_result` is reached with a CE status | `compile()` must check `Status.COMPILATION_ERROR` before returning an artifact |
| `runtime_ms` implausibly large | Using `sub.wall_time` instead of `sub.time` | Use `sub.time` (CPU seconds → ms) |
| All submissions `INTERNAL_ERROR` | Server misconfigured or in maintenance mode | Check `get_config_info().maintenance_mode`; review docker-compose logs |
| Verdicts differ between backends | Real regression vs. comparison difference | Flip `JUDGE_BACKEND=local` to bisect against `sandbox.py`; confirm `expected_output` is unset |
| Program's network call prints success | `ENABLE_NETWORK=true` on the server | Set `ENABLE_NETWORK=false` in the Judge0 server config and restart |

Enable logging ([Logging page](https://python.docs.judge0.com/master/in_depth/logging.html)) with `JUDGE0_ENABLE_LOGGING=1` before debugging any of the above.

---

## 10. Suggested implementation order

1. Stand up pinned Judge0 CE (§5 a-25-1); verify `get_about()` + `get_config_info()`.
2. Write the new `judge/interface.py` (§5 a-25-2/3/4/5).
3. Apply the `_classify` `>=` tweak (§6).
4. Run `python scripts/test_judge.py` → must pass 11/11 (§7).
5. Add the reaper (§5 a-25-8) and run the killed-worker self-heal test.
6. Run the network-blocked probe (§8).
7. Decide `sandbox.py`'s fate and record it in a comment (§5 a-25-7).
8. Confirm the gate checklist (§8) on the contest host, with the worker running the same way it will on contest day.

---

## 11. Gotchas & decisions log

1. **Never set `expected_output`.** Judge0's built-in comparison is stricter than BYTEARENA's lenient `judge/compare.py` (trailing-whitespace / trailing-newline tolerant). If you set it, Judge0's verdict becomes the source of truth and you get false WAs. Leave it unset; `compare.py` stays the correctness check.
2. **CE must come from `compile()`.** `worker._classify` can only produce `TLE/MLE/RE/AC/WA`. The syntax-check submission in `compile()` is what keeps `CE` landing on `SubmissionStatus.COMPILE_ERROR` with `Verdict.CE`.
3. **The compile-check box is deliberately tiny** (2 s / 64 MB). A TLE or RE there must never be treated as a compile failure — only status 6 is. This is why the syntax check costs ~1 extra Judge0 run per submission; acceptable at MVP scale (optional future optimization: reuse the first testcase's run to detect CE, which requires touching `worker.py`).
4. **`Status` ≠ `SubmissionStatus`.** The SDK's 14-value `Status` enum is the Judge0 verdict; BYTEARENA's `SubmissionStatus` is its own pipeline state. Keep the mapping in the named function (§5 a-25-4).
5. **No implicit clients.** Configure `JUDGE0_ENDPOINT` so failures are loud. The preview-client fallback is rate-limited and wrong to ship against.
6. **MLE needs the `>=` tweak** (§6). Without it, the two MLE cases regress to `RE`.
7. **Batch/`additional_files` are deferred.** `create_submissions` / `create_submissions_from_test_cases` and the `Filesystem`/`File` module ([Filesystem module](https://python.docs.judge0.com/master/api/filesystem.html), for multi-file programs via `LanguageAlias.MULTI_FILE`) are Phase-2 scope. MVP is single-file `python`/`cpp`.
8. **Server clamps limits.** Judge0 enforces its configured maxima; if a problem's limits exceed them, expect clamped or rejected submissions. Check `get_config_info()` early.
9. **The enum `.name` gotcha applies** to the reaper's raw SQL (§5 a-25-8), same as in `claim_next`.
10. **Judge0 owns its own DB/Redis.** Never let BYTEARENA code touch Judge0's Postgres/Redis; the only interface is the REST API on port 2358.
11. **`CE` is ambiguous** (Compilation Error vs Community Edition) — see §1.

---

## 12. References

Primary sources (also linked inline above):

- Judge0 Python SDK — Home / Getting Started: https://python.docs.judge0.com/master/index.html
- SDK — API module (`execute`, `run`, `wait`, `get_submissions`): https://python.docs.judge0.com/master/api/api.html
- SDK — Clients module (`Client`, `create_submission`, `get_config_info`, …): https://python.docs.judge0.com/master/api/clients.html
- SDK — Submission module (constructor params, `is_done`): https://python.docs.judge0.com/master/api/submission.html
- SDK — Types module (`Status`, `LanguageAlias`, `Config`, `TestCase`): https://python.docs.judge0.com/master/api/types.html
- SDK — Retry module (`MaxRetries`, `MaxWaitTime`, `RegularPeriodRetry`): https://python.docs.judge0.com/master/api/retry.html
- SDK — Errors module (`ClientResolutionError`, `PreviewClientLimitError`): https://python.docs.judge0.com/master/api/errors.html
- SDK — Filesystem module (`File`, `Filesystem`, multi-file): https://python.docs.judge0.com/master/api/filesystem.html
- SDK — In depth: Client Resolution: https://python.docs.judge0.com/master/in_depth/client_resolution.html
- SDK — In depth: Logging: https://python.docs.judge0.com/master/in_depth/logging.html
- Judge0 platform docs (self-hosting, docker-compose, server config env vars): https://docs.judge0.com/
- Judge0 source (pin a release tag): https://github.com/judge0/judge0
- SDK repo + examples: https://github.com/judge0/judge0-python
- Judge0 IDE (manual probes): https://ide.judge0.com/
- Sprint 2.5 assignment + gate: `bytearena_mvp_assignments.html` (Person A → Sprint 2.5)
- Existing code: `judge/interface.py`, `judge/worker.py`, `judge/languages.py`, `judge/compare.py`, `scripts/test_judge.py`, `server/models.py`
