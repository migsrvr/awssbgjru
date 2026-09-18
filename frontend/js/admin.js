/**
 * AWS SBG JRU - Admin Review Panel JavaScript
 * Client logic for queue management, applicant review, email preview & dispatch
 */

const API_BASE = (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1")
  ? `http://${window.location.hostname}:${window.location.port || "8000"}`
  : "";

let cachedUser = null;
try {
  const u = localStorage.getItem("admin_user");
  if (u) cachedUser = JSON.parse(u);
} catch (_) {}

const state = {
  token: localStorage.getItem("admin_token") || "",
  user: cachedUser,
  currentView: "dashboard",
  applications: [],
  recentApplications: [],
  total: 0,
  page: 1,
  pageSize: 15,
  statusCounts: {},
  filters: {
    status: "all",
    search: "",
    year: "",
    program: "",
    division_type: "",
  },
  activeApp: null,
  rubricItems: [],
  templates: [],
  settings: {
    registration_open: true,
    closed_message: "",
  },
  pendingDecision: null, // holds decision type when opening email confirmation modal
};

// ---------------- Initialization ----------------
document.addEventListener("DOMContentLoaded", () => {
  initNav();
  initFilters();
  initLogin();
  checkAuth();
});

function getHeaders() {
  const headers = {
    "Content-Type": "application/json",
  };
  if (state.token) {
    headers["Authorization"] = `Bearer ${state.token}`;
  }
  return headers;
}

// ---------------- Toast Notifications ----------------
function showToast(message, type = "info") {
  const container = document.getElementById("toastContainer");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    setTimeout(() => toast.remove(), 250);
  }, 4000);
}

// ---------------- Authentication & Session ----------------
function checkAuth() {
  if (!state.token) {
    showLoginScreen();
    return;
  }

  // Instantly activate workspace without waiting for server response
  hideLoginScreen();
  if (state.user) {
    renderUserHeader();
  }

  // Restore view from URL hash or previous session
  const validViews = ["dashboard", "queue", "templates", "settings", "audit"];
  const hash = window.location.hash.replace("#", "").trim();
  const savedView = localStorage.getItem("admin_active_view");
  const initialView = validViews.includes(hash) ? hash : (validViews.includes(savedView) ? savedView : "dashboard");
  switchView(initialView);

  // Background verification of token with /me (non-blocking)
  fetch(`${API_BASE}/api/v1/admin/me`, { headers: getHeaders() })
    .then((res) => {
      if (res.status === 401 || res.status === 403) {
        throw new Error("UNAUTHORIZED");
      }
      if (!res.ok) throw new Error("SERVER_ERROR");
      return res.json();
    })
    .then((userData) => {
      state.user = userData;
      localStorage.setItem("admin_user", JSON.stringify(userData));
      renderUserHeader();
    })
    .catch((err) => {
      // Only logout if token is confirmed invalid or expired
      if (err.message === "UNAUTHORIZED") {
        logout();
      } else {
        console.warn("Notice: /me session validation completed with non-fatal status:", err);
      }
    });
}

function initLogin() {
  const loginForm = document.getElementById("loginForm");
  if (loginForm) {
    loginForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const email = document.getElementById("loginEmail").value.trim();
      const password = document.getElementById("loginPassword").value;
      const btn = loginForm.querySelector("button[type='submit']");
      btn.disabled = true;
      btn.textContent = "Authenticating...";

      // Attempt Supabase auth or fallback token
      loginWithCredentials(email, password)
        .then(() => {
          checkAuth();
        })
        .catch((err) => {
          showToast(err.message || "Login failed", "error");
        })
        .finally(() => {
          btn.disabled = false;
          btn.textContent = "Sign In as Officer";
        });
    });
  }

}

