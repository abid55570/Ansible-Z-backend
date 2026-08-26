# Neviri-Ansi — Backend (FastAPI)

API + Ansible-project generator engine.

## Run locally

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1          # Windows PowerShell  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env               # then edit values

uvicorn app.main:app --reload        # http://localhost:8000/health
```

Optional local dependencies (Postgres + MinIO):

```bash
docker compose up -d
```

## Tests + coverage gate

```bash
pytest          # fails if coverage < 93% (configured in pyproject.toml)
```

## API (v1)

```
GET  /health
POST /auth/google            { id_token }      -> verify, upsert user, set JWT cookie
GET  /auth/me                                  -> current user
POST /auth/logout
GET  /templates                                -> list 11 templates (+ ready flag)
GET  /templates/{slug}                         -> manifest + variable schema + guidance
POST /projects               { name, template_slug, config }
GET  /projects
GET  /projects/{id}
POST /projects/{id}/generate { env }           -> validate -> render -> lint -> zip -> store
GET  /projects/{id}/download?env=uat           -> the generated zip
```

## Layout

```
app/
  main.py                FastAPI factory + CORS + lifespan(init_db)
  config.py  db.py  deps.py
  core/      security.py (JWT)  google.py (verify ID token)
  models/    user, project, generation (SQLAlchemy)
  routers/   health, auth, templates, projects
  services/  generator, linter, packager, storage (S3-compatible)
  templates/ 11 blueprints; web-3tier fully implemented (template.yaml + files/*.j2)
tests/       pytest suite — 100% coverage (gate 93%)
scripts/smoke_docker.py    end-to-end check vs real Postgres + MinIO
```

## Verify against real Docker services

```bash
docker compose up -d                       # Postgres + MinIO (needs Docker Desktop running)
.venv\Scripts\python scripts\smoke_docker.py
```

## Next (phase 2)

Frontend variable wizard + generate/download UI; deeper `ansible-lint` / `--syntax-check` gate;
fill in the remaining 10 templates; GitHub App push; Alembic migrations. See `../docs/PLAN.md`.
