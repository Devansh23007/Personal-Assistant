# Personal Assistant

A small starting point for the Personal Assistant project. The first version contains a React + TypeScript frontend and a FastAPI backend, organized so features can grow into separate modules.

## Project layout

```text
frontend/   React, TypeScript, and Vite application
backend/    FastAPI application and API modules
```

## Requirements

- Node.js 20 or newer with npm
- Python 3.11 or newer

## Run locally

Start the backend in one terminal:

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API is available at `http://localhost:8000`; interactive API docs are at `http://localhost:8000/docs`.

Start the frontend in another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Vite serves the app at `http://localhost:5173`. The `/api` path is proxied to the backend.

## Current scope

This is intentionally just the application shell and a health endpoint. There is no authentication, database, external integration, or AI action enabled yet. Add those after agreeing on the first user workflow and its data model.
