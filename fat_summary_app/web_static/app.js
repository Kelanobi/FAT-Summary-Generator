const steps = ["import", "review", "observations", "pictures", "preview"];

const state = {
  session: "",
  values: {},
  pdf: null,
  pictures: Array.from({ length: 4 }, () => ({ file: null, caption: "" })),
  step: "import",
  unlocked: 0,
  previewUrl: "",
  outputUrl: "",
  page: 1,
  pages: 1,
  filename: "Qualitrol_FAT_Summary.pdf",
};

const labels = {
  system_variant: "System Variant",
  readiness_posture: "Readiness",
  "project.project_name": "Project",
  "project.substation": "Substation",
  "project.customer": "Customer",
  "project.country": "Country",
  "project.voltage": "Voltage",
  "project.contract_number": "Contract No.",
  "project.manufacturing_number": "Manufacturing No.",
  "equipment.system_type": "System Type",
  "equipment.equipment": "Equipment",
  "equipment.equipment_tag": "Equipment Tag",
  "equipment.ocu_model": "OCU / Sensor Scope",
  "equipment.ocu_channel_count": "OCU Channel",
  "equipment.operating_frequency": "Frequency",
  "equipment.number_of_ocus": "OCU / GDM Unit Count",
  "equipment.sensor_count": "Sensor Count",
  "equipment.gdm_module_count": "GDM Module Count",
  "fat_context.document_no": "Document No.",
  "fat_context.revision": "Revision",
  "fat_context.fat_date": "FAT Date",
  "fat_context.date_range": "Date Range",
  "fat_context.venue": "Venue",
  "fat_context.inspection_type": "Inspection Type",
  "fat_context.tester": "Tester",
  "fat_context.project_owner": "Project Owner",
  "test_coverage.detected_test_count": "Total Checks",
  "test_coverage.passed_count": "Passed",
  "test_coverage.failed_count": "Failed",
  "test_coverage.na_count": "N/A",
  "test_coverage.completion_percent": "Completion %",
  "final_checks.ups_result": "UPS / FINAL CHECKS result",
  "final_checks.ups_note": "UPS / FINAL CHECKS note",
};

const selectOptions = {
  "final_checks.ups_result": ["", "PASS", "FAIL"],
};

const $ = (id) => document.getElementById(id);

document.querySelectorAll(".step").forEach((button, index) => {
  button.addEventListener("click", () => {
    if (index <= state.unlocked) show(button.dataset.step);
  });
});

document.querySelectorAll("[data-back]").forEach((button) => {
  button.addEventListener("click", () => show(button.dataset.back));
});

$("pdfs").addEventListener("change", (event) => setPdf(event.target.files[0] || null));
$("replacePdf").addEventListener("click", () => $("pdfs").click());
$("removePdf").addEventListener("click", clearPdf);
$("extractBtn").addEventListener("click", extract);
$("saveReviewBtn").addEventListener("click", () => {
  collectValues();
  unlock("observations");
  setStatus("Review saved");
  show("observations");
});
$("observationsText").addEventListener("input", updateObservationCount);
$("saveObsBtn").addEventListener("click", () => {
  unlock("pictures");
  setStatus("Observations saved");
  show("pictures");
});
$("continuePreviewBtn").addEventListener("click", () => render(true));
$("previewBtn").addEventListener("click", () => render(true));
$("exportBtn").addEventListener("click", () => render(false));
$("prevPage").addEventListener("click", () => movePage(-1));
$("nextPage").addEventListener("click", () => movePage(1));
$("newBtn").addEventListener("click", startNew);

wireGlobalDropGuard();
wireDropzone($("pdfDrop"), (files) => setPdf(files[0] || null));
buildPictureCards();
updateButtons();

function show(name) {
  state.step = name;
  document.querySelectorAll(".page").forEach((page) => {
    const active = page.id === name;
    page.classList.toggle("active", active);
    page.hidden = !active;
  });
  document.querySelectorAll(".step").forEach((step, index) => {
    step.classList.toggle("active", step.dataset.step === name);
    step.classList.toggle("complete", index < state.unlocked);
    step.disabled = index > state.unlocked;
  });
  updateButtons();
}

function unlock(name) {
  state.unlocked = Math.max(state.unlocked, steps.indexOf(name));
}

function setStatus(text) {
  $("status").textContent = text;
}

function setPdf(file) {
  state.pdf = file;
  $("pdfs").value = "";
  $("fileCard").classList.toggle("hidden", !file);
  $("pdfName").textContent = file ? file.name : "";
  $("pdfSize").textContent = file ? formatSize(file.size) : "";
  $("fileTypeIcon").textContent = file ? fileTypeLabel(file) : "PDF";
  updateButtons();
}

