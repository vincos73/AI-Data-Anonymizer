const source = document.querySelector("#source");
const result = document.querySelector("#result");
const findingsBody = document.querySelector("#findings-body");
const counter = document.querySelector("#counter");
const statusLabel = document.querySelector("#engine-status");
const modeSelect = document.querySelector("#mode-select");
const reportSummary = document.querySelector("#report-summary");
let modeNotes = {
  standard: "Standard conserva iniziali e date: per testo da condividere con chatbot valuta Massima protezione.",
  maximum: "Massima protezione usa segnaposto completi e redige anche date comuni riconosciute.",
};

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

function renderFindings(findings) {
  findingsBody.replaceChildren();
  counter.textContent = `${findings.length} ${findings.length === 1 ? "elemento" : "elementi"}`;

  for (const finding of findings) {
    const row = document.createElement("tr");
    const cells = [
      finding.entity_type,
      finding.preview,
      `${finding.start}-${finding.end}`,
      Number(finding.score).toFixed(2),
      finding.source,
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
  if (report && report.summary) {
    reportSummary.textContent = report.summary;
    return;
  }

  reportSummary.textContent = modeNotes[modeSelect.value] || "";
}

function setBusy(isBusy) {
  document.querySelectorAll("button").forEach((button) => {
    button.disabled = isBusy;
  });
}

async function analyze() {
  setBusy(true);
  try {
    const data = await postJson("/api/analyze", source.value);
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

async function anonymize() {
  setBusy(true);
  try {
    const data = await postJson("/api/anonymize", source.value);
    result.value = data.text;
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
  renderFindings([]);
  renderReport(null);
});
document.querySelector("#copy-btn").addEventListener("click", async () => {
  await navigator.clipboard.writeText(result.value);
});

fetch("/api/health", {cache: "no-store"})
  .then((response) => response.json())
  .then((data) => {
    statusLabel.textContent = data.engine_status;
    modeNotes = data.mode_notes || modeNotes;
    renderReport(null);
  })
  .catch(() => {
    statusLabel.textContent = "Server non raggiungibile.";
  });

modeSelect.addEventListener("change", () => {
  renderReport(null);
});