async function loginWithCredentials(email, password) {
  const res = await fetch(`${API_BASE}/api/v1/admin/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });

  if (!res.ok) {
    let errMsg = "Invalid email or password.";
    try {
      const errPayload = await res.json();
      errMsg = errPayload.detail || errMsg;
    } catch (_) {}
    throw new Error(errMsg);
  }

  const data = await res.json();
  state.token = data.access_token;
  state.user = data.user;
  localStorage.setItem("admin_token", state.token);
  localStorage.setItem("admin_user", JSON.stringify(state.user));
  document.documentElement.classList.add("admin-authenticated");
}

function logout() {
  state.token = "";
  state.user = null;
  localStorage.removeItem("admin_token");
  localStorage.removeItem("admin_user");
  localStorage.removeItem("admin_active_view");
  document.documentElement.classList.remove("admin-authenticated");
  showLoginScreen();
  showToast("Logged out successfully", "info");
}

function showLoginScreen() {
  document.documentElement.classList.remove("admin-authenticated");
  document.getElementById("loginScreen").style.display = "flex";
  document.getElementById("adminMainContent").style.display = "none";
  document.getElementById("adminNavbar").style.display = "none";
}

function hideLoginScreen() {
  document.documentElement.classList.add("admin-authenticated");
  document.getElementById("loginScreen").style.display = "none";
  document.getElementById("adminMainContent").style.display = "block";
  document.getElementById("adminNavbar").style.display = "flex";
}

function renderUserHeader() {
  const nameEl = document.getElementById("officerName");
  const roleEl = document.getElementById("officerRole");
  if (nameEl && state.user) nameEl.textContent = state.user.full_name;
  if (roleEl && state.user) roleEl.textContent = `(${state.user.role.toUpperCase()})`;

  // Hide admin-only tabs if reviewer
  if (state.user && state.user.role !== "administrator") {
    document.querySelectorAll(".admin-only").forEach((el) => (el.style.display = "none"));
  }
}

// ---------------- View Navigation ----------------
function initNav() {
  document.querySelectorAll(".admin-nav-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      const view = tab.dataset.view;
      switchView(view);
    });
  });

  const logoutBtn = document.getElementById("btnLogout");
  if (logoutBtn) logoutBtn.addEventListener("click", logout);
}

function switchView(viewName) {
  state.currentView = viewName;
  localStorage.setItem("admin_active_view", viewName);
  window.location.hash = viewName;

  document.querySelectorAll(".admin-nav-tab").forEach((t) => {
    t.classList.toggle("active", t.dataset.view === viewName);
  });
  document.querySelectorAll(".admin-view").forEach((v) => {
    v.classList.remove("active");
  });
  const activeViewEl = document.getElementById(`view-${viewName}`);
  if (activeViewEl) activeViewEl.classList.add("active");

  if (viewName === "dashboard") loadDashboard();
  else if (viewName === "queue") loadQueue();
  else if (viewName === "templates") loadTemplates();
  else if (viewName === "settings") loadSettings();
  else if (viewName === "audit") loadAuditLogs();
}

// ---------------- Dashboard ----------------
function loadDashboard() {
  fetch(`${API_BASE}/api/v1/admin/metrics`, { headers: getHeaders() })
    .then((res) => {
      if (!res.ok) throw new Error("Metrics response not ok");
      return res.json();
    })
    .then((data) => {
      updateKpiElements(data);
    })
    .catch((err) => console.warn("Metrics load notice:", err));

  // Quick queue list in dashboard
  fetch(`${API_BASE}/api/v1/admin/applications?page_size=5&status=new`, { headers: getHeaders() })
    .then((res) => {
      if (!res.ok) throw new Error("Recent queue response not ok");
      return res.json();
    })
    .then((data) => {
      state.recentApplications = data.applications || [];
      renderRecentQueue(state.recentApplications);
    })
    .catch((err) => console.warn("Recent queue load notice:", err));
}

function updateKpiElements(data) {
  if (!data) return;
  const totalEl = document.getElementById("metricTotal");
  const turnaroundEl = document.getElementById("metricTurnaround");
  if (totalEl) totalEl.textContent = data.total_applications || 0;
  if (turnaroundEl) turnaroundEl.textContent = `${data.median_turnaround_hours || 0} hrs`;

  const breakdown = data.status_breakdown || {};
  const map = {
    metricNew: breakdown.new || 0,
    metricUnderReview: breakdown.under_review || 0,
    metricApproved: breakdown.approved || 0,
    metricRevision: breakdown.revision_requested || 0,
    metricDeclined: breakdown.declined || 0,
  };
  for (const [id, val] of Object.entries(map)) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  }
}

function renderRecentQueue(apps) {
  const container = document.getElementById("recentQueueBody");
  if (!container) return;
  if (apps.length === 0) {
    container.innerHTML = `<tr><td colspan="5" class="empty-state-cell">No new applications waiting in queue.</td></tr>`;
    return;
  }
  container.innerHTML = apps
    .map(
      (app) => `
    <tr>
      <td>
        <div class="applicant-cell">
          <div class="avatar-circle">${escapeHtml(app.full_name.charAt(0))}</div>
          <div>
            <div class="applicant-info-name">${escapeHtml(app.full_name)}</div>
            <div class="applicant-info-id">${escapeHtml(app.student_id)}</div>
          </div>
        </div>
      </td>
      <td>${escapeHtml(app.program)} (${escapeHtml(app.year)})</td>
      <td>${escapeHtml(app.division_name)}</td>
      <td><span class="badge badge-${escapeHtml(app.application_status)}">${escapeHtml(app.application_status.replace("_", " "))}</span></td>
      <td>
        <button class="btn-sm btn-primary-sm" onclick="openReviewModal(${app.id})">Review</button>
      </td>
    </tr>
  `
    )
    .join("");
}

// ---------------- Queue View ----------------
function initFilters() {
  const searchInput = document.getElementById("queueSearchInput");
  if (searchInput) {
    let debounceTimeout = null;
    searchInput.addEventListener("input", () => {
      clearTimeout(debounceTimeout);
      debounceTimeout = setTimeout(() => {
        state.filters.search = searchInput.value.trim();
        state.page = 1;
        loadQueue();
      }, 300);
    });
  }

  ["filterYear", "filterProgram", "filterDivision"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener("change", () => {
        if (id === "filterYear") state.filters.year = el.value;
        if (id === "filterProgram") state.filters.program = el.value;
        if (id === "filterDivision") state.filters.division_type = el.value;
        state.page = 1;
        loadQueue();
      });
    }
  });

  // Status pills
  document.querySelectorAll(".status-pill-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".status-pill-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.filters.status = btn.dataset.status;
      state.page = 1;
      loadQueue();
    });
  });

  const prevBtn = document.getElementById("queuePrevPage");
  const nextBtn = document.getElementById("queueNextPage");
  if (prevBtn) {
    prevBtn.addEventListener("click", () => {
      if (state.page > 1) {
        state.page--;
        loadQueue();
      }
    });
  }
  if (nextBtn) {
    nextBtn.addEventListener("click", () => {
      if (state.page * state.pageSize < state.total) {
        state.page++;
        loadQueue();
      }
    });
  }
}

function loadQueue() {
  const params = new URLSearchParams({
    page: state.page,
    page_size: state.pageSize,
  });

  if (state.filters.status && state.filters.status !== "all") params.append("status", state.filters.status);
  if (state.filters.search) params.append("search", state.filters.search);
  if (state.filters.year) params.append("year", state.filters.year);
  if (state.filters.program) params.append("program", state.filters.program);
  if (state.filters.division_type) params.append("division_type", state.filters.division_type);

  fetch(`${API_BASE}/api/v1/admin/applications?${params.toString()}`, { headers: getHeaders() })
    .then((res) => res.json())
    .then((data) => {
      state.applications = data.applications || [];
      state.total = data.total || 0;
      state.statusCounts = data.status_counts || {};
      updateStatusCounters();
      renderQueueTable();
      updatePaginationControls();
    })
    .catch((err) => {
      console.error("Queue load failed:", err);
      showToast("Failed to load queue applications", "error");
    });
}

function updateStatusCounters() {
  for (const [key, count] of Object.entries(state.statusCounts)) {
    const pill = document.querySelector(`.status-pill-btn[data-status="${key}"] .status-pill-count`);
    if (pill) pill.textContent = count;
  }
}

function renderQueueTable() {
  const tbody = document.getElementById("queueTableBody");
  if (!tbody) return;

  if (state.applications.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="empty-state-cell empty-state-cell-lg">No applications match the active filters.</td></tr>`;
    return;
  }

  tbody.innerHTML = state.applications
    .map((app) => {
      const isClaimedByMe = state.user && app.assigned_reviewer_id === state.user.id;
      const isClaimedByOther = app.assigned_reviewer_id && !isClaimedByMe;

      let claimDisplay = `<span class="claim-tag">Unclaimed</span>`;
      if (isClaimedByMe) {
        claimDisplay = `<span class="claim-tag claimed-by-me">Claimed by You</span>`;
      } else if (isClaimedByOther) {
        claimDisplay = `<span class="claim-tag" title="Review in progress">${escapeHtml(app.assigned_reviewer_name || "Officer")}</span>`;
      }

      return `
      <tr>
        <td>
          <div class="applicant-cell">
            <div class="avatar-circle">${escapeHtml(app.full_name.charAt(0))}</div>
            <div>
              <div class="applicant-info-name">${escapeHtml(app.full_name)}</div>
              <div class="applicant-info-id">${escapeHtml(app.student_id)}</div>
            </div>
          </div>
        </td>
        <td>${escapeHtml(app.email)}</td>
        <td>${escapeHtml(app.program)}</td>
        <td>${escapeHtml(app.division_name)}</td>
        <td><span class="badge badge-${escapeHtml(app.application_status)}">${escapeHtml(app.application_status.replace("_", " "))}</span></td>
        <td>${claimDisplay}</td>
        <td>
          <button class="btn-sm btn-primary-sm" onclick="openReviewModal(${app.id})">Open</button>
        </td>
      </tr>
    `;
    })
    .join("");
}

