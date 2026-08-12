"""
Policy Red Team — Streamlit Web App
=====================================
Minimal MVP for 1-2 tester deployment on Cloud Run.

Environment variables required:
  APP_PASSWORD          — shared password to access the app
  APP_MODE              — "developer_pays" or "user_key"
  LLAMA_CLOUD_API_KEY   — required when APP_MODE=developer_pays
  GOOGLE_CLOUD_PROJECT  — GCP project for Vertex AI embeddings
  GCS_BUCKET            — GCS bucket for feedback storage
  GOOGLE_CLOUD_LOCATION — Vertex AI region (default: us-central1)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

# ---------------------------------------------------------------------------
# Page config — must be the very first Streamlit call
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Policy Red Team",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Project root on sys.path
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
APP_PASSWORD = os.environ.get("APP_PASSWORD", "policy2026")
APP_MODE = os.environ.get("APP_MODE", "developer_pays")   # "developer_pays" | "user_key"
DEV_LLAMA_KEY = os.environ.get("LLAMA_CLOUD_API_KEY", "")
GCS_BUCKET = os.environ.get("GCS_BUCKET", "")
MAX_PAGES = 80
MAX_FILES = 2
PAKISTAN_KEYWORDS = [
    "pakistan", "punjab", "sindh", "khyber", "pakhtunkhwa", "balochistan",
    "islamabad", "karachi", "lahore", "rawalpindi", "peshawar", "quetta",
    "secp", "fbr", "sbp", "pta", "nepra", "ogra", "ccp",
    "rda", "cda", "lda", "kda", "sbca", "nha",
    "cantonment", "ordinance", "gazette", "statutory regulatory order",
    "provincial assembly", "national assembly", "senate of pakistan",
]

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

.app-header {
    background: linear-gradient(135deg, #1a1f2e 0%, #0d1117 100%);
    border-bottom: 1px solid #30363d;
    padding: 1.2rem 2rem;
    margin: -1rem -1rem 2rem -1rem;
    display: flex;
    align-items: center;
    gap: 0.75rem;
}
.app-header h1 { font-size: 1.5rem; font-weight: 700; color: #e6edf3; margin: 0; }
.app-header .badge {
    background: #1f6feb; color: #fff; font-size: 0.65rem; font-weight: 600;
    padding: 0.2rem 0.5rem; border-radius: 4px; text-transform: uppercase; letter-spacing: 0.08em;
}
.banner-info {
    background: linear-gradient(90deg, #0d1117 0%, #0f2744 100%);
    border: 1px solid #1f6feb; border-left: 4px solid #1f6feb;
    border-radius: 6px; padding: 1rem 1.2rem; margin-bottom: 1.5rem;
    color: #c9d1d9; font-size: 0.87rem; line-height: 1.6;
}
.banner-warn {
    background: linear-gradient(90deg, #0d1117 0%, #291d00 100%);
    border: 1px solid #bb8009; border-left: 4px solid #d29922;
    border-radius: 6px; padding: 0.85rem 1.1rem; margin-bottom: 1rem;
    color: #c9d1d9; font-size: 0.85rem;
}
.section-label {
    font-size: 0.75rem; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.1em; color: #8b949e; margin-bottom: 0.4rem;
}
.result-card {
    background: #161b22; border: 1px solid #30363d;
    border-radius: 8px; padding: 1.2rem 1.5rem; margin-bottom: 1rem;
}
.result-card h4 { color: #58a6ff; margin: 0 0 0.5rem 0; font-size: 0.95rem; }
.result-card p  { color: #c9d1d9; margin: 0; font-size: 0.88rem; line-height: 1.6; }
.badge-critical { background:#da3633; color:#fff; padding:2px 8px; border-radius:4px; font-size:0.78rem; font-weight:600; }
.badge-high     { background:#d29922; color:#000; padding:2px 8px; border-radius:4px; font-size:0.78rem; font-weight:600; }
.badge-medium   { background:#1f6feb; color:#fff; padding:2px 8px; border-radius:4px; font-size:0.78rem; font-weight:600; }
.badge-low      { background:#238636; color:#fff; padding:2px 8px; border-radius:4px; font-size:0.78rem; font-weight:600; }
.divider { border: none; border-top: 1px solid #21262d; margin: 1.5rem 0; }
</style>
""", unsafe_allow_html=True)


