import os
import json

from .models import Problem, Testcase
from .database import DB_PATH

PROBLEMS_DIR = os.path.join(os.path.dirname(os.path.dirname(DB_PATH)), "Problems")


def load_problem_from_disk(contest_id: int, code: str):
    problem_dir = os.path.join(PROBLEMS_DIR, code)
    if not os.path.isdir(problem_dir):
        raise FileNotFoundError(f"Problem directory not found: {code}")

    statement_path = os.path.join(problem_dir, "statement.md")
    if not os.path.isfile(statement_path):
        raise FileNotFoundError(f"statement.md not found for problem {code}")

    config_path = os.path.join(problem_dir, "config.json")
    config = {}
    if os.path.isfile(config_path):
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)

    with open(statement_path, encoding="utf-8") as f:
        statement_md = f.read()

    title = config.get("title", code)
    time_limit_ms = config.get("time_limit_ms", 1000)
    mem_limit_mb = config.get("mem_limit_mb", 256)
    points = config.get("points", 100)

    problem = Problem(
        contest_id=contest_id,
        code=code,
        title=title,
        statement_md=statement_md,
        time_limit_ms=time_limit_ms,
        mem_limit_mb=mem_limit_mb,
        points=points,
    )

    testcase_dir = os.path.join(problem_dir, "tests")
    testcases = []
    if os.path.isdir(testcase_dir):
        files = sorted(os.listdir(testcase_dir))
        inputs = {}
        outputs = {}
        for fname in files:
            fname_lower = fname.lower()
            if fname_lower.startswith("input") or fname_lower.startswith("in"):
                base = os.path.splitext(fname)[0]
                inputs[base] = os.path.join(testcase_dir, fname)
            elif fname_lower.startswith("output") or fname_lower.startswith("out") or fname_lower.startswith("ans"):
                base = os.path.splitext(fname)[0]
                outputs[base] = os.path.join(testcase_dir, fname)

        used_inputs = set()
        for base, in_path in sorted(inputs.items()):
            if base in used_inputs:
                continue

            out_key = (
                base.replace("input", "output")
                .replace("Input", "Output")
                .replace("in", "out")
                .replace("In", "Out")
            )

            out_path = (
                outputs.get(out_key)
                or outputs.get(base.replace("input", "output").replace("Input", "Output"))
                or outputs.get(base.replace("in", "out").replace("In", "Out"))
                or outputs.get(base.replace("in", "ans").replace("In", "Ans"))
            )

            if out_path and os.path.isfile(out_path):
                testcases.append(Testcase(
                    input_path=in_path,
                    output_path=out_path,
                    is_sample=0,
                    points=0,
                    checker_type="exact_match",
                ))
                used_inputs.add(base)

                out_base = os.path.splitext(os.path.basename(out_path))[0]
                outputs.pop(out_key, None)

    return problem, testcases
