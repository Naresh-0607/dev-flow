# PROJECT CONTEXT
I'm building DevFlow: a tool that tracks which git branch I'm working on in each of my projects.
A local Python agent (built later) will send git events (commit, branch checkout) as JSON to this
API, which stores them in Postgres. A React PWA (built later) will display them.
Multiple users will eventually use one hosted server, each with their own data; usernames may later be used for friends and collaboration. Docker and AWS come much later (deployment phase).
Do NOT create Docker files in this phase.

Environment:
- Windows 11. Project at C:\Users\Naresh\Projects\dev-flow. I use PowerShell.
- PostgreSQL is installed locally on Windows (localhost:5432).
- Python: use a virtual environment at backend\.venv with Python 3.12 or 3.13 (NOT 3.14, some
  packages lack wheels for it).
- I'm an intermediate developer. Explain briefly what each piece does, and give complete files, not snippets.

# CURRENT STATE
Only empty folders exist: backend/, agent/, frontend/, infra/, plus .gitattributes (eol=lf).
git is initialized. No code has been written yet.

# YOUR TASK: PHASE A, BACKEND
Build the full backend API (FastAPI + SQLAlchemy 2.0 + Alembic + Postgres). Do these in order and
keep the app runnable after each step.

## A0. Scaffold
Create:
- .gitignore (Python, .venv, .env, __pycache__, node_modules)
- backend/requirements.txt: fastapi, uvicorn[standard], sqlalchemy>=2, psycopg[binary], alembic,
  pydantic-settings, pytest, httpx
- backend/.env.example (committed) and backend/.env (gitignored, I fill it in) with:
  DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/devflow
  TEST_DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/devflow_test
  CORS_ORIGINS=http://localhost:5173,http://localhost:3000
- backend/app/__init__.py, config.py (pydantic-settings reading backend/.env), db.py (engine,
  SessionLocal, Base, get_db dependency), main.py (FastAPI app with GET /health and GET /health/db)
Give me the exact PowerShell commands to: create the venv with the right Python version
(py -3.12 -m venv .venv), activate it, install requirements, create the two databases
(devflow and devflow_test) with psql, and start the server:
uvicorn app.main:app --reload
I check http://localhost:8000/health, /health/db and /docs before we continue.

## A1. Database models + Alembic migrations
Add app/models.py (typed, Mapped / mapped_column). All datetimes are timezone-aware UTC.
Tables:
- users: id, username (unique, stored lowercase, 3-30 chars: letters, numbers, dashes),
  email (nullable, unique), password_hash (nullable, web login arrives in Phase D),
  is_public (bool, default false), created_at.
- projects: id, owner_id (FK users), name, repo_path, remote_url (nullable), identity_key, created_at.
  identity_key = remote_url if present, otherwise repo_path.
  Unique constraint on (owner_id, identity_key): two users can both have "dev-flow".
- branches: id, project_id (FK), name, last_commit_hash (nullable), last_commit_message (nullable),
  last_commit_author (nullable), last_activity_at, is_active (bool), created_at.
  Unique constraint on (project_id, name).
- events: id, project_id (FK), branch_id (FK, nullable), branch_name, type (enum: commit, checkout,
  merge, scan), commit_hash (nullable), message (nullable), author (nullable), payload (JSONB, raw event),
  occurred_at (timestamptz, from the agent), received_at (timestamptz, server time),
  dedupe_key (str, UNIQUE): sha256 of project_id|type|branch_name|commit_hash-or-empty|occurred_at.
  Idempotency is enforced through dedupe_key (NOT a multi-column unique constraint, because NULL
  commit_hash values would defeat it).
  Index on (branch_id, occurred_at DESC).
- api_keys: id, user_id (FK users), label, key_prefix (first 8 chars, for display), key_hash
  (sha256 hex, unique), created_at, last_used_at (nullable), is_active.
Do NOT create friendships or project_members tables yet. Every relationship points to user_id,
never to the username.
Set up Alembic (alembic.ini, env.py reading DATABASE_URL from app.config) and generate the initial
migration. I run migrations MANUALLY with `alembic upgrade head` (no auto-run on startup).
Tell me the commands to run it.

## A2. POST /events
Request body (Pydantic v2 validation):
```json
{
  "type": "commit",
  "project": "dev-flow",
  "repo_path": "C:/Users/Naresh/Projects/dev-flow",
  "remote_url": "https://github.com/me/dev-flow.git",
  "branch": "close_feature",
  "commit_hash": "a1b2c3d4",
  "message": "add branch table",
  "author": "naresh",
  "timestamp": "2026-10-10T10:51:00+05:30",
  "previous_branch": null
}
```
Behavior:
- Projects are looked up and created under the authenticated user (owner_id = current user).
- Create the project and the branch if they don't exist (get-or-create inside one transaction).
- For type=commit: update the branch's last_commit_* fields and last_activity_at, and mark it active.
- For type=checkout: mark the new branch active and the previous_branch (if given) inactive in that
  project. Only one active branch per project.
- Only move last_activity_at forward, never backward (events can arrive late from the offline queue).
- Idempotent: an exact duplicate event returns 200 with {"status": "duplicate"}; a new one returns 201
  with {"status": "created", "event_id": ...}. Never create a duplicate row.
