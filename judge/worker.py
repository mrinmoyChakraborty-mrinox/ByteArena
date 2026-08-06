"""DB-backed judge worker.

Polls the `submissions` table (status column) for queued submissions, claims
one, compiles it, runs it against every testcase of its problem under the
sandbox, and writes per-testcase verdicts plus the aggregate verdict.

Queue is the DB itself — no Redis. Scaling to N workers is just running N
worker processes; the claim UPDATE is atomic, so no two workers can grab the
same submission.
"""

import os
import shutil
import sys
import tempfile
import time
import traceback

from sqlalchemy import text
from sqlalchemy.orm import Session

from . import interface
from .compare import compare
from .reaper import reap_stale

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from server.database import engine  # noqa: E402
from server.models import Problem, Submission, Testcase, TestcaseStatus, Verdict, SubmissionStatus  # noqa: E402

RUNS_DIR = os.path.join(REPO_ROOT, "Contest", "Runs")


class JudgeError(Exception):
    pass


def claim_next(db: Session):
    """Atomically claim the oldest queued submission; return its id or None."""
    # NOTE: SQLAlchemy's SAEnum stores the enum member *name*, not the value.
    row = db.execute(
        text(
            "UPDATE submissions SET status = :compiling "
            "WHERE id = (SELECT id FROM submissions WHERE status = :queued "
            "ORDER BY submitted_at, id LIMIT 1) "
            "RETURNING id"
        ),
        {"compiling": SubmissionStatus.COMPILING.name, "queued": SubmissionStatus.QUEUED.name},
    ).fetchone()
    db.commit()
    return int(row[0]) if row else None


def _scratch_dir(submission_id: int) -> str:
    os.makedirs(RUNS_DIR, exist_ok=True)
    return tempfile.mkdtemp(prefix=f"run_{submission_id}_", dir=RUNS_DIR)


def _read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def process_submission(db: Session, submission_id: int):
    submission = db.get(Submission, submission_id)
    if not submission:
        raise JudgeError(f"submission {submission_id} not found")

    problem = db.get(Problem, submission.problem_id)
    if not problem:
        _fail(db, submission, "judge_error", "problem not found")
        return

    testcases = (
        db.query(Testcase)
        .filter(Testcase.problem_id == problem.id)
        .order_by(Testcase.id)
        .all()
    )

    scratch = _scratch_dir(submission_id)
    try:
        src_path = os.path.join(scratch, interface.source_name(submission.lang))
        shutil.copyfile(submission.source_path, src_path)

        submission.status = SubmissionStatus.RUNNING
        db.commit()

        result = interface.compile(src_path, submission.lang)
        if isinstance(result, interface.CompileError):
            _fail(db, submission, "compile_error", result.stderr or result.message)
            return

        artifact = result
        limits = interface.Limits(
            time_limit_ms=problem.time_limit_ms,
            mem_limit_mb=problem.mem_limit_mb,
        )

        final_verdict = Verdict.AC
        max_runtime_ms = 0
        max_mem_kb = 0
        found_failure = False

        for tc in testcases:
            if found_failure:
                _add_verdict(db, submission.id, tc.id, TestcaseStatus.SKIPPED)
                continue

            input_data = _read_file(tc.input_path)
            expected = _read_file(tc.output_path)

            run_res = interface.run(artifact, input_data, limits)

            max_runtime_ms = max(max_runtime_ms, run_res.runtime_ms)
            max_mem_kb = max(max_mem_kb, run_res.mem_kb)

            tc_status, tc_verdict = _classify(run_res, expected, limits)
            _add_verdict(db, submission.id, tc.id, tc_status, run_res.runtime_ms, run_res.mem_kb)

            if tc_verdict != Verdict.AC:
                final_verdict = tc_verdict
                found_failure = True

        submission.status = SubmissionStatus.JUDGED
        submission.verdict = final_verdict
        submission.runtime_ms = max_runtime_ms
        submission.mem_kb = max_mem_kb
        db.commit()

    except Exception as e:
        traceback.print_exc()
        _fail(db, submission, "judge_error", str(e))
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _classify(run_res: interface.RunResult, expected: str, limits: interface.Limits):
    mem_limit_kb = limits.mem_limit_mb * 1024
    if run_res.status == "timeout":
        return TestcaseStatus.TLE, Verdict.TLE
    # Judge0 kills the process AT the limit and reports memory == limit, so a
    # strict ">" would misreport OOM kills as RE. (JUDGE0_GUIDE.md §6)
    if run_res.mem_kb and run_res.mem_kb >= mem_limit_kb:
        return TestcaseStatus.MLE, Verdict.MLE
    if run_res.status == "error":
        return TestcaseStatus.RE, Verdict.RE
    if compare(run_res.stdout, expected):
        return TestcaseStatus.AC, Verdict.AC
    return TestcaseStatus.WA, Verdict.WA


def _add_verdict(db: Session, submission_id: int, testcase_id: int, status, runtime_ms=None, mem_kb=None):
    db.execute(
        text(
            "INSERT INTO verdicts (submission_id, testcase_id, status, runtime_ms, mem_kb) "
            "VALUES (:sid, :tid, :st, :rt, :mem)"
        ),
        {
            "sid": submission_id,
            "tid": testcase_id,
            "st": status.name,
            "rt": runtime_ms,
            "mem": mem_kb,
        },
    )
    db.commit()


def _fail(db: Session, submission: Submission, status, detail: str):
    submission.status = SubmissionStatus(status)
    if status == "compile_error":
        submission.verdict = Verdict.CE
    db.commit()


def run_worker(once: bool = False, poll_interval: float = 1.0):
    while True:
        with Session(engine) as db:
            reap_stale(db)  # self-heal any stuck claims from a crashed worker
            submission_id = claim_next(db)
            if submission_id is not None:
                process_submission(db, submission_id)
                if once:
                    return
            else:
                if once:
                    return
                time.sleep(poll_interval)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="BYTEARENA judge worker")
    parser.add_argument("--once", action="store_true", help="process one submission and exit")
    parser.add_argument("--poll-interval", type=float, default=1.0)
    args = parser.parse_args()
    run_worker(once=args.once, poll_interval=args.poll_interval)
