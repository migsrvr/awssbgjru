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
    status: "new",
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
  loaded: {
    dashboard: false,
    queue: false,
    departments: false,
    templates: false,
    settings: false,
    audit: false,
  },
  reqSeq: {
    dashboardMetrics: 0,
    dashboardQueue: 0,
    queue: 0,
    departments: 0,
    templates: 0,
    settings: 0,
    audit: 0,
    modal: 0,
  },
  queueAbortController: null,
  auditLogs: [],
  metrics: null,
  defaultQueueCache: null,
  syncState: null,
  preloadStarted: false,
  syncTimer: null,
  syncChannel: null,
  syncWatcherAttached: false,
  reviewReturnView: "queue",
  activeResumeBlobUrl: null,
  activeResumeFilename: null,
  activeResumeMimeType: null,
  aiReqSeq: 0,
};

const ADMIN_CACHE_KEY = "awssbg_admin_cache_v1";
const SYNC_POLL_INTERVAL_MS = 15000;

function saveAdminCache() {
  try {
    if (typeof sessionStorage === "undefined") return;
    const payload = {
      savedAt: Date.now(),
      metrics: state.metrics,
      recentApplications: state.recentApplications,
      defaultQueueCache: state.defaultQueueCache,
      settings: state.settings,
      templates: state.templates,
      auditLogs: state.auditLogs,
      syncState: state.syncState,
      loaded: state.loaded,
    };
    sessionStorage.setItem(ADMIN_CACHE_KEY, JSON.stringify(payload));
  } catch (_) {}
}

function restoreAdminCache() {
  try {
    if (typeof sessionStorage === "undefined") return false;
    const raw = sessionStorage.getItem(ADMIN_CACHE_KEY);
    if (!raw) return false;
    const cached = JSON.parse(raw);
    if (!cached || typeof cached !== "object") return false;

    if (cached.metrics) {
      state.metrics = cached.metrics;
      state.loaded.dashboard = true;
    }
    if (Array.isArray(cached.recentApplications)) {
      state.recentApplications = cached.recentApplications;
    }
    if (cached.defaultQueueCache) {
      state.defaultQueueCache = cached.defaultQueueCache;
      state.applications = cached.defaultQueueCache.applications || [];
      state.total = cached.defaultQueueCache.total || 0;
      state.statusCounts = cached.defaultQueueCache.statusCounts || {};
      state.loaded.queue = true;
    }
    if (cached.settings && typeof cached.settings === "object") {
      state.settings = cached.settings;
      if (cached.settings.qualification_rubric) {
        state.rubricItems = cached.settings.qualification_rubric;
      }
      if (cached.settings.division_availability) {
        state.savedDivisionAvailability = mergeDivisionAvailability(cached.settings.division_availability);
        state.loaded.departments = true;
      }
      if (cached.loaded && cached.loaded.settings) {
        state.loaded.settings = true;
      }
    }
    if (Array.isArray(cached.templates) && cached.templates.length > 0) {
      state.templates = cached.templates;
      state.loaded.templates = true;
    }
    if (Array.isArray(cached.auditLogs) && cached.loaded && cached.loaded.audit) {
      state.auditLogs = cached.auditLogs;
      state.loaded.audit = true;
    }
    if (cached.syncState && typeof cached.syncState.version === "number") {
      state.syncState = cached.syncState;
    }
    return true;
  } catch (_) {
    return false;
  }
}

function clearAdminCache() {
  state.metrics = null;
  state.recentApplications = [];
  state.defaultQueueCache = null;
  state.applications = [];
  state.total = 0;
  state.statusCounts = {};
  state.templates = [];
  state.auditLogs = [];
  state.syncState = null;
  state.preloadStarted = false;
  Object.keys(state.loaded).forEach((k) => {
    state.loaded[k] = false;
  });
  try {
    if (typeof sessionStorage !== "undefined") {
      sessionStorage.removeItem(ADMIN_CACHE_KEY);
    }
  } catch (_) {}
}

function isDefaultQueueView() {
  return (
    state.page === 1 &&
    state.filters.status === "new" &&
    !state.filters.search &&
    !state.filters.year &&
    !state.filters.program &&
    !state.filters.division_type
  );
}

function renderTableSkeleton(colCount, rowCount = 4) {
  let rows = "";
  for (let i = 0; i < rowCount; i++) {
    let cells = "";
    for (let c = 0; c < colCount; c++) {
      const width = c === 0 ? "78%" : c === colCount - 1 ? "56%" : "68%";
      cells += `<td><span class="skeleton-bar" style="width:${width}"></span></td>`;
    }
    rows += `<tr class="skeleton-row">${cells}</tr>`;
  }
  return rows;
}

function setKpiSkeleton(isLoading) {
  const ids = [
    "metricTotal",
    "metricTurnaround",
    "metricNew",
    "metricUnderReview",
    "metricApproved",
    "metricRevision",
    "metricDeclined",
  ];
  ids.forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.classList.toggle("is-skeleton", isLoading);
    if (isLoading && !state.loaded.dashboard) {
      el.innerHTML = `<span class="skeleton-kpi-bar"></span>`;
    }
  });
}

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

  // Hydrate cached admin views synchronously before switching view (0ms warm boot)
  const hadWarmCache = restoreAdminCache();

  // Restore view from URL hash or previous session (supports #review/<id>)
  const validViews = ["dashboard", "queue", "departments", "templates", "settings", "audit"];
  const hash = window.location.hash.replace("#", "").trim();
  const reviewMatch = hash.match(/^review\/(\d+)$/);
  if (reviewMatch) {
    state.reviewReturnView = "queue";
    openReviewModal(parseInt(reviewMatch[1], 10));
  } else {
    const savedView = localStorage.getItem("admin_active_view");
    const initialView = validViews.includes(hash) ? hash : (validViews.includes(savedView) ? savedView : "dashboard");
    switchView(initialView);
  }

  // Preload Dashboard + all other admin pages in background and start POST-mutation watcher
  preloadAllAdminViews({ force: false });
  startSyncWatcher();
  if (hadWarmCache) {
    // Check immediately if any POST happened while tab was closed/reloaded
    checkForServerUpdates();
  }

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
  stopSyncWatcher();
  clearAdminCache();
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
  else if (viewName === "departments") loadDepartments();
  else if (viewName === "templates") loadTemplates();
  else if (viewName === "settings") loadSettings();
  else if (viewName === "audit") loadAuditLogs();
}

