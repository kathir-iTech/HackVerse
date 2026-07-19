import os

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma

CHROMA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "chroma_db")

_embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
_db = Chroma(
    embedding_function=_embeddings,
    persist_directory=CHROMA_DIR,
)


def retrieve(query: str, k: int = 3):
    results = _db.similarity_search(query, k=k)
    return [
        {
            "content": doc.page_content,
            "source": doc.metadata.get("source", "unknown"),
        }
        for doc in results
    ]
