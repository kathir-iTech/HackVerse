import os
import uuid

import chromadb
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "sidbi_docs")
CHROMA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "chroma_db")


def ingest():
    docs = []
    for fname in os.listdir(DATA_DIR):
        if fname.lower().endswith(".pdf"):
            path = os.path.join(DATA_DIR, fname)
            loader = PyPDFLoader(path)
            docs.extend(loader.load())

    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
    chunks = splitter.split_documents(docs)

    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_or_create_collection(name="sidbi_docs")

    ids = [str(uuid.uuid4()) for _ in chunks]
    documents = [c.page_content for c in chunks]
    metadatas = [{"source": c.metadata.get("source", "unknown")} for c in chunks]

    collection.add(documents=documents, ids=ids, metadatas=metadatas)
    print(f"Ingested {len(chunks)} chunks from {len(docs)} pages into {CHROMA_DIR}")


if __name__ == "__main__":
    ingest()