- Branch may be null/empty for a detached HEAD: store it as the branch name "(detached)".
- Reject invalid input with clear 422 errors (empty project, bad type, timestamp without timezone).
- Also add POST /events/batch accepting a list of up to 500 events, which processes each one
  independently and returns per-event results (the agent uses this to flush its offline queue).

## A3. Read endpoints
- GET /projects: list the current user's projects with branch_count, active_branch (name),
  last_activity_at. Sorted by last_activity_at DESC.
- GET /projects/{project_id}: one project with details.
- GET /projects/{project_id}/branches: branches with last commit info and is_active,
  sorted by last_activity_at DESC. Optional query params: `q` (name search) and `limit`/`offset`.
- GET /branches/{branch_id}/events: event timeline, newest first, with limit/offset (max 200).
- Use Pydantic response models. Avoid N+1 queries (use joins or aggregates).
- Every read endpoint returns only the current user's data. Unknown ids AND another user's ids
  both return 404 with a clear message (not 403), so ids can't be probed.

## A4. Users + API-key authentication
- Keys have the format "df_" + secrets.token_urlsafe(32). Store only the SHA-256 hash plus
  key_prefix. The plaintext is printed once at creation.
- Scripts (run with the venv active in PowerShell):
  - scripts/create_user.py <username>: validates the username (rules above, plus a reserved list:
    admin, api, login, logout, settings, me, www, devflow, support) and creates the user.
  - scripts/create_api_key.py <username> --label "laptop": creates a key for that user.
  Show me the exact commands to run them.
- Dependency `get_current_user` (in app/auth.py): reads X-API-Key, hashes it, finds the active key,
  updates last_used_at, returns the User. 401 for missing, invalid or inactive keys.
  Mark it clearly so I can later add web-session login alongside it (Phase D).
- GET /auth/whoami: returns {"username": ..., "key_label": ...} for the key in the header.
  The CLI uses this to verify the login (and to check that the username in a URL such as
  https://host/@naresh matches the key's owner).
- All /events and read endpoints require get_current_user.
- Add CORS middleware using the CORS_ORIGINS env var.

## A5. Tests
Use pytest + httpx/TestClient, run with plain `pytest` from backend/ in PowerShell.
Tests must use TEST_DATABASE_URL (devflow_test) and must refuse to run (clear error) if that URL does
not end with "_test", so they can never touch my dev data. Tables are created and cleaned per test run.
Cover:
- creating a project/branch from an event; commit updates the summary; checkout switches the
  active branch
- duplicate events are ignored (including duplicate checkout events with no commit_hash)
- late (older) events don't move last_activity_at back
- invalid payloads return 422
- a missing, invalid or inactive API key returns 401
- the batch endpoint with mixed valid and duplicate events
- read endpoints' ordering and 404 behavior
- user A cannot see or write into user B's projects; the same repo name for two users creates
  two separate projects
- GET /auth/whoami returns the right username, and 401 for a bad key
- username validation: reserved names, uppercase letters, too short or too long, duplicates

# RULES
- You may run commands yourself in PowerShell from C:\Users\Naresh\Projects\dev-flow:
  creating the venv, pip install, psql, alembic, uvicorn, pytest, and the scripts in backend/scripts.
  Always use the venv at backend\.venv (Python 3.12 or 3.13).
- Before running anything, tell me in one line what you're about to run and why.
- Never run destructive commands without asking me first: DROP DATABASE, DROP TABLE, deleting files
  or folders, git reset --hard, git push, force flags, or anything outside this project folder.
  Only create/touch the databases devflow and devflow_test, never any other database.
- My PostgreSQL password goes into backend/.env. Ask me for it (or tell me to fill the file in myself)
  and never print it in chat, commit it, or put it in any committed file.
- Don't commit with git. I do the commits myself.
- Run the server with uvicorn only long enough to test the endpoints, then stop it. Don't leave
  background processes running.
- After each step (A0-A5), stop and give me:
  1. The files you created or changed.
  2. The commands you ran and their results (short, with the important output).
  3. Anything that failed and how you fixed it.
  4. How I can verify it myself (URLs, commands).
  Then wait for me to say "continue" before starting the next step.
- If a command fails, read the error and fix the cause. Don't retry the same command blindly,
  and don't guess at causes the output doesn't support. If you're stuck after two attempts, stop
  and ask me.
- Keep the folder layout clean: app/models.py, app/schemas.py, app/routers/events.py,
  app/routers/projects.py, app/routers/auth.py, app/auth.py, app/services/ (business logic
  outside routers), scripts/, tests/.
- Do not hardcode secrets. Use environment variables through app/config.py.
- Use type hints throughout. Keep functions small. Add short comments only where logic is not obvious.
- Don't touch agent/, frontend/ or infra/. Don't create Dockerfiles or docker-compose files.

# ACCEPTANCE CHECKS (final)
1. `alembic upgrade head` succeeds, then `uvicorn app.main:app --reload` starts cleanly.
2. create_user and create_api_key scripts work, and GET /auth/whoami returns the username.
3. A POST to /events with the key returns 201, repeating it returns 200 "duplicate".
4. GET /projects shows the project with its active branch, and only for that user.
5. http://localhost:8000/docs shows all endpoints and lets me authorize with the key.
6. `pytest` passes all tests.