from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import engine
from ..models import Contest, ContestState
from ..schemas import ContestCreate, ContestUpdate, ContestOut

router = APIRouter(prefix="/api/contests", tags=["contests"])


def get_db():
    with Session(engine) as session:
        yield session


@router.post("", response_model=ContestOut, status_code=201)
def create_contest(body: ContestCreate, db: Session = Depends(get_db)):
    contest = Contest(
        name=body.name,
        start_at=body.start_at,
        end_at=body.end_at,
        state=ContestState.SCHEDULED,
        freeze_minutes=body.freeze_minutes,
        penalty_minutes=body.penalty_minutes,
    )
    db.add(contest)
    db.commit()
    db.refresh(contest)
    contest.problem_count = 0
    return contest


@router.get("", response_model=list[ContestOut])
def list_contests(db: Session = Depends(get_db)):
    contests = db.query(Contest).all()
    for c in contests:
        c.problem_count = len(c.problems)
    return contests


@router.get("/{contest_id}", response_model=ContestOut)
def get_contest(contest_id: int, db: Session = Depends(get_db)):
    contest = db.query(Contest).filter(Contest.id == contest_id).first()
    if not contest:
        raise HTTPException(status_code=404, detail="Contest not found")
    contest.problem_count = len(contest.problems)
    return contest


@router.put("/{contest_id}", response_model=ContestOut)
def update_contest(contest_id: int, body: ContestUpdate, db: Session = Depends(get_db)):
    contest = db.query(Contest).filter(Contest.id == contest_id).first()
    if not contest:
        raise HTTPException(status_code=404, detail="Contest not found")
    update_data = body.dict(exclude_unset=True)
    for key, value in update_data.items():
        if key == "state":
            value = ContestState(value)
        setattr(contest, key, value)
    db.commit()
    db.refresh(contest)
    contest.problem_count = len(contest.problems)
    return contest


@router.delete("/{contest_id}", status_code=204)
def delete_contest(contest_id: int, db: Session = Depends(get_db)):
    contest = db.query(Contest).filter(Contest.id == contest_id).first()
    if not contest:
        raise HTTPException(status_code=404, detail="Contest not found")
    db.delete(contest)
    db.commit()
