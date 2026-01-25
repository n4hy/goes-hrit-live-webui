const img = document.getElementById("img");
const imgsel = document.getElementById("imgsel");
const satsel = document.getElementById("satsel");
const evt = document.getElementById("eventtime");
const modesel = document.getElementById("modesel");

// Timelapse controls
const timelapseControls = document.getElementById("timelapse-controls");
const bandsel = document.getElementById("bandsel");
const durationsel = document.getElementById("durationsel");
const framesel = document.getElementById("framesel");
const generatebtn = document.getElementById("generatebtn");
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

let currentMode = "live";

function parseTime(fn) {
  const m = fn.match(/_(\d{8})T(\d{6})Z/);
  if (!m) return "";
  const d = m[1], t = m[2];
  return `${d.slice(0,4)}-${d.slice(4,6)}-${d.slice(6,8)} `
       + `${t.slice(0,2)}:${t.slice(2,4)}:${t.slice(4,6)} UTC`;
}

function show(sat, file) {
  img.src = `/goes/current/${sat}/${file}?t=${Date.now()}`;
  evt.textContent = parseTime(file);
}

function showGif(sat, band, hours) {
  const gifPath = `/goes/timelapse/${sat}_B${band}_${hours}h.gif?t=${Date.now()}`;
  const metaPath = `/goes/timelapse/${sat}_B${band}_${hours}h.json?t=${Date.now()}`;

  img.src = gifPath;

  fetch(metaPath)
    .then(r => r.ok ? r.json() : null)
    .then(meta => {
      if (meta) {
        evt.textContent = `Timelapse: ${meta.frames} frames over ${meta.hours}h | Generated: ${meta.generated_utc}`;
      } else {
        evt.textContent = `Timelapse: ${sat} Band ${band} (${hours}h)`;
      }
    })
    .catch(() => {
      evt.textContent = `Timelapse: ${sat} Band ${band} (${hours}h)`;
    });
}

function showFalseColor(sat, preset, rBand, gBand, bBand) {
  let imgName, metaName;

  if (preset === "custom") {
    imgName = `${sat}_custom_R${rBand}_G${gBand}_B${bBand}.png`;
  } else {
    imgName = `${sat}_${preset}.png`;
  }
  metaName = imgName.replace(".png", ".json");

  const imgPath = `/goes/falsecolor/${imgName}?t=${Date.now()}`;
  const metaPath = `/goes/falsecolor/${metaName}?t=${Date.now()}`;

  img.src = imgPath;

  fetch(metaPath)
    .then(r => r.ok ? r.json() : null)
    .then(meta => {
      if (meta) {
        let desc = `False Color: ${meta.preset}`;
        if (meta.preset === "custom") {
          desc += ` (R:CH${meta.r_band} G:CH${meta.g_band} B:CH${meta.b_band})`;
        }
        desc += ` | Source: ${meta.source_frame} | Generated: ${meta.generated_utc}`;
        evt.textContent = desc;
      } else {
        evt.textContent = `False Color: ${sat} - ${preset}`;
      }
    })
    .catch(() => {
      evt.textContent = `False Color: ${sat} - ${preset}`;
    });
}

