const img = document.getElementById("img");
const imgsel = document.getElementById("imgsel");
const satsel = document.getElementById("satsel");
const evt = document.getElementById("eventtime");

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
}

satsel.onchange = async () => reloadUI(false);
imgsel.onchange = () => show(satsel.value, imgsel.value);

const es = new EventSource("/goes/events");
es.addEventListener("update", async () => {
  await reloadUI(true);
});

reloadUI(true);
