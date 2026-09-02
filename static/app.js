// ==========================================================================
// Policy Red Team — 2002–2007 Classic UI & Multi-User App Logic (Optimized)
// ==========================================================================

let currentUser = null;
let currentReportJson = null;
let currentSessionId = "";

// Dual file state
let targetFile = null;
let parentFile = null;

// DOM Elements: Authentication & Guidance
const authOverlay = document.getElementById('auth-overlay');
const authForm = document.getElementById('auth-form');
const passwordInput = document.getElementById('password-input');
const authError = document.getElementById('auth-error');
const instructionsModal = document.getElementById('instructions-modal');
const btnAckInstructions = document.getElementById('btn-ack-instructions');
const btnCloseInstructions = document.getElementById('btn-close-instructions');
const appWindow = document.getElementById('app-window');
const tabButtons = document.querySelectorAll('.tab-button');
const tabContents = document.querySelectorAll('.tab-content');
const tabBtnAdmin = document.getElementById('tab-btn-admin');

// Status Bar Elements
const statusText = document.getElementById('status-text');
const statusUser = document.getElementById('status-user');
const statusQuota = document.getElementById('status-quota');

// Audit Form Elements
const uploadForm = document.getElementById('upload-form');
const targetDropBox = document.getElementById('target-drop-box');
const targetFileInput = document.getElementById('target-file-input');
const targetFileBadge = document.getElementById('target-file-badge');
const targetFileName = document.getElementById('target-file-name');
const btnRemoveTarget = document.getElementById('btn-remove-target');

const parentDropBox = document.getElementById('parent-drop-box');
const parentFileInput = document.getElementById('parent-file-input');
const parentFileBadge = document.getElementById('parent-file-badge');
const parentFileName = document.getElementById('parent-file-name');
const btnRemoveParent = document.getElementById('btn-remove-parent');

const runBtn = document.getElementById('run-btn');
const quotaWarningBanner = document.getElementById('quota-warning-banner');
const loadingState = document.getElementById('loading-state');
const resultsState = document.getElementById('results-state');
const idleState = document.getElementById('idle-state');
const progressFill = document.getElementById('progress-fill');
const stepLabel = document.getElementById('step-label');

// ==========================================================================
// 1. Authentication & Session Flow
// ==========================================================================

async function checkSavedSession() {
    const savedCode = sessionStorage.getItem('auth_passcode');
    if (savedCode) {
        try {
            const res = await fetch(`/api/user/info?passcode=${encodeURIComponent(savedCode)}`);
            if (res.ok) {
                const info = await res.json();
                loginSuccess(info, false); // Don't re-show popup on page reload
                return;
            }
        } catch (e) {
            console.error("Session restore failed", e);
        }
    }
    authOverlay.classList.remove('hidden');
    appWindow.classList.add('hidden');
}

function loginSuccess(userInfo, showGuide = true) {
    currentUser = userInfo;
    sessionStorage.setItem('auth_passcode', userInfo.passcode);
    authOverlay.classList.add('hidden');
    appWindow.classList.remove('hidden');

    // Update Status Bar
    statusUser.textContent = `User: ${userInfo.label}`;
    updateQuotaDisplay();

    // Reveal Administrator Tab if user is admin
    if (userInfo.is_admin) {
        tabBtnAdmin.classList.remove('hidden');
    } else {
        tabBtnAdmin.classList.add('hidden');
    }

    statusText.textContent = "Ready";

    // Check if Sample Demo Mode was entered
    if (userInfo.passcode === "DEMO-SAMPLE-2026" || userInfo.passcode.toUpperCase().includes("SAMPLE")) {
        preloadSampleDemo();
    } else if (showGuide) {
        // Show Testing Instructions & Guidelines Modal upon entering regular passcode
        instructionsModal.classList.remove('hidden');
    }
}

