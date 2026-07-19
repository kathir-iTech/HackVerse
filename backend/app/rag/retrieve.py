import os

import chromadb

CHROMA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "chroma_db")

_client = chromadb.PersistentClient(path=CHROMA_DIR)
_collection = _client.get_collection(name="sidbi_docs")


def retrieve(query: str, k: int = 3):
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
