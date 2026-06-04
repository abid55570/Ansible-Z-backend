# Deploying the Ansible-Z backend

## What it needs
- **PostgreSQL** — connection string in `DATABASE_URL`.
- **Object storage** — S3-compatible (`STORAGE_PROVIDER=s3`) or OpenStack Swift (`STORAGE_PROVIDER=swift`).
- **Google OAuth client ID** — `GOOGLE_CLIENT_ID` (public; used to verify sign-in ID tokens).
- A strong **`JWT_SECRET`**.

Copy `.env.example` to `.env` and fill it in — that file documents every variable.

## Database migrations (Alembic)
The schema is versioned in `alembic/versions/`.

```bash
alembic upgrade head                         # apply all migrations
alembic downgrade -1                         # roll back one
alembic revision --autogenerate -m "add X"   # after changing a model
```

The container runs `alembic upgrade head` automatically before serving (see the
Dockerfile `CMD`). If you have a database that was already created by the app's
`create_all`, baseline it once with `alembic stamp head` so Alembic adopts it.

## Local (Docker Compose)
Runs Postgres + MinIO (S3) + the API:

```bash
cp .env.example .env        # then edit
docker compose --profile full up --build
# API on http://localhost:8000
```

Or run only the dependencies and the app on your host:

```bash
docker compose up -d db minio
uvicorn app.main:app --reload
```

## Production image
```bash
docker build -t ansible-z-backend .
docker run -p 8000:8000 --env-file .env ansible-z-backend
```

The image applies migrations, then serves on `:8000` with a `/health` healthcheck,
as a non-root user.

## Optional: deep validation
`DEEP_LINT=true` runs `ansible-playbook --syntax-check` on every generated project.
It requires `ansible-core` plus the `amazon.aws`, `community.aws` and
`community.docker` collections in the image — extend the Dockerfile if you enable it.

## CORS
Set `FRONTEND_ORIGIN` to your deployed frontend URL (defaults to `http://localhost:3000`).
