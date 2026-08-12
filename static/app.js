let currentSessionId = "";

// Auth Logic
const authForm = document.getElementById('auth-form');
const pwdInput = document.getElementById('password-input');
const authError = document.getElementById('auth-error');
const authOverlay = document.getElementById('auth-overlay');
const appContainer = document.getElementById('app-container');

authForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const pwd = pwdInput.value;
    
    try {
        const formData = new FormData();
        formData.append("password", pwd);
        const res = await fetch('/api/auth', { method: 'POST', body: formData });
        
        if (res.ok) {
            authOverlay.classList.add('hidden');
            appContainer.classList.remove('hidden');
            sessionStorage.setItem('auth_pwd', pwd);
        } else {
            authError.classList.remove('hidden');
        }
    } catch (err) {
        authError.textContent = "Network error.";
        authError.classList.remove('hidden');
    }
});

// File Upload Logic
const dropArea = document.getElementById('drop-area');
const fileInput = document.getElementById('file-input');
const fileList = document.getElementById('file-list');
const runBtn = document.getElementById('run-btn');
let selectedFiles = [];

dropArea.addEventListener('click', () => fileInput.click());
dropArea.addEventListener('dragover', (e) => { e.preventDefault(); dropArea.classList.add('dragover'); });
dropArea.addEventListener('dragleave', () => dropArea.classList.remove('dragover'));
dropArea.addEventListener('drop', (e) => {
    e.preventDefault();
    dropArea.classList.remove('dragover');
    handleFiles(e.dataTransfer.files);
});
fileInput.addEventListener('change', (e) => handleFiles(e.target.files));

function handleFiles(files) {
    if (selectedFiles.length + files.length > 2) {
        alert("Maximum 2 files allowed.");
        return;
    }
    for (let f of files) {
        if (f.type === "application/pdf") {
            selectedFiles.push(f);
        } else {
            alert("Only PDFs are allowed.");
        }
    }
    renderFileList();
}

function renderFileList() {
    fileList.innerHTML = "";
    selectedFiles.forEach((file, index) => {
        const li = document.createElement('li');
        li.innerHTML = `<span>📄 ${file.name} (${(file.size / 1024 / 1024).toFixed(2)} MB)</span>
                        <span class="remove-file" onclick="removeFile(${index})">✕</span>`;
        fileList.appendChild(li);
    });
    runBtn.disabled = selectedFiles.length === 0;
}
window.removeFile = (index) => {
    selectedFiles.splice(index, 1);
    renderFileList();
};

// Form Submission
const uploadForm = document.getElementById('upload-form');
const loadingState = document.getElementById('loading-state');
const resultsState = document.getElementById('results-state');
const progressFill = document.getElementById('progress-fill');
const statusSteps = document.getElementById('status-steps').children;

uploadForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (selectedFiles.length === 0) return;

    // UI Updates
    uploadForm.querySelectorAll('button, input, select, textarea').forEach(el => el.disabled = true);
    resultsState.classList.add('hidden');
    loadingState.classList.remove('hidden');
    
    // Fake progress animation
    progressFill.style.width = "10%";
    statusSteps[0].className = "active";
    statusSteps[1].className = "pending";
    statusSteps[2].className = "pending";

    const formData = new FormData();
    formData.append("password", sessionStorage.getItem('auth_pwd'));
    
    const jLevel = document.getElementById('jurisdiction_level').value;
    const jDist = document.getElementById('jurisdiction').value;
    const target = document.getElementById('target_entity').value;
    const inst = document.getElementById('custom_instructions').value;
    
    if (jLevel) formData.append("jurisdiction_level", jLevel);
    if (jDist) formData.append("jurisdiction", jDist);
    if (target) formData.append("target_entity", target);
    if (inst) formData.append("custom_instructions", inst);
    
    selectedFiles.forEach(f => formData.append("files", f));

    try {
        setTimeout(() => {
            progressFill.style.width = "40%";
            statusSteps[0].className = "done";
            statusSteps[1].className = "active";
        }, 3000); // UI illusion of steps

        const res = await fetch('/api/analyze', { method: 'POST', body: formData });
        
        progressFill.style.width = "90%";
        statusSteps[1].className = "done";
        statusSteps[2].className = "active";

        if (!res.ok) {
            const error = await res.json();
            throw new Error(error.detail || "Analysis failed");
        }
        
        const report = await res.json();
        renderReport(report);
        
        progressFill.style.width = "100%";
        statusSteps[2].className = "done";
        setTimeout(() => {
            loadingState.classList.add('hidden');
            resultsState.classList.remove('hidden');
        }, 800);

    } catch (err) {
        alert(`Error: ${err.message}`);
        loadingState.classList.add('hidden');
    } finally {
        uploadForm.querySelectorAll('button, input, select, textarea').forEach(el => el.disabled = false);
    }
});