function updatePaginationControls() {
  const info = document.getElementById("paginationInfo");
  const prev = document.getElementById("queuePrevPage");
  const next = document.getElementById("queueNextPage");

  const start = state.total === 0 ? 0 : (state.page - 1) * state.pageSize + 1;
  const end = Math.min(state.page * state.pageSize, state.total);
  if (info) info.textContent = `Showing ${start}-${end} of ${state.total} applications`;

  if (prev) prev.disabled = state.page <= 1;
  if (next) next.disabled = end >= state.total;
}

// ---------------- Review Workspace Modal ----------------
window.openReviewModal = function (appId) {
  fetch(`${API_BASE}/api/v1/admin/applications/${appId}`, { headers: getHeaders() })
    .then((res) => res.json())
    .then((app) => {
      state.activeApp = app;
      renderReviewModal(app);
      document.getElementById("reviewModalOverlay").classList.add("active");
    })
    .catch((err) => {
      showToast(err.message || "Failed to load application detail", "error");
    });
};

function closeReviewModal() {
  document.getElementById("reviewModalOverlay").classList.remove("active");
  state.activeApp = null;
}

function renderReviewModal(app) {
  document.getElementById("modalApplicantName").textContent = app.full_name;
  document.getElementById("modalStudentId").textContent = app.student_id;
  document.getElementById("modalEmail").textContent = app.email;
  document.getElementById("modalProgram").textContent = `${app.program} — ${app.year}`;
  document.getElementById("modalDob").textContent = app.dob || "Not provided";
  document.getElementById("modalDivision").textContent = `${app.division_name} (${app.division_type.toUpperCase()})`;
  document.getElementById("modalStatusBadge").innerHTML = `<span class="badge badge-${escapeHtml(app.application_status)}">${escapeHtml(app.application_status.replace("_", " "))}</span>`;

  // Photo
  const photoEl = document.getElementById("modalPhotoPreview");
  if (app.photo_base64) {
    photoEl.src = app.photo_base64;
    photoEl.style.display = "block";
  } else {
    photoEl.style.display = "none";
  }

  // Explanation
  document.getElementById("modalExplanation").textContent = app.explanation || "No statement provided.";

  // Claim button state
  renderClaimButton(app);

  // Rubric checklist
  loadAndRenderRubric();

  // Notes Thread
  renderNotesThread(app.reviews || []);
}

function renderClaimButton(app) {
  const claimBtn = document.getElementById("btnModalClaim");
  if (!claimBtn) return;

  const isClaimedByMe = state.user && app.assigned_reviewer_id === state.user.id;
  if (isClaimedByMe) {
    claimBtn.textContent = "Release Claim";
    claimBtn.className = "btn-sm";
    claimBtn.onclick = () => releaseCurrentApp();
  } else {
    claimBtn.textContent = "Claim Application";
    claimBtn.className = "btn-sm btn-primary-sm";
    claimBtn.onclick = () => claimCurrentApp();
  }
}

function claimCurrentApp() {
  if (!state.activeApp) return;
  const appId = state.activeApp.id;
  const myId = state.user ? state.user.id : "officer";
  const myName = state.user ? state.user.full_name : "You";

  // Instant optimistic update
  state.activeApp.assigned_reviewer_id = myId;
  state.activeApp.assigned_reviewer_name = myName;
  renderClaimButton(state.activeApp);

  const rowApp = state.applications.find((a) => a.id === appId);
  if (rowApp) {
    rowApp.assigned_reviewer_id = myId;
    rowApp.assigned_reviewer_name = myName;
    renderQueueTable();
  }
  showToast("Application claimed!", "success");

  fetch(`${API_BASE}/api/v1/admin/applications/${appId}/claim`, {
    method: "POST",
    headers: getHeaders(),
  })
    .then((res) => {
      if (!res.ok) throw new Error("Could not claim application");
      return res.json();
    })
    .catch((err) => {
      showToast(err.message, "error");
      openReviewModal(appId);
    });
}

function releaseCurrentApp() {
  if (!state.activeApp) return;
  const appId = state.activeApp.id;

  // Instant optimistic update
  state.activeApp.assigned_reviewer_id = null;
  state.activeApp.assigned_reviewer_name = null;
  renderClaimButton(state.activeApp);

  const rowApp = state.applications.find((a) => a.id === appId);
  if (rowApp) {
    rowApp.assigned_reviewer_id = null;
    rowApp.assigned_reviewer_name = null;
    renderQueueTable();
  }
  showToast("Application released back to queue", "info");

  fetch(`${API_BASE}/api/v1/admin/applications/${appId}/release`, {
    method: "POST",
    headers: getHeaders(),
  })
    .then((res) => res.json())
    .catch((err) => {
      showToast(err.message, "error");
      openReviewModal(appId);
    });
}

