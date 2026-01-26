// DOM Elements
const img = document.getElementById("img");
const imgsel = document.getElementById("imgsel");
const satsel = document.getElementById("satsel");
const sectorsel = document.getElementById("sectorsel");
const evt = document.getElementById("eventtime");
const modesel = document.getElementById("modesel");
const emwinContent = document.getElementById("emwin-content");

// History controls
const historyControls = document.getElementById("history-controls");
const histSelect = document.getElementById("hist-select");
const histInfo = document.getElementById("hist-info");
const histFirst = document.getElementById("hist-first");
const histPrev = document.getElementById("hist-prev");
const histNext = document.getElementById("hist-next");
const histLast = document.getElementById("hist-last");

// Timelapse controls
const timelapseControls = document.getElementById("timelapse-controls");
const bandsel = document.getElementById("bandsel");
const durationsel = document.getElementById("durationsel");
const framesel = document.getElementById("framesel");
const generatebtn = document.getElementById("generatebtn");
const downloadgif = document.getElementById("downloadgif");
const rejectbusted = document.getElementById("rejectbusted");
const gifstatus = document.getElementById("gifstatus");

// False color controls
const falsecolorControls = document.getElementById("falsecolor-controls");
const fcpresetsel = document.getElementById("fcpresetsel");
const customRgbDiv = document.getElementById("custom-rgb");
const fcRBand = document.getElementById("fc-r-band");
const fcGBand = document.getElementById("fc-g-band");
const fcBBand = document.getElementById("fc-b-band");
const fcgeneratebtn = document.getElementById("fcgeneratebtn");
const fcstatus = document.getElementById("fcstatus");

// EMWIN controls
const emwinControls = document.getElementById("emwin-controls");
const emwinRefresh = document.getElementById("emwin-refresh");
const emwinSelect = document.getElementById("emwin-select");
const emwinStatus = document.getElementById("emwin-status");

let currentMode = "live";
let historyFrames = [];
let historyIndex = 0;

// Utility functions
function parseTime(fn) {
  const m = fn.match(/_(\d{8})T(\d{6})Z/);
  if (!m) return "";
  const d = m[1], t = m[2];
  return `${d.slice(0,4)}-${d.slice(4,6)}-${d.slice(6,8)} ${t.slice(0,2)}:${t.slice(2,4)}:${t.slice(4,6)} UTC`;
}

function safeSector(sector) {
  return sector.replace(/ /g, "_");
}

function displaySector(sector) {
  return sector.replace(/_/g, " ");
}

// Show functions
function show(sat, sector, file) {
  const safeSec = safeSector(sector);
  img.src = `/goes/current/${sat}/${safeSec}/${file}?t=${Date.now()}`;
  img.style.display = "";
  emwinContent.style.display = "none";
  evt.textContent = parseTime(file);
}

function showHistorical(sat, sector, dir, file) {
  const safeSec = safeSector(sector);
  // Historical images are served via API
  img.src = `/goes/api/history/image?sat=${encodeURIComponent(sat)}&sector=${encodeURIComponent(safeSec)}&dir=${encodeURIComponent(dir)}&file=${encodeURIComponent(file)}&t=${Date.now()}`;
  img.style.display = "";
  emwinContent.style.display = "none";
  evt.textContent = `Historical: ${dir} | ${parseTime(file)}`;
}

function showGif(sat, band, hours) {
  const gifUrl = `/goes/timelapse/${sat}_B${band}_${hours}h.gif`;
  img.src = `${gifUrl}?t=${Date.now()}`;
  img.style.display = "";
  emwinContent.style.display = "none";

  // Set up download button
  downloadgif.href = gifUrl;
  downloadgif.download = `${sat}_B${band}_${hours}h.gif`;
  downloadgif.style.display = "inline";

  fetch(`/goes/timelapse/${sat}_B${band}_${hours}h.json?t=${Date.now()}`)
    .then(r => r.ok ? r.json() : null)
    .then(meta => {
      if (meta) {
        evt.textContent = `Timelapse: ${meta.frames} frames over ${meta.hours}h | Generated: ${meta.generated_utc}`;
      } else {
        evt.textContent = `Timelapse: ${sat} Band ${band} (${hours}h)`;
      }
    })
    .catch(() => evt.textContent = `Timelapse: ${sat} Band ${band} (${hours}h)`);
}

