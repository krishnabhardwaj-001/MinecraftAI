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
  const clarificationOptionsSection = document.getElementById("clarificationOptionsSection");
  const clarificationOptionsChips = document.getElementById("clarificationOptionsChips");
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

  // Stage Elements (1 to 8: Authoritative Pipeline)
  const stages = [
    { el: document.getElementById("stage1"), statusEl: document.getElementById("statusStage1"), label: "Understanding" },
    { el: document.getElementById("stage2"), statusEl: document.getElementById("statusStage2"), label: "RAG Retrieval" },
    { el: document.getElementById("stage3"), statusEl: document.getElementById("statusStage3"), label: "Planning" },
    { el: document.getElementById("stage4"), statusEl: document.getElementById("statusStage4"), label: "Generator" },
    { el: document.getElementById("stage5"), statusEl: document.getElementById("statusStage5"), label: "Validation & Repair" },
    { el: document.getElementById("stage6"), statusEl: document.getElementById("statusStage6"), label: "Autonomous QA" },
    { el: document.getElementById("stage7"), statusEl: document.getElementById("statusStage7"), label: "Intent Verification" },
    { el: document.getElementById("stage8"), statusEl: document.getElementById("statusStage8"), label: "READY Gate" },
  ];

  let stageTimer = null;

  // Metric and Version Badge Elements
  const versionSelect = document.getElementById("minecraftVersionSelect");
  const versionBadge = document.getElementById("versionBadge");
  const metricVersionDisplay = document.getElementById("metricVersionDisplay");
  const metricPackFormatDisplay = document.getElementById("metricPackFormatDisplay");

  if (versionSelect) {
    versionSelect.addEventListener("change", () => {
      const v = versionSelect.value;
      if (versionBadge) versionBadge.textContent = `Java ${v}`;
      if (metricVersionDisplay) metricVersionDisplay.textContent = `Java ${v}`;
      if (metricPackFormatDisplay) {
        metricPackFormatDisplay.textContent = v === "1.21.1" ? "Format 48" : "Format 94";
      }
    });
  }

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

  // Mode & Conversational Elements
  const tabConversational = document.getElementById("tabConversational");
  const tabDirect = document.getElementById("tabDirect");
  const submitBtnText = document.getElementById("submitBtnText");
  const conversationPanel = document.getElementById("conversationPanel");
  const chatThread = document.getElementById("chatThread");
  const proposalCard = document.getElementById("proposalCard");
  const proposalStatusBadge = document.getElementById("proposalStatusBadge");
  const proposalSummaryText = document.getElementById("proposalSummaryText");
  const proposalTriggerText = document.getElementById("proposalTriggerText");
  const proposalTargetText = document.getElementById("proposalTargetText");
  const proposalAssumptionsSection = document.getElementById("proposalAssumptionsSection");
  const proposalAssumptionsList = document.getElementById("proposalAssumptionsList");
  const proposalChoicesSection = document.getElementById("proposalChoicesSection");
  const proposalChoiceChips = document.getElementById("proposalChoiceChips");
  const proposalUnsupportedBanner = document.getElementById("proposalUnsupportedBanner");
  const proposalUnsupportedText = document.getElementById("proposalUnsupportedText");
  const confirmProposalBtn = document.getElementById("confirmProposalBtn");
  const resetSessionBtn = document.getElementById("resetSessionBtn");

  let activeMode = "conversational";
  let currentSessionId = null;

  // Mode Switcher Handling
  if (tabConversational && tabDirect) {
    tabConversational.addEventListener("click", () => {
      activeMode = "conversational";
      tabConversational.classList.add("active");
      tabDirect.classList.remove("active");
      if (submitBtnText) submitBtnText.textContent = "Chat & Plan";
      requestInput.placeholder = "Describe what you want, ask questions, or refine...";
      if (currentSessionId && chatThread && chatThread.children.length > 0) {
        conversationPanel.classList.remove("hidden");
      }
    });

    tabDirect.addEventListener("click", () => {
      activeMode = "direct";
      tabDirect.classList.add("active");
      tabConversational.classList.remove("active");
      if (submitBtnText) submitBtnText.textContent = "Generate Datapack";
      requestInput.placeholder = "e.g. When it starts raining, give every player one diamond.";
      conversationPanel.classList.add("hidden");
    });
  }

  // Session Management
  async function ensureSession() {
    if (currentSessionId) return currentSessionId;
    try {
      const selectedVer = versionSelect ? versionSelect.value : "1.21.11";
      const res = await fetch("/api/conversation/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ minecraft_version: selectedVer })
      });
      if (res.ok) {
        const d = await res.json();
        currentSessionId = d.session_id;
        return currentSessionId;
      }
    } catch (err) {
      console.warn("Failed to create conversation session:", err);
    }
    return null;
  }

  if (resetSessionBtn) {
    resetSessionBtn.addEventListener("click", async () => {
      if (currentSessionId) {
        try {
          await fetch(`/api/conversation/session/${currentSessionId}`, { method: "DELETE" });
        } catch (_) {}
      }
      currentSessionId = null;
      if (chatThread) {
        chatThread.innerHTML = "";
        chatThread.classList.add("hidden");
      }
      if (proposalCard) proposalCard.classList.add("hidden");
      if (conversationPanel) conversationPanel.classList.add("hidden");
      requestInput.value = "";
      requestInput.focus();
    });
  }

  // Append Chat Message to UI
  function appendChatMessage(role, text) {
    if (!chatThread || !conversationPanel) return;
    conversationPanel.classList.remove("hidden");
    chatThread.classList.remove("hidden");

    const bubble = document.createElement("div");
    bubble.className = `chat-bubble ${role}`;

    const author = document.createElement("div");
    author.className = "chat-bubble-author";
    author.textContent = role === "user" ? "You" : "MinecraftAI Assistant";

    const body = document.createElement("div");
    body.textContent = text;

    bubble.appendChild(author);
    bubble.appendChild(body);
    chatThread.appendChild(bubble);
    chatThread.scrollTop = chatThread.scrollHeight;
  }

  // Render Proposal Card
  function renderProposal(proposal, canGenerate) {
    if (!proposalCard) return;

    if (proposalSummaryText) proposalSummaryText.textContent = proposal.summary;
    if (proposalTriggerText) proposalTriggerText.textContent = proposal.trigger_condition || "Any gameplay event";
    if (proposalTargetText) proposalTargetText.textContent = proposal.target_affected || "Players / world";

    // Assumptions
    if (proposalAssumptionsSection && proposalAssumptionsList) {
      proposalAssumptionsList.innerHTML = "";
      const assumptions = proposal.assumptions || [];
      if (assumptions.length > 0) {
        assumptions.forEach((a) => {
          const item = document.createElement("div");
          item.className = "assumption-item";

          const desc = document.createElement("div");
          desc.className = "assumption-desc";
          desc.textContent = a.description || a.default_applied;

          const rat = document.createElement("div");
          rat.className = "assumption-rationale";
          rat.textContent = `Rationale: ${a.rationale}`;

          item.appendChild(desc);
          item.appendChild(rat);
          proposalAssumptionsList.appendChild(item);
        });
        proposalAssumptionsSection.classList.remove("hidden");
      } else {
        proposalAssumptionsSection.classList.add("hidden");
      }
    }

    // Open Choices
    if (proposalChoicesSection && proposalChoiceChips) {
      proposalChoiceChips.innerHTML = "";
      const choices = proposal.open_choices || [];
      if (choices.length > 0) {
        choices.forEach((choice) => {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "choice-chip-btn";
          btn.textContent = choice;
          btn.addEventListener("click", async () => {
            await sendChatMessage(choice);
          });
          proposalChoiceChips.appendChild(btn);
        });
        proposalChoicesSection.classList.remove("hidden");
      } else {
        proposalChoicesSection.classList.add("hidden");
      }
    }

    // Unsupported Banner
    if (proposalUnsupportedBanner && proposalUnsupportedText) {
      if (proposal.status === "unsupported") {
        proposalUnsupportedText.textContent = proposal.unsupported_reason || "Requested feature is outside Minecraft datapack capabilities.";
        proposalUnsupportedBanner.classList.remove("hidden");
      } else {
        proposalUnsupportedBanner.classList.add("hidden");
      }
    }

    // Status Badge
    if (proposalStatusBadge) {
      proposalStatusBadge.className = "proposal-status-badge";
      if (proposal.status === "confirmed") {
        proposalStatusBadge.classList.add("proposal-status-confirmed");
        proposalStatusBadge.textContent = "Confirmed & Ready";
      } else if (proposal.status === "unsupported") {
        proposalStatusBadge.classList.add("proposal-status-unsupported");
        proposalStatusBadge.textContent = "Unsupported Capability";
      } else if (proposal.open_choices && proposal.open_choices.length > 0) {
        proposalStatusBadge.classList.add("proposal-status-clarify");
        proposalStatusBadge.textContent = "Needs Clarification";
      } else {
        proposalStatusBadge.classList.add("proposal-status-proposed");
        proposalStatusBadge.textContent = "Proposal Ready";
      }
    }

    // Confirm Button
    if (confirmProposalBtn) {
      confirmProposalBtn.disabled = !canGenerate;
    }

    proposalCard.classList.remove("hidden");
    conversationPanel.classList.remove("hidden");
  }

  // Send Conversational Message
  async function sendChatMessage(messageText) {
    hideAllCards();
    submitBtn.disabled = true;
    submitBtn.classList.add("loading");
    resultMeta.textContent = "Planning behavior...";

    await ensureSession();
    appendChatMessage("user", messageText);

    try {
      const res = await fetch("/api/conversation/message", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: currentSessionId,
          message: messageText
        })
      });

      const data = await res.json();
      submitBtn.disabled = false;
      submitBtn.classList.remove("loading");

      if (!res.ok) {
        showErrorState(data.detail || "Error communicating with conversational agent.");
        return;
      }

      appendChatMessage("assistant", data.proposal.summary);
      renderProposal(data.proposal, data.can_generate);
      resultMeta.textContent = data.can_generate ? "Proposal ready for review & confirmation" : "Clarification required";
    } catch (err) {
      submitBtn.disabled = false;
      submitBtn.classList.remove("loading");
      showErrorState(`Conversational network error: ${err.message}`);
    }
  }

  // Confirm Proposal and Trigger Generation
  if (confirmProposalBtn) {
    confirmProposalBtn.addEventListener("click", async () => {
      if (!currentSessionId) return;

      hideAllCards();
      loadingState.classList.remove("hidden");
      confirmProposalBtn.disabled = true;
      submitBtn.disabled = true;
      resultMeta.textContent = "Building confirmed datapack...";

      startSimulatedProgress();

      try {
        const res = await fetch("/api/conversation/confirm", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: currentSessionId })
        });

        const data = await res.json();
        clearInterval(stageTimer);
        hideAllCards();
        submitBtn.disabled = false;
        confirmProposalBtn.disabled = false;

        if (!res.ok) {
          showErrorState(data.detail || "Server error occurred during datapack compilation.");
          return;
        }

        handlePipelineSuccess(data);
      } catch (err) {
        clearInterval(stageTimer);
        hideAllCards();
        submitBtn.disabled = false;
        confirmProposalBtn.disabled = false;
        showErrorState(`Generation error: ${err.message}`);
      }
    });
  }

  // Main Submit Handler
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const query = requestInput.value.trim();
    if (!query) return;

    if (activeMode === "conversational") {
      requestInput.value = "";
      await sendChatMessage(query);
    } else {
      await executePipeline(query);
    }
  });

  // Clarification Refine Handler
  clarifyBtn.addEventListener("click", async () => {
    const original = requestInput.value.trim();
    const additional = clarifyInput.value.trim();
    if (!additional) return;

    clarifyInput.value = "";
    await executePipeline(original, additional, original);
  });

  // Pipeline Execution Function (Direct One-Shot)
  async function executePipeline(requestText, clarificationAnswer = null, previousRequest = null) {
    hideAllCards();
    loadingState.classList.remove("hidden");
    submitBtn.disabled = true;
    submitBtn.classList.add("loading");
    resultMeta.textContent = "Processing...";

    startSimulatedProgress();

    try {
      const selectedVersion = versionSelect ? versionSelect.value : "1.21.11";

      const payload = {
        request: requestText,
        minecraft_version: selectedVersion
      };

      if (clarificationAnswer) {
        payload.clarification_answer = clarificationAnswer;
      }
      if (previousRequest) {
        payload.previous_request = previousRequest;
      }

      const response = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
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
    // Populate Technical Inspector safely
    ragContextPreview.textContent = JSON.stringify(data.context_summary || {}, null, 2);
    executionSummaryPreview.textContent = data.execution_summary || "Execution complete.";

    const currentVer = data.minecraft_version || (versionSelect ? versionSelect.value : "1.21.11");
    if (versionBadge) versionBadge.textContent = `Java ${currentVer}`;
    if (metricVersionDisplay) metricVersionDisplay.textContent = `Java ${currentVer}`;
    if (metricPackFormatDisplay) {
      metricPackFormatDisplay.textContent = currentVer === "1.21.1" ? "Format 48" : "Format 94";
    }

    if (data.status === "needs_clarification") {
      // Stage 1/3 indicated clarification needed
      setStage(0, "done", "Understood");
      setStage(1, "skipped", "Paused");
      setStage(2, "failed", "Needs Input");
      for (let i = 3; i < 8; i++) setStage(i, "skipped", "Skipped");

      clarificationQuestion.textContent = data.clarification || "Please provide more details on ambiguous parameters.";

      // Render dynamic structured clarification options
      if (clarificationOptionsChips && clarificationOptionsSection) {
        clarificationOptionsChips.innerHTML = "";
        const availableOptions = [];
        const clarReqs = data.clarification_requirements || [];
        clarReqs.forEach((req) => {
          const opts = req.options || [];
          opts.forEach((opt) => {
            if (opt && !availableOptions.includes(opt)) {
              availableOptions.push(opt);
            }
          });
        });

        if (availableOptions.length > 0) {
          availableOptions.forEach((opt) => {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "chip-btn chip-option";
            btn.textContent = opt;
            btn.addEventListener("click", async () => {
              const original = requestInput.value.trim();
              clarifyInput.value = "";
              await executePipeline(original, opt, original);
            });
            clarificationOptionsChips.appendChild(btn);
          });
          clarificationOptionsSection.classList.remove("hidden");
        } else {
          clarificationOptionsSection.classList.add("hidden");
        }
      }

      clarificationCard.classList.remove("hidden");
      resultMeta.textContent = "Clarification required";
      clarifyInput.focus();
      return;
    }

    if (data.status === "failed" || data.status === "error" || data.status === "verification_failed") {
      setStage(0, "done", "Done");
      setStage(1, "done", "Done");
      setStage(2, "done", "Done");
      setStage(3, "done", "Generated");

      if (data.verification_status === "qa_failed") {
        setStage(4, "done", "Passed");
        setStage(5, "failed", "QA Failed");
        setStage(6, "failed", "Aborted");
        setStage(7, "failed", "Aborted");
      } else {
        setStage(4, "failed", "Failed");
        setStage(5, "failed", "Unresolved");
        setStage(6, "failed", "Aborted");
        setStage(7, "failed", "Aborted");
      }

      showErrorState(data.errors, data.repair);
      resultMeta.textContent = "Pipeline failed";
      return;
    }

    // Success State across all 8 stages
    setStage(0, "done", "Passed");
    setStage(1, "done", "Passed");
    setStage(2, "done", "Passed");
    setStage(3, "done", "Generated");

    // Stage 5: Validation & Repair
    if (data.repair && data.repair.total_attempts > 0) {
      setStage(4, "done", `Healed (${data.repair.total_attempts} att)`);
      repairStatusBadge.textContent = `Repaired (${data.repair.total_attempts} attempt${data.repair.total_attempts > 1 ? "s" : ""})`;
      repairStatusBadge.className = "metric-value text-emerald";
    } else {
      setStage(4, "done", "Passed (0 errors)");
      repairStatusBadge.textContent = "Skipped (0 errors)";
      repairStatusBadge.className = "metric-value text-dim";
    }

    // Stage 6: Autonomous QA
    setStage(5, "done", "Passed Cleanly");

    // Stage 7: Intent Verification
    setStage(6, "done", "Verified 100%");

    // Stage 8: READY Gate
    setStage(7, "done", "READY & Zipped");

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

    // Paths (Safe display via textContent if present)
    if (folderPathCode) folderPathCode.textContent = data.datapack_path || "N/A";
    if (zipPathCode) zipPathCode.textContent = data.zip_path || "N/A";

    successCard.classList.remove("hidden");
    resultMeta.textContent = `Datapack ready for Minecraft ${currentVer}`;
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
        const strong = document.createElement("strong");
        strong.textContent = `Attempt #${att.attempt_number} [${att.validation_status}]: `;
        item.appendChild(strong);
        item.appendChild(document.createTextNode(att.reasoning || ""));
        repairAttemptsLog.appendChild(item);
      });
    } else {
      repairHistorySection.classList.add("hidden");
    }

    errorCard.classList.remove("hidden");
    resultMeta.textContent = "Execution halted with errors";
  }
});
