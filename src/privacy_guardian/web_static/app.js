const source = document.querySelector("#source");
const result = document.querySelector("#result");
const findingsBody = document.querySelector("#findings-body");
const findingsHeading = document.querySelector("#findings-heading");
const counter = document.querySelector("#counter");
const statusLabel = document.querySelector("#engine-status");
const modeSelect = document.querySelector("#mode-select");
const modeNote = document.querySelector("#mode-note");
const report = document.querySelector("#report");
const reportSummary = document.querySelector("#report-summary");
const reportChecklist = document.querySelector("#report-checklist");
const fileInput = document.querySelector("#file-input");
const fileStatusTitle = document.querySelector("#file-status-title");
const fileStatus = document.querySelector("#file-status");
const processingNotice = document.querySelector("#processing-notice");
const primaryAction = document.querySelector("#primary-action");
const primaryLabel = document.querySelector("#primary-label");
const clearButton = document.querySelector("#clear-btn");
const secondarySaveButton = document.querySelector("#secondary-save-btn");
const stepEyebrow = document.querySelector("#step-eyebrow");
const actionTitle = document.querySelector("#action-title");
const actionDescription = document.querySelector("#action-description");
const liveStatus = document.querySelector("#live-status");
const errorNotice = document.querySelector("#error-notice");
const errorMessage = document.querySelector("#error-message");
const documentResult = document.querySelector("#document-result");
const resultFilename = document.querySelector("#result-filename");
const sourceState = document.querySelector("#source-state");
const resultState = document.querySelector("#result-state");
const reviewGuidance = document.querySelector("#review-guidance");
const actionStage = document.querySelector("#action-stage");
const findingsSection = document.querySelector("#findings-section");
const workflowSteps = Array.from(document.querySelectorAll(".workflow-step"));

const phases = ["load", "analyze", "review", "protect", "use"];
let phase = "load";
let busy = false;
let activeDocument = false;
let currentFindings = [];
let pendingDocument = null;
let maxFileBytes = 0;
let cueTimer = null;
let reviewExposed = false;
let modeNotes = {
  standard: "Mantiene leggibili struttura e contesto, conservando iniziali e date.",
  maximum: "Usa segnaposto completi e protegge anche le date comuni riconosciute.",
};

function updateProcessingNotice() {
  const hostname = location.hostname;
  const isLocalhost = hostname === "localhost" || hostname === "127.0.0.1" || hostname === "::1";
  processingNotice.textContent = isLocalhost
    ? "Elaborazione locale · i dati restano sul dispositivo"
    : "Elaborazione sul server OMISSIS configurato · i dati vengono inviati a questo server";
}

function hasDocument() {
  return activeDocument && fileInput.files.length > 0;
}

function hasText() {
  return source.value.trim().length > 0;
}

function hasInput() {
  return hasDocument() || hasText();
}

function phaseIndex() {
  return phase === "complete" ? phases.length : phases.indexOf(phase);
}

function reviewTitle() {
  const count = currentFindings.length;
  if (count === 0) return "Controlla il risultato dell'analisi";
  if (count === 1) return "Controlla il dato rilevato";
  return `Controlla ${count} dati rilevati`;
}

function actionContent() {
  if (busy) {
    return {
      eyebrow: phase === "analyze" ? "ANALISI IN CORSO" : "PROTEZIONE IN CORSO",
      title: phase === "analyze" ? "Sto cercando i dati personali" : "Sto creando la copia protetta",
      description: "Il documento resta in questa sessione. Attendi il completamento del passaggio.",
      label: phase === "analyze" ? "Analisi in corso…" : "Protezione in corso…",
    };
  }

  if (phase === "analyze") {
    return {
      eyebrow: "PASSAGGIO 2 DI 5",
      title: "Il contenuto è pronto per il controllo",
      description: "Avvia l'analisi locale per individuare nomi, contatti, codici e altri dati personali.",
      label: "Analizza dati",
    };
  }
  if (phase === "review") {
    return {
      eyebrow: "PASSAGGIO 3 DI 5",
      title: reviewTitle(),
      description: "Rileggi i valori trovati: il controllo umano resta importante anche quando l'analisi è automatica.",
      label: "Ho controllato, continua",
    };
  }
  if (phase === "protect") {
    return {
      eyebrow: "PASSAGGIO 4 DI 5",
      title: "Crea ora la copia protetta",
      description: "OMISSIS applicherà la modalità scelta senza modificare il documento originale.",
      label: "Crea copia protetta",
    };
  }
  if (phase === "use") {
    return {
      eyebrow: "PASSAGGIO 5 DI 5",
      title: "La copia protetta è pronta",
      description: pendingDocument
        ? "Scarica il nuovo documento e rileggilo prima di condividerlo."
        : "Copiala negli appunti e rileggila prima di usarla con un servizio di IA.",
      label: pendingDocument ? "Scarica risultato" : "Copia risultato",
    };
  }
  if (phase === "complete") {
    return {
      eyebrow: "FLUSSO COMPLETATO",
      title: "Il risultato è sotto il tuo controllo",
      description: pendingDocument
        ? "Il documento protetto è stato scaricato. Puoi scaricarlo di nuovo oppure iniziare una nuova sessione."
        : "Il testo protetto è stato copiato. Puoi copiarlo di nuovo oppure iniziare una nuova sessione.",
      label: pendingDocument ? "Scarica di nuovo" : "Copia di nuovo",
    };
  }
  return {
    eyebrow: "PASSAGGIO 1 DI 5",
    title: "Porta qui ciò che vuoi proteggere",
    description: "Carica un documento dal computer oppure incolla direttamente il testo nel riquadro sottostante.",
    label: "Carica documento",
  };
}

