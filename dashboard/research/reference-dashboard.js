const $ = (id) => document.getElementById(id);
const dimensions = ["condition", "age", "sex", "source"];
const number = new Intl.NumberFormat(navigator.language);
let catalog = null;
let result = null;
let requestId = 0;
let saved = [];
try {
  const stored = JSON.parse(localStorage.getItem("stegnoz-research-cohorts") || "[]");
  if (Array.isArray(stored)) saved = stored.filter((x) => x && x.filters).slice(0, 20);
} catch { /* Browser storage is optional. */ }

function setStatus(message) { $("status").textContent = message; }
function filters() { return Object.fromEntries(dimensions.map((key) => [key, $(key).value])); }
function labelFor(values) {
  return dimensions.filter((key) => values[key] !== "All").map((key) => values[key]).join(" · ") || "All available records";
}
function syncUrl(values, question = "") {
  const params = new URLSearchParams();
  dimensions.forEach((key) => { if (values[key] !== "All") params.set(key, values[key]); });
  if (question) params.set("q", question);
  history.replaceState(null, "", "/dashboard" + (params.size ? "?" + params : "") + location.hash);
}
function option(select, value) {
  const el = document.createElement("option");
  el.value = value;
  el.textContent = value;
  select.append(el);
}
function node(tag, className = "", text = "") {
  const el = document.createElement(tag);
  el.className = className;
  el.textContent = text;
  return el;
}
function navigate() {
  const page = ["explore", "saved", "methods"].includes(location.hash.slice(1)) ? location.hash.slice(1) : "explore";
  document.querySelectorAll(".console-page").forEach((el) => { el.hidden = el.id !== page; });
  document.querySelectorAll(".console-nav").forEach((el) => {
    el.classList.toggle("active", el.dataset.page === page);
    if (el.dataset.page === page) el.setAttribute("aria-current", "page");
    else el.removeAttribute("aria-current");
  });
  if (page === "saved") renderSaved();
}
window.addEventListener("hashchange", navigate);