# ===========================================================================
# HELPERS
# ===========================================================================

def _check_password() -> bool:
    if st.session_state.get("authenticated"):
        return True
    st.markdown("""
    <div style="max-width:420px; margin:8vh auto; text-align:center;">
        <span style="font-size:2.5rem;">⚖️</span>
        <h2 style="color:#e6edf3; margin:0.5rem 0 0.2rem 0;">Policy Red Team</h2>
        <p style="color:#8b949e; font-size:0.85rem;">Beta Access — Enter password to continue</p>
    </div>
    """, unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 1.5, 1])
    with mid:
        pwd = st.text_input("Password", type="password", key="pwd_input",
                            label_visibility="collapsed", placeholder="Enter access password…")
        if st.button("Enter →", use_container_width=True, type="primary"):
            if pwd == APP_PASSWORD:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Incorrect password.")
    return False


def _get_page_count(pdf_bytes: bytes) -> int:
    try:
        from pypdf import PdfReader
        from io import BytesIO
        return len(PdfReader(BytesIO(pdf_bytes)).pages)
    except Exception:
        return 0


def _extract_text_sample(pdf_bytes: bytes, max_pages: int = 3) -> str:
    try:
        from pypdf import PdfReader
        from io import BytesIO
        reader = PdfReader(BytesIO(pdf_bytes))
        return " ".join((p.extract_text() or "") for p in reader.pages[:max_pages]).lower()
    except Exception:
        return ""


def _is_pakistan_doc(pdf_bytes: bytes) -> bool:
    text = _extract_text_sample(pdf_bytes)
    return any(kw in text for kw in PAKISTAN_KEYWORDS)


def _save_feedback_to_gcs(feedback: dict) -> bool:
    if not GCS_BUCKET:
        logger.warning("GCS_BUCKET not set — feedback not saved remotely.")
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
        logger.info("Feedback saved → gs://%s/%s", GCS_BUCKET, filename)
        return True
    except Exception as e:
        logger.error("GCS feedback save failed: %s", e)
        return False


def _autodetect_metadata(files: list[dict]) -> dict:
    """Auto-detect jurisdiction level, location, and target entity from document text."""
    if not files:
        return {"level": "Federal", "jurisdiction": "Pakistan", "target_entity": "Regulated Entities & Businesses"}
    
    combined_text = " ".join(_extract_text_sample(f["bytes"], max_pages=3) for f in files).lower()
    file_names = " ".join(f["name"] for f in files).lower()
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


def _severity_badge(severity: str) -> str:
    return f'<span class="badge-{severity.lower()}">{severity.upper()}</span>'


# ===========================================================================
# MAIN APP
# ===========================================================================