function clearPdf() {
  state.pdf = null;
  $("fileCard").classList.add("hidden");
  $("pdfName").textContent = "";
  $("pdfSize").textContent = "";
  updateButtons();
}

async function extract() {
  if (!state.pdf) return;
  setStatus("Extracting...");
  toggleBusy($("extractBtn"), true);
  const form = new FormData();
  form.append("pdf", state.pdf);
  form.append("variant", $("variant").value);
  try {
    const data = await post("/extract", form);
    state.session = data.session;
    state.values = data.values;
    renderFields();
    unlock("review");
    setStatus("Extracted");
    show("review");
  } catch (error) {
    setStatus(`Extract failed: ${error.message}`);
  } finally {
    toggleBusy($("extractBtn"), false);
  }
}

function renderFields() {
  const root = $("fields");
  root.innerHTML = "";
  Object.entries(labels).forEach(([key, label]) => {
    const wrap = document.createElement("label");
    wrap.className = "field";
    const input = selectOptions[key] ? document.createElement("select") : document.createElement("input");
    if (!selectOptions[key]) input.type = "text";
    input.dataset.key = key;
    if (selectOptions[key]) {
      selectOptions[key].forEach((optionValue) => {
        const option = document.createElement("option");
        option.value = optionValue;
        option.textContent = optionValue || "Select";
        input.appendChild(option);
      });
    }
    input.value = normalizeFieldValue(key, state.values[key] ?? "");
    input.addEventListener("input", () => {
      state.values[key] = input.value;
      setStatus("Review edits pending");
    });
    wrap.append(label, input);
    root.appendChild(wrap);
  });
}

function normalizeFieldValue(key, value) {
  if (key === "final_checks.ups_result") {
    const normalized = String(value || "").trim().toUpperCase();
    if (normalized === "PASSED") return "PASS";
    if (normalized === "FAILED") return "FAIL";
    if (normalized === "PASS" || normalized === "FAIL") return normalized;
    return "";
  }
  return value;
}

function collectValues() {
  document.querySelectorAll("#fields input").forEach((input) => {
    state.values[input.dataset.key] = input.value;
  });
}

function updateObservationCount() {
  $("obsCount").textContent = `${$("observationsText").value.length} / 2000`;
}

function buildPictureCards() {
  const root = $("pictureGrid");
  root.innerHTML = "";
  state.pictures.forEach((picture, index) => {
    const card = document.createElement("div");
    card.className = "picture-card";
    card.innerHTML = `
      <label class="picture-drop">
      <input type="file" accept="image/jpeg,image/png">
        <span class="thumb">+</span>
        <strong>Picture ${index + 1}</strong>
      </label>
      <input class="caption" type="text" placeholder="Caption">
      <button class="ghost remove-picture" type="button">Remove</button>
    `;
    const fileInput = card.querySelector("input[type=file]");
    const caption = card.querySelector(".caption");
    fileInput.addEventListener("change", (event) => setPicture(index, event.target.files[0] || null, card));
    caption.addEventListener("input", () => {
      state.pictures[index].caption = caption.value;
    });
    card.querySelector(".remove-picture").addEventListener("click", () => removePicture(index, card));
    wireDropzone(card.querySelector(".picture-drop"), (files) => setPicture(index, files[0] || null, card));
    root.appendChild(card);
  });
  updatePictureCount();
}

function setPicture(index, file, card) {
  if (!file) return;
  state.pictures[index].file = file;
  const thumb = card.querySelector(".thumb");
  thumb.textContent = "";
  thumb.classList.add("has-image");
  if (file.type.startsWith("image/")) {
    thumb.style.backgroundImage = `url(${URL.createObjectURL(file)})`;
  } else {
    thumb.style.backgroundImage = "";
    thumb.textContent = "PDF";
  }
  updatePictureCount();
}

function removePicture(index, card) {
  state.pictures[index] = { file: null, caption: "" };
  card.querySelector("input[type=file]").value = "";
  card.querySelector(".caption").value = "";
  const thumb = card.querySelector(".thumb");
  thumb.classList.remove("has-image");
  thumb.style.backgroundImage = "";
  thumb.textContent = "+";
  updatePictureCount();
}

function updatePictureCount() {
  const count = state.pictures.filter((item) => item.file).length;
  $("pictureCount").textContent = `${count} of 4 pictures added`;
}

