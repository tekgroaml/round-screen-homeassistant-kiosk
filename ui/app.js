"use strict";
const MIN = 16, MAX = 30, RADIUS = 184, CIRCUMFERENCE = 2 * Math.PI * RADIUS;
const $ = (id) => document.getElementById(id);
const dial = document.querySelector(".dial"), control = $("control");
let target = 22, authoritativeTarget = 22, dragging = false, saving = false;
let writeTimer, revision = 0;
let writeChain = Promise.resolve();
const weather = { sunny: ["☀", "Clear"], clear: ["☀", "Clear"], "clear-night": ["☾", "Clear night"],
  cloudy: ["☁", "Cloudy"], partlycloudy: ["⛅", "Partly cloudy"], rainy: ["☂", "Rain"],
  pouring: ["☂", "Heavy rain"], snowy: ["❄", "Snow"], unavailable: ["—", "Unavailable"] };
function status(text, error = false) { $("status").textContent = text; $("status").classList.toggle("error", error); }
function drawTarget(value) {
  target = Math.max(MIN, Math.min(MAX, Math.round(value * 2) / 2));
  const fraction = (target - MIN) / (MAX - MIN), angle = (135 + fraction * 270) * Math.PI / 180;
  $("setpoint").textContent = target.toFixed(1);
  control.setAttribute("aria-valuenow", String(target));
  control.setAttribute("aria-valuetext", `${target.toFixed(1)} degrees Celsius`);
  $("progress").setAttribute("stroke-dasharray", `${fraction * CIRCUMFERENCE * .75} ${CIRCUMFERENCE}`);
  $("marker").setAttribute("cx", String(240 + Math.cos(angle) * RADIUS));
  $("marker").setAttribute("cy", String(240 + Math.sin(angle) * RADIUS));
}
for (let i = 0; i <= 56; i++) {
  const angle = (135 + i / 56 * 270) * Math.PI / 180, major = i % 4 === 0;
  const tick = document.createElementNS("http://www.w3.org/2000/svg", "line");
  for (const [attribute, value] of Object.entries({ x1: 240 + Math.cos(angle) * 198, y1: 240 + Math.sin(angle) * 198,
    x2: 240 + Math.cos(angle) * (major ? 209 : 204), y2: 240 + Math.sin(angle) * (major ? 209 : 204) })) tick.setAttribute(attribute, String(value));
  tick.setAttribute("class", major ? "tick major" : "tick"); $("ticks").append(tick);
}
async function request(path, options = {}) {
  const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch(path, { ...options, cache: "no-store", signal: controller.signal });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } finally { clearTimeout(timer); }
}
function displayState(state) {
  if (![state.temperature, state.humidity, state.target].every(Number.isFinite)) throw new Error("Invalid telemetry");
  $("ambient").textContent = state.temperature.toFixed(1); $("humidity").textContent = String(Math.round(state.humidity));
  const icon = weather[state.weather] || ["◌", String(state.weather).slice(0, 20)];
  $("weather-icon").textContent = icon[0]; $("weather-label").textContent = icon[1];
  authoritativeTarget = state.target;
  if (!dragging && !saving) drawTarget(state.target);
  if (!saving && !dragging) status(state.mode === "homeassistant" ? "HOME ASSISTANT · LIVE" : "DEMO · SIMULATED DATA");
}
async function poll() {
  try { displayState(await request("/api/state")); }
  catch (_) { status("OFFLINE · LAST KNOWN DATA", true); }
  finally { setTimeout(poll, 10000); }
}
function scheduleWrite() {
  clearTimeout(writeTimer); saving = true;
  const currentRevision = ++revision, value = target;
  status("SAVING TARGET");
  writeTimer = setTimeout(() => { writeChain = writeChain.then(async () => {
    if (currentRevision !== revision) return;
    try {
      const result = await request("/api/setpoint", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ target: value }) });
      if (currentRevision === revision) { authoritativeTarget = result.target; status(result.mode === "homeassistant" ? "TARGET SENT TO HA" : "DEMO TARGET SAVED"); }
    } catch (_) {
      if (currentRevision === revision) { if (!dragging) drawTarget(authoritativeTarget); status("TARGET NOT SAVED", true); }
    } finally { if (currentRevision === revision) saving = false; }
  }); }, 250);
}
function pointerValue(event) {
  const box = dial.getBoundingClientRect();
  let degrees = (Math.atan2(event.clientY - box.top - box.height / 2, event.clientX - box.left - box.width / 2) * 180 / Math.PI - 135 + 360) % 360;
  if (degrees > 270) degrees = degrees > 315 ? 0 : 270;
  drawTarget(MIN + degrees / 270 * (MAX - MIN));
}
dial.addEventListener("pointerdown", (event) => {
  if (event.button !== 0) return;
  dragging = true; dial.setPointerCapture(event.pointerId); pointerValue(event); control.focus();
});
dial.addEventListener("pointermove", (event) => { if (dragging) pointerValue(event); });
dial.addEventListener("pointerup", (event) => { if (dragging) { pointerValue(event); dragging = false; scheduleWrite(); } });
dial.addEventListener("pointercancel", () => { dragging = false; drawTarget(authoritativeTarget); });
control.addEventListener("keydown", (event) => {
  const changes = { ArrowUp: .5, ArrowRight: .5, ArrowDown: -.5, ArrowLeft: -.5 };
  if (event.key in changes || event.key === "Home" || event.key === "End") {
    event.preventDefault(); drawTarget(event.key === "Home" ? MIN : event.key === "End" ? MAX : target + changes[event.key]); scheduleWrite();
  }
});
function updateClock() {
  const date = new Date(); $("clock").textContent = date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  $("clock").dateTime = date.toISOString();
}
drawTarget(target); updateClock(); setInterval(updateClock, 1000); poll();