def main() -> None:
    if not _check_password():
        return

    st.markdown("""
    <div class="app-header">
        <span style="font-size:1.8rem;">⚖️</span>
        <h1>Policy Red Team</h1>
        <span class="badge">Beta</span>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="banner-info">
        <strong>🇵🇰 Beta Notice — Pakistan Laws Only</strong><br>
        This tool is designed specifically for <strong>Pakistani laws, regulations, and statutory instruments</strong>
        (federal acts, provincial statutes, and municipal bylaws). Analysis accuracy is optimised for Pakistan's
        legal framework. Results for other jurisdictions may be unreliable.<br><br>
        <strong>🧪 Active Testing Phase</strong> — We value your feedback! After running an analysis, please use
        the feedback form at the bottom of the page to report issues, suggest improvements, or share your experience.
        Your input directly shapes the development of this system.
    </div>
    """, unsafe_allow_html=True)

    col_left, col_right = st.columns([1, 1.6], gap="large")

    with col_left:
        # ---- Mode B: API Key ----
        llama_key = DEV_LLAMA_KEY
        if APP_MODE == "user_key":
            st.markdown('<p class="section-label">LlamaCloud API Key</p>', unsafe_allow_html=True)
            llama_key = st.text_input(
                "LlamaCloud API Key",
                type="password",
                placeholder="llx-…  (get yours free at cloud.llamaindex.ai)",
                label_visibility="collapsed",
                help="Used only to parse your PDFs. Never stored.",
            )
            if not llama_key:
                st.info("ℹ️ Get a free key at [cloud.llamaindex.ai](https://cloud.llamaindex.ai/api-key)")

        # ---- PDF Upload / URL ----
        st.markdown('<p class="section-label">Provide Policy PDFs</p>', unsafe_allow_html=True)
        tab1, tab2 = st.tabs(["Upload File", "From URL (Fallback)"])
        
        uploaded_files = []
        
        with tab1:
            st_files = st.file_uploader(
                "Upload PDFs",
                type=["pdf"],
                accept_multiple_files=True,
                label_visibility="collapsed",
                help=f"Max {MAX_FILES} PDF files · max {MAX_PAGES} pages total",
            )
            if st_files:
                uploaded_files.extend(st_files)
                
        with tab2:
            st.caption("If the file uploader fails, paste a direct link to a PDF here.")
            pdf_url = st.text_input("Direct URL to PDF", placeholder="https://example.com/document.pdf", label_visibility="collapsed")
            if pdf_url:
                import urllib.request
                try:
                    req = urllib.request.Request(pdf_url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=15) as response:
                        url_bytes = response.read()
                    
                    class DownloadedFile:
                        def __init__(self, name, data):
                            self.name = name
                            self.data = data
                        def read(self):
                            return self.data
                    
                    filename = pdf_url.split("/")[-1] or "document.pdf"
                    if "?" in filename:
                        filename = filename.split("?")[0]
                    if not filename.lower().endswith(".pdf"):
                        filename += ".pdf"
                        
                    uploaded_files.append(DownloadedFile(filename, url_bytes))
                    st.success(f"✅ Downloaded {filename} successfully!")
                except Exception as e:
                    st.error(f"Failed to fetch PDF: {e}")

        valid_files: list = []
        total_pages = 0

        if uploaded_files:
            if len(uploaded_files) > MAX_FILES:
                st.error(f"❌ Max {MAX_FILES} files allowed. Please remove {len(uploaded_files) - MAX_FILES} file(s).")
            else:
                for uf in uploaded_files:
                    pdf_bytes = uf.read()
                    pages = _get_page_count(pdf_bytes)
                    is_pak = _is_pakistan_doc(pdf_bytes)
                    total_pages += pages
                    valid_files.append({"bytes": pdf_bytes, "pages": pages, "name": uf.name})

                    if not is_pak:
                        st.markdown(f"""
                        <div class="banner-warn">
                          ⚠️ <strong>{uf.name}</strong> — Pakistan-specific legal content not detected
                          in the first 3 pages. You can still proceed, but accuracy may be reduced.
                        </div>""", unsafe_allow_html=True)

                    st.markdown(f"✅ **{uf.name}** — {pages} page{'s' if pages != 1 else ''}")

                if total_pages > MAX_PAGES:
                    st.error(f"❌ Collective page count ({total_pages}) exceeds the {MAX_PAGES}-page limit.")
                    valid_files = []
                elif total_pages > 0:
                    st.caption(f"📄 Total: {total_pages} / {MAX_PAGES} pages")

        auto_meta = _autodetect_metadata(valid_files) if valid_files else {"level": "Federal", "jurisdiction": "Pakistan", "target_entity": "Regulated Entities & Businesses"}

        # ---- Optional Focus Settings ----
        with st.expander("⚙️ Focus & Target Settings (Optional)", expanded=False):
            levels = ["Municipal", "Provincial", "Federal"]
            auto_level = auto_meta["level"]
            default_index = levels.index(auto_level) if auto_level in levels else 2
            
            jd_level = st.selectbox(
                "Jurisdiction Level",
                levels,
                index=default_index,
                help="Auto-detected from your document. You can override it here.",
            )
            jurisdiction = st.text_input(
                "Jurisdiction",
                value=auto_meta["jurisdiction"],
                help="Auto-detected from your document. You can override it here.",
            )
            target_entity = st.text_input(
                "Target Entity",
                value=auto_meta["target_entity"],
                help="Auto-detected from your document. You can override it here.",
            )
            custom_instructions = st.text_area(
                "Custom Focus Instructions (optional)",
                placeholder="e.g. Focus on fee schedule ambiguities or penalty exemptions.",
                height=80,
                help="Optional guidance for the Attacker agent.",
            )

        st.markdown('<hr class="divider">', unsafe_allow_html=True)
        can_run = (
            bool(valid_files)
            and (APP_MODE == "developer_pays" or bool(llama_key))
        )
        run_clicked = st.button("▶ Run Red Team Analysis", type="primary",
                                use_container_width=True, disabled=not can_run)
        if not can_run:
            hints = []
            if not valid_files: hints.append("upload at least one valid PDF")
            if APP_MODE == "user_key" and not llama_key: hints.append("enter your LlamaCloud API key")
            if hints: st.caption("ℹ️ To run: " + ", ".join(hints) + ".")

        st.caption("⏱️ Analysis typically takes **3–8 minutes**. Keep this tab open.")


    # ===========================================================================
    # RESULTS PANEL
    # ===========================================================================
    with col_right:
        if run_clicked and can_run:
            st.markdown('<p class="section-label">Analysis Progress</p>', unsafe_allow_html=True)
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)
                faiss_dir = tmp_path / "faiss"
                faiss_dir.mkdir()
                pdf_paths = []
                for vf in valid_files:
                    dest = tmp_path / vf["name"]
                    dest.write_bytes(vf["bytes"])
                    pdf_paths.append(dest)
                pdf_names = [vf["name"] for vf in valid_files]

                progress = st.progress(0, text="Starting…")
                status_box = st.status("Initialising pipeline…", expanded=True)
                try:
                    with status_box:
                        st.write("📄 **Step 1 / 3** — Parsing PDFs via LlamaCloud…")
                    progress.progress(10, text="Parsing & indexing PDFs…")

                    from src.ingest_policy import ingest_document
                    ingest_document(
                        pdf_paths=pdf_paths,
                        llama_api_key=llama_key or None,
                        output_dir=faiss_dir,
                    )

                    with status_box:
                        st.write("✅ PDFs parsed and indexed.")
                        st.write("🤖 **Step 2 / 3** — Running multi-agent red team analysis…")
                        st.write("   → Attacker is scanning for loopholes…")
                    progress.progress(35, text="Multi-agent debate running…")

                    from src.orchestration.runner import run_audit_simple
                    report_path = tmp_path / f"report_{uuid.uuid4().hex[:8]}.json"
                    report = asyncio.run(
                        run_audit_simple(
                            pdf_names=pdf_names,
                            jurisdiction=jurisdiction,
                            jurisdiction_level_str=jd_level,
                            target_entity=target_entity,
                            custom_instructions=custom_instructions,
                            output_path=report_path,
                        )
                    )

                    with status_box:
                        st.write("✅ Analysis complete.")
                        st.write("📊 **Step 3 / 3** — Rendering report…")
                    progress.progress(95, text="Rendering…")

                    st.session_state["last_report"] = report
                    st.session_state["last_report_json"] = (
                        report_path.read_text(encoding="utf-8")
                        if report_path.exists() else report.model_dump_json(indent=2)
                    )
                    status_box.update(label="✅ Analysis complete!", state="complete", expanded=False)
                    progress.progress(100, text="Done!")

                except Exception as e:
                    status_box.update(label="❌ Analysis failed", state="error", expanded=True)
                    progress.empty()
                    st.error(f"**Error**: {e}")
                    logger.exception("Analysis failed")

        # ---- Render stored report ----
        if "last_report" in st.session_state:
            report = st.session_state["last_report"]
            report_json_str = st.session_state.get("last_report_json", "{}")

            st.markdown('<hr class="divider">', unsafe_allow_html=True)
            st.markdown('<p class="section-label">Analysis Results</p>', unsafe_allow_html=True)

            sev = report.severity_classification.value
            st.markdown(f"""
            <div class="result-card">
                <h4>🎯 Core Finding</h4>
                <p><strong>Exploit Vector:</strong> {report.exploit_vector.value} &nbsp;·&nbsp;
                   <strong>Severity:</strong> {_severity_badge(sev)} &nbsp;·&nbsp;
                   <strong>Confidence:</strong> {report.legal_confidence_score:.2f}</p>
                <p style="margin-top:0.7rem;">{report.canonical_exploit.summary}</p>
            </div>""", unsafe_allow_html=True)

            c1, c2 = st.columns(2)
            with c1:
                cs = report.citizen_score
                st.markdown(f"""
                <div class="result-card">
                    <h4>👥 Citizen Impact</h4>
                    <p>Harm: <strong>{cs.harm_score:.2f}</strong> · Benefit: <strong>{cs.benefit_score:.2f}</strong>
                    <br>{cs.affected_population}</p>
                </div>""", unsafe_allow_html=True)
            with c2:
                bs = report.business_score
                st.markdown(f"""
                <div class="result-card">
                    <h4>🏢 Business Impact</h4>
                    <p>Harm: <strong>{bs.harm_score:.2f}</strong> · Benefit: <strong>{bs.benefit_score:.2f}</strong>
                    <br>{bs.affected_population}</p>
                </div>""", unsafe_allow_html=True)

            st.markdown(f"""
            <div class="result-card">
                <h4>🔧 Remediation Recommendation</h4>
                <p>{report.remediation_recommendation}</p>
            </div>""", unsafe_allow_html=True)

            if report.debate_transcript:
                with st.expander(f"📜 Debate Transcript ({len(report.debate_transcript)} turn(s))", expanded=False):
                    for turn in report.debate_transcript:
                        st.markdown(f"**Turn {turn.turn_number}** — `{turn.turn_verdict.value}`")
                        st.markdown(f"> **Attacker**: {turn.exploit_claim}")
                        st.markdown(f"> **Defender**: {turn.defender_rebuttal}")
                        cites_a = ", ".join(turn.attacker_citations) or "None"
                        cites_d = ", ".join(turn.defender_citations) or "None"
                        st.caption(f"Attacker cited: {cites_a}  |  Defender cited: {cites_d}")
                        st.divider()

            if report.statutory_citations:
                with st.expander(f"📚 Statutory Citations ({len(report.statutory_citations)})", expanded=False):
                    for cite in report.statutory_citations:
                        st.markdown(f"**{cite.section_id}** — *{cite.source_document}*" +
                                    (f", p. {cite.page_number}" if cite.page_number else ""))
                        st.markdown(f"> {cite.quoted_text}")
                        st.caption(f"FAISS score: {cite.retrieval_score:.4f}")

            st.download_button(
                label="📥 Download Full Report (JSON)",
                data=report_json_str,
                file_name=f"policy_redteam_{report.session_id[:8]}.json",
                mime="application/json",
                use_container_width=True,
            )

    # ===========================================================================
    # FEEDBACK SECTION
    # ===========================================================================
    if "last_report" in st.session_state:
        st.markdown('<hr class="divider">', unsafe_allow_html=True)
        st.markdown('<p class="section-label">Submit Feedback</p>', unsafe_allow_html=True)
        st.markdown("**💬 How was this analysis?** Your feedback directly shapes the development of this system.")

        with st.form("feedback_form", clear_on_submit=True):
            fb1, fb2 = st.columns([1, 3])
            with fb1:
                rating = st.select_slider(
                    "Rating", options=[1, 2, 3, 4, 5], value=4,
                    format_func=lambda x: "★" * x + "☆" * (5 - x),
                )
                category = st.selectbox("Category", [
                    "Accuracy Issue", "Missing Loophole", "Hallucinated Citation",
                    "UI / UX Issue", "Feature Request", "General Feedback",
                ])
            with fb2:
                message = st.text_area(
                    "Message", height=104, label_visibility="collapsed",
                    placeholder="e.g. The defender agent missed Section 12 of the Punjab LGA 2022…",
                )

            if st.form_submit_button("Submit Feedback →", type="primary"):
                report = st.session_state.get("last_report")
                fd = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "rating": rating, "category": category, "message": message,
                    "jurisdiction": report.jurisdiction if report else "",
                    "target_entity": report.target_entity if report else "",
                    "session_id": report.session_id if report else "",
                    "mode": APP_MODE,
                }
                if _save_feedback_to_gcs(fd):
                    st.success("✅ Thank you! Feedback saved.")
                else:
                    st.warning("⚠️ Remote save failed — feedback noted locally.")
                    logger.info("LOCAL FEEDBACK: %s", json.dumps(fd, indent=2))


if __name__ == "__main__":
    main()