function loadAndRenderRubric() {
  const rubricContainer = document.getElementById("rubricContainer");
  if (!rubricContainer) return;

  // Fetch settings rubric
  fetch(`${API_BASE}/api/v1/admin/settings`, { headers: getHeaders() })
    .then((res) => res.json())
    .then((settings) => {
      const items = settings.qualification_rubric || [];
      state.rubricItems = items;
      rubricContainer.innerHTML = items
        .map(
          (item) => `
        <label class="rubric-item">
          <input type="checkbox" id="rubric_${escapeHtml(item.id)}" />
          <span class="rubric-label">${escapeHtml(item.label)}</span>
        </label>
      `
        )
        .join("");
    })
    .catch(() => {
      rubricContainer.innerHTML = `<p class="decision-hint">Standard JRU Enrollment & Authentic Interest checks</p>`;
    });
}

function renderNotesThread(reviews) {
  const container = document.getElementById("notesThread");
  if (!container) return;

  const notesReviews = reviews.filter((r) => r.internal_notes && r.internal_notes.trim());
  if (notesReviews.length === 0) {
    container.innerHTML = `<div class="decision-hint" style="text-align:center;padding:0.75rem;">No internal notes added yet.</div>`;
    return;
  }

  container.innerHTML = notesReviews
    .map((r) => {
      const timeStr = new Date(r.created_at).toLocaleDateString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
      return `
      <div class="note-bubble">
        <div class="note-bubble-meta">${escapeHtml(r.reviewer_name)} • ${escapeHtml(timeStr)}</div>
        <div>${escapeHtml(r.internal_notes)}</div>
      </div>
    `;
    })
    .join("");
}

window.submitQuickNote = function () {
  const input = document.getElementById("inputQuickNote");
  if (!input || !input.value.trim() || !state.activeApp) return;
  const noteText = input.value.trim();
  input.value = "";

  const myName = state.user ? state.user.full_name : "You";
  if (!state.activeApp.reviews) state.activeApp.reviews = [];
  state.activeApp.reviews.push({
    reviewer_name: myName,
    created_at: new Date().toISOString(),
    internal_notes: noteText,
  });
  renderNotesThread(state.activeApp.reviews);
  showToast("Note added", "success");

  fetch(`${API_BASE}/api/v1/admin/applications/${state.activeApp.id}/notes`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({ notes: noteText }),
  }).catch((err) => showToast(err.message || "Failed to add note", "error"));
};

// ---------------- Decision Flow, Banners & Email Preview ----------------
state.generalQrBase64 = "";
state.divisionQrBase64 = "";
state.activeEmailTab = "compose";

window.initiateDecision = function (decisionType) {
  if (!state.activeApp) return;
  state.pendingDecision = decisionType;

  // Reset QR attachments and modal view
  removeQr("general");
  removeQr("division");
  switchEmailModalTab("compose");

  // Gather rubric scores
  const rubricScores = {};
  state.rubricItems.forEach((item) => {
    const chk = document.getElementById(`rubric_${item.id}`);
    if (chk) rubricScores[item.id] = chk.checked;
  });

  if (decisionType === "pending") {
    // Immediate save without email
    submitDecisionPayload({
      decision: "pending",
      internal_notes: "Marked as pending review.",
      rubric_scores: rubricScores,
      send_email: false,
    });
    return;
  }

  // Open Email Preview modal
  document.getElementById("confirmDecisionTitle").textContent = `Confirm Action: ${decisionType.toUpperCase().replace("_", " ")}`;
  document.getElementById("emailRecipient").textContent = state.activeApp.email;

  // Show / hide specific fields based on decision
  const nextStepsGroup = document.getElementById("inputNextStepsGroup");
  const revNotesGroup = document.getElementById("inputRevisionGroup");
  const declineReasonGroup = document.getElementById("inputDeclineGroup");
  const acceptanceAssetsGroup = document.getElementById("inputAcceptanceAssetsGroup");

  if (nextStepsGroup) nextStepsGroup.style.display = decisionType === "approved" ? "block" : "none";
  if (revNotesGroup) revNotesGroup.style.display = decisionType === "revision_requested" ? "block" : "none";
  if (declineReasonGroup) declineReasonGroup.style.display = decisionType === "declined" ? "block" : "none";

  if (acceptanceAssetsGroup) {
    acceptanceAssetsGroup.style.display = decisionType === "approved" ? "block" : "none";
    const divName = state.activeApp.division_name || "";
    const divClean = divName.replace(/ (Office|Department)$/i, "");
    const labelInput = document.getElementById("inputDivisionChatLabel");
    const linkInput = document.getElementById("inputDivisionChatLink");

    if (labelInput) {
      if (/data|tech|cloud|developer|software/i.test(divName)) {
        labelInput.value = "Technology Group Chat";
        if (linkInput && !linkInput.value.trim()) {
          linkInput.value = "https://m.me/j/Abb8Zoll7JHw3hNg/";
        }
      } else if (/creative|media|design/i.test(divName)) {
        labelInput.value = "Creatives Group Chat";
        if (linkInput && !linkInput.value.trim()) {
          linkInput.value = "https://m.me/j/AbaoQzrJXHAqFy08/";
        }
      } else {
        labelInput.value = `${divClean} Group Chat`;
      }
    }
  }

  // Auto-select footer banner matching logged in officer if found
  const selectFooter = document.getElementById("selectFooterBanner");
  if (selectFooter && state.user && state.user.full_name) {
    const officerLower = state.user.full_name.toLowerCase();
    const tokens = officerLower.split(/\s+/).filter((t) => t.length > 2);
    for (const opt of selectFooter.options) {
      const optValLower = opt.value.toLowerCase();
      const optTextLower = opt.textContent.toLowerCase();
      if (tokens.some((t) => optValLower.includes(t) || optTextLower.includes(t))) {
        selectFooter.value = opt.value;
        break;
      }
    }
  }

  // Fetch preview from backend
  fetchEmailPreview(decisionType);
  document.getElementById("emailModalOverlay").classList.add("active");
};