function cuePrimaryAction() {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    return;
  }
  window.clearTimeout(cueTimer);
  primaryAction.classList.remove("attention-cue");
  void primaryAction.offsetWidth;
  primaryAction.classList.add("attention-cue");
  cueTimer = window.setTimeout(() => primaryAction.classList.remove("attention-cue"), 820);
}

function updateWorkflowSteps() {
  const currentIndex = phaseIndex();
  workflowSteps.forEach((step, index) => {
    const marker = step.querySelector(".step-marker");
    const isDone = index < currentIndex || phase === "complete";
    const isCurrent = index === currentIndex && phase !== "complete";
    step.classList.toggle("is-done", isDone);
    step.classList.toggle("is-current", isCurrent);
    step.classList.toggle("is-pending", !isDone && !isCurrent);
    marker.textContent = isDone ? "✓" : String(index + 1);
    if (isCurrent) {
      step.setAttribute("aria-current", "step");
    } else {
      step.removeAttribute("aria-current");
    }
  });
}

function updateInterface({cue = false, announce = true} = {}) {
  const content = actionContent();
  document.body.dataset.phase = phase;
  actionStage.classList.toggle("is-compact", phase !== "load");
  stepEyebrow.textContent = content.eyebrow;
  actionTitle.textContent = content.title;
  actionDescription.textContent = content.description;
  primaryLabel.textContent = content.label;
  primaryAction.disabled = busy || (phase === "review" && !reviewExposed);
  primaryAction.setAttribute("aria-busy", String(busy));
  modeSelect.disabled = busy;
  source.readOnly = busy || hasDocument();
  clearButton.disabled = busy;
  clearButton.hidden = !hasInput() && phase === "load";
  modeNote.textContent = modeNotes[modeSelect.value] || "";
  updateWorkflowSteps();

  sourceState.textContent = hasDocument() ? "Documento caricato" : hasText() ? "Testo presente" : "In attesa";
  resultState.textContent = pendingDocument || result.value.trim() ? "Pronta" : "Non ancora creata";
  secondarySaveButton.hidden = !result.value.trim();
  reviewGuidance.classList.toggle("is-active", phase === "review");

  if (announce) {
    liveStatus.textContent = `${content.eyebrow}. ${content.title}.`;
  }
  if (cue) {
    cuePrimaryAction();
  }
}

function setPhase(nextPhase, options = {}) {
  const changed = phase !== nextPhase;
  phase = nextPhase;
  if (phase !== "review") reviewExposed = false;
  updateInterface({cue: changed && options.cue !== false, announce: options.announce !== false});
}

function exposeReviewResults() {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  window.requestAnimationFrame(() => {
    findingsSection.scrollIntoView({behavior: reduceMotion ? "auto" : "smooth", block: "start"});
    findingsHeading.focus({preventScroll: true});
    window.setTimeout(() => {
      reviewExposed = true;
      updateInterface({cue: true, announce: false});
    }, reduceMotion ? 0 : 360);
  });
}

function showError(message) {
  errorMessage.textContent = message;
  errorNotice.hidden = false;
  liveStatus.textContent = `Errore. ${message}`;
}

function clearError() {
  errorMessage.textContent = "";
  errorNotice.hidden = true;
}

