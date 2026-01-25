const img = document.getElementById("img");
const imgsel = document.getElementById("imgsel");
const satsel = document.getElementById("satsel");
const evt = document.getElementById("eventtime");
const modesel = document.getElementById("modesel");
const timelapseControls = document.getElementById("timelapse-controls");
const bandsel = document.getElementById("bandsel");
const durationsel = document.getElementById("durationsel");
const framesel = document.getElementById("framesel");
const generatebtn = document.getElementById("generatebtn");
const gifstatus = document.getElementById("gifstatus");

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

async function listAvailableGifs() {
  try {
    const html = await fetch("/goes/timelapse/").then(r => r.text());
    const gifs = (html.match(/GOES-\d{2}_B\d+_\d+h\.gif/g) || []);
    return [...new Set(gifs)];
  } catch {
    return [];
  }
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
  } else {
    // In timelapse mode, try to show existing GIF
    loadTimelapseIfExists();
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
      // Reload the timelapse
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

// Mode switching
modesel.onchange = () => {
  currentMode = modesel.value;
  if (currentMode === "timelapse") {
    timelapseControls.style.display = "flex";
    imgsel.style.display = "none";
    document.querySelector('label[for="imgsel"]')?.style.setProperty('display', 'none');
    loadTimelapseIfExists();
  } else {
    timelapseControls.style.display = "none";
    imgsel.style.display = "";
    document.querySelector('label[for="imgsel"]')?.style.setProperty('display', '');
    reloadUI(true);
  }
};

// Event handlers
satsel.onchange = async () => {
  if (currentMode === "live") {
    reloadUI(false);
  } else {
    loadTimelapseIfExists();
  }
};

imgsel.onchange = () => show(satsel.value, imgsel.value);

bandsel.onchange = () => loadTimelapseIfExists();
durationsel.onchange = () => loadTimelapseIfExists();
generatebtn.onclick = generateGif;

// SSE for live updates
const es = new EventSource("/goes/events");
es.addEventListener("update", async () => {
  if (currentMode === "live") {
    await reloadUI(true);
  }
});

// Initial load
reloadUI(true);