function renderBars(target, groups) {
  target.replaceChildren();
  if (!groups.length) {
    target.append(node("p", "text-sm text-zinc-400", "No releasable breakdown. Small groups are withheld."));
    return;
  }
  const max = Math.max(...groups.map((x) => x.count), 1);
  groups.forEach((group, index) => {
    const row = node("div", "chart-row grid items-center gap-3 text-xs text-zinc-300");
    row.append(node("span", "truncate", group.label));
    const track = node("div", "h-3 rounded bg-zinc-800 overflow-hidden");
    const fill = node("div", "chart-fill h-full rounded bg-zinc-200");
    fill.style.width = `${(group.count / max) * 100}%`;
    fill.style.backgroundColor = ["#f4f4f5", "#d4d4d8", "#a1a1aa", "#71717a"][Math.min(index, 3)];
    track.append(fill);
    row.append(track, node("span", "text-right tabular-nums", number.format(group.count)));
    target.append(row);
  });
}
function renderAge(groups) {
  const target = $("age-chart");
  target.replaceChildren();
  if (!groups.length) {
    target.append(node("p", "text-sm text-zinc-400", "No releasable age breakdown."));
    return;
  }
  const max = Math.max(...groups.map((x) => x.count), 1);
  const ordered = catalog.ages.map((age) => groups.find((x) => x.label === age)).filter(Boolean);
  ordered.forEach((group, index) => {
    const column = node("div", "age-column flex-1 min-w-0 h-full flex flex-col justify-end items-center gap-2");
    column.append(node("span", "text-xs text-zinc-200 tabular-nums", number.format(group.count)));
    const bar = node("div", "age-fill w-full max-w-12 rounded-t bg-zinc-200");
    bar.style.height = `${Math.max(3, (group.count / max) * 78)}%`;
    bar.style.backgroundColor = ["#71717a", "#a1a1aa", "#f4f4f5", "#d4d4d8", "#52525b"][index % 5];
    column.append(bar, node("span", "text-[11px] text-zinc-400 whitespace-nowrap", group.label));
    target.append(column);
  });
}
function renderTable() {
  const target = $("table-body");
  target.replaceChildren();
  const groups = result.distributions[$("breakdown").value] || [];
  if (!groups.length) {
    const cell = node("td", "py-4 text-zinc-400", "No releasable breakdown. Small groups are withheld.");
    cell.colSpan = 3;
    const row = document.createElement("tr"); row.append(cell); target.append(row);
    return;
  }
  groups.forEach((group) => {
    const row = document.createElement("tr");
    row.append(node("td", "py-3 text-zinc-100", group.label),
      node("td", "py-3 text-right text-zinc-200", number.format(group.count)),
      node("td", "py-3 text-right text-zinc-400", `${((group.count / result.patients) * 100).toFixed(1)}%`));
    target.append(row);
  });
}
function render() {
  const data = result.distributions;
  dimensions.forEach((key) => { $("active-" + key).textContent = result.filters[key]; $(key).value = result.filters[key]; });
  $("minimum-cell").textContent = `${result.minimum_cell} profiles`;
  $("metric-profiles").textContent = result.suppressed ? `< ${result.minimum_cell}` : number.format(result.patients);
  $("metric-conditions").textContent = data.condition.length || "—";
  $("metric-sources").textContent = data.source.length || "—";
  $("metric-ages").textContent = data.age.length || "—";
  $("suppression-banner").hidden = !result.suppressed;
  $("result-note").textContent = result.note;
  renderBars($("condition-chart"), data.condition);
  renderAge(data.age);
  renderTable();
  $("export").disabled = !result.patients;
  $("save").disabled = !result.patients;
  setStatus(result.suppressed ? "Small cohort withheld." : `${result.patients} matching profiles. Results updated.`);
  if (window.gsap && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
    gsap.fromTo(".chart-fill", { scaleX: 0, transformOrigin: "left" }, { scaleX: 1, duration: .65, ease: "power3.out", overwrite: true });
    gsap.fromTo(".age-fill", { scaleY: 0, transformOrigin: "bottom" }, { scaleY: 1, duration: .65, ease: "power3.out", overwrite: true });
  }
}
async function query(params, question = "") {
  const current = ++requestId;
  $("run-query").disabled = true;
  $("error").hidden = true;
  try {
    const response = await fetch("/api/query", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(params) });
    const data = await response.json();
    if (current !== requestId) return;
    if (!response.ok) throw new Error(data.error || "Could not run this query.");
    result = data;
    render();
    syncUrl(data.filters, question);
  } catch (error) {
    if (current !== requestId) return;
    $("error").textContent = error.message + " Try a suggested question or choose filters.";
    $("error").hidden = false;
    setStatus("Query could not be completed.");
  } finally {
    if (current === requestId) $("run-query").disabled = false;
  }
}
function renderSaved() {
  $("saved-count").textContent = saved.length;
  const target = $("saved-list"); target.replaceChildren();
  if (!saved.length) target.append(node("p", "text-zinc-400", "No saved cohorts yet. Save an active cohort from the console."));
  saved.forEach((item, index) => {
    const card = node("div", "bg-surface-container-low rounded-xl p-5 border border-outline-variant/40 flex flex-wrap items-center justify-between gap-3");
    const copy = node("div"); copy.append(node("h2", "editorial-title text-xl text-white font-bold", item.name), node("p", "text-xs text-zinc-400 mt-1", item.mode + " dataset · Stored in this browser"));
    const actions = node("div", "flex gap-2");
    const open = node("button", "px-4 py-2 rounded-full bg-white text-zinc-950 font-semibold text-xs", "Open cohort");
    open.addEventListener("click", () => { dimensions.forEach((key) => { $(key).value = item.filters[key] || "All"; }); location.hash = "explore"; query({ ...filters() }); });
    const remove = node("button", "px-4 py-2 rounded-full bg-surface-container-high text-zinc-200 text-xs", "Remove");
    remove.addEventListener("click", () => { saved.splice(index, 1); persistSaved(); renderSaved(); });
    actions.append(open, remove); card.append(copy, actions); target.append(card);
  });
}
function persistSaved() {
  try { localStorage.setItem("stegnoz-research-cohorts", JSON.stringify(saved)); return true; }
  catch { setStatus("Browser storage is unavailable."); return false; }
}
function exportCsv() {
  if (!result?.patients) return;
  const rows = [["StegnoZ Research aggregate export"], ["Dataset", catalog.title], ["Mode", catalog.mode], ["Filters", labelFor(result.filters)], ["Matching profiles", result.patients], ["Method", result.note], [], ["Dimension", "Group", "Distinct profiles"]];
  Object.entries(result.distributions).forEach(([dimension, groups]) => {
    if (!groups.length) rows.push([dimension, "Breakdown withheld", ""]);
    groups.forEach((group) => rows.push([dimension, group.label, group.count]));
  });
  const csv = rows.map((row) => row.map((value) => '"' + String(value).replace(/"/g, '""') + '"').join(",")).join("\r\n");
  const url = URL.createObjectURL(new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a"); link.href = url; link.download = "stegnoz-cohort.csv"; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  setStatus("Aggregate CSV exported.");
}

$("query-form").addEventListener("submit", (event) => { event.preventDefault(); query({ ...filters(), question: $("question").value.trim() }, $("question").value.trim()); });
document.querySelectorAll(".suggestion").forEach((button) => button.addEventListener("click", () => { $("question").value = button.dataset.query; query({ ...filters(), question: button.dataset.query }, button.dataset.query); }));
dimensions.forEach((key) => $(key).addEventListener("change", () => { $("question").value = ""; query({ ...filters() }); }));
$("breakdown").addEventListener("change", () => { if (result) renderTable(); });
$("reset").addEventListener("click", () => { dimensions.forEach((key) => { $(key).value = "All"; }); $("question").value = ""; query({ ...filters() }); });
$("save").addEventListener("click", () => { if (!result?.patients) return; saved.unshift({ name: labelFor(result.filters), filters: result.filters, mode: catalog.mode }); saved = saved.slice(0, 20); if (persistSaved()) { renderSaved(); setStatus("Cohort saved in this browser."); } });
$("export").addEventListener("click", exportCsv);
$("share").addEventListener("click", async () => { try { await navigator.clipboard.writeText(location.href); setStatus("Cohort URL copied."); } catch { setStatus("Copy the URL from your browser address bar."); } });

async function init() {
  navigate();
  try {
    const response = await fetch("/api/catalog");
    if (!response.ok) throw new Error("Dataset unavailable.");
    catalog = await response.json();
    const values = { condition: catalog.conditions, age: catalog.ages, sex: catalog.sexes, source: catalog.sources };
    dimensions.forEach((key) => values[key].forEach((value) => option($(key), value)));
    const mode = catalog.mode === "demo" ? "Synthetic demo dataset" : "Sanitized release";
    $("dataset-tag").textContent = mode;
    $("sidebar-mode").textContent = mode;
    $("dataset-title").textContent = catalog.title;
    $("dataset-detail").textContent = catalog.mode === "demo" ? "Deterministic synthetic data for local review. No patient release is loaded." : "Only sanitized files in the selected release manifest are used. Review the pipeline report and release audit before interpreting results.";
    const params = new URLSearchParams(location.search);
    dimensions.forEach((key) => { if (values[key].includes(params.get(key))) $(key).value = params.get(key); });
    $("question").value = params.get("q") || "";
    await query({ ...filters(), question: $("question").value }, $("question").value);
  } catch (error) {
    $("error").textContent = error.message;
    $("error").hidden = false;
    $("dataset-tag").textContent = "Dataset unavailable";
  }
}
init();
