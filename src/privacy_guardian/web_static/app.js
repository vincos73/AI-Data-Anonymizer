const source = document.querySelector("#source");
const result = document.querySelector("#result");
const findingsBody = document.querySelector("#findings-body");
const counter = document.querySelector("#counter");
const statusLabel = document.querySelector("#engine-status");
const modeSelect = document.querySelector("#mode-select");
const reportSummary = document.querySelector("#report-summary");
const reportChecklist = document.querySelector("#report-checklist");
const fileInput = document.querySelector("#file-input");
const fileStatus = document.querySelector("#file-status");
const saveButton = document.querySelector("#save-btn");
const workflowFileButton = document.querySelector(".workflow-button[for='file-input']");
let modeNotes = {
  standard: "Standard conserva iniziali e date: per testo da condividere con chatbot valuta Massima protezione.",
  maximum: "Massima protezione usa segnaposto completi e redige anche date comuni riconosciute.",
};
let maxFileBytes = 0;
let activeDocument = false;

async function postJson(path, text) {
  const response = await fetch(path, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    cache: "no-store",
    body: JSON.stringify({text, mode: modeSelect.value}),
  });

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "Richiesta non riuscita");
  }

  return response.json();
}

async function postDocument(path) {
  if (!fileInput.files.length) {
    throw new Error("Scegli un documento da anonimizzare.");
  }

  const formData = new FormData();
  formData.append("mode", modeSelect.value);
  formData.append("file", fileInput.files[0]);

  const response = await fetch(path, {
    method: "POST",
    cache: "no-store",
    body: formData,
  });

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "Documento non elaborato");
  }

  return response.json();
}

function renderFindings(findings) {
  findingsBody.replaceChildren();
  counter.textContent = `${findings.length} ${findings.length === 1 ? "elemento" : "elementi"}`;

  for (const finding of findings) {
    const row = document.createElement("tr");
    const cells = [
      finding.label || finding.entity_type,
      finding.preview,
      `${finding.start}-${finding.end}`,
      Number(finding.score).toFixed(2),
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

function renderReport(report) {
  reportChecklist.replaceChildren();
  if (report && report.summary) {
    reportSummary.textContent = report.summary;
    for (const item of report.checklist || []) {
      const checklistItem = document.createElement("li");
      checklistItem.textContent = item;
      reportChecklist.appendChild(checklistItem);
    }
    return;
  }

  reportSummary.textContent = modeNotes[modeSelect.value] || "";
}

function hasDocument() {
  return activeDocument && fileInput.files.length > 0;
}

function hasText() {
  return source.value.trim().length > 0;
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

function formatBytes(value) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "";
  }
  if (value % (1024 * 1024) === 0) {
    return `${value / (1024 * 1024)} MB`;
  }
  if (value % 1024 === 0) {
    return `${value / 1024} KB`;
  }
  return `${value} byte`;
}

function setBusy(isBusy) {
  document.querySelectorAll("button").forEach((button) => {
    button.disabled = isBusy;
  });
  if (isBusy) {
    workflowFileButton.classList.add("disabled");
  } else {
    workflowFileButton.classList.remove("disabled");
  }
}

async function analyze() {
  setBusy(true);
  try {
    const data = hasDocument() && !hasText()
      ? await postDocument("/api/analyze-document")
      : await postJson("/api/analyze", source.value);
    statusLabel.textContent = data.engine_status;
    if (data.filename) {
      fileStatus.textContent = `Documento analizzato: ${data.filename}`;
    }
    renderFindings(data.findings);
    renderReport(data.report);
  } catch (error) {
    statusLabel.textContent = error.message;
    reportSummary.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

async function anonymize() {
  setBusy(true);
  try {
    const data = hasDocument() && !hasText()
      ? await postDocument("/api/anonymize-document")
      : await postJson("/api/anonymize", source.value);
    if (data.content_base64) {
      downloadBase64(data.filename, data.content_base64, data.media_type);
      result.value = "";
      fileStatus.textContent = `Documento pronto: ${data.filename}`;
    } else {
      result.value = data.text;
    }
    statusLabel.textContent = data.engine_status;
    renderFindings(data.findings);
    renderReport(data.report);
  } catch (error) {
    statusLabel.textContent = error.message;
    reportSummary.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

document.querySelector("#analyze-btn").addEventListener("click", analyze);
document.querySelector("#anonymize-btn").addEventListener("click", anonymize);
document.querySelector("#clear-btn").addEventListener("click", () => {
  source.value = "";
  result.value = "";
  fileInput.value = "";
  activeDocument = false;
  fileStatus.textContent = "Nessun file selezionato";
  renderFindings([]);
  renderReport(null);
});
document.querySelector("#copy-btn").addEventListener("click", async () => {
  await navigator.clipboard.writeText(result.value);
});
saveButton.addEventListener("click", () => {
  if (result.value.trim()) {
    downloadText("testo_anonimizzato.txt", result.value);
  }
});

fetch("/api/health", {cache: "no-store"})
  .then((response) => response.json())
  .then((data) => {
    statusLabel.textContent = data.engine_status;
    modeNotes = data.mode_notes || modeNotes;
    maxFileBytes = data.max_file_bytes || 0;
    renderReport(null);
  })
  .catch(() => {
    statusLabel.textContent = "Server non raggiungibile.";
  });

fileInput.addEventListener("change", () => {
  if (!fileInput.files.length) {
    activeDocument = false;
    fileStatus.textContent = "Nessun documento caricato. Puoi incollare testo o trascinare un file nella finestra.";
    return;
  }

  const file = fileInput.files[0];
  const limit = maxFileBytes ? `, limite ${formatBytes(maxFileBytes)}` : "";
  activeDocument = true;
  source.value = "";
  result.value = "";
  if (file.name.toLowerCase().endsWith(".pdf")) {
    fileStatus.textContent = (
      `PDF caricato: ${file.name} (${formatBytes(file.size)}${limit}). ` +
      "L'export creerà un PDF rasterizzato con oscuramenti permanenti."
    );
  } else {
    fileStatus.textContent = `Documento caricato: ${file.name} (${formatBytes(file.size)}${limit})`;
  }
  renderFindings([]);
  renderReport(null);
});

modeSelect.addEventListener("change", () => {
  renderReport(null);
});

source.addEventListener("input", () => {
  if (source.value.trim() && activeDocument) {
    activeDocument = false;
    fileInput.value = "";
    fileStatus.textContent = "Testo incollato. Puoi pulire e caricare un documento quando vuoi.";
  }
});

document.addEventListener("dragover", (event) => {
  event.preventDefault();
});

document.addEventListener("drop", (event) => {
  event.preventDefault();
  if (!event.dataTransfer.files.length) {
    return;
  }
  fileInput.files = event.dataTransfer.files;
  fileInput.dispatchEvent(new Event("change"));
});
