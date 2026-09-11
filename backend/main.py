from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field

DATABASE = Path(__file__).with_name("review_desk.db")
FRONTEND = Path(__file__).parent.parent / "frontend"
app = FastAPI(title="Review Desk API", version="0.1.0")
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def connection() -> sqlite3.Connection:
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db


def init_db() -> None:
    with connection() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                account_type TEXT NOT NULL CHECK (account_type IN ('administrator', 'developer'))
            );
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS review_requests (
                id TEXT PRIMARY KEY,
                temporary_name TEXT NOT NULL,
                task_id TEXT NOT NULL REFERENCES tasks(id),
                element_to_review TEXT NOT NULL,
                deadline TEXT NOT NULL,
                developer_id TEXT NOT NULL REFERENCES accounts(id)
            );
            CREATE TABLE IF NOT EXISTS review_assignments (
                request_id TEXT NOT NULL REFERENCES review_requests(id),
                reviewer_id TEXT NOT NULL REFERENCES accounts(id),
                decision TEXT NOT NULL DEFAULT 'pending' CHECK (decision IN ('pending', 'done', 'not-concerned')),
                PRIMARY KEY (request_id, reviewer_id)
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                account_id TEXT NOT NULL REFERENCES accounts(id)
            );
            """
        )


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/", include_in_schema=False)
def application() -> FileResponse:
    return FileResponse(FRONTEND / "index.html")


def password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return f"{salt.hex()}:{digest.hex()}"


def password_matches(password: str, stored: str) -> bool:
    salt_hex, digest_hex = stored.split(":", 1)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 120_000)
    return hmac.compare_digest(digest.hex(), digest_hex)


def public_account(row: sqlite3.Row) -> dict[str, str]:
    return {"id": row["id"], "name": row["name"], "email": row["email"], "accountType": row["account_type"]}


def require_account(authorization: str | None = Header(default=None)) -> sqlite3.Row:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login required")
    with connection() as db:
        account = db.execute(
            "SELECT a.* FROM accounts a JOIN sessions s ON s.account_id = a.id WHERE s.token = ?",
            (authorization.removeprefix("Bearer "),),
        ).fetchone()
    if not account:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    return account


def require_admin(account: sqlite3.Row = Depends(require_account)) -> sqlite3.Row:
    if account["account_type"] != "administrator":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required")
    return account


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=4, max_length=200)
    accountType: Literal["administrator", "developer"] = "developer"


class LoginInput(BaseModel):
    identifier: str
    password: str


class TaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1)


class ReviewCreate(BaseModel):
    temporaryName: str = Field(min_length=1, max_length=160)
    taskId: str
    elementToReview: str = Field(min_length=1)
    deadline: date
    reviewerIds: list[str] = Field(min_length=1)


class ReviewDecision(BaseModel):
    decision: Literal["done", "not-concerned"]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
    
@app.get("/auth/status")
def auth_status() -> dict[str, bool]:
    with connection() as db:
        return {"hasAccounts": db.execute("SELECT 1 FROM accounts LIMIT 1").fetchone() is not None}


@app.post("/auth/setup")
def setup_admin(payload: AccountCreate) -> dict[str, object]:
    with connection() as db:
        if db.execute("SELECT 1 FROM accounts LIMIT 1").fetchone():
            raise HTTPException(status_code=409, detail="Initial administrator already exists")
        account_id = secrets.token_hex(16)
        db.execute("INSERT INTO accounts VALUES (?, ?, ?, ?, 'administrator')", (account_id, payload.name, payload.email, password_hash(payload.password)))
    return {"account": {"id": account_id, "name": payload.name, "email": str(payload.email), "accountType": "administrator"}}


@app.post("/auth/login")
def login(payload: LoginInput) -> dict[str, object]:
    with connection() as db:
        account = db.execute("SELECT * FROM accounts WHERE lower(email) = lower(?) OR lower(name) = lower(?)", (payload.identifier, payload.identifier)).fetchone()
        if not account or not password_matches(payload.password, account["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid account or password")
        token = secrets.token_urlsafe(32)
        db.execute("INSERT INTO sessions VALUES (?, ?)", (token, account["id"]))
    return {"token": token, "account": public_account(account)}


@app.get("/accounts")
def accounts(_: sqlite3.Row = Depends(require_admin)) -> list[dict[str, str]]:
    with connection() as db:
        return [public_account(row) for row in db.execute("SELECT * FROM accounts ORDER BY name")]


@app.post("/accounts")
def create_account(payload: AccountCreate, _: sqlite3.Row = Depends(require_admin)) -> dict[str, str]:
    account_id = secrets.token_hex(16)
    try:
        with connection() as db:
            db.execute("INSERT INTO accounts VALUES (?, ?, ?, ?, ?)", (account_id, payload.name, payload.email, password_hash(payload.password), payload.accountType))
    except sqlite3.IntegrityError as error:
        raise HTTPException(status_code=409, detail="Email already exists") from error
    return {"id": account_id, "name": payload.name, "email": str(payload.email), "accountType": payload.accountType}


@app.delete("/accounts/{account_id}")
def delete_account(account_id: str, _: sqlite3.Row = Depends(require_admin)) -> dict[str, str]:
    with connection() as db:
        account = db.execute("SELECT account_type FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if not account or account["account_type"] != "developer":
            raise HTTPException(status_code=404, detail="Developer account not found")
        db.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
    return {"status": "deleted"}


@app.get("/tasks")
def tasks(_: sqlite3.Row = Depends(require_account)) -> list[dict[str, str]]:
    with connection() as db:
        return [dict(row) for row in db.execute("SELECT id, name, description FROM tasks ORDER BY name")]


@app.post("/tasks")
def create_task(payload: TaskCreate, _: sqlite3.Row = Depends(require_admin)) -> dict[str, str]:
    task_id = secrets.token_hex(16)
    with connection() as db:
        db.execute("INSERT INTO tasks VALUES (?, ?, ?)", (task_id, payload.name, payload.description))
    return {"id": task_id, "name": payload.name, "description": payload.description}


@app.delete("/tasks/{task_id}")
def delete_task(task_id: str, _: sqlite3.Row = Depends(require_admin)) -> dict[str, str]:
    with connection() as db:
        db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    return {"status": "deleted"}


@app.post("/review-requests")
def create_review(payload: ReviewCreate, account: sqlite3.Row = Depends(require_account)) -> dict[str, str]:
    if account["account_type"] != "developer":
        raise HTTPException(status_code=403, detail="Only developers can create review requests")
    request_id = secrets.token_hex(16)
    with connection() as db:
        if not db.execute("SELECT 1 FROM tasks WHERE id = ?", (payload.taskId,)).fetchone():
            raise HTTPException(status_code=404, detail="Task not found")
        reviewers = [db.execute("SELECT id FROM accounts WHERE id = ? AND account_type = 'developer'", (reviewer_id,)).fetchone() for reviewer_id in payload.reviewerIds]
        if any(reviewer is None for reviewer in reviewers):
            raise HTTPException(status_code=400, detail="Every reviewer must be a developer account")
        db.execute("INSERT INTO review_requests VALUES (?, ?, ?, ?, ?, ?)", (request_id, payload.temporaryName, payload.taskId, payload.elementToReview, payload.deadline.isoformat(), account["id"]))
        db.executemany("INSERT INTO review_assignments VALUES (?, ?, 'pending')", [(request_id, reviewer_id) for reviewer_id in payload.reviewerIds])
    return {"id": request_id, "status": "pending"}


@app.get("/review-requests/inbox")
def inbox(account: sqlite3.Row = Depends(require_account)) -> list[dict[str, object]]:
    with connection() as db:
        rows = db.execute("""SELECT r.*, t.name AS task_name, a.name AS developer_name, ra.decision
            FROM review_assignments ra JOIN review_requests r ON r.id = ra.request_id
            JOIN tasks t ON t.id = r.task_id JOIN accounts a ON a.id = r.developer_id
            WHERE ra.reviewer_id = ? AND ra.decision = 'pending' ORDER BY r.deadline""", (account["id"],)).fetchall()
    return [dict(row) for row in rows]


@app.post("/review-requests/{request_id}/decision")
def decide_review(request_id: str, payload: ReviewDecision, account: sqlite3.Row = Depends(require_account)) -> dict[str, str]:
    with connection() as db:
        result = db.execute("UPDATE review_assignments SET decision = ? WHERE request_id = ? AND reviewer_id = ?", (payload.decision, request_id, account["id"]))
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Review assignment not found")
    return {"status": payload.decision}
