import os

import chromadb

CHROMA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "chroma_db")

_client = None
_collection = None

try:
    _client = chromadb.PersistentClient(path=CHROMA_DIR)
    _collection = _client.get_collection(name="sidbi_docs")
except Exception:
    _collection = None


def retrieve(query: str, k: int = 3):
    if _collection is None:
        return [
            {
                "content": "RAG collection not available — run `python -m app.rag.ingest` first.",
                "source": "system",
            }
        ]
    results = _collection.query(query_texts=[query], n_results=k)
    out = []
    for i in range(len(results["ids"][0])):
        out.append(
            {
                "content": results["documents"][0][i],
                "source": (
                    results["metadatas"][0][i].get("source", "unknown")
                    if results["metadatas"]
                    else "unknown"
                ),
            }
        )
    return out
