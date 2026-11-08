// 3D view and surface measurement with CesiumJS (loaded on demand from args.cesium_base_url).
//
// The Cesium ion access token is typed here and stays in this browser: it is sent only to
// Cesium ion, never to the Streamlit server, and saved in localStorage only if the user ticks
// "Remember". Google Photorealistic 3D Tiles are offered for viewing only: Google's Map Tiles
// API policies prohibit geodata extraction, so the Measure button works only with Cesium OSM
// Buildings + Cesium World Terrain, and Google tiles are shown only with Google's geocoder,
// as Cesium requires.
"use strict";

const TOKEN_KEY = "hubDesigner.cesiumIonToken";
let viewer = null;
let cesiumLoading = null;
let tileset = null;
let layerMode = "osm";
let hubGround = 0;
let ours = [];          // entities we drew, excluded from height sampling
let flown = false;

const $ = (id) => document.getElementById(id);

function savedToken() { try { return localStorage.getItem(TOKEN_KEY) || ""; } catch (e) { return ""; } }
function saveToken(t) { try { if (t) localStorage.setItem(TOKEN_KEY, t); else localStorage.removeItem(TOKEN_KEY); } catch (e) { /* storage blocked */ } }

function loadCesium() {
  if (window.Cesium) return Promise.resolve();
  if (cesiumLoading) return cesiumLoading;
  const base = args.cesium_base_url;
  window.CESIUM_BASE_URL = base;
  cesiumLoading = new Promise((resolve, reject) => {
    const css = document.createElement("link");
    css.rel = "stylesheet"; css.href = base + "Widgets/widgets.css";
    document.head.appendChild(css);
    const s = document.createElement("script");
    s.src = base + "Cesium.js";
    s.onload = resolve;
    s.onerror = () => { cesiumLoading = null; reject(new Error("could not load CesiumJS")); };
    document.head.appendChild(s);
  });
  return cesiumLoading;
}

function hasToken() { return !!$("ion-token").value.trim(); }

async function buildViewer() {
  if (viewer) { viewer.destroy(); viewer = null; tileset = null; }
  const token = $("ion-token").value.trim();
  if (token) Cesium.Ion.defaultAccessToken = token;
  viewer = new Cesium.Viewer("globe", {
    baseLayer: token ? undefined : false,
    geocoder: token ? Cesium.IonGeocodeProviderType.GOOGLE : false,
    animation: false, timeline: false, baseLayerPicker: false, homeButton: false, sceneModePicker: false,
    navigationHelpButton: false, fullscreenButton: false, infoBox: false, selectionIndicator: false,
  });
  viewer.scene.globe.depthTestAgainstTerrain = true;
  flown = false;
  if (!token) {
    status("3D view without a Cesium ion token: no terrain, imagery or buildings. Enter your token and Connect.");
    await drawScene();
    return;
  }
  try {
    viewer.terrainProvider = await Cesium.createWorldTerrainAsync();
  } catch (err) {
    status(`Cesium World Terrain failed to load (${err.message}). Check the token.`);
  }
  await setLayer($("layer3d").value);
}

async function setLayer(mode) {
  layerMode = mode;
  if (!viewer) return;
  if (tileset) { viewer.scene.primitives.remove(tileset); tileset = null; }
  if (!hasToken()) { await drawScene(); return; }
  status("Loading 3D buildings…");
  try {
    if (mode === "google") {
      tileset = await Cesium.createGooglePhotorealistic3DTileset({ onlyUsingWithGoogleGeocoder: true });
      viewer.scene.globe.show = false;  // the Google tiles include the ground
    } else {
      tileset = await Cesium.createOsmBuildingsAsync();
      viewer.scene.globe.show = true;
    }
    viewer.scene.primitives.add(tileset);
    status(mode === "google"
      ? "Google Photorealistic 3D Tiles: for viewing only. Switch to Cesium OSM Buildings to measure heights."
      : "Cesium OSM Buildings on Cesium World Terrain.");
  } catch (err) {
    status(`3D buildings failed to load (${err.message}). Is this asset added to your Cesium ion account?`);
  }
  $("measure").disabled = mode !== "osm";
  await drawScene();
}

async function groundAt(lat, lon) {
  const tp = viewer.terrainProvider;
  if (!tp || tp instanceof Cesium.EllipsoidTerrainProvider) return 0;
  const [c] = await Cesium.sampleTerrainMostDetailed(tp, [Cesium.Cartographic.fromDegrees(lon, lat)]);
  return c && Number.isFinite(c.height) ? c.height : 0;
}

const COLORS = { setback: "#e8eef5", building: "#c9b99a", apron: "#d9dde2", pad: "#4a7fb5", battery: "#d0573a" };

