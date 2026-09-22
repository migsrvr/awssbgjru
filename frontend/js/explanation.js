function initFormValidation() {
  const explanationInput = document.getElementById("explanationText");
  const saveBtn = document.getElementById("btnSave");

  if (saveBtn) {
    saveBtn.addEventListener("click", (e) => {
      e.preventDefault();
      validateForm();
    });
  }

  if (explanationInput) {
    explanationInput.addEventListener("input", () => {
      clearFieldError();
    });
  }
}

function validateForm() {
  const explanationInput = document.getElementById("explanationText");
  const saveBtn = document.getElementById("btnSave");

  if (explanationInput && explanationInput.value.trim()) {
    saveBtn.classList.remove("constraint-btn");
    onValidSubmit();
  } else {
    showFieldError();
    saveBtn.classList.add("constraint-btn");
  }
}

function showFieldError() {
  const group = document.getElementById("explanationText")?.closest(".form-group");
  if (!group) return;
  const err = group.querySelector('.form-error[data-for="explanation"]');
  if (err) err.classList.add("visible");
}

function clearFieldError() {
  const group = document.getElementById("explanationText")?.closest(".form-group");
  if (!group) return;
  const err = group.querySelector('.form-error[data-for="explanation"]');
  if (err) err.classList.remove("visible");

  const saveBtn = document.getElementById("btnSave");
  if (document.querySelectorAll(".form-error.visible").length === 0 && saveBtn) {
    saveBtn.classList.remove("constraint-btn");
  }
}

function initResumeUpload() {
  const fileInput = document.getElementById("resumeInput");
  const label = document.getElementById("btnResumeLabel");
  const textSpan = document.getElementById("resumePillText");
  const removeBtn = document.getElementById("btnRemoveResume");
  const errorEl = document.querySelector('.form-error[data-for="resume"]');

  if (!fileInput || !label) return;

  // Keyboard accessibility for label
  label.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fileInput.click();
    }
  });

  fileInput.addEventListener("change", () => {
    const file = fileInput.files && fileInput.files[0];
    if (!file) return;

    // Check size (max 3MB)
    const MAX_SIZE = 3 * 1024 * 1024;
    if (file.size > MAX_SIZE) {
      if (errorEl) {
        errorEl.classList.add("visible");
        const txt = errorEl.querySelector(".error-text");
        if (txt) txt.textContent = "File must be under 3MB.";
      }
      fileInput.value = "";
      return;
    }

    if (errorEl) errorEl.classList.remove("visible");

    const reader = new FileReader();
    reader.onload = function (evt) {
      const base64Data = evt.target.result;
      try {
        sessionStorage.setItem("regResumeBase64", base64Data);
        sessionStorage.setItem("regResumeName", file.name);
      } catch (err) {
        console.warn("Storage quota exceeded for resume:", err);
      }

      setResumeUploadedUI(file.name);
      markFormDirty();
    };
    reader.readAsDataURL(file);
  });

  if (removeBtn) {
    removeBtn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      clearResume();
      markFormDirty();
    });
  }
}

function setResumeUploadedUI(fileName) {
  const label = document.getElementById("btnResumeLabel");
  const textSpan = document.getElementById("resumePillText");
  const removeBtn = document.getElementById("btnRemoveResume");

  if (textSpan) {
    textSpan.textContent = fileName;
    textSpan.title = fileName;
  }
  if (label) {
    label.classList.add("has-file");
  }
  if (removeBtn) {
    removeBtn.style.display = "inline-flex";
  }
}

function clearResume() {
  const fileInput = document.getElementById("resumeInput");
  const label = document.getElementById("btnResumeLabel");
  const textSpan = document.getElementById("resumePillText");
  const removeBtn = document.getElementById("btnRemoveResume");
  const errorEl = document.querySelector('.form-error[data-for="resume"]');

  if (fileInput) fileInput.value = "";
  if (textSpan) {
    textSpan.textContent = "Attach Resume (Optional)";
    textSpan.removeAttribute("title");
  }
  if (label) label.classList.remove("has-file");
  if (removeBtn) removeBtn.style.display = "none";
  if (errorEl) errorEl.classList.remove("visible");

  sessionStorage.removeItem("regResumeBase64");
  sessionStorage.removeItem("regResumeName");
}

function onValidSubmit() {
  const explanationInput = document.getElementById("explanationText");
  const saveBtn = document.getElementById("btnSave");

  sessionStorage.setItem("regExplanation", explanationInput.value.trim());
  saveBtn.textContent = "Saving...";
  saveBtn.disabled = true;

  clearAutoSave();
  window.removeEventListener("beforeunload", onBeforeUnload);
  setTimeout(() => {
    window.location.href = "/department";
  }, 500);
}

function initBackNavigation() {
  const backBtn = document.querySelector(".register-back");
  if (backBtn) {
    backBtn.addEventListener("click", (e) => {
      e.preventDefault();
      window.removeEventListener("beforeunload", onBeforeUnload);
      window.location.href = backBtn.getAttribute("href");
    });
  }
}

function saveFormState() {
  try {
    sessionStorage.setItem(
      "reg_autosave_explanation",
      document.getElementById("explanationText")?.value || ""
    );
  } catch (e) {}
}

function restoreFormState() {
  const savedExplanation = sessionStorage.getItem("reg_autosave_explanation");
  if (savedExplanation) {
    const txt = document.getElementById("explanationText");
    if (txt) txt.value = savedExplanation;
  }

  // Restore resume state
  const resumeName = sessionStorage.getItem("regResumeName");
  if (resumeName) {
    setResumeUploadedUI(resumeName);
  }
}

function clearAutoSave() {
  sessionStorage.removeItem("reg_autosave_explanation");
}

let formDirty = false;
function markFormDirty() {
  formDirty = true;
}

function onBeforeUnload(e) {
  if (formDirty) {
    e.preventDefault();
    e.returnValue = "";
  }
}

function initBeforeUnload() {
  window.addEventListener("beforeunload", onBeforeUnload);
}

function initAutoSave() {
  const explanationInput = document.getElementById("explanationText");
  if (explanationInput) {
    explanationInput.addEventListener("input", () => {
      markFormDirty();
      saveFormState();
    });
  }
}

document.addEventListener("DOMContentLoaded", () => {
  if (!sessionStorage.getItem("regBasic")) {
    window.location.href = "/register";
    return;
  }
  restoreFormState();
  initAutoSave();
  initBeforeUnload();
  initFormValidation();
  initResumeUpload();
  initBackNavigation();
});