function preloadSampleDemo() {
    alert(
        "🧪 Sample Demonstration Mode Active!\n\n" +
        "You have logged in using demo credentials (DEMO-SAMPLE-2026).\n\n" +
        "• A real-world sample regulatory audit (CDA Islamabad Speed Breakers Policy) has been pre-loaded.\n" +
        "• You can immediately inspect the Attacker vs. Defender debate, statutory citations, and Judge verdicts."
    );

    // Pre-populate configuration fields
    const jLevel = document.getElementById('jurisdiction_level');
    const jDist = document.getElementById('jurisdiction');
    const tEntity = document.getElementById('target_entity');
    const cInst = document.getElementById('custom_instructions');

    if (jLevel) jLevel.value = "Municipal";
    if (jDist) jDist.value = "Islamabad, Pakistan";
    if (tEntity) tEntity.value = "Real Estate Developers & Housing Societies";
    if (cInst) cInst.value = "Focus on negative criteria for primary emergency response routes and volume thresholds (>3000 vpd).";

    // Show sample document badges
    targetFileName.textContent = "🎯 CDA_Speed_Breakers_Policy_2019.pdf (Sample)";
    targetFileBadge.classList.remove('hidden');
    parentFileName.textContent = "🛡️ CDA_Ordinance_1960.pdf (Sample)";
    parentFileBadge.classList.remove('hidden');

    // Automatically load the pre-seeded sample report
    fetch(`/api/user/reports?passcode=${encodeURIComponent(currentUser.passcode)}`)
        .then(res => res.json())
        .then(reports => {
            if (reports && reports.length > 0) {
                openReportById(reports[0].report_id);
            }
        })
        .catch(err => console.log("Sample load error:", err));
}

function updateQuotaDisplay() {
    if (!currentUser) return;
    if (currentUser.is_admin || currentUser.report_limit === -1) {
        statusQuota.textContent = "Quota: Unlimited (Admin)";
        quotaWarningBanner.classList.add('hidden');
        if (targetFile) runBtn.disabled = false;
    } else {
        const remaining = Math.max(0, currentUser.report_limit - currentUser.reports_used);
        statusQuota.textContent = `Quota: ${currentUser.reports_used} / ${currentUser.report_limit} Used (${remaining} left)`;
        
        if (remaining <= 0) {
            runBtn.disabled = true;
            quotaWarningBanner.textContent = `⚠️ Report limit reached (${currentUser.report_limit}/${currentUser.report_limit}). Contact administrator for more quota.`;
            quotaWarningBanner.classList.remove('hidden');
        } else {
            quotaWarningBanner.classList.add('hidden');
            if (targetFile) runBtn.disabled = false;
        }
    }
}

authForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    authError.classList.add('hidden');
    const pwd = passwordInput.value.trim();
    if (!pwd) return;

    try {
        const formData = new FormData();
        formData.append("password", pwd);
        const res = await fetch('/api/auth', { method: 'POST', body: formData });
        
        if (res.ok) {
            const data = await res.json();
            loginSuccess(data, true);
        } else {
            const err = await res.json();
            authError.textContent = err.detail || "Invalid passcode.";
            authError.classList.remove('hidden');
        }
    } catch (err) {
        authError.textContent = "Network error connecting to server.";
        authError.classList.remove('hidden');
    }
});

btnAckInstructions?.addEventListener('click', () => instructionsModal.classList.add('hidden'));
btnCloseInstructions?.addEventListener('click', () => instructionsModal.classList.add('hidden'));

document.getElementById('btn-auth-cancel')?.addEventListener('click', () => {
    passwordInput.value = "";
    authError.classList.add('hidden');
});

document.getElementById('btn-window-close')?.addEventListener('click', () => {
    if (confirm("Log out of Policy Red Team?")) {
        sessionStorage.removeItem('auth_passcode');
        currentUser = null;
        authOverlay.classList.remove('hidden');
        appWindow.classList.add('hidden');
    }
});

// ==========================================================================
// 2. Navigation & Menu Bar Actions
// ==========================================================================

function switchTab(targetTabId) {
    tabButtons.forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === targetTabId);
    });

    tabContents.forEach(content => {
        content.classList.toggle('hidden', content.id !== targetTabId);
    });

    if (targetTabId === 'tab-past-reports') {
        loadUserReports();
    } else if (targetTabId === 'tab-admin') {
        loadAdminPasscodes();
        loadAdminAllReports();
    }
}

tabButtons.forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
});

document.getElementById('menu-audit')?.addEventListener('click', () => switchTab('tab-audit'));
document.getElementById('menu-reports')?.addEventListener('click', () => switchTab('tab-past-reports'));
document.getElementById('menu-help')?.addEventListener('click', () => instructionsModal.classList.remove('hidden'));
document.getElementById('menu-admin')?.addEventListener('click', () => {
    if (currentUser?.is_admin) {
        switchTab('tab-admin');
    } else {
        alert("Access Denied: Administrator privileges required.");
    }
});