function showFalseColor(sat, preset, rBand, gBand, bBand) {
  let imgName = preset === "custom"
    ? `${sat}_custom_R${rBand}_G${gBand}_B${bBand}.png`
    : `${sat}_${preset}.png`;

  img.src = `/goes/falsecolor/${imgName}?t=${Date.now()}`;
  img.style.display = "";
  emwinContent.style.display = "none";

  const metaName = imgName.replace(".png", ".json");
  fetch(`/goes/falsecolor/${metaName}?t=${Date.now()}`)
    .then(r => r.ok ? r.json() : null)
    .then(meta => {
      if (meta) {
        let desc = `False Color: ${meta.preset}`;
        if (meta.preset === "custom") desc += ` (R:CH${meta.r_band} G:CH${meta.g_band} B:CH${meta.b_band})`;
        desc += ` | Source: ${meta.source_frame} | Generated: ${meta.generated_utc}`;
        evt.textContent = desc;
      } else {
        evt.textContent = `False Color: ${sat} - ${preset}`;
      }
    })
    .catch(() => evt.textContent = `False Color: ${sat} - ${preset}`);
}

// List functions
async function listSats() {
  try {
    const resp = await fetch("/goes/api/sectors");
    if (resp.ok) {
      const sectors = await resp.json();
      const sats = [...new Set(sectors.map(s => s.satellite))].sort();
      return sats;
    }
  } catch {}

  // Fallback to directory listing
  const html = await fetch("/goes/current/").then(r => r.text());
  const sats = [];
  const m = html.match(/href="(GOES-\d{2})\//g) || [];
  m.forEach(x => sats.push(x.replace('href="','').replace('/','').replace('"','')));
  return [...new Set(sats)].sort();
}

async function listSectors(sat) {
  try {
    const html = await fetch(`/goes/current/${sat}/`).then(r => r.text());
    const sectors = [];
    const m = html.match(/href="([^"]+)\//g) || [];
    m.forEach(x => {
      const sec = x.replace('href="','').replace('/','').replace('"','');
      if (sec && !sec.startsWith('.')) sectors.push(sec);
    });
    return [...new Set(sectors)];
  } catch {
    return ["Full_Disk"];
  }
}

