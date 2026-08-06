"""Judge backend interface (Sprint 2.5: Judge0 migration).

The public contract here is frozen — `CompiledArtifact`, `CompileError`,
`RunResult`, `Limits`, and the signatures of `compile()`, `run()`,
`source_name()` must not change, because `judge/worker.py` and
`scripts/test_judge.py` call into them and are expected to pass 11/11 with no
edits. Only the implementation underneath swapped from the local sandbox to a
self-hosted Judge0 CE instance (see JUDGE0_GUIDE.md).

Judge0 has no compile-only endpoint, so `compile()` runs one submission in a
tiny box (2 s / 64 MB) with empty stdin purely to detect status 6
(COMPILATION_ERROR). Everything else means "it parsed fine" and returns the
source as the compiled artifact. `run()` runs one submission per testcase with
the problem's real limits and the testcase's stdin. We deliberately never set
`expected_output`: Judge0's built-in comparison is stricter than BYTEARENA's
lenient `judge/compare.py` (trailing-whitespace/-newline tolerant), so
`compare.py` stays the source of truth.
"""

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
    status: str            # "ok" | "timeout" | "error" (error = non-zero exit)
    stdout: str
    stderr: str
    runtime_ms: int
    mem_kb: int
    exit_status: int


# ---------------------------------------------------------------------------
# Judge0 client + language table (a-25-1, a-25-3)
# ---------------------------------------------------------------------------

JUDGE0_ENDPOINT = os.environ.get("JUDGE0_ENDPOINT", "http://localhost:2358")

# BYTEARENA language key -> SDK alias. LanguageAlias is version-agnostic; it
# always resolves to the *latest* version of that language on the connected
# client, so numeric IDs never need to be hardcoded (a-25-3).
LANGUAGE_ALIASES = {
    "python": judge0.LanguageAlias.PYTHON3,
    "cpp": judge0.LanguageAlias.CPP_GCC,
}

_client = None
_language_ids = {}

# The compile-check box is deliberately tiny: a TLE/RE/MLE here just means "the
# source parsed fine" — only status 6 is a compile failure. Re-measure with the
# problem's real limits in run(). (JUDGE0_GUIDE.md §5 a-25-2, gotcha 3)
COMPILE_CHECK_TIMEOUT_S = 2.0
COMPILE_CHECK_MEM_KB = 64 * 1024   # 64 MB


def _judge0_client() -> Client:
    """Construct an explicit Client so failures are loud.

    Without this, the SDK auto-resolves and silently falls back to the
    rate-limited, cloud-hosted PreviewClient — never what you ship against.
    (JUDGE0_GUIDE.md §4.2, gotcha 5)
    """
    global _client
    if _client is None:
        _client = Client(
            endpoint=JUDGE0_ENDPOINT,
            retry_strategy=MaxWaitTime(max_wait_time_sec=120),
        )
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
    # problem's real limits. (JUDGE0_GUIDE.md §5 a-25-2)
    sub = _submit(
        source, lang, stdin="",
        time_limit_s=COMPILE_CHECK_TIMEOUT_S,
        memory_limit_kb=COMPILE_CHECK_MEM_KB,
    )

    if not sub.is_done():
        raise RuntimeError(f"Judge0 submission {sub.token} did not finish within the retry budget")

    if sub.status == judge0.Status.COMPILATION_ERROR:
        stderr = sub.stderr or sub.compile_output or ""
        message = sub.message or f"compilation error (status {sub.status.value})"
        return CompileError(message, stderr)

    # Judge0 recompiles per submission, so the artifact points back at the
    # source file. workdir kept for shape compatibility with worker.py.
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
    judge-infrastructure failures and raise so the worker marks the submission
    JUDGE_ERROR rather than blaming the participant.
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
        # All RUNTIME_ERROR_* subtypes collapse to "error" -> flat RE in the
        # worker, mirroring the old "any non-zero exit is RE" behavior.
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