// ==========================================================================
// 3. Dual PDF Ingestion Zones (Target vs Parent Statute)
// ==========================================================================

// Target Policy Setup
targetDropBox.addEventListener('click', (e) => {
    if (e.target !== btnRemoveTarget) targetFileInput.click();
});
targetDropBox.addEventListener('dragover', (e) => { e.preventDefault(); targetDropBox.style.background = "#eef4ff"; });
targetDropBox.addEventListener('dragleave', () => { targetDropBox.style.background = "#ffffff"; });
targetDropBox.addEventListener('drop', (e) => {
    e.preventDefault();
    targetDropBox.style.background = "#ffffff";
    if (e.dataTransfer.files.length > 0) assignTargetFile(e.dataTransfer.files[0]);
});
targetFileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) assignTargetFile(e.target.files[0]);
});

function assignTargetFile(file) {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
        alert("Only PDF documents are supported.");
        return;
    }
    targetFile = file;
    targetFileName.textContent = `🎯 ${file.name} (${(file.size / 1024 / 1024).toFixed(2)} MB)`;
    targetFileBadge.classList.remove('hidden');
    updateQuotaDisplay();
}

btnRemoveTarget.addEventListener('click', (e) => {
    e.stopPropagation();
    targetFile = null;
    targetFileInput.value = "";
    targetFileBadge.classList.add('hidden');
    runBtn.disabled = true;
});

// Parent Statute Setup
parentDropBox.addEventListener('click', (e) => {
    if (e.target !== btnRemoveParent) parentFileInput.click();
});
parentDropBox.addEventListener('dragover', (e) => { e.preventDefault(); parentDropBox.style.background = "#f0fff0"; });
parentDropBox.addEventListener('dragleave', () => { parentDropBox.style.background = "#ffffff"; });
parentDropBox.addEventListener('drop', (e) => {
    e.preventDefault();
    parentDropBox.style.background = "#ffffff";
    if (e.dataTransfer.files.length > 0) assignParentFile(e.dataTransfer.files[0]);
});
parentFileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) assignParentFile(e.target.files[0]);
});

function assignParentFile(file) {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
        alert("Only PDF documents are supported.");
        return;
    }
    parentFile = file;
    parentFileName.textContent = `🛡️ ${file.name} (${(file.size / 1024 / 1024).toFixed(2)} MB)`;
    parentFileBadge.classList.remove('hidden');
}

btnRemoveParent.addEventListener('click', (e) => {
    e.stopPropagation();
    parentFile = null;
    parentFileInput.value = "";
    parentFileBadge.classList.add('hidden');
});

// ==========================================================================
// 4. Audit Execution & Progress Simulation
// ==========================================================================

uploadForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!targetFile || !currentUser) {
        alert("Please upload at least the Target Policy document.");
        return;
    }

    // Quota pre-check
    if (!currentUser.is_admin && currentUser.report_limit !== -1) {
        if (currentUser.reports_used >= currentUser.report_limit) {
            alert("Your report generation quota has been reached. Please contact an administrator.");
            return;
        }
    }

    // UI state transitions
    uploadForm.querySelectorAll('button, input, select, textarea').forEach(el => el.disabled = true);
    idleState.classList.add('hidden');
    resultsState.classList.add('hidden');
    loadingState.classList.remove('hidden');

    progressFill.style.width = "15%";
    stepLabel.textContent = "Step 1 / 3 — Ingesting policy document and building FAISS vector index...";
    statusText.textContent = "Ingesting documents...";

    const formData = new FormData();
    formData.append("password", currentUser.passcode);

    const jLevel = document.getElementById('jurisdiction_level').value;
    const jDist = document.getElementById('jurisdiction').value;
    const target = document.getElementById('target_entity').value;
    const inst = document.getElementById('custom_instructions').value;
    const webSearch = document.getElementById('enable_web_search').checked;

    if (jLevel) formData.append("jurisdiction_level", jLevel);
    if (jDist) formData.append("jurisdiction", jDist);
    if (target) formData.append("target_entity", target);
    if (inst) formData.append("custom_instructions", inst);
    formData.append("enable_web_search", webSearch ? "true" : "false");

    // Construct typed document roles
    const docRoles = [];
    docRoles.push({ filename: targetFile.name, role: "target" });
    formData.append("files", targetFile);

    if (parentFile) {
        docRoles.push({ filename: parentFile.name, role: "supporting" });
        formData.append("files", parentFile);
    }
    formData.append("document_roles_json", JSON.stringify(docRoles));

    const t1 = setTimeout(() => {
        progressFill.style.width = "45%";
        stepLabel.textContent = "Step 2 / 3 — Running adversarial debate (AttackerAgent vs. DefenderAgent)...";
        statusText.textContent = "Running multi-agent debate...";
    }, 4000);

    const t2 = setTimeout(() => {
        progressFill.style.width = "80%";
        stepLabel.textContent = "Step 3 / 3 — Synthesizing Senior Judge verdict and evaluating stakeholder impact...";
        statusText.textContent = "Evaluating loophole severity...";
    }, 15000);

    try {
        const res = await fetch('/api/analyze', { method: 'POST', body: formData });
        clearTimeout(t1);
        clearTimeout(t2);

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || "Analysis request failed.");
        }

        const report = await res.json();
        progressFill.style.width = "100%";
        stepLabel.textContent = "Analysis Complete! Rendering report...";
        statusText.textContent = "Analysis completed.";

        // Update local quota count
        if (!currentUser.is_admin && currentUser.report_limit !== -1) {
            currentUser.reports_used += 1;
            updateQuotaDisplay();
        }

        setTimeout(() => {
            loadingState.classList.add('hidden');
            renderReport(report);
            resultsState.classList.remove('hidden');
        }, 500);

    } catch (err) {
        clearTimeout(t1);
        clearTimeout(t2);
        alert(`Analysis Error: ${err.message}`);
        loadingState.classList.add('hidden');
        idleState.classList.remove('hidden');
        statusText.textContent = "Analysis failed.";
    } finally {
        uploadForm.querySelectorAll('button, input, select, textarea').forEach(el => el.disabled = false);
        updateQuotaDisplay();
    }
});

// ==========================================================================
// 5. Report Viewer & Renderer
// ==========================================================================

function renderReport(report) {
    currentReportJson = report;
    currentSessionId = report.session_id || "";

    // Core finding
    document.getElementById('res-vector').textContent = report.exploit_vector || "N/A";
    const sevEl = document.getElementById('res-severity');
    const sev = (report.severity_classification || "N/A").toUpperCase();
    sevEl.textContent = sev;
    sevEl.className = `badge-sev ${sev}`;
    document.getElementById('res-confidence').textContent = (report.legal_confidence_score || 0).toFixed(2);
    document.getElementById('res-summary').textContent = (report.canonical_exploit || {}).summary || report.summary || "No summary available.";

    // Stakeholders
    const cit = report.citizen_score || {};
    document.getElementById('res-cit-harm').textContent = (cit.harm_score || 0).toFixed(2);
    document.getElementById('res-cit-ben').textContent = (cit.benefit_score || 0).toFixed(2);
    document.getElementById('res-cit-pop').textContent = cit.affected_population || "";

    const bus = report.business_score || {};
    document.getElementById('res-bus-harm').textContent = (bus.harm_score || 0).toFixed(2);
    document.getElementById('res-bus-ben').textContent = (bus.benefit_score || 0).toFixed(2);
    document.getElementById('res-bus-pop').textContent = bus.affected_population || "";

    document.getElementById('res-remediation').textContent = report.remediation_recommendation || "None";
    document.getElementById('res-judge-reasoning').textContent = report.raw_judge_reasoning || "No chain-of-thought available.";

    // Debate transcript
    const transContainer = document.getElementById('res-transcript');
    transContainer.innerHTML = "";
    (report.debate_transcript || []).forEach(t => {
        const div = document.createElement('div');
        div.className = 'turn-box-classic';
        div.innerHTML = `
            <strong>Turn ${t.turn_number}</strong> — <span class="badge-sev" style="background:#555">${t.turn_verdict}</span>
            <blockquote class="attacker"><strong>Attacker:</strong> ${t.exploit_claim}</blockquote>
            <blockquote><strong>Defender:</strong> ${t.defender_rebuttal}</blockquote>
            <small style="color:#666;">Attacker: ${(t.attacker_citations || []).join(", ") || "None"} | Defender: ${(t.defender_citations || []).join(", ") || "None"}</small>
        `;
        transContainer.appendChild(div);
    });

    // Statutory citations
    const citeContainer = document.getElementById('res-citations');
    citeContainer.innerHTML = "";
    (report.statutory_citations || []).forEach(c => {
        const div = document.createElement('div');
        div.className = 'cite-box-classic';
        div.innerHTML = `
            <strong>${c.section_id}</strong> — <em>${c.source_document}</em> (Page ${c.page_number || '?'})
            <p style="margin-top: 3px;">"${c.quoted_text}"</p>
        `;
        citeContainer.appendChild(div);
    });

    // Retrieval Provenance
    const provContainer = document.getElementById('res-provenance');
    provContainer.innerHTML = "";
    const provs = report.retrieval_provenance || [];
    if (provs.length === 0) {
        provContainer.innerHTML = "<p style='color:#666;'>No search queries recorded in session.</p>";
    } else {
        provs.forEach((p, idx) => {
            const div = document.createElement('div');
            div.className = 'turn-box-classic';
            div.innerHTML = `
                <strong>Query ${idx + 1}:</strong> <code>"${p.search_query}"</code>
                <small style="display:block; color:#555;">Returned ${p.nodes_returned} node(s) | Agent: ${p.agent_name || 'Defender'}</small>
            `;
            provContainer.appendChild(div);
        });
    }
}

