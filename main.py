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

from src.db import (
    init_db,
    verify_passcode,
    can_generate_report,
    record_report,
    get_user_reports,
    get_all_reports,
    get_report_by_id,
    delete_report,
    create_passcode,
    list_all_passcodes,
    delete_passcode,
    update_passcode_limit,
    update_user_llama_key,
)

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")
logger = logging.getLogger(__name__)

# Environment variables
APP_PASSWORD = os.environ.get("APP_PASSWORD", "policy2026")
DEV_LLAMA_KEY = os.environ.get("LLAMA_CLOUD_API_KEY", "")
GCS_BUCKET = os.environ.get("GCS_BUCKET", "")

# Initialize FastAPI & Database
app = FastAPI(title="Policy Red Team API")
init_db()

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
    info = verify_passcode(password)
    if info:
        return {
            "status": "ok",
            "passcode": info["passcode"],
            "is_admin": info["is_admin"],
            "label": info["label"],
            "reports_used": info["reports_used"],
            "report_limit": info["report_limit"],
            "has_llama_key": bool(info.get("llama_key")),
        }
    raise HTTPException(status_code=401, detail="Invalid passcode. Please check your credentials.")

@app.post("/api/analyze")
async def analyze_policies(
    password: str = Form(...),
    jurisdiction_level: Optional[str] = Form(None),
    jurisdiction: Optional[str] = Form(None),
    target_entity: Optional[str] = Form(None),
    custom_instructions: Optional[str] = Form(""),
    document_roles_json: Optional[str] = Form("[]"),
    enable_web_search: Optional[str] = Form("false"),
    files: List[UploadFile] = File(...),
):
    # Verify passcode and quota
    allowed, reason, user_info = can_generate_report(password)
    if not allowed or not user_info:
        raise HTTPException(status_code=403, detail=reason)

    if not files or len(files) == 0:
        raise HTTPException(status_code=400, detail="No files uploaded.")
    if len(files) > 2:
        raise HTTPException(status_code=400, detail="Max 2 files allowed.")

    files_data = []
    for f in files:
        content = await f.read()
        files_data.append({"name": f.filename, "bytes": content})
        
    # Archive uploaded PDFs to GCS bucket if configured
    if GCS_BUCKET:
        try:
            from google.cloud import storage
            client = storage.Client()
            bucket = client.bucket(GCS_BUCKET)
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            for idx, f_data in enumerate(files_data):
                clean_name = Path(f_data["name"]).name
                blob = bucket.blob(f"uploads/{ts}_{idx}_{clean_name}")
                blob.upload_from_string(f_data["bytes"], content_type="application/pdf")
        except Exception as e:
            logger.warning(f"GCS PDF archive failed: {e}")

    auto_meta = _autodetect_metadata(files_data)
    j_level = jurisdiction_level if jurisdiction_level else auto_meta["level"]
    j_dist = jurisdiction if jurisdiction else auto_meta["jurisdiction"]
    t_entity = target_entity if target_entity else auto_meta["target_entity"]

    # Parse document roles from frontend
    try:
        doc_roles = json.loads(document_roles_json) if document_roles_json else []
    except json.JSONDecodeError:
        doc_roles = []

    web_search_enabled = str(enable_web_search).lower() in ("true", "1", "yes", "on")

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
            actual_faiss_dir = ingest_document(
                pdf_paths=pdf_paths,
                llama_api_key=user_info.get("llama_key") or DEV_LLAMA_KEY or None,
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
                document_roles=doc_roles if doc_roles else None,
                enable_web_search=web_search_enabled,
                faiss_persist_dir=actual_faiss_dir,
                output_path=report_path,
            )
            
            report_dict = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else report.model_dump()
            report_id = report_dict.get("session_id", str(uuid.uuid4()))

            # Identify target and parent pdf names from doc_roles or pdf_names
            target_pdf = ""
            parent_pdf = ""
            for role_item in doc_roles:
                if isinstance(role_item, dict):
                    if role_item.get("role") == "target":
                        target_pdf = role_item.get("filename", "")
                    elif role_item.get("role") == "parent":
                        parent_pdf = role_item.get("filename", "")

            if not target_pdf and pdf_names:
                target_pdf = pdf_names[0]
            if not parent_pdf and len(pdf_names) > 1:
                parent_pdf = pdf_names[1]

            # Save uploaded PDFs locally in storage/uploads/{report_id}
            upload_save_dir = Path("storage") / "uploads" / report_id
            upload_save_dir.mkdir(parents=True, exist_ok=True)
            for f_data in files_data:
                clean_f_name = Path(f_data["name"]).name
                (upload_save_dir / clean_f_name).write_bytes(f_data["bytes"])

            # Store full scoping parameters for past reports inspection
            report_dict["target_pdf"] = target_pdf
            report_dict["parent_pdf"] = parent_pdf
            report_dict["jurisdiction"] = j_dist
            report_dict["jurisdiction_level"] = j_level
            report_dict["target_entity"] = t_entity
            report_dict["custom_instructions"] = custom_instructions or ""
            report_dict["enable_web_search"] = web_search_enabled
            report_dict["document_roles"] = doc_roles
            report_dict["attached_files"] = [f["name"] for f in files_data]

            # Persist report to database and mirror to cloud storage
            record_report(
                report_id=report_id,
                passcode=password,
                user_label=user_info["label"],
                report_data=report_dict,
            )
            
            return report_dict
            
        except Exception as e:
            logger.exception("Analysis failed in backend")
            raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/user/info")