function ring(points) { return Cesium.Cartesian3.fromDegreesArray(points.flatMap(([lat, lon]) => [lon, lat])); }

// Offset a lat/lon by east/north metres (same flat projection as hub/geo.py).
function offset(lat, lon, east, north) {
  const R = 6371008.8;
  return [lat + (north / R) * 180 / Math.PI, lon + (east / (R * Math.cos(lat * Math.PI / 180))) * 180 / Math.PI];
}

let drawSeq = 0;
async function drawScene() {
  if (!viewer) return;
  const seq = ++drawSeq;
  if (!state.hub) { status("Place the hub on the 2D map first."); return; }
  const ground = await groundAt(state.hub[0], state.hub[1]);
  if (seq !== drawSeq) return;  // a newer redraw started while we waited for the terrain
  hubGround = ground;
  ours.forEach((e) => viewer.entities.remove(e));
  ours = [];
  const add = (spec) => { const e = viewer.entities.add(spec); ours.push(e); return e; };
  const ov = args.overlay || {};
  const clamp = { classificationType: Cesium.ClassificationType.BOTH };

  (ov.layout || []).forEach((s) => add({ name: s.name, polygon: Object.assign({ hierarchy: ring(s.polygon),
    material: Cesium.Color.fromCssColorString(COLORS[s.kind] || "#d9dde2").withAlpha(0.85) }, clamp) }));
  state.zones.forEach((z) => add({ name: z.name, polygon: Object.assign({ hierarchy: ring(z.polygon),
    material: Cesium.Color.fromCssColorString("#eb6834").withAlpha(0.25) }, clamp) }));
  state.obstacles.filter((o) => !String(o.source || "").startsWith("Cesium")).forEach((o) => {
    const h = Math.max(Number(o.height_m) || 0, 0.5);
    add({ name: o.name, position: Cesium.Cartesian3.fromDegrees(o.lon, o.lat, hubGround + h / 2),
      cylinder: { length: h, topRadius: Math.max((Number(o.width_m) || 1) / 2, 0.5),
        bottomRadius: Math.max((Number(o.width_m) || 1) / 2, 0.5), material: Cesium.Color.GRAY.withAlpha(0.6) } });
  });

  // Corridors: a ribbon that follows the climb profile, heights above the hub's ground.
  (ov.corridors || []).forEach((c) => {
    const prof = c.profile || [];
    if (prof.length < 2) return;
    const t = c.heading_deg * Math.PI / 180;
    const px = c.half_width_m * Math.cos(t), py = -c.half_width_m * Math.sin(t);
    const left = prof.map(([lat, lon, alt]) => [...offset(lat, lon, px, py), alt]);
    const right = prof.map(([lat, lon, alt]) => [...offset(lat, lon, -px, -py), alt]).reverse();
    const pts = left.concat(right).flatMap(([lat, lon, alt]) => [lon, lat, hubGround + alt]);
    add({ name: `Corridor ${c.heading_deg}`, polygon: { hierarchy: Cesium.Cartesian3.fromDegreesArrayHeights(pts),
      perPositionHeight: true, material: Cesium.Color.fromCssColorString("#2a78d6").withAlpha(0.35),
      outline: true, outlineColor: Cesium.Color.fromCssColorString("#2a78d6") } });
    add({ polyline: { positions: Cesium.Cartesian3.fromDegreesArrayHeights(prof.flatMap(([lat, lon, alt]) => [lon, lat, hubGround + alt])),
      width: 3, material: Cesium.Color.fromCssColorString("#2a78d6") } });
    const [elat, elon, ealt] = prof[prof.length - 1];
    add({ position: Cesium.Cartesian3.fromDegrees(elon, elat, hubGround + ealt + 3),
      label: { text: String(Math.round(c.heading_deg)).padStart(3, "0") + "°", font: "14px sans-serif",
        fillColor: Cesium.Color.WHITE, outlineColor: Cesium.Color.BLACK, outlineWidth: 3,
        style: Cesium.LabelStyle.FILL_AND_OUTLINE, disableDepthTestDistance: Number.POSITIVE_INFINITY } });
  });
  add({ position: Cesium.Cartesian3.fromDegrees(state.hub[1], state.hub[0], hubGround + 1),
    point: { pixelSize: 10, color: Cesium.Color.fromCssColorString("#2a78d6"), outlineColor: Cesium.Color.WHITE, outlineWidth: 2,
      disableDepthTestDistance: Number.POSITIVE_INFINITY },
    label: { text: "Hub", pixelOffset: new Cesium.Cartesian2(0, -18), font: "13px sans-serif", fillColor: Cesium.Color.WHITE,
      outlineColor: Cesium.Color.BLACK, outlineWidth: 3, style: Cesium.LabelStyle.FILL_AND_OUTLINE,
      disableDepthTestDistance: Number.POSITIVE_INFINITY } });

  if (!flown) {
    const centre = Cesium.Cartesian3.fromDegrees(state.hub[1], state.hub[0], hubGround);
    viewer.camera.lookAt(centre, new Cesium.HeadingPitchRange(0, Cesium.Math.toRadians(-35), 450));
    viewer.camera.lookAtTransform(Cesium.Matrix4.IDENTITY);
    flown = true;
  }
}

