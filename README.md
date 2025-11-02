# 🧠 MoodBoard Backend — FastAPI + Redis Worker + PostgreSQL

This is the backend API for MoodBoard, a visual mood collection and AI-powered clustering platform. It handles all API routes, database operations, async background clustering via Redis workers, and OpenAI-powered AI features: live at https://moodboard.fly.dev/docs.

---

## 🚀 Tech Stack

- FastAPI – web framework & OpenAPI docs
- SQLAlchemy – ORM & async DB handling
- Arq – async Redis-based task queue
- PostgreSQL – persistent storage (Supabase)
- OpenAI – embeddings & GPT-based labeling
- Fly.io – deployment for both API & worker
- scikit-learn – KMeans for semantic clustering
- Redis – distributed cache and task queue

## 📂 Project Structure

```text
backend/
├── app/
│   ├── core/                # Environment config, ARQ worker settings, utilities
│   │   ├── config.py        # Settings for DB, Redis, OpenAI, etc.
│   │   └── arq_worker.py    # ARQ background task configuration
│   ├── db/                  # Database models and session
│   │   ├── base.py          # Base model class
│   │   ├── models.py        # SQLAlchemy models (Board, Item, ClusterLabel, etc.)
│   │   └── session.py       # Async engine and session factory
│   ├── routers/             # API endpoints grouped by feature
│   │   ├── boards.py        # Board CRUD and clustering trigger
│   │   └── items.py         # Item CRUD and embedding generation
│   ├── schemas/             # Pydantic request/response models
│   │   ├── board.py
│   │   ├── item.py
│   │   └── cluster.py
│   ├── services/            # Business logic and external API helpers
│   │   ├── embeddings.py    # OpenAI embedding services
│   │   ├── clustering.py    # KMeans clustering logic
│   │   └── search.py        # Full-text search across boards/items
│   ├── static/              # Uploaded images (served via /static route)
│   ├── main.py              # FastAPI entry point
│   └── redis_utils.py       # Utilities for Redis connections in API routes
├── Dockerfile               # API and worker containerization definition
├── fly.toml                 # Fly.io deployment configuration
├── requirements.txt         # Python dependencies
├── alembic/                 # Migration directory
│   └── versions/            # Auto-generated migration scripts
└── README.md                # Project docs (auto-deployed from this file)
```

## 🛠️ Local Development

### 1. Clone & Install

git clone https://github.com/yourname/moodboard-backend.git
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

### 2. Environment Variables

Copy .env.example → .env:

DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/moodboard
REDIS_URL=redis://localhost:6379
OPENAI_API_KEY=your_openai_key_here
PEXEL_API_KEY=your_pexel_key_here
APP_ENV=development

### 3. Start Services

docker compose up --build

### 4. Run API + Worker

uvicorn app.main:app --reload
arq app.core.arq_worker.WorkerSettings

Visit:
http://localhost:8080/api/docs

---

## 🚢 Deploying to Fly.io

fly launch --name moodboard
fly launch --name moodboard-redis --image flyio/redis
fly secrets set DATABASE_URL=...
fly secrets set REDIS_URL=redis://moodboard-redis.internal:6379
fly secrets set OPENAI_API_KEY=...
fly secrets set PEXEL_API_KEY=your_pexel_key_here
fly deploy

Backend URL:
https://moodboard.fly.dev/api

---

## 🧠 Features

- RESTful CRUD for Boards, Items, and Clusters
- Async background jobs via Redis + Arq
- AI embedding + semantic clustering
- GPT-powered cluster labeling
- /static for image uploads

## 👤 Author

Joseph Nechleba  
https://josephnechleba.com

---
