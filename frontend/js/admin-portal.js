/**
 * AWS SBG JRU — Executive Portal & Centralized Validation API Manager
 * Strictly accessible to officers with the `executive` role.
 * Zero plaintext passwords are ever displayed, returned, or exported in this module.
 */

const portalState = {
  subTab: "members", // 'members' | 'apikeys' | 'sdk'
  genMode: "approved", // 'approved' | 'csv'
  unprovisioned: [],
  selectedRegIds: new Set(),
  csvRows: [],
  members: [],
  membersTotal: 0,
  membersPage: 1,
  membersSearch: "",
  membersStatus: "all",
  apiKeys: [],
  validationLogs: [],
  lastBatchResult: null,
  newlyCreatedApiKey: null,
};

function portalEscapeHtml(val) {
  if (val === null || val === undefined) return "";
  return String(val)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function switchPortalSubTab(subTab) {
  portalState.subTab = subTab;
  document.querySelectorAll(".portal-subtab-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.subtab === subTab);
  });
  document.querySelectorAll(".portal-subpanel").forEach((panel) => {
    panel.style.display = panel.id === `portal-subpanel-${subTab}` ? "block" : "none";
  });

  if (subTab === "members") {
    loadUnprovisionedApproved();
    loadProvisionedMembers();
  } else if (subTab === "apikeys") {
    loadPortalApiKeys();
    loadPortalValidationLogs();
  } else if (subTab === "sdk") {
    populateSdkSnippets();
  }
}

function switchGeneratorMode(mode) {
  portalState.genMode = mode;
  document.querySelectorAll(".portal-genmode-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.genmode === mode);
  });
  const approvedBox = document.getElementById("portalGenApprovedBox");
  const csvBox = document.getElementById("portalGenCsvBox");
  if (approvedBox) approvedBox.style.display = mode === "approved" ? "block" : "none";
  if (csvBox) csvBox.style.display = mode === "csv" ? "block" : "none";
}

window.loadPortalView = function loadPortalView() {
  if (!state.user || state.user.role !== "executive") {
    showToast("Executive privileges required.", "error");
    return;
  }
  switchPortalSubTab(portalState.subTab || "members");
};

// ============================================================================
// 1. UNPROVISIONED APPROVED APPLICANTS & BULK GENERATOR
// ============================================================================

