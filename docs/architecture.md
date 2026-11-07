# Foundation architecture

## Runtime pieces

- **Frontend:** Vite serves the React + TypeScript single-page app. It calls `/api` so browser requests use the same origin in development.
- **API:** FastAPI exposes routes through `app/api/router.py`. Each feature owns a package under `app/modules/`.
- **Persistence:** SQLAlchemy 2.x connects to PostgreSQL. Alembic owns schema changes. A request-scoped session is provided by `get_db`.
- **Authentication:** password hashes use Argon2; login issues short-lived HS256 JWT access tokens. Protected routes resolve the user from the token subject.
- **Assistant:** the provider client is configured by environment values. A tool registry maps explicit function names to backend handlers. Tool execution is bounded and currently read-only.

## Module boundary

A module may expose a router and service functions. Other modules should call a public service or registered tool rather than importing internal database queries. Shared infrastructure belongs in `app/core/`; API composition belongs in `app/api/`.

## Request flow

```text
Browser -> FastAPI router -> auth dependency -> feature service -> database/provider
                                              -> tool registry (only for explicit tool calls)
```

The browser sends a bearer token for protected routes. The assistant endpoint only accepts an authenticated request. The model may request a tool, but Python code chooses whether the named tool exists and executes it; model output is not executed as code.

## Current limitations

- Accounts are open-registration and meant for local development.
- The browser keeps the access token in `sessionStorage` for this starter. Production should use a secure, HTTP-only cookie design with CSRF protection and review the full auth flow.
- Conversation history is supplied by the browser and is not persisted. Treat it as untrusted context.
- The initial tool is read-only and has no access to personal module data.
- `Base.metadata` is used by Alembic migrations. Do not rely on automatic table creation in production.

## Adding the next feature

For a feature such as LifeOS, create a module package with `models.py`, `schemas.py`, `service.py`, and `router.py`; include the router in `app/api/router.py`; create and review an Alembic migration; add UI views/components; then define its permission and reminder behavior before exposing it as an assistant tool.
