import asyncio
import os
import shutil
import tempfile
import time
from typing import List

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

from app.rag.retrieve import retrieve
from app.agents.vision_agent import analyze_photos
from app.agents.voice_agent import process_voice
from app.agents.transaction_agent import analyze_transactions
from app.agents.synthesis_agent import synthesize_report

app = FastAPI(title="HackVerse RAG API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    query: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/rag/query")
def rag_query(req: QueryRequest):
    results = retrieve(req.query, k=3)
    return {"query": req.query, "results": results}


@app.post("/agents/vision")
async def agents_vision(files: List[UploadFile] = File(...)):
    temp_paths = []
    try:
        for f in files:
            suffix = os.path.splitext(f.filename)[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                shutil.copyfileobj(f.file, tmp)
                temp_paths.append(tmp.name)
        return analyze_photos(temp_paths)
    finally:
        for p in temp_paths:
            os.remove(p)


@app.post("/agents/voice")
async def agents_voice(file: UploadFile = File(...)):
    suffix = os.path.splitext(file.filename)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        temp_path = tmp.name
    try:
        return process_voice(temp_path)
    finally:
        os.remove(temp_path)


async def _run_agent(
    label: str,
    files_data: list | None,
    single_file: bool,
    handler,
    timings: dict,
):
    if files_data is None:
        return None
    t0 = time.time()
    paths = []
    try:
        if single_file:
            f = files_data
            suffix = os.path.splitext(f.filename)[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                shutil.copyfileobj(f.file, tmp)
                path = tmp.name
            result = await asyncio.to_thread(handler, path)
            paths.append(path)
        else:
            for f in files_data:
                suffix = os.path.splitext(f.filename)[1]
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    shutil.copyfileobj(f.file, tmp)
                    paths.append(tmp.name)
            result = await asyncio.to_thread(handler, paths)
        return result
    finally:
        for p in paths:
            os.remove(p)
        timings[label] = round(time.time() - t0, 2)


@app.post("/report")
async def report(
    photos: List[UploadFile] = File(None),
    audio: UploadFile = File(None),
    transactions: UploadFile = File(None),
):
    timings = {}

    vision_coro = _run_agent("vision", photos, False, analyze_photos, timings)
    voice_coro = _run_agent("voice", audio, True, process_voice, timings)
    txn_coro = _run_agent("transactions", transactions, True, analyze_transactions, timings)

    coros = []
    mapping = []
    if photos is not None:
        coros.append(vision_coro)
        mapping.append("vision")
    if audio is not None:
        coros.append(voice_coro)
        mapping.append("voice")
    if transactions is not None:
        coros.append(txn_coro)
        mapping.append("transactions")

    gathered = await asyncio.gather(*coros) if coros else []

    vision_result = None
    voice_result = None
    transaction_result = None
    for label, result in zip(mapping, gathered):
        if label == "vision":
            vision_result = result
        elif label == "voice":
            voice_result = result
        elif label == "transactions":
            transaction_result = result

    input_errors = []
    missing = []

    if vision_result is None:
        missing.append("photos")
    elif "error" in vision_result:
        input_errors.append("photos: could not process image(s)")

    if voice_result is None:
        missing.append("voice")
    elif "error" in voice_result:
        input_errors.append("voice: could not process audio")

    if transaction_result is None:
        missing.append("transactions")
    elif "error" in transaction_result:
        input_errors.append("transactions: could not parse CSV columns")

    t0 = time.time()
    rag_context = retrieve("MSME working capital lending guidance", k=3)
    timings["rag"] = round(time.time() - t0, 2)

    t0 = time.time()
    report_data = synthesize_report(
        vision_result, voice_result, transaction_result, rag_context
    )
    timings["synthesis"] = round(time.time() - t0, 2)

    report_data["missing_inputs"] = missing
    report_data["input_errors"] = input_errors
    report_data["_timings"] = timings

    print(f"[timings] {timings}", flush=True)
    return report_data