function getActiveHeaderBannerUrl() {
  const select = document.getElementById("selectHeaderBanner");
  if (!select) return "/assets/email-banners/AWS-Banner.png";
  if (select.value === "none") return null;
  if (select.value === "custom") {
    return document.getElementById("inputCustomHeaderBanner")?.value.trim() || null;
  }
  return select.value;
}

function getActiveFooterBannerUrl() {
  const select = document.getElementById("selectFooterBanner");
  if (!select) return "/assets/email-banners/Khobe Customized footer.png";
  if (select.value === "none") return null;
  if (select.value === "custom") {
    return document.getElementById("inputCustomFooterBanner")?.value.trim() || null;
  }
  return select.value;
}

window.onHeaderBannerChange = function () {
  const select = document.getElementById("selectHeaderBanner");
  const customInput = document.getElementById("inputCustomHeaderBanner");
  if (select && customInput) {
    customInput.style.display = select.value === "custom" ? "block" : "none";
  }
  updateVisualPreview();
};

window.onFooterBannerChange = function () {
  const select = document.getElementById("selectFooterBanner");
  const customInput = document.getElementById("inputCustomFooterBanner");
  if (select && customInput) {
    customInput.style.display = select.value === "custom" ? "block" : "none";
  }
  updateVisualPreview();
};