// ---------------- Background Preloader & Mutation Sync Watcher ----------------
function preloadAllAdminViews({ force = false } = {}) {
  if (!state.token) return;
  if (!force && state.preloadStarted) return;
  state.preloadStarted = true;

  // 1. Ensure Dashboard is always preloaded first (even if user opened another hash tab)
  if (force || !state.loaded.dashboard) {
    loadDashboard({ force: true, silent: state.currentView !== "dashboard" });
  }

  // 2. Capture baseline server sync version
  if (!state.syncState) {
    fetch(`${API_BASE}/api/v1/admin/sync-version?_t=${Date.now()}`, {
      headers: getHeaders(),
      cache: "no-store",
    })
      .then((res) => (res.ok ? res.json() : null))
      .then((sync) => {
        if (sync && typeof sync.version === "number") {
          state.syncState = sync;
          saveAdminCache();
        }
      })
      .catch(() => {});
  }

  // 3. Background preload all remaining admin views into cache without blocking active paint
  const runBackgroundFetches = () => {
    if (!state.token) return;
    if (force || !state.loaded.queue) {
      loadQueue({ force: true, silent: state.currentView !== "queue", backgroundDefault: true });
    }
    if (force || !state.loaded.settings || !state.loaded.departments) {
      loadSettingsShared({ force: true, silent: state.currentView !== "settings" && state.currentView !== "departments" });
    }
    if (force || !state.loaded.templates) {
      loadTemplates({ force: true, silent: state.currentView !== "templates" });
    }
    if (force || !state.loaded.audit) {
      loadAuditLogs({ force: true, silent: state.currentView !== "audit" });
    }
  };

  if (force) {
    runBackgroundFetches();
  } else {
    const bgTimer = setTimeout(runBackgroundFetches, 120);
    if (bgTimer && typeof bgTimer.unref === "function") bgTimer.unref();
  }
}

function refreshScopes(scopes, eventName = "") {
  if (!state.token || !Array.isArray(scopes) || scopes.length === 0) return;
  const scopeSet = new Set(scopes);

  if (scopeSet.has("applications") || scopeSet.has("all")) {
    loadDashboard({ force: true, silent: true });
    loadQueue({ force: true, silent: true });
  }
  if (scopeSet.has("settings") || scopeSet.has("all")) {
    loadSettingsShared({ force: true, silent: true });
  }
  if (scopeSet.has("templates") || scopeSet.has("all")) {
    loadTemplates({ force: true, silent: true });
  }
  if (scopeSet.has("audit") || scopeSet.has("all")) {
    loadAuditLogs({ force: true, silent: true });
  }

  if (eventName === "new_registration") {
    showToast("New membership application received — views updated!", "info");
  } else if (eventName === "revision_submitted") {
    showToast("Applicant revision submitted — views updated!", "info");
  }
}

function captureCurrentSyncVersion() {
  if (!state.token) return;
  fetch(`${API_BASE}/api/v1/admin/sync-version?_t=${Date.now()}`, {
    headers: getHeaders(),
    cache: "no-store",
  })
    .then((res) => (res.ok ? res.json() : null))
    .then((sync) => {
      if (sync && typeof sync.version === "number") {
        state.syncState = sync;
        saveAdminCache();
      }
    })
    .catch(() => {});
}

function checkForServerUpdates() {
  if (!state.token) return;
  if (typeof document !== "undefined" && document.visibilityState === "hidden") return;

  fetch(`${API_BASE}/api/v1/admin/sync-version?_t=${Date.now()}`, {
    headers: getHeaders(),
    cache: "no-store",
  })
    .then((res) => (res.ok ? res.json() : null))
    .then((remote) => {
      if (!remote || typeof remote.version !== "number") return;

      if (!state.syncState) {
        state.syncState = remote;
        saveAdminCache();
        return;
      }

      if (remote.version === state.syncState.version) {
        return; // No POST/PUT mutation happened — stay 100% on cache!
      }

      const prevScopes = state.syncState.scopes || {};
      const nextScopes = remote.scopes || {};
      const changedScopes = [];
      for (const scope of ["applications", "settings", "templates", "audit"]) {
        if ((nextScopes[scope] || 0) !== (prevScopes[scope] || 0)) {
          changedScopes.push(scope);
        }
      }
      state.syncState = remote;
      saveAdminCache();

      refreshScopes(changedScopes.length > 0 ? changedScopes : ["all"], remote.last_event || "");
    })
    .catch(() => {});
}

function startSyncWatcher() {
  if (typeof window === "undefined") return;

  if (!state.syncTimer) {
    state.syncTimer = setInterval(checkForServerUpdates, SYNC_POLL_INTERVAL_MS);
    if (state.syncTimer && typeof state.syncTimer.unref === "function") {
      state.syncTimer.unref();
    }
  }

  if (!state.syncChannel && typeof BroadcastChannel !== "undefined") {
    try {
      state.syncChannel = new BroadcastChannel("awssbg_sync");
      state.syncChannel.onmessage = (event) => {
        const msg = event?.data;
        if (!msg || msg.type !== "mutation") return;
        const scopes = msg.scope === "applications" ? ["applications", "audit"] : [msg.scope || "all"];
        refreshScopes(scopes, msg.event || "");
        captureCurrentSyncVersion();
      };
    } catch (_) {}
  }

  if (!state.syncWatcherAttached) {
    state.syncWatcherAttached = true;
    window.addEventListener("focus", checkForServerUpdates);
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") checkForServerUpdates();
    });
    window.addEventListener("storage", (e) => {
      if (e.key === "awssbg_last_post_event" && e.newValue) {
        try {
          const parsed = JSON.parse(e.newValue);
          const scopes = parsed.scope === "applications" ? ["applications", "audit"] : [parsed.scope || "all"];
          refreshScopes(scopes, parsed.event || "");
          captureCurrentSyncVersion();
        } catch (_) {}
      }
    });
  }
}

function stopSyncWatcher() {
  if (state.syncTimer) {
    clearInterval(state.syncTimer);
    state.syncTimer = null;
  }
  if (state.syncChannel) {
    try {
      state.syncChannel.close();
    } catch (_) {}
    state.syncChannel = null;
  }
}

// ---------------- Dashboard ----------------
function loadDashboard({ force = false, silent = false } = {}) {
  // Cache-first: render cached Dashboard immediately with 0 network calls unless forced
  if (!force && state.loaded.dashboard && state.metrics) {
    setKpiSkeleton(false);
    updateKpiElements(state.metrics);
    renderRecentQueue(state.recentApplications || []);
    return;
  }

  if (!state.loaded.dashboard && !silent) {
    setKpiSkeleton(true);
    const recentBody = document.getElementById("recentQueueBody");
    if (recentBody) recentBody.innerHTML = renderTableSkeleton(5, 3);
  }

  const metricsReqId = ++state.reqSeq.dashboardMetrics;
  fetch(`${API_BASE}/api/v1/admin/metrics`, { headers: getHeaders() })
    .then((res) => {
      if (!res.ok) throw new Error("Metrics response not ok");
      return res.json();
    })
    .then((data) => {
      if (metricsReqId !== state.reqSeq.dashboardMetrics) return;
      state.metrics = data;
      state.loaded.dashboard = true;
      setKpiSkeleton(false);
      updateKpiElements(data);
      saveAdminCache();
    })
    .catch((err) => {
      if (metricsReqId !== state.reqSeq.dashboardMetrics) return;
      setKpiSkeleton(false);
      console.warn("Metrics load notice:", err);
    });

  // Quick queue list in dashboard
  const queueReqId = ++state.reqSeq.dashboardQueue;
  fetch(`${API_BASE}/api/v1/admin/applications?page_size=5&status=new`, { headers: getHeaders() })
    .then((res) => {
      if (!res.ok) throw new Error("Recent queue response not ok");
      return res.json();
    })
    .then((data) => {
      if (queueReqId !== state.reqSeq.dashboardQueue) return;
      state.recentApplications = data.applications || [];
      renderRecentQueue(state.recentApplications);
      saveAdminCache();
    })
    .catch((err) => {
      if (queueReqId !== state.reqSeq.dashboardQueue) return;
      console.warn("Recent queue load notice:", err);
    });
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
        loadQueue({ force: true });
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
        loadQueue({ force: true });
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
      loadQueue({ force: true });
    });
  });

  const prevBtn = document.getElementById("queuePrevPage");
  const nextBtn = document.getElementById("queueNextPage");
  if (prevBtn) {
    prevBtn.addEventListener("click", () => {
      if (state.page > 1) {
        state.page--;
        loadQueue({ force: true });
      }
    });
  }
  if (nextBtn) {
    nextBtn.addEventListener("click", () => {
      if (state.page * state.pageSize < state.total) {
        state.page++;
        loadQueue({ force: true });
      }
    });
  }
}

