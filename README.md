# Review Desk

Review Desk is a Python web application for company review requests. Administrators manage accounts and preparation tasks; developers submit review requests and receive reviewer assignments.

## Stack

- FastAPI
- Python 3.13+
- SQLite for local development
- HTML, CSS, and browser JavaScript served by FastAPI
- PostgreSQL and Redis (next production infrastructure slice)

## Project structure

```text
review_dashboard/
├── backend/       FastAPI API, authentication, SQLite, business rules
├── frontend/      HTML, CSS, and browser JavaScript
└── docs/          Workflow documentation
```

The frontend is a separate sibling folder, but FastAPI serves it so the whole
application runs from one Python process.

## Run locally

Install Python 3.13 or later, then run from the project root:

```powershell
cd C:\workspace\project\review_dashboard
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r backend\requirements.txt
py -m uvicorn backend.main:app --reload --port 8000
```

Open [http://localhost:8000](http://localhost:8000). API documentation is at [http://localhost:8000/docs](http://localhost:8000/docs).

The local database is `backend/review_desk.db`. The first page creates the administrator account. After that, the administrator creates developers and tasks; developers sign in and manage review requests.

## Current workflow

- First launch creates one administrator account.
- The administrator creates Administrator or Developer accounts and preparation tasks.
- Developers sign in, select a task, describe the element to review, select a deadline and reviewers, and send the request.
- Reviewers sign in to open the request and choose **Review done by me** or **I'm not concerned**.
- Passwords are hashed server-side with PBKDF2 and sessions are held by the API.

Email/Teams notifications, deadlines, reminders, rework, and final approval are the next backend slices.
