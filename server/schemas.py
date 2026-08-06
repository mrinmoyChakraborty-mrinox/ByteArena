from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict


# === Contest ===
class ContestCreate(BaseModel):
    name: str
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    freeze_minutes: int = 0
    penalty_minutes: int = 20


class ContestUpdate(BaseModel):
    name: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    state: Optional[str] = None
    freeze_minutes: Optional[int] = None
    penalty_minutes: Optional[int] = None


class ContestOut(BaseModel):
    id: int
    name: str
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    state: str
    freeze_minutes: int
    penalty_minutes: int
    problem_count: int = 0

    model_config = ConfigDict(from_attributes=True)


# === Problem ===
class ProblemCreate(BaseModel):
    code: str
    title: str
    statement_md: str
    time_limit_ms: int = 1000
    mem_limit_mb: int = 256
    points: int = 100


class ProblemUpdate(BaseModel):
    title: Optional[str] = None
    statement_md: Optional[str] = None
    time_limit_ms: Optional[int] = None
    mem_limit_mb: Optional[int] = None
    points: Optional[int] = None


class ProblemOut(BaseModel):
    id: int
    contest_id: int
    code: str
    title: str
    statement_md: str
    time_limit_ms: int
    mem_limit_mb: int
    points: int
    testcase_count: int = 0

    model_config = ConfigDict(from_attributes=True)


# === Testcase ===
class TestcaseCreate(BaseModel):
    input_path: str
    output_path: str
    is_sample: bool = False
    points: int = 0
    checker_type: str = "exact_match"


class TestcaseOut(BaseModel):
    id: int
    problem_id: int
    input_path: str
    output_path: str
    is_sample: bool
    points: int
    checker_type: str

    model_config = ConfigDict(from_attributes=True)


# === Problem Loading from Files ===
class ProblemLoadResult(BaseModel):
    code: str
    title: str
    testcases_found: int
    errors: List[str] = []