// Sample the 3D surface on a polar grid around the hub; heights relative to the hub's ground.
async function measure() {
  if (!viewer || !state.hub) { status("Place the hub, then open the 3D view."); return; }
  const testMode = window.__hubDesignerTest === true;  // set only by the automated browser test
  if (!testMode && (layerMode !== "osm" || !tileset)) {
    status("Measuring needs Cesium OSM Buildings (Google tiles are view-only). Choose it and Connect.");
    return;
  }
  const m = args.measure || {};
  const step = m.step_deg || 5, dr = m.step_m || 10, R = m.radius_m || 300, thr = m.threshold_m ?? 1;
  const carts = [], meta = [];
  for (let b = 0; b < 360; b += step) {
    for (let d = dr; d <= R; d += dr) {
      const t = b * Math.PI / 180;
      const [lat, lon] = offset(state.hub[0], state.hub[1], d * Math.sin(t), d * Math.cos(t));
      carts.push(Cesium.Cartographic.fromDegrees(lon, lat));
      meta.push([b, d]);
    }
  }
  status(`Measuring ${carts.length} points within ${R} m…`);
  $("measure").disabled = true;
  try {
    hubGround = await groundAt(state.hub[0], state.hub[1]);
    let terrain = carts.map(() => undefined);
    const tp = viewer.terrainProvider;
    if (tp && !(tp instanceof Cesium.EllipsoidTerrainProvider)) {
      const tc = carts.map((c) => c.clone());
      await Cesium.sampleTerrainMostDetailed(tp, tc);
      terrain = tc.map((c) => c.height);
    }
    const surface = await viewer.scene.sampleHeightMostDetailed(carts.map((c) => c.clone()), ours);
    const points = [];
    surface.forEach((c, i) => {
      const top = Math.max(c && Number.isFinite(c.height) ? c.height : -Infinity,
                           Number.isFinite(terrain[i]) ? terrain[i] : -Infinity);
      const h = top - hubGround;
      if (Number.isFinite(h) && h >= thr) points.push([meta[i][0], meta[i][1], Math.round(h * 10) / 10]);
    });
    commit({ cesium: { request_id: `${Date.now()}`, hub: state.hub, hub_ground_m: hubGround, step_deg: step,
      step_m: dr, radius_m: R, threshold_m: thr, sampled: carts.length, points } });
    status(`Measured ${carts.length} points; ${points.length} stand at least ${thr} m above the hub's ground.`);
  } catch (err) {
    status(`Measuring failed (${err.message}).`);
  } finally {
    $("measure").disabled = layerMode !== "osm";
  }
}

async function show3d(on) {
  $("v2d").classList.toggle("on", !on);
  $("v3d").classList.toggle("on", on);
  $("map").style.display = on ? "none" : "";
  $("tools").style.display = on ? "none" : "";
  $("globe").style.display = on ? "" : "none";
  $("cesium-controls").style.display = on ? "flex" : "none";
  setHeight();
  if (!on) { map.invalidateSize(); return; }
  if (!args.cesium_base_url) { status("3D view unavailable: no CesiumJS location configured."); return; }
  try {
    status("Loading CesiumJS…");
    await loadCesium();
    if (!viewer) await buildViewer(); else await drawScene();
  } catch (err) {
    status(`3D view failed (${err.message}).`);
  }
}

$("ion-token").value = savedToken();
$("ion-remember").checked = !!savedToken();
$("v2d").addEventListener("click", () => show3d(false));
$("v3d").addEventListener("click", () => show3d(true));
$("connect").addEventListener("click", async () => {
  saveToken($("ion-remember").checked ? $("ion-token").value.trim() : "");
  if (window.Cesium) await buildViewer();
});
$("layer3d").addEventListener("change", (e) => setLayer(e.target.value));
$("measure").addEventListener("click", measure);

// Redraw the 3D scene when Python sends new results.
window.addEventListener("message", (event) => {
  if (event.data && event.data.type === "streamlit:render" && viewer && $("globe").style.display !== "none") {
    drawScene();
  }
});
