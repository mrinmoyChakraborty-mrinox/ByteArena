from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Enum as SAEnum
from sqlalchemy.orm import relationship
import enum

from .database import Base


class ContestState(str, enum.Enum):
    SCHEDULED = "scheduled"
    RUNNING = "running"
    PAUSED = "paused"
    FROZEN = "frozen"
    ENDED = "ended"


class SubmissionStatus(str, enum.Enum):
    QUEUED = "queued"
    COMPILING = "compiling"
    RUNNING = "running"
    JUDGED = "judged"
    COMPILE_ERROR = "compile_error"
    JUDGE_ERROR = "judge_error"


class Verdict(str, enum.Enum):
    AC = "AC"
    WA = "WA"
    TLE = "TLE"
    MLE = "MLE"
    RE = "RE"
    CE = "CE"
    PENDING = "PENDING"


class TestcaseStatus(str, enum.Enum):
    AC = "AC"
    WA = "WA"
    TLE = "TLE"
    MLE = "MLE"
    RE = "RE"
    SKIPPED = "skipped"


class EventType(str, enum.Enum):
    HEARTBEAT = "heartbeat"
    TAB_SWITCH = "tab_switch"
    WINDOW_BLUR = "window_blur"
    FULLSCREEN_EXIT = "fullscreen_exit"
    INTERNET_DETECTED = "internet_detected"


class ReviewDecision(str, enum.Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    FLAGGED = "flagged"


class ComplexityDecision(str, enum.Enum):
    VALID = "valid"
    INVALID = "invalid"


class Contest(Base):
    __tablename__ = "contests"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    start_at = Column(DateTime, nullable=True)
    end_at = Column(DateTime, nullable=True)
    state = Column(SAEnum(ContestState), default=ContestState.SCHEDULED, nullable=False)
    freeze_minutes = Column(Integer, default=0)
    penalty_minutes = Column(Integer, default=20)

    problems = relationship("Problem", back_populates="contest")
    participants = relationship("Participant", back_populates="contest")


class Problem(Base):
    __tablename__ = "problems"

    id = Column(Integer, primary_key=True)
    contest_id = Column(Integer, ForeignKey("contests.id"), nullable=False)
    code = Column(String, nullable=False)
    title = Column(String, nullable=False)
    statement_md = Column(Text, nullable=False)
    time_limit_ms = Column(Integer, nullable=False)
    mem_limit_mb = Column(Integer, nullable=False)
    points = Column(Integer, default=100)

    contest = relationship("Contest", back_populates="problems")
    testcases = relationship("Testcase", back_populates="problem")
    submissions = relationship("Submission", back_populates="problem")


class Testcase(Base):
    __tablename__ = "testcases"

    id = Column(Integer, primary_key=True)
    problem_id = Column(Integer, ForeignKey("problems.id"), nullable=False)
    input_path = Column(String, nullable=False)
    output_path = Column(String, nullable=False)
    is_sample = Column(Integer, default=0)
    points = Column(Integer, default=0)
    checker_type = Column(String, default="exact_match")

    problem = relationship("Problem", back_populates="testcases")
    verdicts = relationship("VerdictRow", back_populates="testcase")


class Participant(Base):
    __tablename__ = "participants"

    id = Column(Integer, primary_key=True)
    contest_id = Column(Integer, ForeignKey("contests.id"), nullable=False)
    username = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    team_name = Column(String, nullable=True)
    seat_id = Column(String, nullable=True)

    contest = relationship("Contest", back_populates="participants")
    submissions = relationship("Submission", back_populates="participant")
    events = relationship("Event", back_populates="participant")
    warnings = relationship("Warning", back_populates="participant")


class Submission(Base):
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True)
    participant_id = Column(Integer, ForeignKey("participants.id"), nullable=False)
    problem_id = Column(Integer, ForeignKey("problems.id"), nullable=False)
    lang = Column(String, nullable=False)
    source_path = Column(String, nullable=False)
    submitted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    status = Column(SAEnum(SubmissionStatus), default=SubmissionStatus.QUEUED, nullable=False)
    verdict = Column(SAEnum(Verdict), default=Verdict.PENDING, nullable=False)
    runtime_ms = Column(Integer, nullable=True)
    mem_kb = Column(Integer, nullable=True)

    participant = relationship("Participant", back_populates="submissions")
    problem = relationship("Problem", back_populates="submissions")
    verdict_rows = relationship("VerdictRow", back_populates="submission")
    review_flags = relationship("ReviewFlag", back_populates="submission")
    complexity_reviews = relationship("ComplexityReview", back_populates="submission")


class VerdictRow(Base):
    __tablename__ = "verdicts"

    id = Column(Integer, primary_key=True)
    submission_id = Column(Integer, ForeignKey("submissions.id"), nullable=False)
    testcase_id = Column(Integer, ForeignKey("testcases.id"), nullable=False)
    status = Column(SAEnum(TestcaseStatus), nullable=False)
    runtime_ms = Column(Integer, nullable=True)
    mem_kb = Column(Integer, nullable=True)

    submission = relationship("Submission", back_populates="verdict_rows")
    testcase = relationship("Testcase", back_populates="verdicts")


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    participant_id = Column(Integer, ForeignKey("participants.id"), nullable=False)
    type = Column(SAEnum(EventType), nullable=False)
    payload = Column(Text, nullable=True)
    ts = Column(DateTime, default=datetime.utcnow, nullable=False)

    participant = relationship("Participant", back_populates="events")


class Warning(Base):
    __tablename__ = "warnings"

    id = Column(Integer, primary_key=True)
    participant_id = Column(Integer, ForeignKey("participants.id"), nullable=False)
    reason = Column(String, nullable=False)
    ts = Column(DateTime, default=datetime.utcnow, nullable=False)
    resolved_by = Column(String, nullable=True)
    resolved_at = Column(DateTime, nullable=True)

    participant = relationship("Participant", back_populates="warnings")


class ReviewFlag(Base):
    __tablename__ = "review_flags"

    id = Column(Integer, primary_key=True)
    submission_id = Column(Integer, ForeignKey("submissions.id"), nullable=False)
    reviewer = Column(String, nullable=False)
    decision = Column(SAEnum(ReviewDecision), nullable=False)
    note = Column(Text, nullable=True)
    ts = Column(DateTime, default=datetime.utcnow, nullable=False)

    submission = relationship("Submission", back_populates="review_flags")


class ComplexityReview(Base):
    __tablename__ = "complexity_reviews"

    id = Column(Integer, primary_key=True)
    submission_id = Column(Integer, ForeignKey("submissions.id"), nullable=False)
    ai_suggested_class = Column(String, nullable=True)
    ai_reasoning = Column(Text, nullable=True)
    judge_decision = Column(SAEnum(ComplexityDecision), nullable=True)
    judge_class = Column(String, nullable=True)
    judge_note = Column(Text, nullable=True)
    reviewer = Column(String, nullable=True)
    ts = Column(DateTime, default=datetime.utcnow, nullable=False)

    submission = relationship("Submission", back_populates="complexity_reviews")


class PlagiarismMatch(Base):
    __tablename__ = "plagiarism_matches"

    id = Column(Integer, primary_key=True)
    submission_a_id = Column(Integer, ForeignKey("submissions.id"), nullable=False)
    submission_b_id = Column(Integer, ForeignKey("submissions.id"), nullable=False)
    similarity_score = Column(Float, nullable=False)
    ts = Column(DateTime, default=datetime.utcnow, nullable=False)
