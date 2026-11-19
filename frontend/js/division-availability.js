(function attachDivisionAvailability(root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root) root.DivisionAvailability = api;
})(typeof window !== "undefined" ? window : undefined, function createApi() {
  const FULL_MESSAGE = "This team is full! Please choose another!";

  function isFullPill(pill) {
    return pill?.dataset?.availability === "full";
  }

  function rememberDefault(error) {
    if (!error || error.dataset.defaultMessage) return;
    const text = error.querySelector(".error-text");
    error.dataset.defaultMessage = text?.textContent || "";
  }

  function clearInlineUnavailable(pill) {
    const ownNote = pill?.querySelector?.(".division-unavailable-note");
    ownNote?.classList?.remove("visible");
    pill?.classList?.remove("unavailable-message-visible");

    const scope = pill?.parentElement;
    const notes = scope?.querySelectorAll?.(".division-unavailable-note") || [];
    notes.forEach((note) => note.classList.remove("visible"));

    const pills = scope?.querySelectorAll?.(".office-pill, .sb-pill") || [];
    pills.forEach((item) => item.classList.remove("unavailable-message-visible"));
  }

  function showInlineUnavailable(pill) {
    const note = pill?.querySelector?.(".division-unavailable-note");
    if (!note) return false;
    clearInlineUnavailable(pill);
    pill.classList.add("unavailable-message-visible");
    note.classList.add("visible");
    return true;
  }

  function showUnavailable(errorOrSelector, pill) {
    if (showInlineUnavailable(pill)) {
      resetMessage(errorOrSelector);
      return;
    }

    const error = typeof errorOrSelector === "string"
      ? document.querySelector(errorOrSelector)
      : errorOrSelector;
    if (!error) return;
    rememberDefault(error);
    const text = error.querySelector(".error-text");
    if (text) text.textContent = FULL_MESSAGE;
    error.classList.add("visible");
  }

  function resetMessage(error) {
    if (!error) return;
    rememberDefault(error);
    const text = error.querySelector(".error-text");
    if (text) text.textContent = error.dataset.defaultMessage;
    error.classList.remove("visible");
  }

  function bindPill(pill, error) {
    pill.addEventListener("click", (event) => {
      if (!isFullPill(pill)) {
        clearInlineUnavailable(pill);
        resetMessage(error);
        return;
      }
      event.preventDefault();
      event.stopImmediatePropagation();
      showUnavailable(error, pill);
    }, true);
  }

  function clearUnavailableAutosave(pills, storageKey) {
    if (!storageKey || typeof sessionStorage === "undefined") return;
    const saved = sessionStorage.getItem(storageKey);
    const stale = pills.some((pill) => isFullPill(pill) && pill.dataset.division === saved);
    if (stale) sessionStorage.removeItem(storageKey);
  }

  function getApiBase() {
    if (typeof window === "undefined" || !window.location) return "";
    const host = window.location.hostname;
    if (host === "localhost" || host === "127.0.0.1") {
      return `http://${host}:${window.location.port || "8000"}`;
    }
    return "";
  }

  function buildRibbonMarkup(divisionType, status) {
    if (divisionType === "skillbuilder") {
      const file = status === "full" ? "skillbuilder-full.svg" : "skillbuilder-open.svg";
      return `<img src="../assets/registration/ribbons/${file}" alt="" />`;
    }
    if (status === "full") {
      return `<img src="../assets/registration/ribbons/full.svg" alt="" />`;
    }
    return (
      `<img class="ribbon-default" src="../assets/registration/ribbons/open.svg" alt="" />` +
      `<img class="ribbon-selected" src="../assets/registration/ribbons/open-selected.svg" alt="" />`
    );
  }

  function ensureUnavailableNote(pill) {
    const existing = pill?.querySelector?.(".division-unavailable-note");
    if (existing) return existing;
    const copy = pill?.querySelector?.(".division-copy");
    if (!copy || typeof document === "undefined" || !document.createElement) return null;
    const note = document.createElement("span");
    note.className = "division-note division-unavailable-note";
    note.setAttribute("role", "status");
    note.setAttribute("aria-live", "polite");
    note.textContent = FULL_MESSAGE;
    copy.appendChild(note);
    return note;
  }

  function applyAvailability(divisionType, statusMap, pills, storageKey) {
    if (!statusMap || !Array.isArray(pills)) return;
    pills.forEach((pill) => {
      const divisionName = pill?.dataset?.division;
      const nextStatus = divisionName ? statusMap[divisionName] : undefined;
      if (nextStatus !== "open" && nextStatus !== "full") return;

      pill.dataset.availability = nextStatus;

      const ribbon = pill.querySelector?.(".availability-ribbon");
      if (ribbon) {
        ribbon.innerHTML = buildRibbonMarkup(divisionType, nextStatus);
      }

      if (nextStatus === "full") {
        pill.setAttribute?.("aria-disabled", "true");
        pill.classList?.remove?.("selected");
        ensureUnavailableNote(pill);
      } else {
        const isYearIneligible = pill.classList?.contains?.("year-ineligible");
        if (!isYearIneligible) {
          pill.removeAttribute?.("aria-disabled");
        }
        pill.classList?.remove?.("unavailable-message-visible");
        const note = pill.querySelector?.(".division-unavailable-note");
        note?.classList?.remove?.("visible");
      }
    });

    clearUnavailableAutosave(pills, storageKey);

    if (typeof document !== "undefined" && typeof CustomEvent !== "undefined" && document.dispatchEvent) {
      document.dispatchEvent(
        new CustomEvent("divisionAvailabilityUpdated", {
          detail: { divisionType, statusMap },
        }),
      );
    }
  }

  const STORAGE_CACHE_KEY = "awssbg_division_availability_v1";

  function readCachedAvailability(divisionType) {
    try {
      if (typeof localStorage === "undefined") return null;
      const raw = localStorage.getItem(STORAGE_CACHE_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      return parsed?.[divisionType] || null;
    } catch (_) {
      return null;
    }
  }

  function writeCachedAvailability(allAvailability) {
    try {
      if (typeof localStorage === "undefined" || !allAvailability) return;
      localStorage.setItem(STORAGE_CACHE_KEY, JSON.stringify(allAvailability));
    } catch (_) {}
  }

  function hydrateFromServer({ divisionType, pills, storageKey }) {
    if (typeof fetch !== "function" || !pills.length) return;
    const url = `${getApiBase()}/api/v1/revision/status/registration?_t=${Date.now()}`;
    fetch(url, { cache: "no-store" })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!data?.division_availability) return;
        writeCachedAvailability(data.division_availability);
        const statusMap = data.division_availability[divisionType];
        if (statusMap) {
          applyAvailability(divisionType, statusMap, pills, storageKey);
        }
      })
      .catch(() => {});
  }

  function bindSubmit(submit, pills, error) {
    submit?.addEventListener("click", (event) => {
      const selectedFull = pills.find(
        (pill) => isFullPill(pill) && pill.classList.contains("selected"),
      );
      if (!selectedFull) {
        pills.forEach(clearInlineUnavailable);
        resetMessage(error);
        return;
      }
      event.preventDefault();
      event.stopImmediatePropagation();
      showUnavailable(error, selectedFull);
    }, true);
  }

  let initializedPages = [];

  function initPage({ divisionType, pillSelector, errorSelector, submitSelector, storageKey }) {
    const pills = Array.from(document.querySelectorAll(pillSelector));
    if (!pills.length) return;
    const error = document.querySelector(errorSelector);
    rememberDefault(error);

    // Apply latest known snapshot immediately to avoid flashing stale hardcoded HTML
    const cachedMap = readCachedAvailability(divisionType);
    if (cachedMap) {
      applyAvailability(divisionType, cachedMap, pills, storageKey);
    }

    clearUnavailableAutosave(pills, storageKey);
    pills.forEach((pill) => bindPill(pill, error));
    bindSubmit(document.querySelector(submitSelector), pills, error);

    const pageCtx = { divisionType, pills, storageKey };
    initializedPages.push(pageCtx);
    hydrateFromServer(pageCtx);
  }

  let didInit = false;

  function rehydrateAll() {
    initializedPages.forEach((ctx) => hydrateFromServer(ctx));
  }

  function init() {
    if (didInit) return;
    didInit = true;
    initializedPages = [];
    initPage({
      divisionType: "office",
      pillSelector: ".office-pill",
      errorSelector: ".office-error",
      submitSelector: "#btnSaveOffice",
      storageKey: "reg_autosave_office",
    });
    initPage({
      divisionType: "skillbuilder",
      pillSelector: ".sb-pill",
      errorSelector: ".sb-error",
      submitSelector: "#btnSaveSB",
      storageKey: "reg_autosave_sb",
    });

    if (typeof window !== "undefined" && window.addEventListener) {
      window.addEventListener("pageshow", rehydrateAll);
      window.addEventListener("focus", rehydrateAll);
    }
    if (typeof document !== "undefined" && document.addEventListener) {
      document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") rehydrateAll();
      });
    }
  }

  if (typeof document !== "undefined") {
    const hasPillsNow = document.querySelector?.(".office-pill, .sb-pill");
    if (hasPillsNow || document.readyState !== "loading") {
      init();
    } else {
      document.addEventListener("DOMContentLoaded", init);
    }
  }

  return { FULL_MESSAGE, applyAvailability, bindPill, isFullPill, resetMessage, showUnavailable };
});
