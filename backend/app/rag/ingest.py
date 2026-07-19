import os

from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
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

    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

    os.makedirs(CHROMA_DIR, exist_ok=True)
    db = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=CHROMA_DIR,
    )
    print(f"Ingested {len(chunks)} chunks from {len(docs)} pages into {CHROMA_DIR}")


if __name__ == "__main__":
    ingest()
