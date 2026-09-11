# Review Desk Python API

FastAPI backend for accounts, company tasks, review requests, and reviewer decisions. The browser frontend is a sibling project in `../frontend`.

## Run on Windows

From the project root:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r backend\requirements.txt
py -m uvicorn backend.main:app --reload --port 8000
```

API documentation: http://localhost:8000/docs

The development database is `backend/review_desk.db`. It is created automatically on first start.

The FastAPI server serves the sibling frontend at `http://localhost:8000`.
