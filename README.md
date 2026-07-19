# HackVerse Monorepo

## Backend (FastAPI + RAG)

```bash
cd backend
python -m venv venv
venv\Scripts\activate    # Windows
# source venv/bin/activate  # macOS/Linux
pip install -r requirements.txt

# Ingest PDFs from data/sidbi_docs/ into ChromaDB
python -m app.rag.ingest

# Start the server
uvicorn app.main:app --reload
```

- `GET /health` — health check
- `POST /rag/query` — send `{"query": "..."}`, get top-3 chunks back

Place PDF files inside `backend/data/sidbi_docs/` before running the ingest script.

## Frontend (Next.js)

```bash
cd frontend
npm install
npm run dev
```

Opens at `http://localhost:3000`.

## Environment

Copy placeholders — the app uses `.env` files for secrets:

```
# backend/.env
OPENROUTER_API_KEY=your_key_here
HF_TOKEN=your_token_here
```
