import os
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import engine
from ..models import Contest, Problem, Testcase
from ..schemas import ProblemCreate, ProblemUpdate, ProblemOut, TestcaseOut, ProblemLoadResult
from ..problem_loader import load_problem_from_disk

router = APIRouter(tags=["problems"])


def get_db():
    with Session(engine) as session:
        yield session


# === Problems under a contest ===
@router.get("/api/contests/{contest_id}/problems", response_model=list[ProblemOut])
def list_problems(contest_id: int, db: Session = Depends(get_db)):
    contest = db.query(Contest).filter(Contest.id == contest_id).first()
    if not contest:
        raise HTTPException(status_code=404, detail="Contest not found")
    problems = db.query(Problem).filter(Problem.contest_id == contest_id).all()
    for p in problems:
        p.testcase_count = len(p.testcases)
    return problems


@router.get("/api/problems/{problem_id}", response_model=ProblemOut)
def get_problem(problem_id: int, db: Session = Depends(get_db)):
    problem = db.query(Problem).filter(Problem.id == problem_id).first()
    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found")
    problem.testcase_count = len(problem.testcases)
    return problem


@router.put("/api/problems/{problem_id}", response_model=ProblemOut)
def update_problem(problem_id: int, body: ProblemUpdate, db: Session = Depends(get_db)):
    problem = db.query(Problem).filter(Problem.id == problem_id).first()
    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found")
    update_data = body.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(problem, key, value)
    db.commit()
    db.refresh(problem)
    problem.testcase_count = len(problem.testcases)
    return problem


@router.delete("/api/problems/{problem_id}", status_code=204)
def delete_problem(problem_id: int, db: Session = Depends(get_db)):
    problem = db.query(Problem).filter(Problem.id == problem_id).first()
    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found")
    db.delete(problem)
    db.commit()


# === Manual problem creation ===
@router.post("/api/contests/{contest_id}/problems", response_model=ProblemOut, status_code=201)
def create_problem(contest_id: int, body: ProblemCreate, db: Session = Depends(get_db)):
    contest = db.query(Contest).filter(Contest.id == contest_id).first()
    if not contest:
        raise HTTPException(status_code=404, detail="Contest not found")
    existing = db.query(Problem).filter(Problem.contest_id == contest_id, Problem.code == body.code).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Problem with code '{body.code}' already exists in this contest")
    problem = Problem(
        contest_id=contest_id,
        code=body.code,
        title=body.title,
        statement_md=body.statement_md,
        time_limit_ms=body.time_limit_ms,
        mem_limit_mb=body.mem_limit_mb,
        points=body.points,
    )
    db.add(problem)
    db.commit()
    db.refresh(problem)
    problem.testcase_count = 0
    return problem


# === Load problem from disk ===
@router.post("/api/contests/{contest_id}/problems/load", response_model=ProblemLoadResult, status_code=201)
def load_problem(contest_id: int, code: str = Query(..., description="Problem code (directory name under Contest/Problems/)"), db: Session = Depends(get_db)):
    contest = db.query(Contest).filter(Contest.id == contest_id).first()
    if not contest:
        raise HTTPException(status_code=404, detail="Contest not found")
    existing = db.query(Problem).filter(Problem.contest_id == contest_id, Problem.code == code).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Problem with code '{code}' already loaded in this contest")
    try:
        problem, testcases = load_problem_from_disk(contest_id, code)
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    db.add(problem)
    db.flush()
    for tc in testcases:
        tc.problem_id = problem.id
        db.add(tc)
    db.commit()
    db.refresh(problem)
    errors = []
    if not testcases:
        errors.append(f"No testcases found for problem {code}")
    return ProblemLoadResult(
        code=problem.code,
        title=problem.title,
        testcases_found=len(testcases),
        errors=errors,
    )


# === Testcases ===
@router.get("/api/problems/{problem_id}/testcases", response_model=list[TestcaseOut])
def list_testcases(problem_id: int, db: Session = Depends(get_db)):
    problem = db.query(Problem).filter(Problem.id == problem_id).first()
    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found")
    return db.query(Testcase).filter(Testcase.problem_id == problem_id).all()


@router.post("/api/problems/{problem_id}/testcases", response_model=TestcaseOut, status_code=201)
def create_testcase(problem_id: int, body: TestcaseOut, db: Session = Depends(get_db)):
    problem = db.query(Problem).filter(Problem.id == problem_id).first()
    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found")
    tc = Testcase(
        problem_id=problem_id,
        input_path=body.input_path,
        output_path=body.output_path,
        is_sample=1 if body.is_sample else 0,
        points=body.points,
        checker_type=body.checker_type,
    )
    db.add(tc)
    db.commit()
    db.refresh(tc)
    return tc


@router.delete("/api/testcases/{testcase_id}", status_code=204)
def delete_testcase(testcase_id: int, db: Session = Depends(get_db)):
    tc = db.query(Testcase).filter(Testcase.id == testcase_id).first()
    if not tc:
        raise HTTPException(status_code=404, detail="Testcase not found")
    db.delete(tc)
    db.commit()
