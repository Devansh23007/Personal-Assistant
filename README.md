# Personal Assistant

Personal Assistant is a modular personal productivity app. This repository is at the **Project Foundation** stage: it has a React + TypeScript dashboard, a FastAPI modular monolith, PostgreSQL setup, account registration/sign-in, and an optional LLM chat endpoint with a read-only tool registry.

## Start locally (Windows PowerShell)

You need Docker Desktop, Node.js 20 or newer with npm, and Python 3.11 or newer.

### 1. Start PostgreSQL

From the repository root:

```powershell
docker compose up -d database
```

Docker Compose uses local development credentials only. Do not reuse them for a deployed environment.

### 2. Configure and start the API

```powershell
if (-not (Test-Path backend/.env)) { Copy-Item backend/.env.example backend/.env }
Set-Location backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

The API is at `http://localhost:8000`; interactive docs are at `http://localhost:8000/docs`. The liveness endpoint is `/api/health`; `/api/ready` checks the database connection.

### 3. Start the frontend

In a second terminal at the repository root:

```powershell
Set-Location frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The Vite development server proxies `/api` requests to FastAPI.

Create an account from the sign-in screen. Passwords are hashed with Argon2 before storage. Access tokens are kept in the current browser session and cleared when you sign out.

### 4. Enable AI chat (optional)

The backend is configured for Groq's OpenAI-compatible API. Add your provider key and a model ID from your provider account to `backend/.env`:

```dotenv
LLM_API_KEY=your_key_here
LLM_MODEL=your_model_id_here
```

Restart FastAPI. Without these values, the rest of the app works and chat returns a clear “not configured” response. The first tool is read-only and reports the server clock. Tool calls run in the backend and are limited to explicitly registered functions.

## Run backend checks

From the `backend` folder with its virtual environment active:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest
```

The starter tests cover health, registration/login, duplicate registration, and authentication on the assistant endpoint. They use an in-memory SQLite database and do not need the local PostgreSQL container.

## Structure

```text
backend/
  app/core/                 settings, database, and security
  app/api/                  shared API router
  app/modules/auth/         registration, sign-in, and current account
  app/modules/assistant/    provider client, chat API, and tool registry
  app/modules/health/       liveness and database readiness
  app/migrations/           Alembic database migrations
frontend/
  src/App.tsx               sign-in, dashboard, and starter chat interface
  src/styles.css            responsive application styles
docker-compose.yml          local PostgreSQL service
```

Feature modules belong under `backend/app/modules/` and can own their routes, models, schemas, and services. Add cross-module behavior through explicit service/tool interfaces rather than having modules reach into each other's internals.

