import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from .database import engine, Base
from .models import *
from .routers import contests, problems


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="BYTEARENA", version="0.1.0", lifespan=lifespan)

app.include_router(contests.router)
app.include_router(problems.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "bytearena"}


STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
