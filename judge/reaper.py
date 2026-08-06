"""Stale-claim reaper (Sprint 2.5, a-25-8).

Protects BYTEARENA's own `submissions` table, not Judge0's internal queue. If a
worker crashes between atomically claiming a row (`status -> COMPILING`/`RUNNING`)
and getting Judge0's response, that row is stuck forever with no self-healing.
This periodic sweep resets such rows back to `queued` so another worker picks
them up.

The window is computed from `submitted_at` (there is no `updated_at` column, see
`server/models.py`) plus the worst-case judging time for the submission's
problem: the compile-check box (~2 s), then `time_limit_ms` per testcase, one
extra testcase for the SKIPPED short-circuit loop, then a grace buffer.

Race-safety: the reset `UPDATE` guards on the exact current `status` (enum
`.name` — see the Sprint-0 gotcha), so it can never clobber a row that
`claim_next()` just claimed or that another worker is actively judging.
"""

from datetime import datetime, timedelta

from sqlalchemy import text

from server.models import SubmissionStatus, Verdict  # enum .name gotcha

STALE_GRACE_S = 15.0
COMPILE_CHECK_BUDGET_MS = 2000

_SUBMITTED_FMT = "%Y-%m-%d %H:%M:%S.%f"
_SUBMITTED_FMT_NO_US = "%Y-%m-%d %H:%M:%S"


def _as_datetime(value):
    """Coerce `submitted_at` from a raw-SQL row into a datetime.

    Raw `text()` queries are not type-annotated by SQLAlchemy, so SQLite hands
    the DateTime column back as a formatted string, unlike ORM access which
    returns a real datetime. Accept both.
    """
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        for fmt in (_SUBMITTED_FMT, _SUBMITTED_FMT_NO_US):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
    raise TypeError(f"unrecognised submitted_at value: {value!r}")


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
        deadline = _as_datetime(row.submitted_at) + timedelta(milliseconds=worst_ms) + timedelta(seconds=STALE_GRACE_S)
        if now > deadline:
            # WHERE status = :old_status keeps this race-safe with claim_next.
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