async function loadUnprovisionedApproved() {
  const tbody = document.getElementById("portalUnprovisionedBody");
  const countBadge = document.getElementById("portalUnprovisionedCount");
  if (!tbody) return;

  try {
    const res = await fetch(`${API_BASE}/api/v1/admin/portal/unprovisioned-approved`, {
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error("Failed to load approved applicants");
    const items = await res.json();
    portalState.unprovisioned = Array.isArray(items) ? items : [];
    portalState.selectedRegIds.clear();
    if (countBadge) countBadge.textContent = String(portalState.unprovisioned.length);
    renderUnprovisionedTable();
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-row">${portalEscapeHtml(err.message)}</td></tr>`;
  }
}

function renderUnprovisionedTable() {
  const tbody = document.getElementById("portalUnprovisionedBody");
  const selectAllCb = document.getElementById("portalSelectAllApproved");
  const btnGen = document.getElementById("btnGenerateFromApproved");
  if (!tbody) return;

  const list = portalState.unprovisioned;
  if (list.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-row">All approved applicants already have centralized portal credentials.</td></tr>`;
    if (selectAllCb) selectAllCb.checked = false;
    if (btnGen) {
      btnGen.disabled = true;
      btnGen.textContent = "Generate & Email Selected (0)";
    }
    return;
  }

  tbody.innerHTML = list
    .map((item) => {
      const checked = portalState.selectedRegIds.has(item.registration_id) ? "checked" : "";
      const rawDate = item.reviewed_at || item.created_at;
      const acceptedDate = rawDate ? rawDate.slice(0, 10) : "Today";
      return `
        <tr>
          <td style="width: 40px;">
            <input type="checkbox" class="portal-reg-cb" data-regid="${item.registration_id}" ${checked} onchange="toggleApprovedSelection(${item.registration_id}, this.checked)" />
          </td>
          <td>
            <div class="cell-primary">${portalEscapeHtml(item.full_name)}</div>
            <div class="cell-sub">${portalEscapeHtml(item.email)}</div>
          </td>
          <td>${portalEscapeHtml(item.student_id || "-")}</td>
          <td>
            <div class="cell-primary">${portalEscapeHtml(item.program || "-")}</div>
            <div class="cell-sub">${portalEscapeHtml(item.year || "-")}</div>
          </td>
          <td>${portalEscapeHtml(item.division_name || "-")}</td>
          <td><span class="portal-code-pill">${portalEscapeHtml(acceptedDate)}</span></td>
        </tr>
      `;
    })
    .join("");

  if (selectAllCb) {
    selectAllCb.checked = portalState.selectedRegIds.size === list.length && list.length > 0;
  }
  if (btnGen) {
    const count = portalState.selectedRegIds.size;
    btnGen.disabled = count === 0;
    btnGen.textContent = `Generate & Email Selected (${count})`;
  }
}

function toggleApprovedSelection(regId, isChecked) {
  if (isChecked) portalState.selectedRegIds.add(Number(regId));
  else portalState.selectedRegIds.delete(Number(regId));
  renderUnprovisionedTable();
}

function toggleSelectAllApproved(isChecked) {
  portalState.selectedRegIds.clear();
  if (isChecked) {
    portalState.unprovisioned.forEach((item) => portalState.selectedRegIds.add(item.registration_id));
  }
  renderUnprovisionedTable();
}

async function generateFromApprovedSelected() {
  const ids = Array.from(portalState.selectedRegIds);
  if (ids.length === 0) return;

  const btn = document.getElementById("btnGenerateFromApproved");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Generating & Dispatching Emails...";
  }

  try {
    const res = await fetch(`${API_BASE}/api/v1/admin/portal/members/generate-from-approved`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify({ registration_ids: ids }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Bulk generation failed");

    portalState.lastBatchResult = data;
    renderBatchSummaryBanner();
    showToast(`Generated ${data.generated_count} member credentials & dispatched emails!`, "success");
    await Promise.all([loadUnprovisionedApproved(), loadProvisionedMembers()]);
  } catch (err) {
    showToast(err.message || "Error generating credentials", "error");
    renderUnprovisionedTable();
  }
}

// ============================================================================
// 2. CSV BULK UPLOAD & PARSER
// ============================================================================

function downloadPortalCsvTemplate() {
  const headers = "first_name,last_name,email,student_id,year,program,division_type,division_name,accepted_date\n";
  const sample1 = "Juan,Dela Cruz,juan.delacruz@my.jru.edu,24-123456,Third Year,BS Information Technology,skillbuilder,Cloud Computing,2026-11-20\n";
  const sample2 = "Maria Clara,Santos,maria.santos@my.jru.edu,24-654321,Second Year,BS Computer Engineering,office,Operations,2026-11-20\n";
  const blob = new Blob([headers + sample1 + sample2], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "awssbg_member_import_template.csv";
  a.click();
  URL.revokeObjectURL(url);
}

function parseCsvLine(line) {
  const result = [];
  let current = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      inQuotes = !inQuotes;
    } else if (ch === "," && !inQuotes) {
      result.push(current.trim());
      current = "";
    } else {
      current += ch;
    }
  }
  result.push(current.trim());
  return result;
}

function handlePortalCsvFileSelect(event) {
  const file = event.target.files && event.target.files[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = (e) => {
    const text = String(e.target.result || "");
    const lines = text
      .split(/\r?\n/)
      .map((l) => l.trim())
      .filter(Boolean);

    if (lines.length < 2) {
      showToast("CSV file is empty or missing data rows.", "error");
      return;
    }

    const headerCols = parseCsvLine(lines[0]).map((h) => h.toLowerCase().replace(/\s+/g, "_"));
    const rows = [];

    for (let i = 1; i < lines.length; i++) {
      const vals = parseCsvLine(lines[i]);
      const obj = {};
      headerCols.forEach((col, idx) => {
        obj[col] = vals[idx] || "";
      });

      // Support full_name fallback if first_name / last_name not split
      let firstName = obj.first_name || "";
      let lastName = obj.last_name || "";
      if (!firstName && obj.full_name) {
        const parts = obj.full_name.trim().split(/\s+/);
        firstName = parts[0] || "";
        lastName = parts.slice(1).join(" ") || "Member";
      }

      rows.push({
        first_name: firstName,
        last_name: lastName,
        email: obj.email || "",
        student_id: obj.student_id || null,
        year: obj.year || null,
        program: obj.program || null,
        division_type: obj.division_type || null,
        division_name: obj.division_name || null,
        accepted_date: obj.accepted_date || null,
      });
    }

    portalState.csvRows = rows;
    renderCsvPreviewTable();
  };
  reader.readAsText(file);
}

function renderCsvPreviewTable() {
  const wrap = document.getElementById("portalCsvPreviewWrap");
  const tbody = document.getElementById("portalCsvPreviewBody");
  const btn = document.getElementById("btnGenerateFromCsv");
  if (!wrap || !tbody) return;

  if (portalState.csvRows.length === 0) {
    wrap.style.display = "none";
    return;
  }

  wrap.style.display = "block";
  tbody.innerHTML = portalState.csvRows
    .map((r, idx) => {
      const emailOk = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(r.email || "");
      const nameOk = Boolean(r.first_name && r.last_name);
      const badge =
        emailOk && nameOk
          ? `<span class="status-badge status-approved">Ready</span>`
          : `<span class="status-badge status-declined">Invalid Email/Name</span>`;
      return `
        <tr>
          <td>${idx + 1}</td>
          <td>${portalEscapeHtml(r.first_name)} ${portalEscapeHtml(r.last_name)}</td>
          <td>${portalEscapeHtml(r.email)}</td>
          <td>${portalEscapeHtml(r.student_id || "-")}</td>
          <td>${portalEscapeHtml(r.division_name || "-")}</td>
          <td>${portalEscapeHtml(r.accepted_date || "Today")}</td>
          <td>${badge}</td>
        </tr>
      `;
    })
    .join("");

  if (btn) {
    btn.disabled = false;
    btn.textContent = `Generate & Email Credentials for ${portalState.csvRows.length} CSV Row(s)`;
  }
}

async function generateFromCsvRows() {
  if (portalState.csvRows.length === 0) return;
  const btn = document.getElementById("btnGenerateFromCsv");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Generating & Dispatching Emails...";
  }

  try {
    const res = await fetch(`${API_BASE}/api/v1/admin/portal/members/generate-from-csv`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify({ members: portalState.csvRows }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "CSV bulk generation failed");

    portalState.lastBatchResult = data;
    portalState.csvRows = [];
    const fileInput = document.getElementById("portalCsvFileInput");
    if (fileInput) fileInput.value = "";
    renderCsvPreviewTable();
    renderBatchSummaryBanner();
    showToast(`Generated ${data.generated_count} member(s) from CSV & emailed credentials!`, "success");
    await loadProvisionedMembers();
  } catch (err) {
    showToast(err.message || "CSV generation error", "error");
    renderCsvPreviewTable();
  }
}

function renderBatchSummaryBanner() {
  const box = document.getElementById("portalBatchResultBanner");
  if (!box) return;
  const res = portalState.lastBatchResult;
  if (!res) {
    box.style.display = "none";
    return;
  }

  const rowsHtml = (res.members || [])
    .map(
      (m) => `
      <tr>
        <td><span class="portal-code-pill">${portalEscapeHtml(m.org_id)}</span></td>
        <td><span class="portal-code-pill">${portalEscapeHtml(m.username)}</span></td>
        <td>${portalEscapeHtml(m.full_name)}</td>
        <td>${portalEscapeHtml(m.email)}</td>
        <td>
          <span class="status-badge ${m.email_status === "failed" ? "status-declined" : "status-approved"}">
            ${portalEscapeHtml(m.email_status.toUpperCase())}
          </span>
        </td>
      </tr>
    `
    )
    .join("");

  const errHtml =
    res.errors && res.errors.length > 0
      ? `<div class="portal-batch-errors">
          <strong>Row Warnings (${res.errors.length}):</strong>
          <ul>${res.errors.map((e) => `<li>${portalEscapeHtml(e.identifier)}: ${portalEscapeHtml(e.error)}</li>`).join("")}</ul>
        </div>`
      : "";

  box.style.display = "block";
  box.innerHTML = `
    <div class="portal-batch-header">
      <div>
        <strong>Last Batch Summary:</strong> ${res.generated_count} Generated &bull; ${res.emailed_count} Emailed Directly &bull; ${res.failed_count} Skipped/Failed
        <div class="cell-sub">For security, temporary passwords were sent directly to each student's email and redacted from logs.</div>
      </div>
      <button type="button" class="btn-sm" onclick="dismissBatchSummary()">Dismiss</button>
    </div>
    ${errHtml}
    ${
      rowsHtml
        ? `<div class="table-scroll" style="margin-top: 0.75rem; max-height: 220px;">
            <table class="admin-table">
              <thead>
                <tr><th>Org ID</th><th>Username</th><th>Member</th><th>Email</th><th>SMTP Delivery</th></tr>
              </thead>
              <tbody>${rowsHtml}</tbody>
            </table>
          </div>`
        : ""
    }
  `;
}

function dismissBatchSummary() {
  portalState.lastBatchResult = null;
  renderBatchSummaryBanner();
}

// ============================================================================
// 3. PROVISIONED ORG MEMBERS DIRECTORY
// ============================================================================

async function loadProvisionedMembers(page = 1) {
  portalState.membersPage = page;
  const searchInput = document.getElementById("portalMemberSearch");
  const statusSelect = document.getElementById("portalMemberStatusFilter");
  const search = searchInput ? searchInput.value.trim() : "";
  const status = statusSelect ? statusSelect.value : "all";

  const tbody = document.getElementById("portalMembersBody");
  const totalEl = document.getElementById("portalMembersTotalBadge");
  if (!tbody) return;

  const params = new URLSearchParams({
    page: String(page),
    page_size: "20",
  });
  if (search) params.set("search", search);
  if (status && status !== "all") params.set("status", status);

  try {
    const res = await fetch(`${API_BASE}/api/v1/admin/portal/members?${params.toString()}`, {
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error("Failed to load org members");
    const data = await res.json();
    portalState.members = data.members || [];
    portalState.membersTotal = data.total || 0;
    if (totalEl) totalEl.textContent = `${portalState.membersTotal} Total`;
    renderProvisionedMembersTable();
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7" class="empty-row">${portalEscapeHtml(err.message)}</td></tr>`;
  }
}

function renderProvisionedMembersTable() {
  const tbody = document.getElementById("portalMembersBody");
  if (!tbody) return;

  if (portalState.members.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="empty-row">No provisioned org members found. Use the generator above to provision members.</td></tr>`;
    return;
  }

  tbody.innerHTML = portalState.members
    .map((m) => {
      const statusClass =
        m.status === "active"
          ? "status-approved"
          : m.status === "suspended"
          ? "status-revision_requested"
          : "status-declined";
      const toggleStatus = m.status === "active" ? "suspended" : "active";
      const toggleLabel = m.status === "active" ? "Suspend" : "Activate";

      return `
        <tr>
          <td><span class="portal-code-pill">${portalEscapeHtml(m.org_id)}</span></td>
          <td><span class="portal-code-pill">${portalEscapeHtml(m.username)}</span></td>
          <td>
            <div class="cell-primary">${portalEscapeHtml(m.full_name)}</div>
            <div class="cell-sub">${portalEscapeHtml(m.email)}</div>
          </td>
          <td>
            <div class="cell-primary">${portalEscapeHtml(m.division_name || "-")}</div>
            <div class="cell-sub">${portalEscapeHtml(m.program || "-")}</div>
          </td>
          <td>${portalEscapeHtml(m.accepted_date)}</td>
          <td><span class="status-badge ${statusClass}">${portalEscapeHtml(m.status.toUpperCase())}</span></td>
          <td>
            <div style="display: flex; gap: 0.4rem; flex-wrap: wrap;">
              <button type="button" class="btn-sm btn-primary-sm" onclick="resetAndEmailMemberPassword('${portalEscapeHtml(m.id)}', '${portalEscapeHtml(m.org_id)}')">
                Reset &amp; Email PW
              </button>
              <button type="button" class="btn-sm" onclick="changeOrgMemberStatus('${portalEscapeHtml(m.id)}', '${toggleStatus}')">
                ${toggleLabel}
              </button>
            </div>
          </td>
        </tr>
      `;
    })
    .join("");
}

async function resetAndEmailMemberPassword(memberId, orgId) {
  if (!confirm(`Generate a new temporary password for ${orgId} and email it directly to the student?`)) {
    return;
  }
  try {
    const res = await fetch(`${API_BASE}/api/v1/admin/portal/members/${memberId}/reset-password`, {
      method: "POST",
      headers: getHeaders(),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Password reset failed");
    showToast(`New temporary password emailed to ${data.email} (${data.email_status}).`, "success");
    loadProvisionedMembers(portalState.membersPage);
  } catch (err) {
    showToast(err.message || "Failed to reset password", "error");
  }
}

async function changeOrgMemberStatus(memberId, newStatus) {
  try {
    const res = await fetch(`${API_BASE}/api/v1/admin/portal/members/${memberId}/status`, {
      method: "PATCH",
      headers: getHeaders(),
      body: JSON.stringify({ status: newStatus }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Status update failed");
    showToast(`Member ${data.org_id} marked as ${newStatus.toUpperCase()}.`, "info");
    loadProvisionedMembers(portalState.membersPage);
  } catch (err) {
    showToast(err.message || "Failed to update status", "error");
  }
}

// ============================================================================
// 4. EXTERNAL API KEYS & VALIDATION AUDIT LOGS
// ============================================================================

async function loadPortalApiKeys() {
  const tbody = document.getElementById("portalApiKeysBody");
  if (!tbody) return;

  try {
    const res = await fetch(`${API_BASE}/api/v1/admin/portal/api-keys`, {
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error("Failed to load API keys");
    portalState.apiKeys = await res.json();
    renderPortalApiKeysTable();
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-row">${portalEscapeHtml(err.message)}</td></tr>`;
  }
}

function renderPortalApiKeysTable() {
  const tbody = document.getElementById("portalApiKeysBody");
  if (!tbody) return;

  if (portalState.apiKeys.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-row">No external API keys created yet. Create one above to connect an external system.</td></tr>`;
    return;
  }

  tbody.innerHTML = portalState.apiKeys
    .map((k) => {
      const badge = k.is_active
        ? `<span class="status-badge status-approved">ACTIVE</span>`
        : `<span class="status-badge status-declined">REVOKED</span>`;
      const lastUsed = k.last_used_at ? new Date(k.last_used_at).toLocaleString() : "Never";
      const actionBtn = k.is_active
        ? `<button type="button" class="btn-sm" style="color: var(--accent-red);" onclick="revokePortalApiKey('${portalEscapeHtml(k.id)}', '${portalEscapeHtml(k.name)}')">Revoke Key</button>`
        : `<span class="cell-sub">Revoked</span>`;

      return `
        <tr>
          <td>
            <div class="cell-primary">${portalEscapeHtml(k.name)}</div>
            <div class="cell-sub">Created by ${portalEscapeHtml(k.created_by || "Executive")}</div>
          </td>
          <td><span class="portal-code-pill">${portalEscapeHtml(k.key_prefix)}...</span></td>
          <td>${k.rate_limit_per_min} req/min</td>
          <td>${portalEscapeHtml(lastUsed)}</td>
          <td>${badge}</td>
          <td>${actionBtn}</td>
        </tr>
      `;
    })
    .join("");
}

async function createPortalApiKey(event) {
  event.preventDefault();
  const nameInput = document.getElementById("portalApiKeyName");
  const rateInput = document.getElementById("portalApiKeyRate");
  const name = nameInput ? nameInput.value.trim() : "";
  const rate = rateInput ? parseInt(rateInput.value, 10) || 60 : 60;
  if (!name) return;

  try {
    const res = await fetch(`${API_BASE}/api/v1/admin/portal/api-keys`, {
      method: "POST",
      headers: getHeaders(),
      body: JSON.stringify({ name, rate_limit_per_min: rate }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed to create API key");

    portalState.newlyCreatedApiKey = data;
    if (nameInput) nameInput.value = "";
    renderNewlyCreatedApiKeyBox();
    showToast(`API Key created for "${data.name}". Copy it now — it won't be shown again!`, "success");
    loadPortalApiKeys();
  } catch (err) {
    showToast(err.message || "Error creating API key", "error");
  }
}

function renderNewlyCreatedApiKeyBox() {
  const box = document.getElementById("portalNewKeyRevealBox");
  if (!box) return;
  const k = portalState.newlyCreatedApiKey;
  if (!k) {
    box.style.display = "none";
    return;
  }

  box.style.display = "block";
  box.innerHTML = `
    <div class="portal-key-reveal-inner">
      <div>
        <strong>One-Time Secret API Key for "${portalEscapeHtml(k.name)}":</strong>
        <div class="cell-sub">Copy this key into your external project's <code>.env</code> as <code>AWSSBG_API_KEY</code>. Only the SHA-256 hash is stored in our database.</div>
      </div>
      <div class="portal-key-copy-row">
        <code id="portalRevealedKeyText">${portalEscapeHtml(k.api_key)}</code>
        <button type="button" class="btn-sm btn-primary-sm" onclick="copyTextToClipboard('${portalEscapeHtml(k.api_key)}', 'API Key copied to clipboard!')">Copy Key</button>
        <button type="button" class="btn-sm" onclick="portalState.newlyCreatedApiKey = null; renderNewlyCreatedApiKeyBox();">Hide</button>
      </div>
    </div>
  `;
}

async function revokePortalApiKey(keyId, keyName) {
  if (!confirm(`Immediately revoke API key for "${keyName}"? Any external system using this key will receive 401 Unauthorized.`)) {
    return;
  }
  try {
    const res = await fetch(`${API_BASE}/api/v1/admin/portal/api-keys/${keyId}/revoke`, {
      method: "POST",
      headers: getHeaders(),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed to revoke API key");
    showToast(`Revoked API key "${keyName}".`, "info");
    loadPortalApiKeys();
  } catch (err) {
    showToast(err.message || "Error revoking API key", "error");
  }
}

async function loadPortalValidationLogs() {
  const tbody = document.getElementById("portalValidationLogsBody");
  if (!tbody) return;

  try {
    const res = await fetch(`${API_BASE}/api/v1/admin/portal/validation-logs?limit=40`, {
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error("Failed to load validation logs");
    portalState.validationLogs = await res.json();
    renderPortalValidationLogs();
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-row">${portalEscapeHtml(err.message)}</td></tr>`;
  }
}

function renderPortalValidationLogs() {
  const tbody = document.getElementById("portalValidationLogsBody");
  if (!tbody) return;

  if (portalState.validationLogs.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-row">No external API validation attempts recorded yet.</td></tr>`;
    return;
  }

  tbody.innerHTML = portalState.validationLogs
    .map((log) => {
      const outcomeClass =
        log.outcome === "valid"
          ? "status-approved"
          : log.outcome === "rate_limited"
          ? "status-revision_requested"
          : "status-declined";
      const ts = log.created_at ? new Date(log.created_at).toLocaleString() : "-";
      return `
        <tr>
          <td>${portalEscapeHtml(ts)}</td>
          <td>${portalEscapeHtml(log.api_key_name || "-")}</td>
          <td><span class="portal-code-pill">${portalEscapeHtml(log.org_id_attempted || "-")}</span></td>
          <td><span class="portal-code-pill">${portalEscapeHtml(log.username_attempted || "-")}</span></td>
          <td><span class="status-badge ${outcomeClass}">${portalEscapeHtml(log.outcome.toUpperCase())}</span></td>
          <td>${portalEscapeHtml(log.client_ip || "-")}</td>
        </tr>
      `;
    })
    .join("");
}

// ============================================================================
// 5. PLUG-AND-PLAY SDK, AI AGENT PROMPT & LIVE TEST SANDBOX
// ============================================================================

function getPublicOrigin() {
  return window.location.origin || "https://awssbgjru.me";
}

function populateSdkSnippets() {
  const origin = getPublicOrigin();
  const jsEl = document.getElementById("portalSnippetJs");
  const pyEl = document.getElementById("portalSnippetPy");
  const aiEl = document.getElementById("portalSnippetAiPrompt");

  if (jsEl) {
    jsEl.textContent = `# 1. Drop zero-dependency SDK into your JS/TS project folder:
curl -fsSL ${origin}/sdk/js/awssbg-auth-sdk.js -o awssbg-auth-sdk.js
curl -fsSL ${origin}/sdk/js/awssbg-auth-sdk.d.ts -o awssbg-auth-sdk.d.ts

// 2. Call from your backend route (Node 18+ / Next.js / Express):
import { AwsSbgAuthClient } from "./awssbg-auth-sdk.js";

const sbgAuth = new AwsSbgAuthClient({
  baseUrl: process.env.AWSSBG_API_URL || "${origin}",
  apiKey: process.env.AWSSBG_API_KEY,
});

const result = await sbgAuth.validateMember({
  orgId: req.body.org_id,       // e.g. "AWSSBG-1120-001"
  username: req.body.username,  // e.g. "j.delacruz482"
  password: req.body.password,
});

if (result.valid) {
  // Authenticated! Access safe member profile:
  console.log(result.member.full_name, result.member.division_name);
}`;
  }

  if (pyEl) {
    pyEl.textContent = `# 1. Drop zero-dependency SDK into your Python project folder:
curl -fsSL ${origin}/sdk/python/awssbg_auth_sdk.py -o awssbg_auth_sdk.py

# 2. Call from your backend route (FastAPI / Flask / Django):
import os
from awssbg_auth_sdk import AwsSbgAuthClient

sbg_auth = AwsSbgAuthClient(
    base_url=os.getenv("AWSSBG_API_URL", "${origin}"),
    api_key=os.environ["AWSSBG_API_KEY"],
)

result = sbg_auth.validate_member(
    org_id=payload.org_id,
    username=payload.username,
    password=payload.password,
)
if result["valid"]:
    member = result["member"]  # full_name, division_name, program, year, status`;
  }

  if (aiEl) {
    aiEl.textContent = `Integrate AWS SBG JRU Centralized Member Login into this project.
Read the machine-readable specification and download the zero-dependency SDK directly from:
- LLM Integration Guide: ${origin}/sdk/llms.txt
- Drop-in Agent Skill: ${origin}/sdk/AGENT_SKILL.md
- Scoped OpenAPI 3.1 Spec: ${origin}/api/v1/external/openapi.json
- JS/TS SDK: ${origin}/sdk/js/awssbg-auth-sdk.js
- Python SDK: ${origin}/sdk/python/awssbg_auth_sdk.py

Requirements:
1. Build a login form asking for Org ID (AWSSBG-MMDD-NNN), Username, and Password.
2. Validate credentials server-side via POST ${origin}/api/v1/external/validate with header X-API-Key: process.env.AWSSBG_API_KEY.
3. Never expose AWSSBG_API_KEY to the browser or log plaintext passwords.`;
  }
}

function copyTextToClipboard(text, toastMsg = "Copied to clipboard!") {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(() => showToast(toastMsg, "success"));
  } else {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
    showToast(toastMsg, "success");
  }
}

function copyPortalElementText(elementId, toastMsg) {
  const el = document.getElementById(elementId);
  if (!el) return;
  copyTextToClipboard(el.textContent || "", toastMsg);
}

async function runPortalSandboxValidation(event) {
  event.preventDefault();
  const apiKey = (document.getElementById("sandboxApiKey")?.value || "").trim();
  const orgId = (document.getElementById("sandboxOrgId")?.value || "").trim();
  const username = (document.getElementById("sandboxUsername")?.value || "").trim();
  const password = document.getElementById("sandboxPassword")?.value || "";
  const outEl = document.getElementById("sandboxResultOutput");
  if (!outEl) return;

  outEl.style.display = "block";
  outEl.textContent = "Calling POST /api/v1/external/validate ...";

  try {
    const res = await fetch(`${API_BASE}/api/v1/external/validate`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": apiKey,
      },
      body: JSON.stringify({
        org_id: orgId,
        username: username,
        password: password,
      }),
    });
    const data = await res.json();
    outEl.textContent = `HTTP ${res.status}\n` + JSON.stringify(data, null, 2);
  } catch (err) {
    outEl.textContent = `Request Error: ${err.message}`;
  }
}