async function listSats() {
  const html = await fetch("/goes/current/").then(r => r.text());
  const sats = [];
  const m = html.match(/href="(GOES-\d{2})\//g) || [];
  m.forEach(x => sats.push(x.replace('href="','').replace('/','').replace('"','')));
  return [...new Set(sats)].sort();
}

async function listImages(sat) {
  const html = await fetch(`/goes/current/${sat}/`).then(r => r.text());
  const files = (html.match(/G\d{2}_[^"]+\.png/g) || []);
  const seen = new Set();
  const out = [];
  files.forEach(f => { if (!seen.has(f)) { seen.add(f); out.push(f); } });
  return out;
}

async function reloadUI(autoPickNewest=true) {
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
    evt.textContent = "No satellites detected under /goes/current/";
    return;
  }

  const sat = satsel.value || sats[0];
  satsel.value = sat;

  const imgs = await listImages(sat);
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
      show(sat, imgsel.value);
    } else {
      img.src = "";
      evt.textContent = `No images found for ${sat}`;
    }
  } else if (currentMode === "timelapse") {
    loadTimelapseIfExists();
  } else if (currentMode === "falsecolor") {
    loadFalseColorIfExists();
  }
}

async function loadTimelapseIfExists() {
  const sat = satsel.value;
  const band = bandsel.value;
  const hours = durationsel.value;

  const metaPath = `/goes/timelapse/${sat}_B${band}_${hours}h.json?t=${Date.now()}`;
  try {
    const resp = await fetch(metaPath);
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

  let metaName;
  if (preset === "custom") {
    metaName = `${sat}_custom_R${rBand}_G${gBand}_B${bBand}.json`;
  } else {
    metaName = `${sat}_${preset}.json`;
  }

  const metaPath = `/goes/falsecolor/${metaName}?t=${Date.now()}`;
  try {
    const resp = await fetch(metaPath);
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

async function generateGif() {
  const sat = satsel.value;
  const band = bandsel.value;
  const hours = durationsel.value;
  const frames = framesel.value;

  if (!sat) {
    gifstatus.textContent = "No satellite selected";
    return;
  }

  generatebtn.disabled = true;
  gifstatus.textContent = "Generating...";

  try {
    const resp = await fetch("/goes/api/timelapse", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sat, band, hours, frames })
    });

    if (resp.ok) {
      const result = await resp.json();
      gifstatus.textContent = result.message || "Done!";
      setTimeout(() => {
        showGif(sat, band, hours);
        gifstatus.textContent = "";
      }, 500);
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

  if (!sat) {
    fcstatus.textContent = "No satellite selected";
    return;
  }

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
      setTimeout(() => {
        showFalseColor(sat, preset, rBand, gBand, bBand);
        fcstatus.textContent = "";
      }, 500);
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
modesel.onchange = () => {
  currentMode = modesel.value;

  // Hide all mode-specific controls
  timelapseControls.style.display = "none";
  falsecolorControls.style.display = "none";
  imgsel.style.display = "";

  if (currentMode === "live") {
    reloadUI(true);
  } else if (currentMode === "timelapse") {
    timelapseControls.style.display = "flex";
    imgsel.style.display = "none";
    loadTimelapseIfExists();
  } else if (currentMode === "falsecolor") {
    falsecolorControls.style.display = "flex";
    imgsel.style.display = "none";
    loadFalseColorIfExists();
  }
};

// False color preset change - show/hide custom RGB
fcpresetsel.onchange = () => {
  if (fcpresetsel.value === "custom") {
    customRgbDiv.style.display = "inline-flex";
  } else {
    customRgbDiv.style.display = "none";
  }
  loadFalseColorIfExists();
};

// Event handlers
satsel.onchange = async () => {
  if (currentMode === "live") {
    reloadUI(false);
  } else if (currentMode === "timelapse") {
    loadTimelapseIfExists();
  } else if (currentMode === "falsecolor") {
    loadFalseColorIfExists();
  }
};

imgsel.onchange = () => show(satsel.value, imgsel.value);

bandsel.onchange = () => loadTimelapseIfExists();
durationsel.onchange = () => loadTimelapseIfExists();
generatebtn.onclick = generateGif;

fcRBand.onchange = () => loadFalseColorIfExists();
fcGBand.onchange = () => loadFalseColorIfExists();
fcBBand.onchange = () => loadFalseColorIfExists();
fcgeneratebtn.onclick = generateFalseColor;

// SSE for live updates
const es = new EventSource("/goes/events");
es.addEventListener("update", async () => {
  if (currentMode === "live") {
    await reloadUI(true);
  }
});

// Initial load
reloadUI(true);
