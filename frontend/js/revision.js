/**
 * AWS SBG JRU - Applicant Revision Page JavaScript
 */

const API_BASE = (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1")
  ? `http://${window.location.hostname}:${window.location.port || "8000"}`
  : "";

document.addEventListener("DOMContentLoaded", () => {
  const urlParams = new URLSearchParams(window.location.search);
  const token = urlParams.get("token");

  const formWrap = document.getElementById("revisionFormWrap");
  const loadingWrap = document.getElementById("loadingWrap");
  const errorWrap = document.getElementById("errorWrap");
  const successWrap = document.getElementById("successWrap");

  if (!token) {
    loadingWrap.style.display = "none";
    errorWrap.style.display = "block";
    document.getElementById("errorMessage").textContent = "Missing secure revision token in link.";
    return;
  }

  // Fetch revision instructions
  fetch(`${API_BASE}/api/v1/revision/${token}`)
    .then((res) => {
      if (!res.ok) {
        return res.json().then((d) => {
          throw new Error(d.detail || "Invalid or expired revision link.");
        });
      }
      return res.json();
    })
    .then((data) => {
      loadingWrap.style.display = "none";
      formWrap.style.display = "block";

      document.getElementById("revApplicantName").textContent = data.full_name;
      document.getElementById("revStudentId").textContent = data.student_id;
      document.getElementById("revProgram").textContent = `${data.program} (${data.year})`;
      document.getElementById("revDivision").textContent = `${data.division_name} (${data.division_type.toUpperCase()})`;

      document.getElementById("revInstructions").textContent = data.revision_notes;
      if (data.revision_deadline) {
        document.getElementById("revDeadlineTag").textContent = `Deadline: ${data.revision_deadline}`;
      }

      document.getElementById("explanationInput").value = data.explanation || "";
    })
    .catch((err) => {
      loadingWrap.style.display = "none";
      errorWrap.style.display = "block";
      document.getElementById("errorMessage").textContent = err.message;
    });

  // Submit revised response
  const form = document.getElementById("revisionForm");
  if (form) {
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const explanation = document.getElementById("explanationInput").value.trim();
      if (!explanation) {
        alert("Please provide an answer before submitting.");
        return;
      }

      const btn = document.getElementById("btnSubmitRevision");
      btn.disabled = true;
      btn.textContent = "Submitting Updated Response...";

      fetch(`${API_BASE}/api/v1/revision/${token}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ explanation }),
      })
        .then((res) => {
          if (!res.ok) {
            return res.json().then((d) => {
              throw new Error(d.detail || "Submission failed");
            });
          }
          return res.json();
        })
        .then(() => {
          formWrap.style.display = "none";
          successWrap.style.display = "block";
        })
        .catch((err) => {
          alert(`Error: ${err.message}`);
          btn.disabled = false;
          btn.textContent = "Submit Revision for Review";
        });
    });
  }
});