// Download File Handlers
function downloadFile(content, fileName, contentType) {
    const a = document.createElement("a");
    const file = new Blob([content], { type: contentType });
    a.href = URL.createObjectURL(file);
    a.download = fileName;
    a.click();
    URL.revokeObjectURL(a.href);
}

document.getElementById('download-json-btn')?.addEventListener('click', () => {
    if (!currentReportJson) return;
    downloadFile(JSON.stringify(currentReportJson, null, 2), `loophole_report_${currentSessionId || 'audit'}.json`, "application/json");
});

document.getElementById('download-txt-btn')?.addEventListener('click', () => {
    if (!currentReportJson) return;
    const txt = `POLICY RED TEAM AUDIT REPORT\n` +
        `Session ID: ${currentReportJson.session_id}\n` +
        `Severity: ${currentReportJson.severity_classification}\n` +
        `Exploit Vector: ${currentReportJson.exploit_vector}\n` +
        `Legal Confidence: ${currentReportJson.legal_confidence_score}\n\n` +
        `SUMMARY:\n${(currentReportJson.canonical_exploit || {}).summary || ''}\n\n` +
        `REMEDIATION:\n${currentReportJson.remediation_recommendation || ''}\n`;
    downloadFile(txt, `loophole_report_${currentSessionId || 'audit'}.txt`, "text/plain");
});

document.getElementById('download-md-btn')?.addEventListener('click', () => {
    if (!currentReportJson) return;
    const md = `# Policy Red Team — Loophole Report\n\n` +
        `- **Session ID:** \`${currentReportJson.session_id}\`\n` +
        `- **Severity:** **${currentReportJson.severity_classification}**\n` +
        `- **Exploit Vector:** ${currentReportJson.exploit_vector}\n` +
        `- **Legal Confidence Score:** ${currentReportJson.legal_confidence_score}\n\n` +
        `## Core Finding\n${(currentReportJson.canonical_exploit || {}).summary || ''}\n\n` +
        `## Legislative Remediation Recommendation\n${currentReportJson.remediation_recommendation || ''}\n`;
    downloadFile(md, `loophole_report_${currentSessionId || 'audit'}.md`, "text/markdown");
});

// Feedback Form
document.getElementById('feedback-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!currentUser) return;

    const rating = document.getElementById('fb-rating').value;
    const cat = document.getElementById('fb-category').value;
    const msg = document.getElementById('fb-message').value;

    const fd = new FormData();
    fd.append("password", currentUser.passcode);
    fd.append("rating", rating);
    fd.append("category", cat);
    fd.append("message", msg);
    fd.append("session_id", currentSessionId);

    try {
        const res = await fetch('/api/feedback', { method: 'POST', body: fd });
        if (res.ok) {
            alert("Thank you! Your evaluation feedback has been recorded.");
            document.getElementById('fb-message').value = "";
        } else {
            alert("Failed to submit feedback.");
        }
    } catch (e) {
        alert("Network error submitting feedback.");
    }
});

// ==========================================================================
// 6. My Past Reports Tab
// ==========================================================================