window.handleQrUpload = function (event, type) {
  const file = event.target.files && event.target.files[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = function (e) {
    const dataUrl = e.target.result;
    if (type === "general") {
      state.generalQrBase64 = dataUrl;
      const thumb = document.getElementById("imgGeneralQrThumb");
      const chip = document.getElementById("previewGeneralQr");
      if (thumb) thumb.src = dataUrl;
      if (chip) chip.style.display = "inline-flex";
    } else {
      state.divisionQrBase64 = dataUrl;
      const thumb = document.getElementById("imgDivisionQrThumb");
      const chip = document.getElementById("previewDivisionQr");
      if (thumb) thumb.src = dataUrl;
      if (chip) chip.style.display = "inline-flex";
    }
    updateVisualPreview();
    showToast("QR code image attached!", "success");
  };
  reader.readAsDataURL(file);
};

window.removeQr = function (type) {
  if (type === "general") {
    state.generalQrBase64 = "";
    const chip = document.getElementById("previewGeneralQr");
    const input = document.getElementById("fileGeneralQr");
    if (chip) chip.style.display = "none";
    if (input) input.value = "";
  } else {
    state.divisionQrBase64 = "";
    const chip = document.getElementById("previewDivisionQr");
    const input = document.getElementById("fileDivisionQr");
    if (chip) chip.style.display = "none";
    if (input) input.value = "";
  }
  updateVisualPreview();
};

window.switchEmailModalTab = function (tab) {
  state.activeEmailTab = tab;
  const btnCompose = document.getElementById("tabBtnCompose");
  const btnPreview = document.getElementById("tabBtnPreview");
  const composeTab = document.getElementById("emailComposeTab");
  const previewTab = document.getElementById("emailVisualPreviewContainer");

  if (tab === "compose") {
    if (btnCompose) btnCompose.classList.add("active");
    if (btnPreview) btnPreview.classList.remove("active");
    if (composeTab) composeTab.style.display = "block";
    if (previewTab) previewTab.style.display = "none";
  } else {
    if (btnCompose) btnCompose.classList.remove("active");
    if (btnPreview) btnPreview.classList.add("active");
    if (composeTab) composeTab.style.display = "none";
    if (previewTab) previewTab.style.display = "block";
    updateVisualPreview();
  }
};

window.updateVisualPreview = function () {
  const subject = document.getElementById("emailSubject")?.value || "AWS SBG JRU Notification";
  const bodyText = document.getElementById("emailBody")?.value || "";
  const headerBanner = getActiveHeaderBannerUrl();
  const footerBanner = getActiveFooterBannerUrl();
  const genLink = document.getElementById("inputGeneralChatLink")?.value.trim() || "";
  const divLink = document.getElementById("inputDivisionChatLink")?.value.trim() || "";
  const divLabelInput = document.getElementById("inputDivisionChatLabel");
  const genQr = state.generalQrBase64 || "";
  const divQr = state.divisionQrBase64 || "";
  const rawDiv = state.activeApp ? state.activeApp.division_name : "Division";
  const divClean = (rawDiv || "Division").replace(/ (Office|Department)$/i, "");
  const divLabel = (divLabelInput && divLabelInput.value.trim()) || `${divClean} Group Chat`;

  let groupChatsHtml = "";
  if (genLink || divLink || genQr || divQr) {
    let items = "";
    if (genLink || genQr) {
      items += `<div style="margin: 16px 0 20px 0;">`;
      if (genLink) {
        items += `<p style="margin: 0 0 8px 0; font-family: Arial, Helvetica, sans-serif; font-size: 14.5px; color: #222222; line-height: 1.55;"><span style="color: #0c356a; font-weight: bold; font-style: italic;">General Group Chat:</span> <a href="${escapeHtml(genLink)}" style="color: #0066cc; text-decoration: underline;" target="_blank">${escapeHtml(genLink)}</a></p>`;
      } else {
        items += `<p style="margin: 0 0 8px 0; font-family: Arial, Helvetica, sans-serif; font-size: 14.5px; line-height: 1.55;"><span style="color: #0c356a; font-weight: bold; font-style: italic;">General Group Chat:</span></p>`;
      }
      if (genQr) {
        items += `<img src="${genQr}" alt="General Group Chat QR Code" width="170" style="width: 170px; max-width: 100%; height: auto; object-fit: contain; border: 1px solid #e2e8f0; border-radius: 6px; padding: 4px; background: #ffffff; display: block; margin-top: 8px; margin-bottom: 8px;" />`;
      }
      items += `</div>`;
    }

    if (divLink || divQr) {
      items += `<div style="margin: 16px 0 20px 0;">`;
      if (divLink) {
        items += `<p style="margin: 0 0 8px 0; font-family: Arial, Helvetica, sans-serif; font-size: 14.5px; color: #222222; line-height: 1.55;"><span style="color: #0c356a; font-weight: bold; font-style: italic;">${escapeHtml(divLabel)}:</span> <a href="${escapeHtml(divLink)}" style="color: #0066cc; text-decoration: underline;" target="_blank">${escapeHtml(divLink)}</a></p>`;
      } else {
        items += `<p style="margin: 0 0 8px 0; font-family: Arial, Helvetica, sans-serif; font-size: 14.5px; line-height: 1.55;"><span style="color: #0c356a; font-weight: bold; font-style: italic;">${escapeHtml(divLabel)}:</span></p>`;
      }
      if (divQr) {
        items += `<img src="${divQr}" alt="${escapeHtml(divLabel)} QR Code" width="170" style="width: 170px; max-width: 100%; height: auto; object-fit: contain; border: 1px solid #e2e8f0; border-radius: 6px; padding: 4px; background: #ffffff; display: block; margin-top: 8px; margin-bottom: 8px;" />`;
      }
      items += `</div>`;
    }
    groupChatsHtml = items;
  }

  const paragraphs = bodyText.split("\n\n").filter((p) => p.trim());
  let contentBlocks = [];
  let chatsInserted = false;

  for (const p of paragraphs) {
    let pFormatted = escapeHtml(p).replace(/\*([^*]+)\*/g, '<span style="color: #0c356a; font-weight: bold; font-style: italic;">$1</span>');
    contentBlocks.push(`<p style="margin: 0 0 16px 0; font-family: Arial, Helvetica, sans-serif; font-size: 14.5px; color: #222222; line-height: 1.55;">${pFormatted.replace(/\n/g, "<br />")}</p>`);

    if (p.toLowerCase().includes("group chats below") && groupChatsHtml && !chatsInserted) {
      contentBlocks.push(groupChatsHtml);
      chatsInserted = true;
    }
  }

  if (groupChatsHtml && !chatsInserted) {
    contentBlocks.push(groupChatsHtml);
  }

  const bodyContentHtml = contentBlocks.join("\n");

  let headerImgHtml = "";
  if (headerBanner) {
    const safeHeader = encodeURI(headerBanner);
    headerImgHtml = `
      <tr>
        <td align="center" style="padding: 0;">
          <img src="${safeHeader}" alt="AWS SBG JRU Chapter Banner" width="600" style="width: 100%; max-width: 600px; height: auto; display: block; border-top-left-radius: 8px; border-top-right-radius: 8px;" />
        </td>
      </tr>
    `;
  }

  let footerImgHtml = "";
  if (footerBanner) {
    const safeFooter = encodeURI(footerBanner);
    footerImgHtml = `
      <tr>
        <td align="center" style="padding: 0;">
          <img src="${safeFooter}" alt="Officer Sign-off" width="600" style="width: 100%; max-width: 600px; height: auto; display: block; border-bottom-left-radius: 8px; border-bottom-right-radius: 8px;" />
        </td>
      </tr>
    `;
  }

  const html = `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>${escapeHtml(subject)}</title>
</head>
<body style="margin: 0; padding: 20px 0; background-color: #f7fafc; font-family: Arial, Helvetica, sans-serif; -webkit-font-smoothing: antialiased;">
  <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #f7fafc;">
    <tr>
      <td align="center" style="padding: 10px;">
        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 600px; width: 100%; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.06); border: 1px solid #e2e8f0;">
          ${headerImgHtml}
          <tr>
            <td style="padding: 28px 30px 24px 30px; color: #222222; font-family: Arial, Helvetica, sans-serif; font-size: 14.5px; line-height: 1.55;">
              ${bodyContentHtml}
            </td>
          </tr>
          ${footerImgHtml}
        </table>
        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 600px; width: 100%; margin-top: 16px;">
          <tr>
            <td align="center" style="font-family: Arial, Helvetica, sans-serif; font-size: 12px; color: #a0aec0; padding: 10px 20px; line-height: 1.4;">
              AWS Student Builder Group &bull; Jose Rizal University Chapter<br>
              <span style="font-size: 11px;">This is an official administrative communication from AWS SBG JRU.</span>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>`;

  const iframe = document.getElementById("iframeEmailPreview");
  if (iframe) {
    iframe.srcdoc = html;
  }
};

function fetchEmailPreview(decisionType) {
  if (!state.activeApp) return;

  const nextSteps = document.getElementById("inputNextSteps")?.value.trim() || undefined;
  const revNotes = document.getElementById("inputRevisionNotes")?.value.trim() || undefined;
  const revDeadline = document.getElementById("inputRevisionDeadline")?.value.trim() || undefined;
  const declineReason = document.getElementById("inputDeclineReason")?.value.trim() || undefined;
  const templateId = decisionType === "pending" ? "approved" : decisionType;
  const headerBanner = getActiveHeaderBannerUrl();
  const footerBanner = getActiveFooterBannerUrl();
  const genLink = document.getElementById("inputGeneralChatLink")?.value.trim() || undefined;
  const divLink = document.getElementById("inputDivisionChatLink")?.value.trim() || undefined;
  const divLabel = document.getElementById("inputDivisionChatLabel")?.value.trim() || undefined;

  fetch(`${API_BASE}/api/v1/admin/applications/${state.activeApp.id}/email/preview`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({
      template_id: templateId,
      next_steps: nextSteps,
      revision_notes: revNotes,
      revision_deadline: revDeadline,
      decline_reason: declineReason,
      header_banner_url: headerBanner,
      footer_banner_url: footerBanner,
      general_chat_link: genLink,
      division_chat_link: divLink,
      division_chat_label: divLabel,
      general_qr_base64: state.generalQrBase64 || undefined,
      division_qr_base64: state.divisionQrBase64 || undefined,
    }),
  })
    .then((res) => res.json())
    .then((preview) => {
      document.getElementById("emailSubject").value = preview.subject;
      document.getElementById("emailBody").value = preview.body;
      updateVisualPreview();
    })
    .catch((err) => {
      showToast(err.message || "Failed to preview email", "error");
    });
}

window.refreshEmailPreview = function () {
  if (state.pendingDecision) {
    fetchEmailPreview(state.pendingDecision);
  } else {
    updateVisualPreview();
  }
};

