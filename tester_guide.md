# ⚖️ Policy Red Team — Complete Tester Guide

Welcome to the **Policy Red Team** beta testing phase! 

As an International Relations / Public Policy student with knowledge of AI, your domain expertise is crucial. This tool simulates how adversarial actors (such as aggressive real estate developers, multinational corporations, or tax-evading entities) might exploit legal loopholes, statutory ambiguities, or jurisdictional conflicts in public policies.

---

## 🎯 What is Policy Red Team?

**Policy Red Team** is an automated legal stress-testing platform powered by multi-agent AI. It ingests statutory documents (acts, ordinances, bylaws, and regulatory frameworks) and subjects them to an adversarial debate:

1. **The Attacker (Red Team):** Scours the document for definitional gaps, penalty asymmetries, and procedural loopholes to construct a legal or financial exploit.
2. **The Defender (Blue Team):** Attempts to refute or weaken the exploit using counter-clauses, statutory definitions, or overriding legal principles.
3. **The Judge Agent:** Evaluates the adversarial debate, assigns a quantitative severity classification (Critical, High, Medium, Low), measures legal confidence, and calculates harm/benefit impacts for both citizens and businesses.

By identifying these vulnerabilities *before* laws are enacted, policymakers can draft more resilient, equitable legislation.

---

## 🧪 Step-by-Step Testing Guide

### Step 1: Access & Login
1. Open the live application URL:  
   👉 **[https://policy-red-team-823348514584.us-central1.run.app](https://policy-red-team-823348514584.us-central1.run.app)**
2. Enter the Beta Access Password: `policy2026` and click **Enter →**.

---

### Step 2: Upload Policy Documents
1. Drag and drop your policy PDFs directly onto the upload zone, or click to select files from your computer.
2. **Limits:** Up to **2 PDF files** (maximum 80 pages combined).
3. *Recommendation:* Test real Pakistani statutory instruments (e.g., CDA Ordinance 1960, Punjab Local Government Act 2022, FBR Statutory Regulatory Orders, or SECP regulations).

---

### Step 3: Review Auto-Detected Focus Settings (Optional)
The system automatically extracts text from your document to detect:
- **Jurisdiction Level:** (Federal / Provincial / Municipal)
- **Jurisdiction Location:** (e.g., *Islamabad, Pakistan* or *Punjab, Pakistan*)
- **Target Entity:** (e.g., *Real Estate Developers & Builders* or *Financial Institutions*)

If you wish to override these or add custom focus guidance:
1. Click to expand **⚙️ Focus & Target Settings (Optional)**.
2. Select a specific Jurisdiction Level or type custom instructions (e.g., *"Focus on tax penalty exemptions or fee schedule ambiguities"*).

---

### Step 4: Run the Red Team Analysis
1. Click **▶ Run Red Team Analysis**.
2. **Wait Time:** The multi-agent debate and vector search take between **3 to 8 minutes**. Keep the browser tab open while the live progress indicator runs.

---

### Step 5: Review Results & AI Reasoning
Once complete, inspect the comprehensive audit panel:
- **📋 Audit Arguments & Session Context:** Verifies the session ID, jurisdiction, and target entity evaluated.
- **🎯 Core Finding:** Check the identified **Exploit Vector** (e.g., *Definitional Gap*, *Exemption Abuse*), Severity rating, and Exploit Summary.
- **👥 & 🏢 Impact Scores:** Review estimated harm vs. benefit metrics for citizens and businesses.
- **🔧 Remediation Recommendation:** Read the specific statutory amendment proposed by the AI to close the loophole.
- **🧠 Judge Chain-of-Thought:** Expand this tab to read the raw reasoning of the Judge agent as it weighed the Attacker vs. Defender arguments.
- **📜 Debate Transcript & Citations:** Review turn-by-turn arguments and exact statutory text quoted from your PDF.

---

### Step 6: Download the Audit Report
Save your testing records in your preferred format using the download buttons at the bottom of the results section:

- **📥 Download JSON:** Downloads raw structured data (`.json`) including FAISS search scores, timestamps, and model version metadata.
- **📄 Download Text (.txt):** Downloads a clean, readable plain-text report (`.txt`) ideal for archiving.
- **📝 Download Markdown (.md):** Downloads a formatted Markdown file (`.md`) ready to import into Notion, Obsidian, GitHub, or word processors.

---

### Step 7: Submit Feedback (Crucial!)
Your feedback directly improves the prompt engineering and legal accuracy of the multi-agent system:

1. Scroll to the **Submit Feedback** section at the bottom of the page.
2. Select a **Rating (1 to 5 Stars)**.
3. Choose a **Category** (e.g., *Accuracy Issue*, *Missing Loophole*, *Hallucinated Citation*, *UI / UX Issue*, or *Feature Request*).
4. In the **Message** box, explain your evaluation (e.g., *"The Defender agent missed Section 14 of the CDA Ordinance which blocks this exploit"*).
5. Click **Submit Feedback →**. You will see a green **✅ Feedback Submitted** confirmation.

Thank you for contributing to public policy stress-testing! ⚖️