async function loadUserReports() {
    if (!currentUser) return;
    const tbody = document.getElementById('user-reports-tbody');
    const countEl = document.getElementById('past-reports-count');
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;">Loading reports...</td></tr>`;

    try {
        const res = await fetch(`/api/user/reports?passcode=${encodeURIComponent(currentUser.passcode)}`);
        if (!res.ok) throw new Error("Failed to load reports");
        const reports = await res.json();

        countEl.textContent = `Total reports generated: ${reports.length}`;
        if (reports.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; color:#666;">No reports generated under this passcode yet.</td></tr>`;
            return;
        }

        tbody.innerHTML = "";
        reports.forEach(r => {
            const tr = document.createElement('tr');
            const dateStr = new Date(r.created_at).toLocaleString();
            tr.innerHTML = `
                <td>${dateStr}</td>
                <td><strong>${r.policy_document}</strong></td>
                <td>${r.jurisdiction}</td>
                <td><span class="badge-sev ${r.severity.toUpperCase()}">${r.severity}</span></td>
                <td>${r.exploit_vector}</td>
                <td>
                    <button class="btn-classic" onclick="openReportById('${r.report_id}')">📂 Open</button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; color:#990000;">Failed to load reports: ${e.message}</td></tr>`;
    }
}

document.getElementById('btn-refresh-user-reports')?.addEventListener('click', loadUserReports);

window.openReportById = async (reportId) => {
    if (!currentUser) return;
    statusText.textContent = `Loading report ${reportId}...`;
    try {
        const res = await fetch(`/api/reports/${encodeURIComponent(reportId)}?passcode=${encodeURIComponent(currentUser.passcode)}`);
        if (!res.ok) throw new Error("Report not found");
        const report = await res.json();
        
        switchTab('tab-audit');
        idleState.classList.add('hidden');
        loadingState.classList.add('hidden');
        renderReport(report);
        resultsState.classList.remove('hidden');
        statusText.textContent = `Loaded report ${reportId}.`;
    } catch (e) {
        alert(`Error opening report: ${e.message}`);
        statusText.textContent = "Ready";
    }
};

// ==========================================================================
// 7. Administrator Console Tab
// ==========================================================================

async function loadAdminPasscodes() {
    if (!currentUser?.is_admin) return;
    const tbody = document.getElementById('admin-passcodes-tbody');
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;">Loading passcodes...</td></tr>`;

    try {
        const res = await fetch(`/api/admin/passcodes?admin_passcode=${encodeURIComponent(currentUser.passcode)}`);
        if (!res.ok) throw new Error("Failed to load passcodes");
        const passcodes = await res.json();

        tbody.innerHTML = "";
        passcodes.forEach(p => {
            const tr = document.createElement('tr');
            const dateStr = new Date(p.created_at).toLocaleDateString();
            const isMaster = p.is_admin ? '<strong style="color:#0a246a;">👑 Admin</strong>' : 'Tester';
            const limitStr = p.report_limit === -1 ? 'Unlimited' : p.report_limit;
            
            let actions = "";
            if (!p.is_admin) {
                actions = `
                    <button class="btn-classic" onclick="copyToClipboard('${p.passcode}')" title="Copy Passcode">📋 Copy</button>
                    <button class="btn-classic" onclick="adminAdjustLimit('${p.passcode}', ${p.report_limit})">Edit Limit</button>
                    <button class="btn-classic" onclick="adminResetUsed('${p.passcode}')">Reset</button>
                    <button class="btn-classic btn-danger" onclick="adminRevokePasscode('${p.passcode}')">Revoke</button>
                `;
            } else {
                actions = `<em style="color:#666;">Protected Master Key</em>`;
            }

            tr.innerHTML = `
                <td><code>${p.passcode}</code></td>
                <td><strong>${p.label}</strong></td>
                <td>${isMaster}</td>
                <td>${p.reports_used}</td>
                <td>${limitStr}</td>
                <td>${dateStr}</td>
                <td><div style="display:flex; gap:3px;">${actions}</div></td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; color:#990000;">Error: ${e.message}</td></tr>`;
    }
}

async function loadAdminAllReports() {
    if (!currentUser?.is_admin) return;
    const tbody = document.getElementById('admin-all-reports-tbody');
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;">Loading master ledger...</td></tr>`;

    try {
        const res = await fetch(`/api/admin/reports?admin_passcode=${encodeURIComponent(currentUser.passcode)}`);
        if (!res.ok) throw new Error("Failed to load master ledger");
        const allReports = await res.json();

        if (allReports.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; color:#666;">No audit reports have been generated yet.</td></tr>`;
            return;
        }

        tbody.innerHTML = "";
        allReports.forEach(r => {
            const tr = document.createElement('tr');
            const dateStr = new Date(r.created_at).toLocaleString();
            tr.innerHTML = `
                <td>${dateStr}</td>
                <td><strong>${r.user_label}</strong></td>
                <td><code>${r.passcode}</code></td>
                <td>${r.policy_document}</td>
                <td><span class="badge-sev ${r.severity.toUpperCase()}">${r.severity}</span></td>
                <td>${r.exploit_vector}</td>
                <td>
                    <button class="btn-classic" onclick="openReportById('${r.report_id}')">📂 View</button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; color:#990000;">Error: ${e.message}</td></tr>`;
    }
}

document.getElementById('btn-refresh-passcodes')?.addEventListener('click', loadAdminPasscodes);
document.getElementById('btn-refresh-all-reports')?.addEventListener('click', loadAdminAllReports);

// Admin: Create Passcode Form
document.getElementById('admin-create-passcode-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!currentUser?.is_admin) return;

    const label = document.getElementById('admin-new-label').value.trim();
    const limit = parseInt(document.getElementById('admin-new-limit').value, 10) || 5;
    const customCode = document.getElementById('admin-new-code').value.trim();

    const fd = new FormData();
    fd.append("admin_passcode", currentUser.passcode);
    fd.append("label", label);
    fd.append("report_limit", limit);
    if (customCode) fd.append("custom_passcode", customCode);

    try {
        const res = await fetch('/api/admin/passcodes', { method: 'POST', body: fd });
        if (!res.ok) throw new Error("Failed to generate passcode");
        const created = await res.json();

        alert(`✅ Passcode Created Successfully!\n\nPasscode: ${created.passcode}\nAssigned to: ${created.label}\nReport Limit: ${created.report_limit}`);
        document.getElementById('admin-new-label').value = "";
        document.getElementById('admin-new-code').value = "";
        loadAdminPasscodes();
    } catch (err) {
        alert(`Error: ${err.message}`);
    }
});

window.copyToClipboard = (text) => {
    if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(() => {
            alert(`📋 Passcode '${text}' copied to clipboard! You can now send it to your tester.`);
        }).catch(() => {
            prompt("Copy this passcode:", text);
        });
    } else {
        prompt("Copy this passcode:", text);
    }
};

window.adminAdjustLimit = async (code, currentLimit) => {
    const newLimit = prompt(`Enter new report quota limit for ${code}:`, currentLimit);
    if (newLimit === null) return;
    const parsed = parseInt(newLimit, 10);
    if (isNaN(parsed) || parsed < 1) {
        alert("Please enter a valid positive number.");
        return;
    }

    const fd = new FormData();
    fd.append("admin_passcode", currentUser.passcode);
    fd.append("report_limit", parsed);
    fd.append("reset_used", "false");

    try {
        const res = await fetch(`/api/admin/passcodes/${encodeURIComponent(code)}/adjust`, { method: 'POST', body: fd });
        if (res.ok) {
            loadAdminPasscodes();
        } else {
            alert("Failed to adjust limit.");
        }
    } catch (e) {
        alert("Network error.");
    }
};

window.adminResetUsed = async (code) => {
    if (!confirm(`Reset reports used counter to 0 for ${code}?`)) return;

    const fd = new FormData();
    fd.append("admin_passcode", currentUser.passcode);
    fd.append("report_limit", 5);
    fd.append("reset_used", "true");

    try {
        const res = await fetch(`/api/admin/passcodes/${encodeURIComponent(code)}/adjust`, { method: 'POST', body: fd });
        if (res.ok) {
            loadAdminPasscodes();
        } else {
            alert("Failed to reset count.");
        }
    } catch (e) {
        alert("Network error.");
    }
};

window.adminRevokePasscode = async (code) => {
    if (!confirm(`Are you sure you want to REVOKE passcode '${code}'? This cannot be undone.`)) return;

    try {
        const res = await fetch(`/api/admin/passcodes/${encodeURIComponent(code)}?admin_passcode=${encodeURIComponent(currentUser.passcode)}`, {
            method: 'DELETE'
        });
        if (res.ok) {
            loadAdminPasscodes();
        } else {
            alert("Failed to revoke passcode.");
        }
    } catch (e) {
        alert("Network error.");
    }
};

// ==========================================================================
// Initialization
// ==========================================================================
document.addEventListener('DOMContentLoaded', () => {
    checkSavedSession();
});