window.closeEmailModal = function () {
  document.getElementById("emailModalOverlay").classList.remove("active");
  state.pendingDecision = null;
  removeQr("general");
  removeQr("division");
};

window.confirmAndDispatch = function () {
  if (!state.activeApp || !state.pendingDecision) return;

  const rubricScores = {};
  state.rubricItems.forEach((item) => {
    const chk = document.getElementById(`rubric_${item.id}`);
    if (chk) rubricScores[item.id] = chk.checked;
  });

  const subject = document.getElementById("emailSubject").value;
  const body = document.getElementById("emailBody").value;
  const nextSteps = document.getElementById("inputNextSteps")?.value.trim();
  const revisionNotes = document.getElementById("inputRevisionNotes")?.value.trim();
  const revisionDeadline = document.getElementById("inputRevisionDeadline")?.value.trim();
  const headerBanner = getActiveHeaderBannerUrl();
  const footerBanner = getActiveFooterBannerUrl();
  const genLink = document.getElementById("inputGeneralChatLink")?.value.trim();
  const divLink = document.getElementById("inputDivisionChatLink")?.value.trim();
  const divLabel = document.getElementById("inputDivisionChatLabel")?.value.trim();

  const payload = {
    decision: state.pendingDecision,
    rubric_scores: rubricScores,
    internal_notes: `Decision '${state.pendingDecision}' confirmed with email dispatch.`,
    send_email: true,
    custom_subject: subject,
    custom_body: body,
    next_steps: nextSteps,
    revision_notes: revisionNotes,
    revision_deadline: revisionDeadline,
    header_banner_url: headerBanner,
    footer_banner_url: footerBanner,
    general_chat_link: genLink,
    general_qr_base64: state.generalQrBase64 || undefined,
    division_chat_link: divLink,
    division_chat_label: divLabel || undefined,
    division_qr_base64: state.divisionQrBase64 || undefined,
  };

  submitDecisionPayload(payload);
};

// ---------------- Instant Optimistic CRUD Decision ----------------
function applyOptimisticDecision(appId, decision, payload) {
  const targetDecision = decision;
  const newStatus = targetDecision === "pending" ? "under_review" : targetDecision;
  const officerName = state.user ? state.user.full_name : "Officer";
  const nowIso = new Date().toISOString();

  let oldStatus = "new";
  if (state.activeApp && state.activeApp.id === appId) {
    oldStatus = state.activeApp.application_status || "new";
    state.activeApp.application_status = newStatus;
    state.activeApp.reviewed_by = officerName;
    state.activeApp.reviewed_at = nowIso;
    state.activeApp.decision_reason_code = payload.reason_code || payload.decline_reason || null;
  }

  // 1. Instantly update state.applications in memory
  const appInList = state.applications.find((a) => a.id === appId);
  if (appInList) {
    oldStatus = appInList.application_status || oldStatus;
    appInList.application_status = newStatus;
    appInList.reviewed_by = officerName;
    appInList.reviewed_at = nowIso;
    appInList.decision_reason_code = payload.reason_code || payload.decline_reason || null;
  }

  // 2. Instantly update Queue Table
  renderQueueTable();

  // 3. Instantly update Status Pill counters
  if (state.statusCounts) {
    if (oldStatus in state.statusCounts) {
      state.statusCounts[oldStatus] = Math.max(0, (state.statusCounts[oldStatus] || 0) - 1);
    }
    state.statusCounts[newStatus] = (state.statusCounts[newStatus] || 0) + 1;
    updateStatusCounters();
  }

  // 4. Instantly update Dashboard recent applications
  if (state.recentApplications && state.recentApplications.length > 0) {
    const rIdx = state.recentApplications.findIndex((a) => a.id === appId);
    if (rIdx !== -1) {
      if (newStatus !== "new") {
        state.recentApplications.splice(rIdx, 1);
      } else {
        state.recentApplications[rIdx].application_status = newStatus;
      }
      renderRecentQueue(state.recentApplications);
    }
  }

  // 5. Instantly update Dashboard KPI metrics counters
  const statusToMetricId = {
    new: "metricNew",
    under_review: "metricUnderReview",
    approved: "metricApproved",
    revision_requested: "metricRevision",
    declined: "metricDeclined",
  };

  const oldElId = statusToMetricId[oldStatus];
  const newElId = statusToMetricId[newStatus];

  if (oldElId) {
    const el = document.getElementById(oldElId);
    if (el) el.textContent = Math.max(0, parseInt(el.textContent || "0", 10) - 1);
  }
  if (newElId) {
    const el = document.getElementById(newElId);
    if (el) el.textContent = parseInt(el.textContent || "0", 10) + 1;
  }
}

function submitDecisionPayload(payload) {
  if (!state.activeApp) return;
  const appId = state.activeApp.id;
  const decisionType = payload.decision;

  // 1. INSTANT CLOSE MODALS & INSTANT UI UPDATE (0ms delay!)
  closeEmailModal();
  document.getElementById("reviewModalOverlay").classList.remove("active");
  state.pendingDecision = null;

  // Optimistically update memory and DOM
  applyOptimisticDecision(appId, decisionType, payload);

  const formattedDecision = decisionType.replace("_", " ").toUpperCase();
  showToast(`Application #${appId} marked as ${formattedDecision}!`, "success");

  // 2. DISPATCH TO BACKEND IN BACKGROUND
  fetch(`${API_BASE}/api/v1/admin/applications/${appId}/decision`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(payload),
  })
    .then((res) => {
      if (!res.ok) throw new Error("Failed to record decision on server");
      return res.json();
    })
    .then((data) => {
      if (payload.send_email) {
        if (data.email_result && data.email_result.delivery_status === "sent") {
          showToast("Email dispatched successfully to applicant.", "info");
        }
      }
      // Silently sync server state in background
      silentSync();
    })
    .catch((err) => {
      showToast(`Error saving decision: ${err.message}`, "error");
      // Revert / re-fetch on failure
      loadQueue();
      loadDashboard();
    });
}