// Render Report
let currentReportJson = null;

function renderReport(report) {
    currentReportJson = report;
    currentSessionId = report.session_id || "";
    
    // Arguments & Session Context
    const argsContainer = document.getElementById('res-arguments');
    argsContainer.innerHTML = `
        <p><strong>Session ID:</strong> <code>${report.session_id || 'N/A'}</code></p>
        <p><strong>Jurisdiction:</strong> ${report.jurisdiction || 'N/A'} (${report.jurisdiction_level || 'N/A'})</p>
        <p><strong>Target Entity:</strong> ${report.target_entity || 'N/A'}</p>
        <p><strong>Policy Document:</strong> ${report.policy_document || 'N/A'}</p>
    `;

    // Core Finding
    document.getElementById('res-vector').textContent = report.exploit_vector || "N/A";
    const sevEl = document.getElementById('res-severity');
    const sev = report.severity_classification || "N/A";
    sevEl.textContent = sev;
    sevEl.className = `badge-severity ${sev.toUpperCase()}`;
    document.getElementById('res-confidence').textContent = (report.legal_confidence_score || 0).toFixed(2);
    document.getElementById('res-summary').textContent = (report.canonical_exploit || {}).summary || "";

    // Citizen
    const cit = report.citizen_score || {};
    document.getElementById('res-cit-harm').textContent = (cit.harm_score || 0).toFixed(2);
    document.getElementById('res-cit-ben').textContent = (cit.benefit_score || 0).toFixed(2);
    document.getElementById('res-cit-pop').textContent = cit.affected_population || "";

    // Business
    const bus = report.business_score || {};
    document.getElementById('res-bus-harm').textContent = (bus.harm_score || 0).toFixed(2);
    document.getElementById('res-bus-ben').textContent = (bus.benefit_score || 0).toFixed(2);
    document.getElementById('res-bus-pop').textContent = bus.affected_population || "";

    document.getElementById('res-remediation').textContent = report.remediation_recommendation || "";

    // Judge Chain-of-Thought
    document.getElementById('res-judge-reasoning').textContent = report.raw_judge_reasoning || "No judge chain-of-thought available.";

    // Transcript
    const transContainer = document.getElementById('res-transcript');
    transContainer.innerHTML = "";
    (report.debate_transcript || []).forEach(t => {
        const div = document.createElement('div');
        div.className = 'turn-box';
        div.innerHTML = `
            <strong>Turn ${t.turn_number}</strong> — <span class="badge" style="background:#30363d">${t.turn_verdict}</span>
            <blockquote style="color:#ff7b72"><strong>Attacker:</strong> ${t.exploit_claim}</blockquote>
            <blockquote style="color:#58a6ff"><strong>Defender:</strong> ${t.defender_rebuttal}</blockquote>
            <small>Attacker cited: ${(t.attacker_citations||[]).join(", ")} | Defender cited: ${(t.defender_citations||[]).join(", ")}</small>
        `;
        transContainer.appendChild(div);
    });

    // Citations
    const citeContainer = document.getElementById('res-citations');
    citeContainer.innerHTML = "";
    (report.statutory_citations || []).forEach(c => {
        const div = document.createElement('div');
        div.className = 'cite-box';
        div.innerHTML = `
            <strong>${c.section_id}</strong> — <em>${c.source_document}</em> (p. ${c.page_number || '?'})
            <blockquote>${c.quoted_text}</blockquote>
        `;
        citeContainer.appendChild(div);
    });

    // Retrieval Provenance
    const provContainer = document.getElementById('res-provenance');
    provContainer.innerHTML = "";
    const provs = report.retrieval_provenance || [];
    if (provs.length === 0) {
        provContainer.innerHTML = "<p style='color:#8b949e;'>No search queries recorded.</p>";
    } else {
        provs.forEach((p, idx) => {
            const div = document.createElement('div');
            div.className = 'turn-box';
            div.style.borderLeftColor = "#1f6feb";
            div.innerHTML = `
                <strong>Query ${idx + 1}:</strong> <code>"${p.query}"</code><br>
                <small style='color:#8b949e;'>Timestamp: ${p.timestamp || 'N/A'}</small>
            `;
            provContainer.appendChild(div);
        });
    }

    // Model Infrastructure
    const modelsContainer = document.getElementById('res-models');
    modelsContainer.innerHTML = "";
    const models = report.model_versions_used || {};
    if (Object.keys(models).length === 0) {
        modelsContainer.innerHTML = "<p style='color:#8b949e;'>Standard Gemini ensemble used.</p>";
    } else {
        let html = "<ul>";
        for (let [agent, model] of Object.entries(models)) {
            html += `<li><strong>${agent}:</strong> <code>${model}</code></li>`;
        }
        html += "</ul>";
        modelsContainer.innerHTML = html;
    }
}