async function listImages(sat, sector) {
  const safeSec = safeSector(sector);
  try {
    const html = await fetch(`/goes/current/${sat}/${safeSec}/`).then(r => r.text());
    const files = (html.match(/G\d{2}_[^"]+\.png/g) || []);
    const seen = new Set();
    const out = [];
    files.forEach(f => { if (!seen.has(f)) { seen.add(f); out.push(f); } });
    return out;
  } catch {
    return [];
  }
}

async function loadHistory() {
  const sat = satsel.value;
  const sector = displaySector(sectorsel.value);

  try {
    const resp = await fetch(`/goes/api/history?sat=${encodeURIComponent(sat)}&sector=${encodeURIComponent(sector)}&limit=100`);
    if (resp.ok) {
      historyFrames = await resp.json();
      histSelect.innerHTML = "";
      historyFrames.forEach((f, i) => {
        const o = document.createElement("option");
        o.value = i;
        o.text = f.dir;
        histSelect.appendChild(o);
      });
      historyIndex = 0;
      if (historyFrames.length > 0) {
        showHistoryFrame(0);
      } else {
        evt.textContent = "No historical frames available";
        img.src = "";
      }
    }
  } catch (e) {
    evt.textContent = `Error loading history: ${e.message}`;
  }
}

function showHistoryFrame(index) {
  if (index < 0 || index >= historyFrames.length) return;
  historyIndex = index;
  histSelect.value = index;

  const frame = historyFrames[index];
  const sat = satsel.value;
  const sector = displaySector(sectorsel.value);

  // Pick the first available band image
  const band = frame.bands[0] || 13;
  const satNum = sat.replace("GOES-", "");
  const file = `G${satNum}_${band}_${frame.dir.replace(/-/g, "").replace(/_/g, "").replace("T", "T").slice(0,8)}T${frame.dir.slice(11).replace(/-/g, "")}Z.png`;

  // Actually, we need to construct the filename from the dir
  // Dir format: 2026-01-25_15-30-21
  // File format: G19_13_20260125T153021Z.png
  const dirParts = frame.dir.split("_");
  const datePart = dirParts[0].replace(/-/g, "");
  const timePart = dirParts[1].replace(/-/g, "");
  const imgFile = `G${satNum}_${band}_${datePart}T${timePart}Z.png`;

  // Use the API endpoint
  const safeSec = safeSector(sector);
  img.src = `/goes/api/history/image?sat=${encodeURIComponent(sat)}&sector=${encodeURIComponent(safeSec)}&dir=${encodeURIComponent(frame.dir)}&file=${encodeURIComponent(imgFile)}&t=${Date.now()}`;
  img.style.display = "";
  emwinContent.style.display = "none";

  histInfo.textContent = `Frame ${index + 1} of ${historyFrames.length}`;
  evt.textContent = `Historical: ${frame.dir} | Bands: ${frame.bands.join(", ")}`;
}

// EMWIN functions
async function loadEmwinList() {
  emwinStatus.textContent = "Loading...";
  try {
    const resp = await fetch("/goes/api/emwin?limit=50");
    if (resp.ok) {
      const data = await resp.json();
      emwinSelect.innerHTML = "";
      if (data.products.length === 0) {
        const o = document.createElement("option");
        o.text = "No EMWIN products found";
        emwinSelect.appendChild(o);
        emwinStatus.textContent = "No products";
      } else {
        data.products.forEach(p => {
          const o = document.createElement("option");
          o.value = p.path;
          o.text = p.name;
          emwinSelect.appendChild(o);
        });
        emwinStatus.textContent = `${data.products.length} products`;
        loadEmwinProduct(data.products[0].path);
      }
    }
  } catch (e) {
    emwinStatus.textContent = `Error: ${e.message}`;
  }
}

async function loadEmwinProduct(path) {
  if (!path) return;
  try {
    const resp = await fetch(`/goes/api/emwin/read?path=${encodeURIComponent(path)}`);
    if (resp.ok) {
      const data = await resp.json();
      emwinContent.textContent = data.content;
      emwinContent.style.display = "";
      img.style.display = "none";
      evt.textContent = `EMWIN: ${path}`;
    }
  } catch (e) {
    emwinContent.textContent = `Error loading: ${e.message}`;
  }
}

// Main UI reload
async function reloadUI(autoPickNewest = true) {
  // Save current selections before clearing
  const prevSat = satsel.value;
  const prevSector = sectorsel.value;

  const sats = await listSats();
  satsel.innerHTML = "";
  sats.forEach(s => {
    const o = document.createElement("option");
    o.value = s; o.text = s;
    satsel.appendChild(o);
  });

  if (sats.length === 0) {
    imgsel.innerHTML = "";
    img.src = "";
    evt.textContent = "No satellites detected";
    return;
  }

  // Restore satellite selection if still valid
  const sat = (prevSat && sats.includes(prevSat)) ? prevSat : sats[0];
  satsel.value = sat;

  // Load sectors for this satellite
  const sectors = await listSectors(sat);
  sectorsel.innerHTML = "";
  sectors.forEach(s => {
    const o = document.createElement("option");
    o.value = s;
    o.text = displaySector(s);
    sectorsel.appendChild(o);
  });

  // Restore sector selection if still valid
  const sector = (prevSector && sectors.includes(prevSector)) ? prevSector : sectors[0];
  sectorsel.value = sector;

  const imgs = await listImages(sat, sector);
  imgsel.innerHTML = "";
  imgs.forEach(f => {
    const o = document.createElement("option");
    o.value = f; o.text = f;
    imgsel.appendChild(o);
  });

  if (currentMode === "live") {
    if (imgs.length > 0) {
      if (autoPickNewest) {
        const sorted = [...imgs].sort().reverse();
        imgsel.value = sorted[0];
      }
      show(sat, sector, imgsel.value);
    } else {
      img.src = "";
      evt.textContent = `No images found for ${sat} ${displaySector(sector)}`;
    }
  } else if (currentMode === "history") {
    loadHistory();
  } else if (currentMode === "timelapse") {
    loadTimelapseIfExists();
  } else if (currentMode === "falsecolor") {
    loadFalseColorIfExists();
  } else if (currentMode === "emwin") {
    loadEmwinList();
  }
}

async function loadTimelapseIfExists() {
  const sat = satsel.value;
  const band = bandsel.value;
  const hours = durationsel.value;

  try {
    const resp = await fetch(`/goes/timelapse/${sat}_B${band}_${hours}h.json?t=${Date.now()}`);
    if (resp.ok) {
      showGif(sat, band, hours);
      gifstatus.textContent = "";
    } else {
      img.src = "";
      evt.textContent = "No timelapse available. Click Generate GIF to create one.";
    }
  } catch {
    img.src = "";
    evt.textContent = "No timelapse available. Click Generate GIF to create one.";
  }
}

async function loadFalseColorIfExists() {
  const sat = satsel.value;
  const preset = fcpresetsel.value;
  const rBand = fcRBand.value;
  const gBand = fcGBand.value;
  const bBand = fcBBand.value;

  let metaName = preset === "custom"
    ? `${sat}_custom_R${rBand}_G${gBand}_B${bBand}.json`
    : `${sat}_${preset}.json`;

  try {
    const resp = await fetch(`/goes/falsecolor/${metaName}?t=${Date.now()}`);
    if (resp.ok) {
      showFalseColor(sat, preset, rBand, gBand, bBand);
      fcstatus.textContent = "";
    } else {
      img.src = "";
      evt.textContent = "No false color image available. Click Generate to create one.";
    }
  } catch {
    img.src = "";
    evt.textContent = "No false color image available. Click Generate to create one.";
  }
}

// Generation functions
async function generateGif() {
  const sat = satsel.value;
  const band = bandsel.value;
  const hours = durationsel.value;
  const frames = framesel.value;
  const reject_bad = rejectbusted.checked;

  if (!sat) { gifstatus.textContent = "No satellite selected"; return; }

  generatebtn.disabled = true;
  gifstatus.textContent = "Generating...";

  try {
    const resp = await fetch("/goes/api/timelapse", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sat, band, hours, frames, reject_bad })
    });

    if (resp.ok) {
      const result = await resp.json();
      gifstatus.textContent = result.message || "Done!";
      setTimeout(() => { showGif(sat, band, hours); gifstatus.textContent = ""; }, 500);
    } else {
      const err = await resp.text();
      gifstatus.textContent = `Error: ${err}`;
    }
  } catch (e) {
    gifstatus.textContent = `Error: ${e.message}`;
  } finally {
    generatebtn.disabled = false;
  }
}

