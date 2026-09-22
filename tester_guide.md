# ⚖️ Policy Red Team — Complete Tester Guide

Welcome to the **Policy Red Team** beta testing phase!

As an International Relations / Public Policy student with knowledge of AI, your domain expertise is crucial. This platform simulates how adversarial actors (such as aggressive real estate developers, multinational corporations, or tax-evading entities) might exploit legal loopholes, statutory ambiguities, or jurisdictional conflicts in public policies.

---

## 🎯 What is Policy Red Team?

**Policy Red Team** is an automated regulatory stress-testing platform powered by multi-agent AI (Google ADK 2.0). It ingests statutory legal texts (Acts, Ordinances, Statutory Rules, S.R.O.s, municipal bylaws) and private sector compliance frameworks (e.g., housing scheme policies) and subjects them to an adversarial debate:

1. **The Attacker (Red Team):** Scours the target policy for definitional gaps, negative exemption criteria, penalty asymmetries, and jurisdictional overreach to construct an exploit.
2. **The Defender (Blue Team):** Defends the regulation by citing qualifying clauses, enforcement procedures, or companion parent statutes (with optional live Google Search grounding).
3. **The Judge Agent:** Evaluates the debate under Pakistan statutory law, assigns a quantitative severity classification (Critical, High, Medium, Low), measures legal confidence, and calculates harm/benefit impacts for citizens and businesses.

---

## 📋 Document Suitability Guidelines (Read Before Ingesting)

To achieve high-confidence results and avoid unproductive audits, follow these document selection rules:

### ✅ Optimal Documents to Ingest
- **Subordinate Legislation & Bylaws:** Municipal traffic policies (e.g., CDA Speed Breakers Policy), zoning regulations, building control bylaws.
- **Statutory Notifications & S.R.O.s:** FBR customs/tax schedules, NEPRA power tariff directives, SECP corporate compliance guidelines.
- **Operational Rules under an Act:** Rules with concrete rights, duties, thresholds, timelines, or penal sanctions.
- **Parent Statute (as Supporting Document):** The governing primary Act (e.g. CDA Ordinance 1960 or Local Government Act) providing statutory context.

### ❌ Incompatible / Inefficient Documents (Do NOT Ingest)
- **High-Level Policy Visions & Manifestos:** Aspirational whitepapers (e.g. *"National Digital Vision 2030"*) lacking binding clauses or legal penalties.
- **Line-by-line Compliance Checklists:** The system is an adversarial engine, not a standard compliance checkbox tool.
- **Court Judgements & Case Law Briefs:** The engine audits legislative and statutory text, not judicial jurisprudence or case precedents.
- **Scanned Non-OCR PDFs:** Photocopied image PDFs without extractable text cannot be parsed by the vector indexing pipeline.
- **Non-Pakistani Documents:** The reasoning models and legal rubrics are tailored for the statutory architecture of Pakistan.

---

## 🏢 How to Test Private Sector Policies (Compliance Check)

If you are a private entity (like a housing society, developer, or corporation) wanting to test if your internal policy complies with Pakistani law (i.e., avoiding *ultra vires* rules):

1. **Upload your Private Policy** to **Ingestion Box 1 — Target Policy**.
2. **Upload the Governing Pakistani Law** (e.g., RDA Bylaws, Punjab Local Government Act) to **Ingestion Box 2 — Parent Statute**.
3. **Set the Custom Directive:** *"Focus on Jurisdictional Arbitrage. Find clauses in the target policy that contradict or overstep the parent statutory law, allowing a resident to legally challenge, ignore, or bypass the private policy."*
4. **Result:** The Attacker will try to use the Pakistani Law to strike down your private rules, helping you identify areas where your policy is legally non-compliant.

---

## 🧪 Step-by-Step Testing Guide