async function render(preview) {
  if (!state.session) {
    setStatus("Extract first");
    return;
  }
  collectValues();
  setStatus(preview ? "Preparing preview..." : "Generating PDF...");
  toggleBusy(preview ? $("continuePreviewBtn") : $("exportBtn"), true);
  const form = new FormData();
  form.append("session", state.session);
  form.append("values", JSON.stringify(state.values));
  form.append("observations", $("observationsText").value);
  state.pictures.forEach((picture, index) => {
    if (picture.file) {
      const slot = index + 1;
      form.append(`picture${slot}`, picture.file);
      form.append(`caption${slot}`, picture.caption || `Picture ${slot}`);
    }
  });
  try {
    const data = await post(preview ? "/preview" : "/export", form);
    state.pages = data.pages || 1;
    state.page = 1;
    state.filename = data.filename || state.filename;
    if (preview) {
      state.previewUrl = data.url;
      unlock("preview");
      show("preview");
      loadPreview();
      setStatus("Preview ready");
    } else {
      state.outputUrl = data.url;
      $("success").classList.remove("hidden");
      $("suggestedName").textContent = state.filename;
      $("saveLink").href = `${data.url}&download=1`;
      $("saveLink").download = state.filename;
      setStatus("PDF ready");
    }
  } catch (error) {
    setStatus(`${preview ? "Preview" : "Export"} failed: ${error.message}`);
  } finally {
    toggleBusy(preview ? $("continuePreviewBtn") : $("exportBtn"), false);
  }
}

function loadPreview() {
  if (!state.previewUrl) return;
  $("viewer").src = `${state.previewUrl}&t=${Date.now()}#page=${state.page}`;
  $("pageLabel").textContent = `Page ${state.page} of ${state.pages}`;
  $("prevPage").disabled = state.page <= 1;
  $("nextPage").disabled = state.page >= state.pages;
}

function movePage(delta) {
  state.page = Math.min(Math.max(state.page + delta, 1), state.pages);
  loadPreview();
}

function startNew() {
  state.session = "";
  state.values = {};
  state.pdf = null;
  state.pictures = Array.from({ length: 4 }, () => ({ file: null, caption: "" }));
  state.previewUrl = "";
  state.outputUrl = "";
  state.page = 1;
  state.pages = 1;
  state.unlocked = 0;
  $("fields").innerHTML = "";
  $("observationsText").value = "";
  $("viewer").src = "";
  $("success").classList.add("hidden");
  clearPdf();
  buildPictureCards();
  updateObservationCount();
  setStatus("Ready");
  show("import");
}

function wireDropzone(node, callback) {
  node.addEventListener("dragover", (event) => {
    event.preventDefault();
    event.stopPropagation();
    node.classList.add("dragging");
  });
  node.addEventListener("dragleave", () => node.classList.remove("dragging"));
  node.addEventListener("drop", (event) => {
    event.preventDefault();
    event.stopPropagation();
    node.classList.remove("dragging");
    callback([...event.dataTransfer.files]);
  });
}

function wireGlobalDropGuard() {
  window.addEventListener("dragover", (event) => {
    event.preventDefault();
  });
  window.addEventListener("drop", (event) => {
    event.preventDefault();
    const files = [...(event.dataTransfer?.files || [])];
    if (!files.length) return;
    if (state.step === "import") {
      const report = files.find(isReportFile);
      if (report) {
        setPdf(report);
        setStatus("File selected");
      }
      return;
    }
    if (state.step === "pictures") {
      const nextSlot = state.pictures.findIndex((item) => !item.file);
      const image = files.find((file) => file.type.startsWith("image/"));
      if (nextSlot >= 0 && image) {
        const card = document.querySelectorAll(".picture-card")[nextSlot];
        setPicture(nextSlot, image, card);
        setStatus("Picture added");
      }
    }
  });
}

function updateButtons() {
  $("extractBtn").disabled = !state.pdf;
  $("saveReviewBtn").disabled = !state.session;
  $("continuePreviewBtn").disabled = !state.session;
}

function toggleBusy(button, busy) {
  if (!button) return;
  button.disabled = busy;
  button.classList.toggle("busy", busy);
}

function formatSize(bytes) {
  if (bytes < 1024 * 1024) return `${Math.ceil(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function isReportFile(file) {
  const name = file.name.toLowerCase();
  return file.type === "application/pdf" || name.endsWith(".pdf") || name.endsWith(".docx");
}

function fileTypeLabel(file) {
  return file.name.toLowerCase().endsWith(".docx") ? "DOCX" : "PDF";
}

async function post(url, form) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 120000);
  let response;
  try {
    response = await fetch(url, { method: "POST", body: form, signal: controller.signal });
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error("Request timed out. Try again or restart the app.");
    }
    throw new Error("Local app server did not respond.");
  } finally {
    window.clearTimeout(timeout);
  }
  const data = await response.json();
  if (!response.ok) {
    setStatus(data.error || "Error");
    throw new Error(data.error || "Request failed");
  }
  return data;
}