async function generateFalseColor() {
  const sat = satsel.value;
  const preset = fcpresetsel.value;
  const rBand = fcRBand.value;
  const gBand = fcGBand.value;
  const bBand = fcBBand.value;

  if (!sat) { fcstatus.textContent = "No satellite selected"; return; }

  fcgeneratebtn.disabled = true;
  fcstatus.textContent = "Generating...";

  try {
    const body = { sat, preset };
    if (preset === "custom") {
      body.r_band = rBand;
      body.g_band = gBand;
      body.b_band = bBand;
    }

    const resp = await fetch("/goes/api/falsecolor", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });

    if (resp.ok) {
      const result = await resp.json();
      fcstatus.textContent = result.message || "Done!";
      setTimeout(() => { showFalseColor(sat, preset, rBand, gBand, bBand); fcstatus.textContent = ""; }, 500);
    } else {
      const err = await resp.text();
      fcstatus.textContent = `Error: ${err}`;
    }
  } catch (e) {
    fcstatus.textContent = `Error: ${e.message}`;
  } finally {
    fcgeneratebtn.disabled = false;
  }
}

// Mode switching
function hideAllControls() {
  historyControls.style.display = "none";
  timelapseControls.style.display = "none";
  falsecolorControls.style.display = "none";
  emwinControls.style.display = "none";
  downloadgif.style.display = "none";
  imgsel.style.display = "";
  sectorsel.style.display = "";
  img.style.display = "";
  emwinContent.style.display = "none";
}