// Download Helpers
function triggerDownload(content, filename, type) {
    const blob = new Blob([content], { type: type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
}

function generateMarkdownReport(report) {
    let md = `# ⚖️ Policy Red Team Audit Report\n\n`;
    md += `**Session ID:** \`${report.session_id || 'N/A'}\`  \n`;
    md += `**Jurisdiction:** ${report.jurisdiction || 'N/A'} (${report.jurisdiction_level || 'N/A'})  \n`;
    md += `**Target Entity:** ${report.target_entity || 'N/A'}  \n`;
    md += `**Policy Document:** ${report.policy_document || 'N/A'}  \n\n`;
    
    md += `---\n\n`;
    md += `## 🎯 Core Finding\n\n`;
    md += `- **Exploit Vector:** ${report.exploit_vector || 'N/A'}\n`;
    md += `- **Severity:** ${report.severity_classification || 'N/A'}\n`;
    md += `- **Legal Confidence Score:** ${(report.legal_confidence_score || 0).toFixed(2)}\n\n`;
    md += `### Summary\n${(report.canonical_exploit || {}).summary || 'N/A'}\n\n`;

    md += `---\n\n`;
    md += `## 👥 Stakeholder Impact\n\n`;
    const cit = report.citizen_score || {};
    md += `### Citizen Impact\n- Harm Score: ${cit.harm_score || 0} | Benefit Score: ${cit.benefit_score || 0}\n- ${cit.affected_population || ''}\n\n`;
    const bus = report.business_score || {};
    md += `### Business Impact\n- Harm Score: ${bus.harm_score || 0} | Benefit Score: ${bus.benefit_score || 0}\n- ${bus.affected_population || ''}\n\n`;

    md += `---\n\n`;
    md += `## 🔧 Remediation Recommendation\n${report.remediation_recommendation || 'N/A'}\n\n`;

    md += `---\n\n`;
    md += `## 🧠 Judge Chain-of-Thought & Reasoning\n\`\`\`\n${report.raw_judge_reasoning || 'N/A'}\n\`\`\`\n\n`;

    md += `---\n\n`;
    md += `## 📜 Adversarial Debate Transcript\n\n`;
    (report.debate_transcript || []).forEach(t => {
        md += `### Turn ${t.turn_number} (Verdict: ${t.turn_verdict})\n`;
        md += `- **Attacker:** ${t.exploit_claim}\n`;
        md += `- **Defender:** ${t.defender_rebuttal}\n`;
        md += `- *Citations:* Attacker: ${(t.attacker_citations||[]).join(", ") || "None"} | Defender: ${(t.defender_citations||[]).join(", ") || "None"}\n\n`;
    });

    md += `---\n\n`;
    md += `## 📚 Statutory Citations\n\n`;
    (report.statutory_citations || []).forEach(c => {
        md += `### ${c.section_id} — ${c.source_document} (p. ${c.page_number || '?'})\n> ${c.quoted_text}\n\n`;
    });

    return md;
}

document.getElementById('download-json-btn').addEventListener('click', () => {
    if (!currentReportJson) return;
    const filename = `policy_redteam_${currentSessionId.substring(0,8) || "report"}.json`;
    triggerDownload(JSON.stringify(currentReportJson, null, 2), filename, "application/json");
});

document.getElementById('download-md-btn').addEventListener('click', () => {
    if (!currentReportJson) return;
    const md = generateMarkdownReport(currentReportJson);
    const filename = `policy_redteam_${currentSessionId.substring(0,8) || "report"}.md`;
    triggerDownload(md, filename, "text/markdown");
});

document.getElementById('download-txt-btn').addEventListener('click', () => {
    if (!currentReportJson) return;
    const md = generateMarkdownReport(currentReportJson);
    const filename = `policy_redteam_${currentSessionId.substring(0,8) || "report"}.txt`;
    triggerDownload(md, filename, "text/plain");
});

// Feedback
document.getElementById('feedback-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = e.target.querySelector('button');
    btn.disabled = true;
    btn.textContent = "Submitting...";

    const formData = new FormData();
    formData.append("password", sessionStorage.getItem('auth_pwd'));
    formData.append("rating", document.getElementById('fb-rating').value);
    formData.append("category", document.getElementById('fb-category').value);
    formData.append("message", document.getElementById('fb-message').value);
    formData.append("session_id", currentSessionId);

    try {
        await fetch('/api/feedback', { method: 'POST', body: formData });
        btn.textContent = "✅ Feedback Submitted";
        btn.style.background = "#238636";
    } catch (err) {
        alert("Feedback submission failed locally.");
        btn.disabled = false;
        btn.textContent = "Submit Feedback →";
    }
});