function renderFindings(findings, {analyzed = false} = {}) {
  currentFindings = findings;
  findingsBody.replaceChildren();
  counter.textContent = `${findings.length} ${findings.length === 1 ? "elemento" : "elementi"}`;

  if (!findings.length) {
    const row = document.createElement("tr");
    row.className = "empty-row";
    const cell = document.createElement("td");
    cell.colSpan = 4;
    cell.textContent = analyzed
      ? "Nessun dato rilevato automaticamente. Controlla comunque il contenuto originale."
      : "I dati trovati appariranno qui dopo l'analisi.";
    row.appendChild(cell);
    findingsBody.appendChild(row);
    return;
  }

  for (const finding of findings) {
    const row = document.createElement("tr");
    const cells = [
      finding.label || finding.entity_type,
      finding.preview,
      reliabilityLabel(Number(finding.score)),
      finding.source_label || finding.source,
    ];
    for (const value of cells) {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.appendChild(cell);
    }
    findingsBody.appendChild(row);
  }
}

function reliabilityLabel(score) {
  if (score >= 0.9) return "Alta";
  if (score >= 0.8) return "Buona";
  return "Da verificare";
}

function renderReport(payload) {
  reportChecklist.replaceChildren();
  if (!payload || !payload.summary) {
    report.hidden = true;
    reportSummary.textContent = "";
    return;
  }
  report.hidden = false;
  reportSummary.textContent = payload.summary;
  for (const item of payload.checklist || []) {
    const checklistItem = document.createElement("li");
    checklistItem.textContent = item;
    reportChecklist.appendChild(checklistItem);
  }
}

function resetGeneratedState() {
  currentFindings = [];
  pendingDocument = null;
  result.value = "";
  documentResult.hidden = true;
  resultFilename.textContent = "Documento protetto pronto";
  renderFindings([]);
  renderReport(null);
  clearError();
}

function resetSession() {
  source.value = "";
  result.value = "";
  fileInput.value = "";
  activeDocument = false;
  pendingDocument = null;
  currentFindings = [];
  fileStatusTitle.textContent = "Nessun documento caricato";
  fileStatus.textContent = "Puoi anche trascinare un file in questa finestra o incollare del testo.";
  documentResult.hidden = true;
  renderFindings([]);
  renderReport(null);
  clearError();
  setPhase("load");
  source.focus();
}

async function postJson(path) {
  const response = await fetch(path, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    cache: "no-store",
    body: JSON.stringify({text: source.value, mode: modeSelect.value}),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "Richiesta non riuscita");
  }
  return response.json();
}

async function postDocument(path) {
  if (!fileInput.files.length) {
    throw new Error("Scegli un documento da proteggere.");
  }
  const formData = new FormData();
  formData.append("mode", modeSelect.value);
  formData.append("file", fileInput.files[0]);
  const response = await fetch(path, {method: "POST", cache: "no-store", body: formData});
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "Documento non elaborato");
  }
  return response.json();
}

function setBusy(isBusy) {
  busy = isBusy;
  updateInterface({cue: false, announce: true});
}

async function analyze() {
  if (!hasInput()) {
    setPhase("load");
    return;
  }
  clearError();
  setBusy(true);
  try {
    const data = hasDocument()
      ? await postDocument("/api/analyze-document")
      : await postJson("/api/analyze");
    statusLabel.textContent = data.engine_status;
    renderFindings(data.findings || [], {analyzed: true});
    renderReport(data.report);
    if (data.filename) {
      fileStatusTitle.textContent = "Documento analizzato";
      fileStatus.textContent = data.filename;
    }
    setBusy(false);
    setPhase("review", {cue: false});
    exposeReviewResults();
  } catch (error) {
    setBusy(false);
    showError(error.message);
    setPhase("analyze", {cue: false, announce: false});
  }
}

async function anonymize() {
  clearError();
  setBusy(true);
  try {
    const data = hasDocument()
      ? await postDocument("/api/anonymize-document")
      : await postJson("/api/anonymize");
    statusLabel.textContent = data.engine_status;
    renderFindings(data.findings || [], {analyzed: true});
    renderReport(data.report);

    if (data.content_base64) {
      pendingDocument = {
        filename: data.filename,
        contentBase64: data.content_base64,
        mediaType: data.media_type,
      };
      documentResult.hidden = false;
      resultFilename.textContent = data.filename;
      fileStatusTitle.textContent = "Copia protetta pronta";
      fileStatus.textContent = "Il documento originale non è stato modificato.";
    } else {
      pendingDocument = null;
      result.value = data.text || "";
      documentResult.hidden = true;
    }
    setBusy(false);
    setPhase("use");
  } catch (error) {
    setBusy(false);
    showError(error.message);
    setPhase("protect", {cue: false, announce: false});
  }
}

