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

<pre> ```bash backend/ ├── app/ │ ├── core/ # environment, settings, worker config │ ├── db/ # models, database session, migrations │ ├── routers/ # API endpoints organized by feature │ ├── schemas/ # Pydantic schemas for request/response │ ├── main.py # FastAPI entry point │ └── core/arq_worker.py # ARQ worker job settings ├── Dockerfile └── fly.toml ``` </pre>

## 🛠️ Local Development

### 1. Clone & Install

git clone https://github.com/yourname/moodboard.git
cd moodboard/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

### 2. Environment Variables

Copy .env.example → .env:

DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/moodboard
REDIS_URL=redis://localhost:6379
OPENAI_API_KEY=your_openai_key_here
ENV=development

### 3. Start Services

docker compose up

### 4. Run API + Worker

uvicorn app.main:app --reload
arq app.core.arq_worker.WorkerSettings

Visit:
http://localhost:8000/api/docs

---

## 🚢 Deploying to Fly.io

fly launch --name moodboard
fly launch --name moodboard-redis --image flyio/redis
fly secrets set DATABASE_URL=...
fly secrets set REDIS_URL=redis://moodboard-redis.internal:6379
fly secrets set OPENAI_API_KEY=...
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