modesel.onchange = () => {
  currentMode = modesel.value;
  hideAllControls();

  if (currentMode === "live") {
    reloadUI(true);
  } else if (currentMode === "history") {
    historyControls.style.display = "flex";
    imgsel.style.display = "none";
    loadHistory();
  } else if (currentMode === "timelapse") {
    timelapseControls.style.display = "flex";
    imgsel.style.display = "none";
    sectorsel.style.display = "none";
    loadTimelapseIfExists();
  } else if (currentMode === "falsecolor") {
    falsecolorControls.style.display = "flex";
    imgsel.style.display = "none";
    sectorsel.style.display = "none";
    loadFalseColorIfExists();
  } else if (currentMode === "emwin") {
    emwinControls.style.display = "flex";
    imgsel.style.display = "none";
    sectorsel.style.display = "none";
    img.style.display = "none";
    emwinContent.style.display = "";
    loadEmwinList();
  }
};

// Event handlers
satsel.onchange = () => reloadUI(currentMode === "live");
sectorsel.onchange = () => {
  if (currentMode === "live") {
    reloadUI(true);
  } else if (currentMode === "history") {
    loadHistory();
  }
};
imgsel.onchange = () => show(satsel.value, sectorsel.value, imgsel.value);

// History navigation
histSelect.onchange = () => showHistoryFrame(parseInt(histSelect.value));
histFirst.onclick = () => showHistoryFrame(historyFrames.length - 1);
histPrev.onclick = () => showHistoryFrame(historyIndex + 1);
histNext.onclick = () => showHistoryFrame(historyIndex - 1);
histLast.onclick = () => showHistoryFrame(0);

// Timelapse
bandsel.onchange = () => loadTimelapseIfExists();
durationsel.onchange = () => loadTimelapseIfExists();
generatebtn.onclick = generateGif;

// False color
fcpresetsel.onchange = () => {
  customRgbDiv.style.display = fcpresetsel.value === "custom" ? "inline-flex" : "none";
  loadFalseColorIfExists();
};
fcRBand.onchange = () => loadFalseColorIfExists();
fcGBand.onchange = () => loadFalseColorIfExists();
fcBBand.onchange = () => loadFalseColorIfExists();
fcgeneratebtn.onclick = generateFalseColor;

// EMWIN
emwinRefresh.onclick = loadEmwinList;
emwinSelect.onchange = () => loadEmwinProduct(emwinSelect.value);

// SSE for live updates
const es = new EventSource("/goes/events");
let lastUpdateTime = Date.now();

es.addEventListener("update", async () => {
  lastUpdateTime = Date.now();
  if (currentMode === "live") {
    await reloadUI(true);
  }
});

// Fallback refresh if no updates for 15 minutes (live mode only)
const STALE_TIMEOUT = 15 * 60 * 1000; // 15 minutes
setInterval(() => {
  if (currentMode === "live" && (Date.now() - lastUpdateTime) > STALE_TIMEOUT) {
    console.log("No updates for 15 minutes, forcing refresh");
    lastUpdateTime = Date.now(); // Reset to avoid rapid retries
    reloadUI(true);
  }
}, 60 * 1000); // Check every minute

// Initial load
reloadUI(true);
