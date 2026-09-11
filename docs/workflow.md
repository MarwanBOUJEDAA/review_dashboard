# Review Desk Python workflow

```mermaid
flowchart TD
    A[Browser opens localhost:8000] --> B[FastAPI backend.main:app]
    B --> C{Accounts exist?}
    C -->|No| D[POST /auth/setup\ncreate administrator]
    C -->|Yes| E[POST /auth/login\ncreate session token]
    D --> E
    E --> F{Account type}
    F -->|Administrator| G[POST /accounts\nPOST /tasks]
    G --> H[SQLite review_desk.db]
    F -->|Developer| I[GET /tasks]
    I --> J[POST /review-requests]
    J --> K[Reviewer inbox\nGET /review-requests/inbox]
    K --> L[POST /review-requests/:id/decision]
    L --> M[done or not-concerned]
```

## Python entry points

- `backend/main.py`: FastAPI application, authentication, permissions, persistence, and review endpoints.
- `frontend/index.html`: application shell.
- `frontend/app.js`: browser interactions and API calls.
- `frontend/styles.css`: application presentation.
- `backend/review_desk.db`: local SQLite database created at runtime.