function loadQueue({ force = false, silent = false, backgroundDefault = false } = {}) {
  const defaultView = backgroundDefault || isDefaultQueueView();

  // Cache-first for default unfiltered queue view when switching tabs
  if (!force && defaultView && state.loaded.queue && state.defaultQueueCache) {
    state.applications = state.defaultQueueCache.applications || [];
    state.total = state.defaultQueueCache.total || 0;
    state.statusCounts = state.defaultQueueCache.statusCounts || {};
    updateStatusCounters();
    renderQueueTable();
    updatePaginationControls();
    return;
  }

  if (state.queueAbortController && !backgroundDefault) {
    state.queueAbortController.abort();
  }
  const controller = new AbortController();
  if (!backgroundDefault) state.queueAbortController = controller;
  const reqId = ++state.reqSeq.queue;

  const tbody = document.getElementById("queueTableBody");
  if (tbody && !silent) {
    if (!state.loaded.queue) {
      tbody.innerHTML = renderTableSkeleton(7, 5);
    } else {
      tbody.classList.add("is-refreshing");
    }
  }

  const params = new URLSearchParams({
    page: backgroundDefault ? 1 : state.page,
    page_size: state.pageSize,
  });

  if (backgroundDefault) {
    params.append("status", "new");
  } else {
    if (state.filters.status && state.filters.status !== "all") params.append("status", state.filters.status);
    if (state.filters.search) params.append("search", state.filters.search);
    if (state.filters.year) params.append("year", state.filters.year);
    if (state.filters.program) params.append("program", state.filters.program);
    if (state.filters.division_type) params.append("division_type", state.filters.division_type);
  }

  fetch(`${API_BASE}/api/v1/admin/applications?${params.toString()}`, {
    headers: getHeaders(),
    signal: controller.signal,
  })
    .then((res) => {
      if (!res.ok) throw new Error("Failed to load queue applications");
      return res.json();
    })
    .then((data) => {
      if (!backgroundDefault && reqId !== state.reqSeq.queue) return;
      state.loaded.queue = true;
      const apps = data.applications || [];
      const total = data.total || 0;
      const counts = data.status_counts || {};

      if (defaultView) {
        state.defaultQueueCache = { applications: apps, total, statusCounts: counts };
      }

      if (!backgroundDefault || isDefaultQueueView()) {
        state.applications = apps;
        state.total = total;
        state.statusCounts = counts;
        updateStatusCounters();
        renderQueueTable();
        updatePaginationControls();
      }
      saveAdminCache();
    })
    .catch((err) => {
      if (err && err.name === "AbortError") return;
      if (!backgroundDefault && reqId !== state.reqSeq.queue) return;
      console.error("Queue load failed:", err);
      if (!silent) showToast("Failed to load queue applications", "error");
    })
    .finally(() => {
      if (reqId === state.reqSeq.queue && tbody) {
        tbody.classList.remove("is-refreshing");
      }
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

// ---------------- Full-Page Applicant Review Workspace ----------------
function revokeActiveResumeBlob() {
  if (state.activeResumeBlobUrl) {
    try {
      URL.revokeObjectURL(state.activeResumeBlobUrl);
    } catch (_) {}
    state.activeResumeBlobUrl = null;
  }
  state.activeResumeFilename = null;
  state.activeResumeMimeType = null;
}

function showReviewPage(appId) {
  state.currentView = "review";
  window.location.hash = `review/${appId}`;
  document.querySelectorAll(".admin-nav-tab").forEach((t) => {
    t.classList.toggle("active", t.dataset.view === state.reviewReturnView);
  });
  document.querySelectorAll(".admin-view").forEach((v) => {
    v.classList.remove("active");
  });
  const reviewSection = document.getElementById("view-review");
  if (reviewSection) reviewSection.classList.add("active");

  const backLabel = document.getElementById("reviewBackLabel");
  if (backLabel) {
    backLabel.textContent = state.reviewReturnView === "dashboard" ? "Back to Dashboard" : "Back to Queue";
  }
  if (typeof window !== "undefined" && window.scrollTo) {
    window.scrollTo({ top: 0, behavior: "instant" });
  }
}

window.openReviewModal = function (appId) {
  if (state.currentView && state.currentView !== "review") {
    state.reviewReturnView = state.currentView;
  }
  const reqId = ++state.reqSeq.modal;
  revokeActiveResumeBlob();
  showReviewPage(appId);

  const previewSummary =
    state.applications.find((a) => a.id === appId) ||
    state.recentApplications.find((a) => a.id === appId);

  if (previewSummary) {
    state.activeApp = { ...previewSummary, reviews: [], email_logs: [] };
    renderReviewModal(state.activeApp, true);
  } else {
    renderCvViewerState("loading");
    renderAtsInsightsState("loading");
  }

  fetch(`${API_BASE}/api/v1/admin/applications/${appId}`, { headers: getHeaders() })
    .then((res) => {
      if (!res.ok) throw new Error("Failed to load application detail");
      return res.json();
    })
    .then((app) => {
      if (reqId !== state.reqSeq.modal) return;
      state.activeApp = app;
      renderReviewModal(app, false);
      loadApplicantResumeViewer(app, reqId);

      // Auto-trigger ATS AI evaluation once for unevaluated applicants; reuse DB cache otherwise (0 tokens)
      if (app.ai_evaluation && typeof app.ai_evaluation === "object" && app.ai_evaluation.summary) {
        renderAtsInsights(app.ai_evaluation, true);
      } else {
        triggerAiEvaluation(false);
      }
    })
    .catch((err) => {
      if (reqId !== state.reqSeq.modal) return;
      showToast(err.message || "Failed to load application detail", "error");
    });
};

window.closeReviewModal = function () {
  state.reqSeq.modal++;
  state.aiReqSeq++;
  revokeActiveResumeBlob();
  state.activeApp = null;
  switchView(state.reviewReturnView || "queue");
};

function renderReviewModal(app, isPreviewLoading = false) {
  document.getElementById("modalApplicantName").textContent = app.full_name || "Applicant Profile";
  document.getElementById("modalStudentId").textContent = app.student_id || "-";
  document.getElementById("modalEmail").textContent = app.email || "-";
  document.getElementById("modalProgram").textContent = `${app.program || "-"} — ${app.year || "-"}`;
  document.getElementById("modalDob").textContent = app.dob || (isPreviewLoading ? "Loading..." : "Not provided");
  const divLabel = `${app.division_name || "-"} (${(app.division_type || "").toUpperCase()})`;
  document.getElementById("modalDivision").textContent = divLabel;
  const divChip = document.getElementById("reviewDivisionChip");
  if (divChip) divChip.textContent = divLabel;
  document.getElementById("modalStatusBadge").innerHTML = `<span class="badge badge-${escapeHtml(app.application_status)}">${escapeHtml((app.application_status || "new").replace("_", " "))}</span>`;

  // Photo
  const photoEl = document.getElementById("modalPhotoPreview");
  if (app.photo_base64) {
    photoEl.src = app.photo_base64;
    photoEl.style.display = "block";
  } else {
    photoEl.style.display = "none";
  }

  // Explanation
  const explanationEl = document.getElementById("modalExplanation");
  if (explanationEl) {
    if (isPreviewLoading && !app.explanation) {
      explanationEl.innerHTML = `<span class="skeleton-bar" style="width:94%"></span><span class="skeleton-bar" style="width:82%;margin-top:8px"></span><span class="skeleton-bar" style="width:65%;margin-top:8px"></span>`;
    } else {
      explanationEl.textContent = app.explanation || "No statement provided.";
    }
  }

  // Claim button state
  renderClaimButton(app);

  // Rubric checklist
  loadAndRenderRubric();

  // Notes Thread & preview skeletons
  if (isPreviewLoading) {
    const notesEl = document.getElementById("notesThread");
    if (notesEl) {
      notesEl.innerHTML = `<span class="skeleton-bar" style="width:70%;margin:0.5rem 0"></span>`;
    }
    renderCvViewerState("loading");
    renderAtsInsightsState("loading");
  } else {
    renderNotesThread(app.reviews || []);
  }
}

function renderCvViewerState(mode, extra = {}) {
  const fileEl = document.getElementById("cvFileName");
  const actionsEl = document.getElementById("cvToolbarActions");
  const bodyEl = document.getElementById("cvViewerBody");
  if (!bodyEl) return;

  if (mode === "loading") {
    if (fileEl) fileEl.textContent = "Loading CV attachment...";
    if (actionsEl) actionsEl.hidden = true;
    bodyEl.innerHTML = `<div class="cv-placeholder"><span class="skeleton-bar" style="width:60%;margin:0 auto 12px"></span><span class="skeleton-bar" style="width:40%;margin:0 auto"></span></div>`;
    return;
  }

  if (mode === "none") {
    if (fileEl) fileEl.textContent = "No CV / resume attached";
    if (actionsEl) actionsEl.hidden = true;
    bodyEl.innerHTML = `<div class="cv-empty-state">This applicant did not upload a CV or resume. Evaluation is based on their Statement of Interest and academic profile.</div>`;
    return;
  }

  if (mode === "error") {
    if (fileEl) fileEl.textContent = extra.filename || "CV attachment";
    if (actionsEl) actionsEl.hidden = true;
    bodyEl.innerHTML = `<div class="cv-empty-state">Unable to preview CV file (${escapeHtml(extra.message || "load error")}).</div>`;
    return;
  }

  if (fileEl) fileEl.textContent = extra.filename || "applicant_cv.pdf";
  if (actionsEl) actionsEl.hidden = false;

  if (mode === "pdf") {
    bodyEl.innerHTML = `<iframe class="cv-pdf-iframe" src="${extra.blobUrl}" title="Applicant CV PDF"></iframe>`;
  } else if (mode === "image") {
    bodyEl.innerHTML = `<div class="cv-image-wrap"><img class="cv-image-preview" src="${extra.blobUrl}" alt="Applicant CV" /></div>`;
  } else {
    bodyEl.innerHTML = `<div class="cv-empty-state"><strong>${escapeHtml(extra.filename || "Document")}</strong> cannot be rendered natively in the browser. Use <strong>Download</strong> above to view it locally — ATS AI still extracts and evaluates DOCX text automatically.</div>`;
  }
}

function loadApplicantResumeViewer(app, reqId) {
  if (!app || !app.has_resume) {
    renderCvViewerState("none");
    return;
  }

  renderCvViewerState("loading");
  const filename = app.resume_filename || "applicant_cv.pdf";
  const mimeHint = (app.resume_mime_type || "").toLowerCase();

  fetch(`${API_BASE}/api/v1/admin/applications/${app.id}/resume`, {
    headers: { Authorization: `Bearer ${state.token}` },
  })
    .then((res) => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const contentType = (res.headers.get("content-type") || mimeHint || "application/pdf").toLowerCase();
      return res.blob().then((blob) => ({ blob, contentType }));
    })
    .then(({ blob, contentType }) => {
      if (reqId !== state.reqSeq.modal) return;
      revokeActiveResumeBlob();
      const typedBlob = blob.type ? blob : new Blob([blob], { type: contentType });
      const blobUrl = URL.createObjectURL(typedBlob);
      state.activeResumeBlobUrl = blobUrl;
      state.activeResumeFilename = filename;
      state.activeResumeMimeType = contentType;

      if (contentType.includes("pdf") || filename.toLowerCase().endsWith(".pdf")) {
        renderCvViewerState("pdf", { blobUrl, filename });
      } else if (contentType.startsWith("image/")) {
        renderCvViewerState("image", { blobUrl, filename });
      } else {
        renderCvViewerState("other", { blobUrl, filename });
      }
    })
    .catch((err) => {
      if (reqId !== state.reqSeq.modal) return;
      renderCvViewerState("error", { filename, message: err.message });
    });
}

window.openApplicantResumeInNewTab = function () {
  if (!state.activeResumeBlobUrl) return;
  window.open(state.activeResumeBlobUrl, "_blank", "noopener");
};

window.downloadApplicantResume = function () {
  if (!state.activeResumeBlobUrl) return;
  const link = document.createElement("a");
  link.href = state.activeResumeBlobUrl;
  link.download = state.activeResumeFilename || "applicant_cv.pdf";
  document.body.appendChild(link);
  link.click();
  link.remove();
};

function renderAtsInsightsState(mode, errorMsg = "") {
  const hero = document.getElementById("atsHeroSummary");
  const body = document.getElementById("atsInsightsBody");
  const btn = document.getElementById("btnReanalyzeAi");
  if (!body) return;

  if (mode === "loading") {
    if (btn) btn.disabled = true;
    if (hero) {
      hero.innerHTML = `<div class="ats-hero-loading"><span class="skeleton-bar" style="width:52%;height:24px;margin-bottom:10px"></span><span class="skeleton-bar" style="width:82%;height:14px"></span></div>`;
    }
    body.innerHTML = `
      <div class="ats-loading-box">
        <span class="skeleton-bar" style="width:100%;margin-bottom:10px"></span>
        <span class="skeleton-bar" style="width:88%;margin-bottom:18px"></span>
        <span class="skeleton-bar" style="width:74%;margin-bottom:10px"></span>
        <span class="skeleton-bar" style="width:62%"></span>
      </div>
    `;
    return;
  }

  if (mode === "error") {
    if (btn) btn.disabled = false;
    if (hero) hero.innerHTML = "";
    body.innerHTML = `
      <div class="ats-error-box">
        <p>${escapeHtml(errorMsg || "Could not complete AI evaluation.")}</p>
        <button type="button" class="btn-primary-navy" onclick="triggerAiEvaluation(true)">Retry ATS Analysis</button>
      </div>
    `;
  }
}

function renderAtsInsights(ev) {
  const hero = document.getElementById("atsHeroSummary");
  const body = document.getElementById("atsInsightsBody");
  const btn = document.getElementById("btnReanalyzeAi");
  if (!body || !ev) return;

  if (btn) btn.disabled = false;

  const score = Number.isFinite(Number(ev.fit_score)) ? Number(ev.fit_score) : 0;
  const scoreTone = score >= 75 ? "score-high" : score >= 50 ? "score-mid" : "score-low";
  const recMap = {
    approve: { label: "Recommended: Approve", cls: "rec-approve" },
    revision_requested: { label: "Recommended: Request Revision", cls: "rec-revision" },
    declined: { label: "Recommended: Decline", cls: "rec-decline" },
  };
  const recInfo = recMap[ev.recommendation] || recMap.revision_requested;

  const selectedDiv = (state.activeApp?.division_name || "").trim();
  const bestFitDiv = (ev.best_fit_division || "").trim();
  const hasBetterFit = bestFitDiv && selectedDiv && bestFitDiv.toLowerCase() !== selectedDiv.toLowerCase();

  if (hero) {
    const headlineText = ev.candidate_headline
      ? `<p class="ats-hero-headline">${escapeHtml(ev.candidate_headline)}</p>`
      : "";
    hero.innerHTML = `
      <div class="ats-hero-score-row">
        <div class="ats-score-ring ${scoreTone}">
          <span class="ats-score-num">${score}</span>
          <span class="ats-score-max">/100</span>
        </div>
        <div class="ats-hero-verdict">
          <div class="ats-hero-fit-label">${escapeHtml(ev.fit_label || "Evaluated")}</div>
          <span class="ats-hero-rec-pill ${recInfo.cls}">${escapeHtml(recInfo.label)}</span>
        </div>
      </div>
      ${headlineText}
    `;
  }

  const subs = ev.sub_scores || {};
  const subRows = [
    { label: "Division Fit", val: Number(subs.division_relevance ?? score) || 0 },
    { label: "Statement", val: Number(subs.statement_quality ?? score) || 0 },
    { label: "CV Signal", val: Number(subs.cv_signal ?? 0) || 0 },
  ];

  const bestFitBanner = hasBetterFit
    ? `<div class="ats-bestfit-callout">
        <span class="ats-bestfit-label">Best-Fit Track Match</span>
        <span class="ats-bestfit-val">Profile aligns strongly with <strong>${escapeHtml(bestFitDiv)}</strong> (applied to ${escapeHtml(selectedDiv)})</span>
      </div>`
    : "";

  const skillsHtml = Array.isArray(ev.extracted_skills) && ev.extracted_skills.length > 0
    ? `<div class="ats-section">
        <div class="ats-section-label">Verified Skills &amp; Tools</div>
        <div class="ats-skill-chips">${ev.extracted_skills.map((s) => `<span class="ats-skill-chip">${escapeHtml(s)}</span>`).join("")}</div>
      </div>`
    : "";

  const strengthsHtml = Array.isArray(ev.strengths) && ev.strengths.length > 0
    ? `<div class="ats-callout ats-callout-strengths">
        <div class="ats-section-label">Key Strengths</div>
        <ul class="ats-list ats-list-strengths">${ev.strengths.map((s) => `<li>${escapeHtml(s)}</li>`).join("")}</ul>
      </div>`
    : "";

  const concernsHtml = Array.isArray(ev.concerns) && ev.concerns.length > 0
    ? `<div class="ats-callout ats-callout-concerns">
        <div class="ats-section-label">Concerns &amp; Red Flags</div>
        <ul class="ats-list ats-list-concerns">${ev.concerns.map((c) => `<li>${escapeHtml(c)}</li>`).join("")}</ul>
      </div>`
    : "";

  const cvStatusLabels = {
    analyzed_pdf: "PDF CV Analyzed",
    analyzed_docx: "DOCX CV Analyzed",
    no_cv: "No CV Uploaded (Statement Only)",
    image_only: "Image CV (Statement Evaluated)",
    empty_pdf: "Scanned/Image PDF (No Embedded Text)",
    unsupported_format: "Unsupported CV Format",
    parse_error: "CV Unreadable (Statement Evaluated)",
  };
  const cvStatusText = cvStatusLabels[ev.cv_status] || ev.cv_status || "Statement Evaluated";

  body.innerHTML = `
    <div class="ats-subscore-grid">
      ${subRows
        .map(
          (r) => `
        <div class="ats-subscore-tile">
          <span class="ats-tile-label">${escapeHtml(r.label)}</span>
          <strong class="ats-tile-val ${r.val >= 75 ? "tone-high" : r.val >= 50 ? "tone-mid" : "tone-low"}">${r.val}</strong>
          <div class="ats-meter-track">
            <div class="ats-meter-fill ${r.val >= 75 ? "score-high" : r.val >= 50 ? "score-mid" : "score-low"}" style="width:${Math.max(0, Math.min(100, r.val))}%"></div>
          </div>
        </div>
      `
        )
        .join("")}
    </div>

    ${bestFitBanner}

    <div class="ats-section">
      <div class="ats-section-label">Candidate Summary</div>
      <p class="ats-summary">${escapeHtml(ev.summary || "")}</p>
    </div>

    ${skillsHtml}
    ${strengthsHtml}
    ${concernsHtml}

    <div class="ats-meta-footer">
      <span>${escapeHtml(cvStatusText)}</span>
      <span>${escapeHtml(ev.model || "Groq ATS")}</span>
    </div>
  `;
}

window.triggerAiEvaluation = function (forceRefresh = false) {
  if (!state.activeApp) return;
  const appId = state.activeApp.id;
  const aiReqId = ++state.aiReqSeq;
  renderAtsInsightsState("loading");

  fetch(`${API_BASE}/api/v1/admin/applications/${appId}/ai-evaluate`, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({ force_refresh: Boolean(forceRefresh) }),
  })
    .then(async (res) => {
      if (!res.ok) {
        let detail = "AI evaluation failed.";
        try {
          const errBody = await res.json();
          detail = errBody.detail || detail;
        } catch (_) {}
        throw new Error(detail);
      }
      return res.json();
    })
    .then((data) => {
      if (aiReqId !== state.aiReqSeq || !state.activeApp || state.activeApp.id !== appId) return;
      state.activeApp.ai_evaluation = data.evaluation;
      state.activeApp.ai_evaluated_at = data.evaluated_at || data.evaluation?.evaluated_at;
      renderAtsInsights(data.evaluation, Boolean(data.cached));
      if (!data.cached) {
        captureCurrentSyncVersion();
      }
    })
    .catch((err) => {
      if (aiReqId !== state.aiReqSeq) return;
      renderAtsInsightsState("error", err.message);
    });
};

function renderClaimButton(app) {
  const claimBtn = document.getElementById("btnModalClaim");
  if (!claimBtn) return;

  const isClaimedByMe = state.user && app.assigned_reviewer_id === state.user.id;
  if (isClaimedByMe) {
    claimBtn.textContent = "Release Claim";
    claimBtn.className = "review-act-btn review-act-neutral";
    claimBtn.onclick = () => releaseCurrentApp();
  } else {
    claimBtn.textContent = "Claim";
    claimBtn.className = "review-act-btn review-act-claim";
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

function renderRubricItems(rubricContainer, items) {
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
}

function loadAndRenderRubric() {
  const rubricContainer = document.getElementById("rubricContainer");
  if (!rubricContainer) return;

  if (state.rubricItems && state.rubricItems.length > 0) {
    renderRubricItems(rubricContainer, state.rubricItems);
    return;
  }

  // Fetch settings rubric once and cache in memory
  fetch(`${API_BASE}/api/v1/admin/settings`, { headers: getHeaders() })
    .then((res) => res.json())
    .then((settings) => {
      state.settings = settings;
      const items = settings.qualification_rubric || [];
      state.rubricItems = items;
      renderRubricItems(rubricContainer, items);
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

const QR_ASSETS = {
  general: "/assets/QRs/GeneralQR.png",
  relations: "/assets/QRs/RelationsQR.png",
  operations: "/assets/QRs/OperationalQR.png",
  creatives: "/assets/QRs/CreativesQR.png",
};

const qrDataUrlCache = {};

async function loadQrDataUrl(path) {
  if (!path) return "";
  if (qrDataUrlCache[path]) return qrDataUrlCache[path];

  try {
    const resp = await fetch(path);
    if (!resp.ok) {
      console.warn(`Could not load QR asset at ${path} (status ${resp.status})`);
      return "";
    }
    const blob = await resp.blob();
    const dataUrl = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => resolve(reader.result);
      reader.onerror = () => reject(new Error("Failed converting QR blob to data URL"));
      reader.readAsDataURL(blob);
    });
    if (dataUrl && typeof dataUrl === "string") {
      qrDataUrlCache[path] = dataUrl;
    }
    return dataUrl || "";
  } catch (err) {
    console.warn(`Error loading QR image from ${path}:`, err);
    return "";
  }
}

function getDivisionQrConfig(divName) {
  if (!divName) return null;
  const d = divName.trim();
  if (/relation/i.test(d)) {
    return {
      path: QR_ASSETS.relations,
      label: "Relations QR Attached",
    };
  }
  if (/operation/i.test(d)) {
    return {
      path: QR_ASSETS.operations,
      label: "Operations QR Attached",
    };
  }
  if (/creative|media|design/i.test(d)) {
    return {
      path: QR_ASSETS.creatives,
      label: "Creatives QR Attached",
    };
  }
  return null;
}

function preloadQrAssets() {
  if (typeof window === "undefined" || !window.location || !window.location.origin) return;
  Object.values(QR_ASSETS).forEach((url) => {
    loadQrDataUrl(url).catch(() => {});
  });
}
if (typeof window !== "undefined" && typeof document !== "undefined") {
  const preloadTimer = setTimeout(preloadQrAssets, 2000);
  if (preloadTimer && typeof preloadTimer.unref === "function") preloadTimer.unref();
}

window.initiateDecision = async function (decisionType) {
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
      if (/creative|media|design/i.test(divName)) {
        labelInput.value = "Creatives Group Chat";
        if (linkInput) {
          linkInput.value = "https://m.me/j/AbaoQzrJXHAqFy08/";
        }
      } else if (/relation/i.test(divName)) {
        labelInput.value = "Relations Group Chat";
        if (linkInput) {
          linkInput.value = "";
        }
      } else if (/operation/i.test(divName)) {
        labelInput.value = "Operations Group Chat";
        if (linkInput) {
          linkInput.value = "";
        }
      } else {
        // Skill Builder tracks (Software Development, Web Development, UI/UX, Data, Cloud, AI)
        // Kept blank per user preference ("keep it blank for now. We dont have the qr for it")
        labelInput.value = "";
        if (linkInput) {
          linkInput.value = "";
        }
      }
    }

    if (decisionType === "approved") {
      const generalQrPath = QR_ASSETS.general;
      const divQrConfig = getDivisionQrConfig(divName);

      const [genDataUrl, divDataUrl] = await Promise.all([
        loadQrDataUrl(generalQrPath),
        divQrConfig ? loadQrDataUrl(divQrConfig.path) : Promise.resolve(""),
      ]);

      if (genDataUrl) {
        state.generalQrBase64 = genDataUrl;
        const thumb = document.getElementById("imgGeneralQrThumb");
        const chip = document.getElementById("previewGeneralQr");
        const labelEl = document.getElementById("textGeneralQrLabel");
        if (thumb) thumb.src = genDataUrl;
        if (labelEl) labelEl.textContent = "General QR Attached";
        if (chip) chip.style.display = "inline-flex";
      }

      if (divDataUrl && divQrConfig) {
        state.divisionQrBase64 = divDataUrl;
        const thumb = document.getElementById("imgDivisionQrThumb");
        const chip = document.getElementById("previewDivisionQr");
        const labelEl = document.getElementById("textDivisionQrLabel");
        if (thumb) thumb.src = divDataUrl;
        if (labelEl) labelEl.textContent = divQrConfig.label;
        if (chip) chip.style.display = "inline-flex";
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
      const labelEl = document.getElementById("textGeneralQrLabel");
      if (thumb) thumb.src = dataUrl;
      if (labelEl) labelEl.textContent = "General QR Attached";
      if (chip) chip.style.display = "inline-flex";
    } else {
      state.divisionQrBase64 = dataUrl;
      const thumb = document.getElementById("imgDivisionQrThumb");
      const chip = document.getElementById("previewDivisionQr");
      const labelEl = document.getElementById("textDivisionQrLabel");
      if (thumb) thumb.src = dataUrl;
      if (labelEl) labelEl.textContent = "Division QR Attached";
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

  // If approved or if status no longer matches active filter, remove from list view immediately
  if (newStatus === "approved" || (state.filters.status !== "all" && newStatus !== state.filters.status)) {
    const idx = state.applications.findIndex((a) => a.id === appId);
    if (idx !== -1) {
      state.applications.splice(idx, 1);
      state.total = Math.max(0, state.total - 1);
    }
  }

  // 2. Instantly update Queue Table
  renderQueueTable();

  // 3. Instantly update Status Pill counters
  if (state.statusCounts) {
    if (oldStatus in state.statusCounts) {
      state.statusCounts[oldStatus] = Math.max(0, (state.statusCounts[oldStatus] || 0) - 1);
    }
    if (newStatus in state.statusCounts) {
      state.statusCounts[newStatus] = (state.statusCounts[newStatus] || 0) + 1;
    }
    if (newStatus === "approved" && oldStatus !== "approved") {
      state.statusCounts["all"] = Math.max(0, (state.statusCounts["all"] || 0) - 1);
    }
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

  // 1. INSTANT CLOSE EMAIL MODAL & RETURN TO QUEUE/DASHBOARD (0ms delay!)
  closeEmailModal();
  state.pendingDecision = null;

  // Optimistically update memory and DOM
  applyOptimisticDecision(appId, decisionType, payload);
  closeReviewModal();

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
      loadQueue({ force: true });
      loadDashboard({ force: true });
    });
}

function silentSync() {
  loadDashboard({ force: true, silent: true });
  loadQueue({ force: true, silent: true });
  loadAuditLogs({ force: true, silent: true });
  captureCurrentSyncVersion();
}

// ---------------- Email Templates Editor ----------------
function loadTemplates({ force = false, silent = false } = {}) {
  const activeId = document.getElementById("tmplEditId")?.value || "";

  if (!force && state.loaded.templates && state.templates.length > 0) {
    renderTemplateTabs(state.templates);
    const keepId = activeId && state.templates.some((t) => t.id === activeId) ? activeId : state.templates[0].id;
    selectTemplate(keepId);
    return;
  }

  const reqId = ++state.reqSeq.templates;
  fetch(`${API_BASE}/api/v1/admin/templates`, { headers: getHeaders() })
    .then((res) => res.json())
    .then((templates) => {
      if (reqId !== state.reqSeq.templates) return;
      state.loaded.templates = true;
      state.templates = Array.isArray(templates) ? templates : [];
      renderTemplateTabs(state.templates);
      if (state.templates.length > 0) {
        const currentEditId = document.getElementById("tmplEditId")?.value || "";
        const targetId =
          currentEditId && state.templates.some((t) => t.id === currentEditId)
            ? currentEditId
            : state.templates[0].id;
        selectTemplate(targetId);
      }
      saveAdminCache();
    })
    .catch((err) => {
      if (reqId !== state.reqSeq.templates) return;
      if (!silent) showToast(err.message, "error");
    });
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
      loadTemplates({ force: true });
      loadAuditLogs({ force: true, silent: true });
      captureCurrentSyncVersion();
    })
    .catch((err) => showToast(err.message, "error"));
};

// ---------------- Departments & Settings ----------------
const DEFAULT_DIVISION_AVAILABILITY = {
  office: {
    Relations: "open",
    Operations: "open",
    Creatives: "open",
    Marketing: "full",
    Media: "full",
  },
  skillbuilder: {
    "Software Development": "open",
    "Web Development": "full",
    "UI/UX": "open",
    "Data Analyst": "full",
    "Cloud Computing": "full",
    "Machine Learning & AI": "full",
  },
};

const DIVISION_ELIGIBILITY_HINTS = {
  office: {
    Relations: "1st Year Only",
    Creatives: "1st & 2nd Year",
  },
  skillbuilder: {},
};

state.savedDivisionAvailability = mergeDivisionAvailability();
state.draftDivisionAvailability = mergeDivisionAvailability();

function mergeDivisionAvailability(raw) {
  const merged = {
    office: { ...DEFAULT_DIVISION_AVAILABILITY.office },
    skillbuilder: { ...DEFAULT_DIVISION_AVAILABILITY.skillbuilder },
  };
  if (!raw || typeof raw !== "object") return merged;
  for (const dept of ["office", "skillbuilder"]) {
    const incoming = raw[dept];
    if (!incoming || typeof incoming !== "object") continue;
    for (const name of Object.keys(merged[dept])) {
      if (incoming[name] === "open" || incoming[name] === "full") {
        merged[dept][name] = incoming[name];
      }
    }
  }
  return merged;
}

function isDepartmentDraftDirty() {
  for (const dept of ["office", "skillbuilder"]) {
    const saved = state.savedDivisionAvailability[dept] || {};
    const draft = state.draftDivisionAvailability[dept] || {};
    for (const name of Object.keys(DEFAULT_DIVISION_AVAILABILITY[dept])) {
      if (saved[name] !== draft[name]) return true;
    }
  }
  return false;
}

function syncDepartmentSummaryUI() {
  const draft = state.draftDivisionAvailability;
  const officeVals = Object.values(draft.office);
  const sbVals = Object.values(draft.skillbuilder);

  const officeOpen = officeVals.filter((s) => s === "open").length;
  const sbOpen = sbVals.filter((s) => s === "open").length;
  const totalCount = officeVals.length + sbVals.length;
  const totalOpen = officeOpen + sbOpen;
  const totalFull = totalCount - totalOpen;

  const kpiTotal = document.getElementById("deptKpiTotal");
  const kpiOpen = document.getElementById("deptKpiOpen");
  const kpiFull = document.getElementById("deptKpiFull");
  if (kpiTotal) kpiTotal.textContent = String(totalCount);
  if (kpiOpen) kpiOpen.textContent = String(totalOpen);
  if (kpiFull) kpiFull.textContent = String(totalFull);

  const officeCountEl = document.getElementById("officeOpenCount");
  const sbCountEl = document.getElementById("skillbuilderOpenCount");
  if (officeCountEl) officeCountEl.textContent = `${officeOpen} of ${officeVals.length} divisions open`;
  if (sbCountEl) sbCountEl.textContent = `${sbOpen} of ${sbVals.length} divisions open`;

  const officeBar = document.getElementById("officeProgressFill");
  const sbBar = document.getElementById("skillbuilderProgressFill");
  if (officeBar) officeBar.style.width = `${Math.round((officeOpen / officeVals.length) * 100)}%`;
  if (sbBar) sbBar.style.width = `${Math.round((sbOpen / sbVals.length) * 100)}%`;

  const dirty = isDepartmentDraftDirty();
  const dirtyEl = document.getElementById("deptDirtyIndicator");
  const resetBtn = document.getElementById("btnResetDepartments");
  const saveBtn = document.getElementById("btnSaveDepartments");
  if (dirtyEl) dirtyEl.hidden = !dirty;
  if (resetBtn) resetBtn.hidden = !dirty;
  if (saveBtn) saveBtn.disabled = !dirty;
}

function renderDivisionAvailabilitySettings(availability) {
  const merged = mergeDivisionAvailability(availability);
  state.draftDivisionAvailability = merged;

  const groups = [
    { key: "office", containerId: "divisionSettingsOffice" },
    { key: "skillbuilder", containerId: "divisionSettingsSkillbuilder" },
  ];

  groups.forEach(({ key, containerId }) => {
    const container = document.getElementById(containerId);
    if (!container) return;

    const divisions = merged[key];
    container.innerHTML = Object.entries(divisions)
      .map(([name, status]) => {
        const isOpen = status === "open";
        const hint = DIVISION_ELIGIBILITY_HINTS[key]?.[name] || "";
        const hintHtml = hint ? `<span class="dept-eligibility-tag">${escapeHtml(hint)}</span>` : "";
        const safeDept = escapeHtml(key);
        const safeName = escapeHtml(name);
        return `
          <div class="dept-row ${isOpen ? "is-open" : "is-full"}">
            <div class="dept-row-info">
              <span class="dept-row-dot" aria-hidden="true"></span>
              <div class="dept-row-text">
                <span class="dept-row-name">${safeName}</span>
                ${hintHtml}
              </div>
            </div>
            <div class="dept-segment" role="group" aria-label="${safeName} status">
              <button
                type="button"
                class="dept-seg-btn dept-seg-open ${isOpen ? "active" : ""}"
                data-dept="${safeDept}"
                data-division="${safeName}"
                data-status="open"
                aria-pressed="${isOpen ? "true" : "false"}"
                onclick="setDivisionStatus(this)"
              >Open</button>
              <button
                type="button"
                class="dept-seg-btn dept-seg-full ${!isOpen ? "active" : ""}"
                data-dept="${safeDept}"
                data-division="${safeName}"
                data-status="full"
                aria-pressed="${!isOpen ? "true" : "false"}"
                onclick="setDivisionStatus(this)"
              >Full</button>
            </div>
          </div>
        `;
      })
      .join("");
  });

  syncDepartmentSummaryUI();
}

window.setDivisionStatus = function (btn) {
  const deptKey = btn.dataset.dept;
  const divisionName = btn.dataset.division;
  const nextStatus = btn.dataset.status;
  if (!deptKey || !divisionName || (nextStatus !== "open" && nextStatus !== "full")) return;

  state.draftDivisionAvailability[deptKey][divisionName] = nextStatus;

  const row = btn.closest(".dept-row");
  if (row) {
    const isOpen = nextStatus === "open";
    row.classList.toggle("is-open", isOpen);
    row.classList.toggle("is-full", !isOpen);
    row.querySelectorAll(".dept-seg-btn").forEach((seg) => {
      const active = seg.dataset.status === nextStatus;
      seg.classList.toggle("active", active);
      seg.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  syncDepartmentSummaryUI();
};

window.toggleDepartmentGroup = function (deptKey, targetStatus) {
  if (!state.draftDivisionAvailability[deptKey]) return;
  for (const name of Object.keys(state.draftDivisionAvailability[deptKey])) {
    state.draftDivisionAvailability[deptKey][name] = targetStatus;
  }
  renderDivisionAvailabilitySettings(state.draftDivisionAvailability);
};

window.resetDepartmentChanges = function () {
  renderDivisionAvailabilitySettings(state.savedDivisionAvailability);
};

function applySettingsToUI(settings) {
  state.settings = settings;
  if (settings.qualification_rubric) state.rubricItems = settings.qualification_rubric;
  const toggle = document.getElementById("settingRegistrationOpen");
  const msg = document.getElementById("settingClosedMessage");
  if (toggle) toggle.checked = settings.registration_open;
  if (msg) msg.value = settings.closed_message || "";

  const wasDirty = state.loaded.departments && isDepartmentDraftDirty();
  state.savedDivisionAvailability = mergeDivisionAvailability(settings.division_availability);
  try {
    localStorage.setItem("awssbg_division_availability_v1", JSON.stringify(state.savedDivisionAvailability));
  } catch (_) {}
  if (!wasDirty) {
    renderDivisionAvailabilitySettings(state.savedDivisionAvailability);
  } else {
    syncDepartmentSummaryUI();
  }
}

function loadSettingsShared({ force = false, silent = false } = {}) {
  if (!force && state.loaded.settings && state.loaded.departments && state.settings) {
    applySettingsToUI(state.settings);
    return;
  }

  const reqId = ++state.reqSeq.settings;
  fetch(`${API_BASE}/api/v1/admin/settings`, { headers: getHeaders() })
    .then((res) => res.json())
    .then((settings) => {
      if (reqId !== state.reqSeq.settings) return;
      state.loaded.settings = true;
      state.loaded.departments = true;
      applySettingsToUI(settings);
      saveAdminCache();
    })
    .catch((err) => {
      if (reqId !== state.reqSeq.settings) return;
      if (!silent) showToast(err.message || "Failed to load settings", "error");
    });
}

function loadDepartments({ force = false, silent = false } = {}) {
  if (!force && state.loaded.departments) {
    if (!isDepartmentDraftDirty()) {
      renderDivisionAvailabilitySettings(state.savedDivisionAvailability);
    }
    return;
  }

  // Paint local snapshot immediately if available while fetching once
  try {
    const cachedRaw = localStorage.getItem("awssbg_division_availability_v1");
    if (cachedRaw) {
      state.savedDivisionAvailability = mergeDivisionAvailability(JSON.parse(cachedRaw));
    }
  } catch (_) {}
  renderDivisionAvailabilitySettings(state.savedDivisionAvailability);

  loadSettingsShared({ force: true, silent });
}

window.saveDepartmentAvailability = function () {
  const saveBtn = document.getElementById("btnSaveDepartments");
  if (saveBtn) {
    saveBtn.disabled = true;
    saveBtn.textContent = "Saving...";
  }

  fetch(`${API_BASE}/api/v1/admin/settings`, {
    method: "PUT",
    headers: getHeaders(),
    body: JSON.stringify({
      division_availability: state.draftDivisionAvailability,
    }),
  })
    .then((res) => {
      if (!res.ok) throw new Error("Department update failed (Admin only)");
      return res.json();
    })
    .then((updated) => {
      state.loaded.settings = true;
      state.loaded.departments = true;
      state.settings = updated;
      state.savedDivisionAvailability = mergeDivisionAvailability(updated.division_availability);
      try {
        localStorage.setItem("awssbg_division_availability_v1", JSON.stringify(state.savedDivisionAvailability));
      } catch (_) {}
      renderDivisionAvailabilitySettings(state.savedDivisionAvailability);
      saveAdminCache();
      loadAuditLogs({ force: true, silent: true });
      captureCurrentSyncVersion();
      showToast("Department availability updated!", "success");
    })
    .catch((err) => {
      showToast(err.message, "error");
      syncDepartmentSummaryUI();
    })
    .finally(() => {
      if (saveBtn) saveBtn.textContent = "Save Changes";
    });
};

function loadSettings({ force = false, silent = false } = {}) {
  if (!force && state.loaded.settings && state.settings) {
    const toggle = document.getElementById("settingRegistrationOpen");
    const msg = document.getElementById("settingClosedMessage");
    if (toggle) toggle.checked = state.settings.registration_open;
    if (msg) msg.value = state.settings.closed_message || "";
    return;
  }
  loadSettingsShared({ force: true, silent });
}

window.saveSettings = function () {
  const isOpen = document.getElementById("settingRegistrationOpen").checked;
  const msg = document.getElementById("settingClosedMessage").value.trim();

  fetch(`${API_BASE}/api/v1/admin/settings`, {
    method: "PUT",
    headers: getHeaders(),
    body: JSON.stringify({
      registration_open: isOpen,
      closed_message: msg,
    }),
  })
    .then((res) => {
      if (!res.ok) throw new Error("Settings update failed (Admin only)");
      return res.json();
    })
    .then((updated) => {
      state.loaded.settings = true;
      state.settings = updated;
      saveAdminCache();
      loadAuditLogs({ force: true, silent: true });
      captureCurrentSyncVersion();
      showToast("System settings saved!", "success");
    })
    .catch((err) => showToast(err.message, "error"));
};

window.exportCsv = function () {
  window.open(`${API_BASE}/api/v1/admin/export?status=${state.filters.status}`, "_blank");
};

// ---------------- Audit Logs ----------------
function renderAuditLogsTable(logs) {
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
}

function loadAuditLogs({ force = false, silent = false } = {}) {
  const tbody = document.getElementById("auditLogTableBody");

  if (!force && state.loaded.audit) {
    renderAuditLogsTable(state.auditLogs);
    return;
  }

  const reqId = ++state.reqSeq.audit;
  if (tbody && !silent) {
    if (!state.loaded.audit) {
      tbody.innerHTML = renderTableSkeleton(5, 5);
    } else {
      tbody.classList.add("is-refreshing");
    }
  }

  fetch(`${API_BASE}/api/v1/admin/audit-logs`, { headers: getHeaders() })
    .then((res) => res.json())
    .then((logs) => {
      if (reqId !== state.reqSeq.audit) return;
      state.loaded.audit = true;
      state.auditLogs = Array.isArray(logs) ? logs : [];
      renderAuditLogsTable(state.auditLogs);
      saveAdminCache();
    })
    .catch((err) => {
      if (reqId !== state.reqSeq.audit) return;
      if (!silent) showToast(err.message, "error");
    })
    .finally(() => {
      if (reqId === state.reqSeq.audit && tbody) {
        tbody.classList.remove("is-refreshing");
      }
    });
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

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    QR_ASSETS,
    loadQrDataUrl,
    getDivisionQrConfig,
    qrDataUrlCache,
  };
}