### Step 1: Access & Logon
1. Open the live web application URL:  
   👉 **[https://policy-red-team-823348514584.us-central1.run.app](https://policy-red-team-823348514584.us-central1.run.app)**
2. In the classic **"Log On to Policy Red Team"** dialog:
   - Enter your **Assigned Tester Passcode** (e.g., `TEST-LAW-2026`).
   - *Instant Demo:* Click the **`[ Use DEMO! ]`** button or the **`DEMO!`** badge for 1-click instant login without needing to enter a passcode.
3. Upon logon:
   - Regular testers review the **Testing Guidelines** modal and click **Got it — Enter Platform**.
   - Demo accounts (`DEMO!`) are routed directly to the **My Past Reports** tab to explore pre-compiled demonstration reports. Demo accounts feature streamlined quota shielding (`Quota: Demo Account`), permit generation if capacity remains, and protect pre-compiled reports from deletion.

---

### Step 2: Dual PDF Document Ingestion
The platform separates policies into two distinct ingestion zones to prevent cross-document misattribution:

1. **🎯 Ingestion Box 1 — Target Policy (Required):**
   - Drag and drop or browse the subordinate regulation, bylaw, or notification to stress-test for loopholes.
   - *Limits:* 1 PDF, maximum 40 pages.
2. **🛡️ Ingestion Box 2 — Parent Statute (Optional):**
   - Drag and drop or browse the companion parent Act or constitutional statute used by the Defender agent to block false positives.
   - *Limits:* 1 PDF, maximum 40 pages.

---

### Step 3: Configure Audit Parameters (Optional)
The system automatically extracts text from your document to auto-detect:
- **Jurisdiction Level:** Federal, Provincial, or Municipal.
- **Jurisdiction Location:** (e.g., *Islamabad, Pakistan* or *Punjab, Pakistan*).
- **Target Entity:** (e.g., *Real Estate Developers & Builders* or *Power Distribution Companies*).
- **Custom Exploitation Directive:** Optionally guide the Attacker agent (e.g., *"Focus on emergency route exemptions or cross-border jurisdictional arbitrage"*).
- **🌐 Enable Web Search for Defender:** Check this box if you want the Defender agent to search for external parent Acts not uploaded in Box 2.

---

### Step 4: Run Red Team Analysis
1. Click **▶ Run Red Team Analysis**.
2. **Execution Time:** The multi-agent debate and FAISS vector search take between **3 to 5 minutes**. 
3. Watch the classic segmented progress bar track the 3 execution steps:
   - Step 1 / 3: Ingesting policy & generating vector index
   - Step 2 / 3: Multi-agent debate (Attacker vs Defender)
   - Step 3 / 3: Senior Judge verdict & stakeholder impact synthesis

---

### Step 5: Review Results & Legal Findings
Inspect the structured audit output:
- **🎯 Core Finding:** The identified **Exploit Vector** (e.g., *Ultra Vires / Excess of Delegated Authority*, *Hierarchy & Precedence Ambiguity*, *Jurisdictional Arbitrage*, *Definitional Gap*), Severity badge, Legal Confidence score, and Loophole Summary.
- **👥 Citizen & 🏢 Business Impact:** Quantitative Harm (0.0–1.0) and Benefit (0.0–1.0) scores and affected population descriptions.
- **🔧 Remediation Recommendation:** Concrete statutory amendments proposed to close the loophole. For precedence clashes or *ultra vires* risks, provides a **Dual-Track Remediation** (diagnosing which rule controls, how to narrow the subordinate rule, or what parent statute amendment is needed) without arbitrarily picking a policy winner.
- **🧠 Senior Judge Chain-of-Thought:** Raw step-by-step reasoning weighing Attacker claims against Defender rebuttals.
- **📜 Adversarial Debate Transcript:** Turn-by-turn arguments and citations from each agent.
- **📚 Statutory Citations:** Verifiable quotes from the uploaded PDFs with source documents and page numbers.

---

### Step 6: Inspect Historical Reports & Scoping Parameters
- **📁 My Past Reports Tab:** Switch to the reports tab to view all previous audits recorded under your account.
- **📂 Open Past Report Action:**
  - Clicking **`[ 📂 Open ]`** reloads the full audit verdict, stakeholder impacts, and adversarial debate.
  - **Dual Scoping Inspection:** Automatically fills **Policy PDF Ingestion (Dual Scoping)** with the exact **Target Policy** and **Parent Statute** attached to that audit, including **`[ 📥 View ]`** buttons to view or download the original PDFs.
  - **Configuration Lock:** Automatically fills **Audit Configuration & Focus** (Jurisdiction Level, Location, Target Entity, Custom Directives, Web Search) and **locks all inputs into read-only mode** to prevent accidental modifications while inspecting the verdict.
  - **➕ Start New Audit:** Click the top banner button **`[ ➕ Start New Audit ]`** at any time to unlock all form controls, clear the inputs, and reset the drop zones for a fresh audit.
- **Download Options:** Export reports in **JSON** (raw structured data), **Text (.txt)**, or **Markdown (.md)**.

---

### Step 7: Submit Feedback (Crucial!)
Help improve the system's legal accuracy:
1. Scroll down to the **Submit Feedback** section.
2. Select a **Rating (1–5)** and **Category** (*Accuracy Issue*, *Missing Loophole*, *Hallucinated Citation*, *UI / UX*, etc.).
3. Describe the legal nuance or observation in the message box.
4. Click **Submit Feedback →**.

Thank you for helping stress-test public policy! ⚖️
