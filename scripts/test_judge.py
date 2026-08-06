"""Sprint 2 DoD check: submit known-correct / known-infinite-loop / known-bad
solutions straight into the DB (bypassing the API, which doesn't exist yet)
and assert the judge worker returns the expected verdict for each.

Usage:  python scripts/test_judge.py
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from sqlalchemy.orm import Session  # noqa: E402

from server.database import engine  # noqa: E402
from server.models import Contest, Participant, Problem, Submission, SubmissionStatus  # noqa: E402
from judge.worker import claim_next, process_submission  # noqa: E402
from judge.languages import LANGUAGES  # noqa: E402

CONTEST_ID = 1
PROBLEM_CODE = "A"
TEST_USERNAME = "judge_test"

PY_SUM = 'a, b = map(int, input().split())\nprint(a + b)\n'
CPP_SUM = "#include <iostream>\nint main(){ long long a,b; std::cin>>a>>b; std::cout<<a+b<<std::endl; return 0; }\n"

CASES = [
    # (label, lang, source, expected_verdict)
    ("PY AC",   "python", PY_SUM, "AC"),
    ("CPP AC",  "cpp",    CPP_SUM, "AC"),
    ("PY WA",   "python", 'a, b = map(int, input().split())\nprint(a + b + 1)\n', "WA"),
    ("PY TLE",  "python", "while True:\n    pass\n", "TLE"),
    ("CPP TLE", "cpp",    "int main(){ for(;;); return 0; }\n", "TLE"),
    ("PY CE",   "python", "def f(:\n    pass\n", "CE"),
    ("CPP CE",  "cpp",    "int main( {\n", "CE"),
    ("PY RE",   "python", "import sys\nsys.exit(3)\n", "RE"),
    ("CPP RE",  "cpp",    "int main(){ return 3; }\n", "RE"),
    ("PY MLE",  "python", "x = bytearray(300 * 1024 * 1024)\nx[0] = 1\nprint(len(x))\n", "MLE"),
    ("CPP MLE", "cpp",    "#include <vector>\n#include <cstdio>\nint main(){ size_t n = 300ULL*1024*1024; std::vector<char> v(n, 1); std::printf(\"%d\\n\", (int)v[v.size()-1]); return 0; }\n", "MLE"),
]


def ensure_participant(db, contest_id):
    participant = db.query(Participant).filter_by(contest_id=contest_id, username=TEST_USERNAME).first()
    if participant:
        return participant
    participant = Participant(
        contest_id=contest_id,
        username=TEST_USERNAME,
        password_hash="not-a-real-hash",
        team_name="Judge Test",
    )
    db.add(participant)
    db.commit()
    db.refresh(participant)
    return participant


def submit(db, participant, problem, lang, source, label):
    ext = LANGUAGES[lang]["extension"]
    dest_dir = os.path.join(REPO_ROOT, "Contest", "Submissions", participant.username, problem.code)
    os.makedirs(dest_dir, exist_ok=True)
    source_path = os.path.join(dest_dir, f"{label.replace(' ', '_').replace('/', '_')}.{ext}")
    with open(source_path, "w", encoding="utf-8") as f:
        f.write(source)

    submission = Submission(
        participant_id=participant.id,
        problem_id=problem.id,
        lang=lang,
        source_path=source_path,
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)
    return submission.id


def main():
    with Session(engine) as db:
        contest = db.get(Contest, CONTEST_ID)
        if not contest:
            print(f"FATAL: contest {CONTEST_ID} not found. Run Sprint 1 setup first.")
            sys.exit(1)
        problem = db.query(Problem).filter_by(contest_id=CONTEST_ID, code=PROBLEM_CODE).first()
        if not problem:
            print(f"FATAL: problem {PROBLEM_CODE} not found in contest {CONTEST_ID}.")
            sys.exit(1)

        participant = ensure_participant(db, CONTEST_ID)

        # Clean up any leftover queued/running submissions from prior runs.
        db.query(Submission).filter(
            Submission.participant_id == participant.id,
            Submission.status.in_([SubmissionStatus.QUEUED, SubmissionStatus.COMPILING, SubmissionStatus.RUNNING]),
        ).delete(synchronize_session=False)
        db.commit()

        results = []
        for label, lang, source, expected in CASES:
            sub_id = submit(db, participant, problem, lang, source, label)
            claimed = claim_next(db)
            assert claimed == sub_id, f"worker claimed {claimed}, expected {sub_id}"
            process_submission(db, sub_id)
            db.expire_all()
            sub = db.get(Submission, sub_id)
            ok = sub.verdict.value == expected
            results.append(ok)
            print(
                f"{'PASS' if ok else 'FAIL'}  {label:8s}  lang={lang:6s}  "
                f"expected={expected:4s} got={sub.verdict.value:4s}  "
                f"runtime={sub.runtime_ms}ms mem={sub.mem_kb}KB"
            )

    failed = results.count(False)
    print(f"\n{len(results) - failed}/{len(results)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
