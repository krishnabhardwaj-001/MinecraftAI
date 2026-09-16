/**
 * MinecraftAI Web Interface Controller
 * Handles form submission, stage animations, API calls, and dynamic card rendering.
 */

document.addEventListener("DOMContentLoaded", () => {
  // DOM Elements
  const form = document.getElementById("generatorForm");
  const requestInput = document.getElementById("requestInput");
  const submitBtn = document.getElementById("submitBtn");
  
  // Results & States
  const emptyState = document.getElementById("emptyState");
  const loadingState = document.getElementById("loadingState");
  const successCard = document.getElementById("successCard");
  const clarificationCard = document.getElementById("clarificationCard");
  const errorCard = document.getElementById("errorCard");
  
  // Success Card Elements
  const datapackNameDisplay = document.getElementById("datapackNameDisplay");
  const datapackSummaryDisplay = document.getElementById("datapackSummaryDisplay");
  const downloadBtn = document.getElementById("downloadBtn");
  const zipNameTag = document.getElementById("zipNameTag");
  const fileTreeList = document.getElementById("fileTreeList");
  const folderPathCode = document.getElementById("folderPathCode");
  const zipPathCode = document.getElementById("zipPathCode");
  const repairStatusBadge = document.getElementById("repairStatusBadge");

  // Clarification Card Elements
  const clarificationQuestion = document.getElementById("clarificationQuestion");
  const clarifyInput = document.getElementById("clarifyInput");
  const clarifyBtn = document.getElementById("clarifyBtn");

  // Error Card Elements
  const errorList = document.getElementById("errorList");
  const repairHistorySection = document.getElementById("repairHistorySection");
  const repairAttemptsLog = document.getElementById("repairAttemptsLog");

  // Inspector Elements
  const ragContextPreview = document.getElementById("ragContextPreview");
  const executionSummaryPreview = document.getElementById("executionSummaryPreview");
  const resultMeta = document.getElementById("resultMeta");

  // Stage Elements (1 to 7)
  const stages = [
    { el: document.getElementById("stage1"), statusEl: document.getElementById("statusStage1"), label: "Understanding" },
    { el: document.getElementById("stage2"), statusEl: document.getElementById("statusStage2"), label: "RAG Retrieval" },
    { el: document.getElementById("stage3"), statusEl: document.getElementById("statusStage3"), label: "Planning" },
    { el: document.getElementById("stage4"), statusEl: document.getElementById("statusStage4"), label: "Generator" },
    { el: document.getElementById("stage5"), statusEl: document.getElementById("statusStage5"), label: "Validator" },
    { el: document.getElementById("stage6"), statusEl: document.getElementById("statusStage6"), label: "AI Repair" },
    { el: document.getElementById("stage7"), statusEl: document.getElementById("statusStage7"), label: "Validated ZIP" },
  ];

  let stageTimer = null;

  // Example Prompt Chips
  document.querySelectorAll(".chip-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const prompt = btn.getAttribute("data-prompt");
      if (prompt) {
        requestInput.value = prompt;
        requestInput.focus();
      }
    });
  });

  // Reset Pipeline Stages to Idle
  function resetStages() {
    if (stageTimer) clearInterval(stageTimer);
    stages.forEach((s) => {
      s.el.className = "stage-item";
      s.statusEl.textContent = "Idle";
      s.statusEl.style.color = "";
    });
  }

  // Set Stage State
  function setStage(index, state, message) {
    if (index < 0 || index >= stages.length) return;
    const stage = stages[index];
    stage.el.className = `stage-item stage-${state}`;
    stage.statusEl.textContent = message;
  }

  // Animate stages while waiting for the API
  function startSimulatedProgress() {
    resetStages();
    let current = 0;
    setStage(current, "active", "Running...");

    stageTimer = setInterval(() => {
      if (current < 4) { // Only animate up to generation while waiting
        setStage(current, "done", "Done");
        current++;
        setStage(current, "active", "Processing...");
      }
    }, 1800);
  }

  // Hide All Result Cards
  function hideAllCards() {
    emptyState.classList.add("hidden");
    loadingState.classList.add("hidden");
    successCard.classList.add("hidden");
    clarificationCard.classList.add("hidden");
    errorCard.classList.add("hidden");
  }

  // Main Submit Handler
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const query = requestInput.value.trim();
    if (!query) return;

    await executePipeline(query);
  });

  // Clarification Refine Handler
  clarifyBtn.addEventListener("click", async () => {
    const original = requestInput.value.trim();
    const additional = clarifyInput.value.trim();
    if (!additional) return;

    const refined = `${original} Specifically: ${additional}.`;
    requestInput.value = refined;
    clarifyInput.value = "";
    await executePipeline(refined);
  });

  // Pipeline Execution Function
  async function executePipeline(requestText) {
    hideAllCards();
    loadingState.classList.remove("hidden");
    submitBtn.disabled = true;
    submitBtn.classList.add("loading");
    resultMeta.textContent = "Processing...";

    startSimulatedProgress();

    try {
      const response = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          request: requestText,
          minecraft_version: "1.21.11"
        })
      });

      const data = await response.json();
      clearInterval(stageTimer);
      hideAllCards();
      submitBtn.disabled = false;
      submitBtn.classList.remove("loading");

      if (!response.ok) {
        showErrorState(data.detail || "Server error occurred during execution.");
        return;
      }

      handlePipelineSuccess(data);
    } catch (err) {
      clearInterval(stageTimer);
      hideAllCards();
      submitBtn.disabled = false;
      submitBtn.classList.remove("loading");
      showErrorState(`Network or unexpected error: ${err.message}`);
    }
  }

  // Handle Response Logic
  function handlePipelineSuccess(data) {
    // Populate Technical Inspector
    ragContextPreview.textContent = JSON.stringify(data.context_summary || {}, null, 2);
    executionSummaryPreview.textContent = data.execution_summary || "Execution complete.";

    if (data.status === "needs_clarification") {
      // Stage 1/3 indicated clarification needed
      setStage(0, "done", "Understood");
      setStage(1, "skipped", "Paused");
      setStage(2, "failed", "Needs Input");
      for (let i = 3; i < 7; i++) setStage(i, "skipped", "Skipped");

      clarificationQuestion.textContent = data.clarification || "Please provide more details on ambiguous parameters.";
      clarificationCard.classList.remove("hidden");
      resultMeta.textContent = "Clarification required";
      clarifyInput.focus();
      return;
    }

    if (data.status === "failed" || data.status === "error") {
      setStage(0, "done", "Done");
      setStage(1, "done", "Done");
      setStage(2, "done", "Done");
      setStage(3, "done", "Generated");
      setStage(4, "failed", "Failed");
      setStage(5, "failed", "Unresolved");
      setStage(6, "failed", "Aborted");

      showErrorState(data.errors, data.repair);
      resultMeta.textContent = "Pipeline failed";
      return;
    }

    // Success State
    for (let i = 0; i < 5; i++) setStage(i, "done", "Passed");

    // Repair state
    if (data.repair && data.repair.total_attempts > 0) {
      setStage(5, "done", `Healed (${data.repair.total_attempts} att)`);
      repairStatusBadge.textContent = `Repaired (${data.repair.total_attempts} attempt${data.repair.total_attempts > 1 ? "s" : ""})`;
      repairStatusBadge.className = "metric-value text-emerald";
    } else {
      setStage(5, "skipped", "Skipped (0 errors)");
      repairStatusBadge.textContent = "Skipped (0 errors)";
      repairStatusBadge.className = "metric-value text-dim";
    }

    setStage(6, "done", "Validated 100%");

    // Fill Success Card
    datapackNameDisplay.textContent = data.zip_filename ? data.zip_filename.replace(".zip", "") : "minecraft_datapack";
    datapackSummaryDisplay.textContent = data.plan_summary || data.original_request;

    if (data.download_url) {
      downloadBtn.href = data.download_url;
      downloadBtn.setAttribute("download", data.zip_filename || "datapack.zip");
      zipNameTag.textContent = data.zip_filename || "datapack.zip";
    }

    // File Tree
    fileTreeList.innerHTML = "";
    const files = data.files_generated || ["pack.mcmeta"];
    files.forEach((f) => {
      const li = document.createElement("li");
      li.className = "is-file";
      li.textContent = f;
      fileTreeList.appendChild(li);
    });

    // Paths
    folderPathCode.textContent = data.datapack_path || "N/A";
    zipPathCode.textContent = data.zip_path || "N/A";

    successCard.classList.remove("hidden");
    resultMeta.textContent = "Datapack ready for Minecraft 1.21.11";
  }

  // Show Error Card
  function showErrorState(errors, repairData) {
    errorList.innerHTML = "";
    const errArray = Array.isArray(errors) ? errors : [errors];

    errArray.forEach((msg) => {
      const li = document.createElement("li");
      li.textContent = msg;
      errorList.appendChild(li);
    });

    if (repairData && repairData.attempts && repairData.attempts.length > 0) {
      repairHistorySection.classList.remove("hidden");
      repairAttemptsLog.innerHTML = "";
      repairData.attempts.forEach((att) => {
        const item = document.createElement("div");
        item.className = "repair-item";
        item.innerHTML = `<strong>Attempt #${att.attempt_number} [${att.validation_status}]</strong>: ${att.reasoning}`;
        repairAttemptsLog.appendChild(item);
      });
    } else {
      repairHistorySection.classList.add("hidden");
    }

    errorCard.classList.remove("hidden");
    resultMeta.textContent = "Execution halted with errors";
  }
});