function silentSync() {
  // Always keep dashboard metrics updated in background
  fetch(`${API_BASE}/api/v1/admin/metrics`, { headers: getHeaders() })
    .then((res) => res.json())
    .then((data) => updateKpiElements(data))
    .catch(() => {});

  if (state.currentView === "queue") {
    const params = new URLSearchParams({
      page: state.page,
      page_size: state.pageSize,
    });
    if (state.filters.status && state.filters.status !== "all") params.append("status", state.filters.status);
    if (state.filters.search) params.append("search", state.filters.search);
    if (state.filters.year) params.append("year", state.filters.year);
    if (state.filters.program) params.append("program", state.filters.program);
    if (state.filters.division_type) params.append("division_type", state.filters.division_type);

    fetch(`${API_BASE}/api/v1/admin/applications?${params.toString()}`, { headers: getHeaders() })
      .then((res) => res.json())
      .then((data) => {
        state.applications = data.applications || [];
        state.total = data.total || 0;
        state.statusCounts = data.status_counts || {};
        updateStatusCounters();
        renderQueueTable();
        updatePaginationControls();
      })
      .catch(() => {});
  } else if (state.currentView === "dashboard") {
    loadDashboard();
  }
}

// ---------------- Email Templates Editor ----------------
function loadTemplates() {
  fetch(`${API_BASE}/api/v1/admin/templates`, { headers: getHeaders() })
    .then((res) => res.json())
    .then((templates) => {
      state.templates = templates;
      renderTemplateTabs(templates);
      if (templates.length > 0) selectTemplate(templates[0].id);
    })
    .catch((err) => showToast(err.message, "error"));
}

function renderTemplateTabs(templates) {
  const container = document.getElementById("templateTabsList");
  if (!container) return;
  container.innerHTML = templates
    .map(
      (t) => `
    <button class="status-pill-btn" onclick="selectTemplate('${t.id}')" id="tmplTab_${t.id}">
      ${escapeHtml(t.name)}
    </button>
  `
    )
    .join("");
}

window.selectTemplate = function (tmplId) {
  document.querySelectorAll("#templateTabsList .status-pill-btn").forEach((b) => b.classList.remove("active"));
  const tab = document.getElementById(`tmplTab_${tmplId}`);
  if (tab) tab.classList.add("active");

  const tmpl = state.templates.find((t) => t.id === tmplId);
  if (!tmpl) return;

  document.getElementById("tmplEditId").value = tmpl.id;
  document.getElementById("tmplEditName").value = tmpl.name;
  document.getElementById("tmplEditSubject").value = tmpl.subject;
  document.getElementById("tmplEditBody").value = tmpl.body;

  const varsContainer = document.getElementById("tmplVarsContainer");
  if (varsContainer) {
    varsContainer.innerHTML = (tmpl.variables || [])
      .map((v) => `<span class="badge badge-new var-chip" onclick="insertVarTag('${v}')">{{${v}}}</span>`)
      .join(" ");
  }
};

window.insertVarTag = function (varName) {
  const bodyEl = document.getElementById("tmplEditBody");
  if (!bodyEl) return;
  const tag = `{{${varName}}}`;
  bodyEl.value += tag;
  bodyEl.focus();
};

window.saveTemplateChanges = function () {
  const tmplId = document.getElementById("tmplEditId").value;
  const name = document.getElementById("tmplEditName").value.trim();
  const subject = document.getElementById("tmplEditSubject").value.trim();
  const body = document.getElementById("tmplEditBody").value.trim();

  fetch(`${API_BASE}/api/v1/admin/templates/${tmplId}`, {
    method: "PUT",
    headers: getHeaders(),
    body: JSON.stringify({ name, subject, body }),
  })
    .then((res) => {
      if (!res.ok) throw new Error("Update failed (Admin only)");
      return res.json();
    })
    .then(() => {
      showToast("Template updated successfully!", "success");
      loadTemplates();
    })
    .catch((err) => showToast(err.message, "error"));
};

// ---------------- Settings & Availability ----------------
function loadSettings() {
  fetch(`${API_BASE}/api/v1/admin/settings`, { headers: getHeaders() })
    .then((res) => res.json())
    .then((settings) => {
      state.settings = settings;
      const toggle = document.getElementById("settingRegistrationOpen");
      const msg = document.getElementById("settingClosedMessage");
      if (toggle) toggle.checked = settings.registration_open;
      if (msg) msg.value = settings.closed_message || "";
    })
    .catch((err) => showToast(err.message, "error"));
}

window.saveSettings = function () {
  const isOpen = document.getElementById("settingRegistrationOpen").checked;
  const msg = document.getElementById("settingClosedMessage").value.trim();

  fetch(`${API_BASE}/api/v1/admin/settings`, {
    method: "PUT",
    headers: getHeaders(),
    body: JSON.stringify({ registration_open: isOpen, closed_message: msg }),
  })
    .then((res) => {
      if (!res.ok) throw new Error("Settings update failed (Admin only)");
      return res.json();
    })
    .then(() => {
      showToast("System settings saved!", "success");
    })
    .catch((err) => showToast(err.message, "error"));
};

window.exportCsv = function () {
  window.open(`${API_BASE}/api/v1/admin/export?status=${state.filters.status}`, "_blank");
};

// ---------------- Audit Logs ----------------
function loadAuditLogs() {
  fetch(`${API_BASE}/api/v1/admin/audit-logs`, { headers: getHeaders() })
    .then((res) => res.json())
    .then((logs) => {
      const tbody = document.getElementById("auditLogTableBody");
      if (!tbody) return;
      if (logs.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="empty-state-cell">No audit logs recorded yet.</td></tr>`;
        return;
      }
      tbody.innerHTML = logs
        .map((l) => {
          const time = new Date(l.created_at).toLocaleString();
          return `
          <tr>
            <td class="mono-cell">${escapeHtml(time)}</td>
            <td><strong>${escapeHtml(l.actor_name)}</strong></td>
            <td><span class="badge badge-new">${escapeHtml(l.action)}</span></td>
            <td>${escapeHtml(l.target_type)} ${l.target_id ? `(#${escapeHtml(l.target_id)})` : ""}</td>
            <td class="muted-cell">${escapeHtml(JSON.stringify(l.details || {}))}</td>
          </tr>
        `;
        })
        .join("");
    })
    .catch((err) => showToast(err.message, "error"));
}

// ---------------- Utility ----------------
function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
