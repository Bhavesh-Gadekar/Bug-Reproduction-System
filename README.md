# Bug Reproduction Agent Monorepo

An autonomous multi-agent system designed to isolate, reproduce, and validate software bugs end-to-end.

---

## Repository Structure

```
├── .github/
│   └── workflows/
│       └── lint.yml          # GitHub Actions PR linting (Ruff + ESLint)
├── api/                      # FastAPI Backend Service
│   ├── app/
│   │   ├── core/config.py    # Pydantic Settings & Env Loader
│   │   └── main.py           # FastAPI Routes & Middleware
│   ├── .env.example
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── requirements.txt
├── worker/                   # Python Agent Worker (LangGraph ready)
│   ├── app/
│   │   ├── core/config.py    # Worker Settings & Redis Queue Config
│   │   └── main.py           # Async Worker Process Loop
│   ├── .env.example
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── requirements.txt
├── web/                      # Next.js App Router (TypeScript)
│   ├── src/app/
│   │   ├── globals.css
│   │   ├── layout.tsx
│   │   └── page.tsx
│   ├── .env.example
│   ├── .eslintrc.json
│   ├── Dockerfile
│   ├── next.config.mjs
│   ├── package.json
│   └── tsconfig.json
├── docker-compose.yml        # Local Redis and multi-service orchestration
├── pyproject.toml            # Root Ruff lint & format configuration
├── package.json              # Monorepo scripts & workspaces
└── .env.example              # Root global environment template
```

---

## Environment Variables & Backblaze B2

Each package contains a `.env.example` file referencing the necessary keys:

| Key | Description | Example / Format |
|---|---|---|
| `NEON_DATABASE_URL` | Neon Serverless PostgreSQL | `postgresql://user:pass@ep-xyz.us-east-2.aws.neon.tech/neondb?sslmode=require` |
| `CLERK_SECRET_KEY` | Clerk Auth Backend Secret Key | `sk_test_...` |
| `CLERK_PUBLISHABLE_KEY` | Clerk Auth Publishable Key | `pk_test_...` |
| `GEMINI_API_KEY` | Google Gemini LLM API Key | `AIzaSy...` |
| `B2_KEY_ID` | Backblaze B2 Key ID / App Key ID | `your_b2_key_id` |
| `B2_APPLICATION_KEY` | Backblaze B2 Application Key | `your_b2_application_key` |
| `B2_BUCKET_NAME` | Backblaze B2 Bucket Name | `bug-reproduction-artifacts` |
| `B2_ENDPOINT` | Backblaze B2 S3-Compatible Endpoint | `https://s3.<region>.backblazeb2.com` (e.g. `https://s3.us-west-004.backblazeb2.com`) |
| `REDIS_URL` | Redis Connection String | `redis://localhost:6379/0` |
| `NEXT_PUBLIC_API_URL` | Frontend -> FastAPI Backend Base URL | `http://localhost:8000` |

> **Frontend Environment Scoping**: `web/.env.example` is scoped specifically to `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`, and `NEXT_PUBLIC_API_URL` as database and LLM calls are orchestrated via FastAPI.

> **Backblaze B2 vs Cloudflare R2 Note**: Backblaze B2 uses regional S3-compatible endpoints (`https://s3.<region>.backblazeb2.com`) with Application Keys (`B2_KEY_ID` and `B2_APPLICATION_KEY`). Standard `boto3` / AWS S3 client libraries connect seamlessly using these parameters.

---

## Local Development Quickstart

### 1. Start Redis
```bash
docker compose up redis -d
```

### 2. Run API (FastAPI)
```bash
cd api
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 3. Run Worker (LangGraph Agent)
```bash
cd worker
pip install -r requirements.txt
python -m app.main
```

### 4. Run Web Frontend (Next.js)
```bash
cd web
npm install
npm run dev
```

---

## Linting & Quality Checks

- **Python (Ruff)**:
  ```bash
  ruff check .
  ruff format --check .
  ```
- **Next.js (ESLint)**:
  ```bash
  npm --workspace=web run lint
  ```
- **All-in-one**:
  ```bash
  npm run lint
  ```

---

## Continuous Integration

GitHub Actions workflow [`.github/workflows/lint.yml`](.github/workflows/lint.yml) runs automatically on every pull request to ensure all Python code passes `ruff` and web code passes `eslint`.