function downloadBase64(filename, contentBase64, mediaType) {
  const byteCharacters = atob(contentBase64);
  const byteArrays = [];
  const chunkSize = 4096;
  for (let offset = 0; offset < byteCharacters.length; offset += chunkSize) {
    const slice = byteCharacters.slice(offset, offset + chunkSize);
    const bytes = new Uint8Array(slice.length);
    for (let index = 0; index < slice.length; index += 1) {
      bytes[index] = slice.charCodeAt(index);
    }
    byteArrays.push(bytes);
  }
  const blob = new Blob(byteArrays, {type: mediaType || "application/octet-stream"});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function downloadText(filename, text) {
  const blob = new Blob([text], {type: "text/plain;charset=utf-8"});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function copyResult() {
  try {
    await navigator.clipboard.writeText(result.value);
  } catch (_error) {
    result.focus();
    result.select();
    document.execCommand("copy");
  }
}

async function useResult() {
  clearError();
  if (pendingDocument) {
    downloadBase64(pendingDocument.filename, pendingDocument.contentBase64, pendingDocument.mediaType);
    liveStatus.textContent = `Scaricato ${pendingDocument.filename}.`;
  } else if (result.value.trim()) {
    await copyResult();
    liveStatus.textContent = "Testo protetto copiato negli appunti.";
  } else {
    showError("Il risultato non è disponibile. Crea nuovamente la copia protetta.");
    return;
  }
  setPhase("complete");
}

async function runPrimaryAction() {
  if (busy) return;
  if (phase === "load") {
    fileInput.click();
  } else if (phase === "analyze") {
    await analyze();
  } else if (phase === "review") {
    setPhase("protect");
  } else if (phase === "protect") {
    await anonymize();
  } else {
    await useResult();
  }
}

function formatBytes(value) {
  if (!Number.isFinite(value)) return "";
  if (value % (1024 * 1024) === 0) return `${value / (1024 * 1024)} MB`;
  if (value % 1024 === 0) return `${value / 1024} KB`;
  return `${value} byte`;
}

function acceptSelectedFile() {
  if (!fileInput.files.length) return;
  const file = fileInput.files[0];
  activeDocument = true;
  source.value = "";
  resetGeneratedState();
  const limit = maxFileBytes ? ` · limite ${formatBytes(maxFileBytes)}` : "";
  fileStatusTitle.textContent = file.name;
  fileStatus.textContent = `${formatBytes(file.size)}${limit} · pronto per l'analisi`;
  setPhase("analyze");
}

primaryAction.addEventListener("click", runPrimaryAction);
clearButton.addEventListener("click", resetSession);
secondarySaveButton.addEventListener("click", () => {
  if (result.value.trim()) downloadText("testo_anonimizzato.txt", result.value);
});
fileInput.addEventListener("change", acceptSelectedFile);

source.addEventListener("input", () => {
  activeDocument = false;
  fileInput.value = "";
  resetGeneratedState();
  if (hasText()) {
    fileStatusTitle.textContent = "Testo incollato";
    fileStatus.textContent = "Il testo è pronto per l'analisi locale.";
    setPhase("analyze");
  } else {
    fileStatusTitle.textContent = "Nessun documento caricato";
    fileStatus.textContent = "Puoi anche trascinare un file in questa finestra o incollare del testo.";
    setPhase("load");
  }
});

modeSelect.addEventListener("change", () => {
  resetGeneratedState();
  setPhase(hasInput() ? "analyze" : "load");
});

let dragDepth = 0;
document.addEventListener("dragenter", (event) => {
  event.preventDefault();
  dragDepth += 1;
  document.body.classList.add("is-dragging");
});
document.addEventListener("dragover", (event) => event.preventDefault());
document.addEventListener("dragleave", () => {
  dragDepth = Math.max(0, dragDepth - 1);
  if (dragDepth === 0) document.body.classList.remove("is-dragging");
});
document.addEventListener("drop", (event) => {
  event.preventDefault();
  dragDepth = 0;
  document.body.classList.remove("is-dragging");
  if (!event.dataTransfer.files.length) return;
  fileInput.files = event.dataTransfer.files;
  acceptSelectedFile();
});

updateProcessingNotice();
renderFindings([]);
updateInterface({cue: true, announce: false});

fetch("/api/health", {cache: "no-store"})
  .then((response) => response.json())
  .then((data) => {
    statusLabel.textContent = data.engine_status;
    modeNotes = data.mode_notes || modeNotes;
    maxFileBytes = data.max_file_bytes || 0;
    modeNote.textContent = modeNotes[modeSelect.value] || "";
    if (data.ner_active === false) {
      statusLabel.textContent = `${data.engine_status} · riconoscimento nomi ridotto`;
    }
  })
  .catch(() => {
    statusLabel.textContent = "Server non raggiungibile";
    showError("La web app locale non risponde. Riavvia OMISSIS e riprova.");
  });