## API starter endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Liveness and configuration status |
| GET | `/api/ready` | Check database connectivity |
| POST | `/api/auth/register` | Create an account |
| POST | `/api/auth/token` | Exchange email/password for a bearer token |
| GET | `/api/auth/me` | Return the signed-in account |
| POST | `/api/assistant/chat` | Authenticated chat with bounded tool calling |
| GET | `/api/lifeos/tasks` | List user tasks with status, priority, and keyword filters |
| POST | `/api/lifeos/tasks` | Create a task with priority, due date, timezone, and tags |
| GET | `/api/lifeos/tasks/summary` | Task counts and metrics (overdue, today, pending) |
| GET | `/api/lifeos/tasks/{id}` | Retrieve a specific task |
| PATCH | `/api/lifeos/tasks/{id}` | Update task details or toggle status |
| DELETE | `/api/lifeos/tasks/{id}` | Delete a task |
| GET | `/api/inboxzero/stats` | Inbox metrics (unread, action needed, drafts pending) |
| GET | `/api/inboxzero/messages` | List emails filtered by category, read status, and search |
| GET | `/api/inboxzero/messages/{id}` | Retrieve single email message with AI summary |
| PATCH | `/api/inboxzero/messages/{id}` | Mark read/unread, archive, or re-categorize |
| POST | `/api/inboxzero/messages/{id}/draft-reply` | Generate an AI contextual reply draft |
| GET | `/api/inboxzero/drafts` | List pending and sent drafts |
| POST | `/api/inboxzero/drafts` | Create manual draft |
| POST | `/api/inboxzero/drafts/{id}/send` | Explicit human approval gate: send draft |
| DELETE | `/api/inboxzero/drafts/{id}` | Discard a draft |
| GET | `/api/spendwise/summary` | Financial metrics (income, expenses, savings rate, breakdown) |
| GET | `/api/spendwise/transactions` | Filter transactions by type, category, month, and search |
| POST | `/api/spendwise/transactions` | Log new transaction |
| GET | `/api/spendwise/transactions/{id}` | Single transaction details |
| PATCH | `/api/spendwise/transactions/{id}` | Update transaction |
| DELETE | `/api/spendwise/transactions/{id}` | Delete transaction |
| POST | `/api/spendwise/transactions/import-csv` | Import transactions from CSV format |
| GET | `/api/spendwise/budgets` | Category budgets with spending progress |
| POST | `/api/spendwise/budgets` | Set or update monthly category budget |
| DELETE | `/api/spendwise/budgets/{id}` | Delete a budget |
| GET | `/api/docuvault/documents` | List stored documents with search and tags |
| POST | `/api/docuvault/documents` | Store and index a new document |
| GET | `/api/docuvault/documents/search` | Semantic & keyword RAG search with source citations |
| GET | `/api/docuvault/documents/{id}` | Retrieve document text and metadata |
| DELETE | `/api/docuvault/documents/{id}` | Delete document from vault and storage |
| GET | `/api/learnloop/decks` | List study decks with card and review stats |
| POST | `/api/learnloop/decks` | Create a new study deck |
| GET | `/api/learnloop/decks/{id}` | Retrieve study deck |
| DELETE | `/api/learnloop/decks/{id}` | Delete study deck and cards |
| POST | `/api/learnloop/decks/generate-from-doc/{doc_id}` | Auto-generate flashcards from DocuVault document |
| GET | `/api/learnloop/decks/{id}/cards` | List cards for review (optional `due_only=true`) |
| POST | `/api/learnloop/decks/{id}/cards` | Add flashcard to deck |
| POST | `/api/learnloop/cards/{id}/review` | Review card rating (`hard`, `good`, `easy`) with spaced repetition |

## Foundation scope and safety

- The app is a single backend service with feature-module boundaries; it is not split into microservices.
- PostgreSQL credentials, JWT signing key, and LLM settings come from environment configuration. Keep `.env` files private.
- LLM calls only receive the current prompt and the short conversation context supplied by the signed-in browser. The initial tool registry is read-only.
- There is no payment, purchase, email-send, Gmail, calendar, or bank integration in this foundation.
- Database changes go through Alembic. Add a migration whenever a persisted model changes.
- Before deployment, add production secrets, secure cookie-based sessions, rate limiting, account recovery, backups, logging/monitoring, and a deployment-specific security review.

## Roadmap from here

1. **Project Foundation:** app shell, auth, database, AI provider/tool interface, and local developer setup.
2. **LifeOS:** tasks and reminder scheduling with an explicit time-zone model.
3. **InboxZero:** Gmail OAuth, read/summarize/draft flows, then approval-gated sending if needed.
4. **SpendWise:** transactions, CSV import, budgets, and summaries.
5. **LearnLoop + DocuVault:** safe file storage, text extraction, source-linked retrieval, and study tools.
6. **MealMind + PricePilot:** meal plans, grocery lists, and supported product research.
7. **AutoFlow:** bounded cross-module workflows, audit history, and approval gates.
8. **Integration and deployment:** full workflow review, security hardening, and deployment.

Develop on focused feature branches. This foundation is on `feature/project-foundation`; keep `main` stable and merge through a reviewed pull request after local verification.