async def get_current_user_info(passcode: str):
    info = verify_passcode(passcode)
    if not info:
        raise HTTPException(status_code=401, detail="Invalid passcode")
    return info

@app.get("/api/user/reports")
async def list_user_reports(passcode: str):
    info = verify_passcode(passcode)
    if not info:
        raise HTTPException(status_code=401, detail="Invalid passcode")
    return get_user_reports(passcode)

@app.post("/api/user/llama_key")
async def set_user_llama_key(passcode: str = Form(...), llama_key: str = Form(...)):
    info = verify_passcode(passcode)
    if not info:
        raise HTTPException(status_code=401, detail="Invalid passcode")
    success = update_user_llama_key(passcode, llama_key)
    return {"status": "ok", "saved": success}

@app.get("/api/reports/{report_id}")
async def get_report_details(report_id: str, passcode: str):
    info = verify_passcode(passcode)
    if not info:
        raise HTTPException(status_code=401, detail="Invalid passcode")
    report = get_report_by_id(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report

@app.get("/api/reports/{report_id}/pdf/{filename}")
async def get_report_pdf(report_id: str, filename: str, passcode: str):
    """Serve or download attached PDFs for a specific report."""
    info = verify_passcode(passcode)
    if not info:
        raise HTTPException(status_code=401, detail="Invalid passcode")
    clean_name = Path(filename).name
    # Check report upload directory
    p_upload = Path("storage") / "uploads" / report_id / clean_name
    if p_upload.exists():
        return FileResponse(p_upload, media_type="application/pdf", filename=clean_name)
    # Check data directory fallback
    p_data = Path("data") / clean_name
    if p_data.exists():
        return FileResponse(p_data, media_type="application/pdf", filename=clean_name)
    raise HTTPException(status_code=404, detail="Attached PDF document not found on server")


@app.delete("/api/reports/{report_id}")
async def delete_report_endpoint(report_id: str, passcode: str):
    """Delete a report by ID. Users can only delete their own; admins can delete any.
    Demo users cannot delete demonstration reports.
    Quota (reports_used) is NOT restored — deletion does not refund generation capacity."""
    info = verify_passcode(passcode)
    if not info:
        raise HTTPException(status_code=401, detail="Invalid passcode")
    if passcode == "DEMO!" and not info["is_admin"]:
        raise HTTPException(status_code=403, detail="Demo users cannot delete demonstration reports.")
    success = delete_report(report_id, passcode=passcode, is_admin=info["is_admin"])
    if not success:
        raise HTTPException(status_code=404, detail="Report not found or not authorized to delete")
    return {"status": "deleted", "report_id": report_id}

# ---------------------------------------------------------------------------
# Administrator Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/admin/passcodes")
async def admin_list_passcodes(admin_passcode: str):
    info = verify_passcode(admin_passcode)
    if not info or not info["is_admin"]:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return list_all_passcodes()

@app.post("/api/admin/passcodes")
async def admin_create_passcode(
    admin_passcode: str = Form(...),
    label: str = Form(...),
    report_limit: int = Form(5),
    custom_passcode: Optional[str] = Form(""),
    llama_key: Optional[str] = Form(""),
):
    info = verify_passcode(admin_passcode)
    if not info or not info["is_admin"]:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return create_passcode(
        label=label, 
        report_limit=report_limit, 
        custom_passcode=custom_passcode or "",
        llama_key=llama_key or ""
    )

@app.delete("/api/admin/passcodes/{passcode}")
async def admin_delete_passcode(passcode: str, admin_passcode: str):
    info = verify_passcode(admin_passcode)
    if not info or not info["is_admin"]:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    success = delete_passcode(passcode)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot delete master admin passcode")
    return {"status": "ok", "deleted": passcode}

@app.post("/api/admin/passcodes/{passcode}/adjust")
async def admin_adjust_passcode(
    passcode: str,
    admin_passcode: str = Form(...),
    report_limit: int = Form(...),
    reset_used: bool = Form(False),
):
    info = verify_passcode(admin_passcode)
    if not info or not info["is_admin"]:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    success = update_passcode_limit(passcode, report_limit, reset_used)
    return {"status": "ok", "updated": passcode}

@app.get("/api/admin/reports")
async def admin_list_all_reports(admin_passcode: str):
    info = verify_passcode(admin_passcode)
    if not info or not info["is_admin"]:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return get_all_reports()

@app.post("/api/feedback")
async def submit_feedback(
    password: str = Form(...),
    rating: int = Form(...),
    category: str = Form(...),
    message: str = Form(...),
    session_id: str = Form(""),
):
    info = verify_passcode(password)
    if not info:
        raise HTTPException(status_code=401, detail="Unauthorized")

    fd = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user": info["label"],
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


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port)

