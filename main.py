import asyncio
import json
import logging
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Depends
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import pypdf

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")
logger = logging.getLogger(__name__)

# Environment variables
APP_PASSWORD = os.environ.get("APP_PASSWORD", "policy2026")
DEV_LLAMA_KEY = os.environ.get("LLAMA_CLOUD_API_KEY", "")
GCS_BUCKET = os.environ.get("GCS_BUCKET", "")

# Initialize FastAPI
app = FastAPI(title="Policy Red Team API")

# Add CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _extract_text_sample(pdf_bytes: bytes, max_pages: int = 3) -> str:
    try:
        from io import BytesIO
        reader = pypdf.PdfReader(BytesIO(pdf_bytes))
        return " ".join((p.extract_text() or "") for p in reader.pages[:max_pages]).lower()
    except Exception as e:
        logger.error(f"Error extracting text: {e}")
        return ""

def _autodetect_metadata(files_data: list[dict]) -> dict:
    if not files_data:
        return {"level": "Federal", "jurisdiction": "Pakistan", "target_entity": "Regulated Entities & Businesses"}
    
    combined_text = " ".join(_extract_text_sample(f["bytes"], max_pages=3) for f in files_data).lower()
    file_names = " ".join(f["name"] for f in files_data).lower()
    full_search = combined_text + " " + file_names

    level = "Federal"
    jurisdiction = "Pakistan"
    
    if any(kw in full_search for kw in ["cda", "capital development authority", "islamabad"]):
        level = "Municipal"
        jurisdiction = "Islamabad, Pakistan"
    elif any(kw in full_search for kw in ["rda", "rawalpindi"]):
        level = "Municipal"
        jurisdiction = "Rawalpindi, Punjab, Pakistan"
    elif any(kw in full_search for kw in ["lda", "lahore"]):
        level = "Municipal"
        jurisdiction = "Lahore, Punjab, Pakistan"
    elif any(kw in full_search for kw in ["kda", "sbca", "karachi"]):
        level = "Municipal"
        jurisdiction = "Karachi, Sindh, Pakistan"
    elif "punjab" in full_search:
        level = "Provincial"
        jurisdiction = "Punjab, Pakistan"
    elif "sindh" in full_search:
        level = "Provincial"
        jurisdiction = "Sindh, Pakistan"
    elif any(kw in full_search for kw in ["khyber", "pakhtunkhwa", "kpk"]):
        level = "Provincial"
        jurisdiction = "KPK, Pakistan"
    elif "balochistan" in full_search:
        level = "Provincial"
        jurisdiction = "Balochistan, Pakistan"

    target_entity = "Regulated Entities & Businesses"
    if any(kw in full_search for kw in ["housing", "building", "developer", "construction", "real estate", "cda ordinance", "master plan", "zoning"]):
        target_entity = "Real Estate Developers & Builders"
    elif any(kw in full_search for kw in ["bank", "banking", "finance", "microfinance", "sbp"]):
        target_entity = "Financial Institutions & Commercial Banks"
    elif any(kw in full_search for kw in ["tax", "income tax", "customs", "sales tax", "fbr", "duty", "duties"]):
        target_entity = "Taxpayers & Commercial Importers"
    elif any(kw in full_search for kw in ["pharma", "drug", "health", "medicine", "medical"]):
        target_entity = "Pharmaceutical Companies & Manufacturers"
    elif any(kw in full_search for kw in ["power", "electricity", "nepra", "energy", "solar"]):
        target_entity = "Power Generation & Distribution Companies"

    return {"level": level, "jurisdiction": jurisdiction, "target_entity": target_entity}

def _save_feedback_to_gcs(feedback: dict) -> bool:
    if not GCS_BUCKET:
        return False
    try:
        from google.cloud import storage
        client = storage.Client()
        bucket = client.bucket(GCS_BUCKET)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
        filename = f"feedback/{ts}_{uuid.uuid4().hex[:6]}_feedback.json"
        bucket.blob(filename).upload_from_string(
            json.dumps(feedback, indent=2), content_type="application/json"
        )
        return True
    except Exception as e:
        logger.error(f"GCS feedback save failed: {e}")
        return False

# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------

@app.post("/api/auth")
async def authenticate(password: str = Form(...)):
    if password == APP_PASSWORD:
        return {"status": "ok"}
    raise HTTPException(status_code=401, detail="Incorrect password")

@app.post("/api/analyze")
async def analyze_policies(
    password: str = Form(...),
    jurisdiction_level: Optional[str] = Form(None),
    jurisdiction: Optional[str] = Form(None),
    target_entity: Optional[str] = Form(None),
    custom_instructions: Optional[str] = Form(""),
    files: List[UploadFile] = File(...),
):
    if password != APP_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not files or len(files) == 0:
        raise HTTPException(status_code=400, detail="No files uploaded.")
    if len(files) > 2:
        raise HTTPException(status_code=400, detail="Max 2 files allowed.")

    files_data = []
    for f in files:
        content = await f.read()
        files_data.append({"name": f.filename, "bytes": content})
        
    auto_meta = _autodetect_metadata(files_data)
    j_level = jurisdiction_level if jurisdiction_level else auto_meta["level"]
    j_dist = jurisdiction if jurisdiction else auto_meta["jurisdiction"]
    t_entity = target_entity if target_entity else auto_meta["target_entity"]

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        faiss_dir = tmp_path / "faiss"
        faiss_dir.mkdir()
        
        pdf_paths = []
        pdf_names = []
        for f_data in files_data:
            dest = tmp_path / f_data["name"]
            dest.write_bytes(f_data["bytes"])
            pdf_paths.append(dest)
            pdf_names.append(f_data["name"])

        try:
            from src.ingest_policy import ingest_document
            ingest_document(
                pdf_paths=pdf_paths,
                llama_api_key=DEV_LLAMA_KEY or None,
                output_dir=faiss_dir,
            )

            from src.orchestration.runner import run_audit_simple
            report_path = tmp_path / f"report_{uuid.uuid4().hex[:8]}.json"
            
            report = await run_audit_simple(
                pdf_names=pdf_names,
                jurisdiction=j_dist,
                jurisdiction_level_str=j_level,
                target_entity=t_entity,
                custom_instructions=custom_instructions,
                output_path=report_path,
            )
            
            if report_path.exists():
                return json.loads(report_path.read_text(encoding="utf-8"))
            return report.model_dump()
            
        except Exception as e:
            logger.exception("Analysis failed in backend")
            raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/feedback")
async def submit_feedback(
    password: str = Form(...),
    rating: int = Form(...),
    category: str = Form(...),
    message: str = Form(...),
    session_id: str = Form(""),
):
    if password != APP_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

    fd = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "rating": rating,
        "category": category,
        "message": message,
        "session_id": session_id,
    }
    success = _save_feedback_to_gcs(fd)
    if not success:
        logger.info(f"LOCAL FEEDBACK: {json.dumps(fd, indent=2)}")
    return {"status": "ok", "saved_remotely": success}


# ---------------------------------------------------------------------------
# Static Files & Frontend Routing
# ---------------------------------------------------------------------------
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def serve_index():
    return FileResponse("static/index.html")
