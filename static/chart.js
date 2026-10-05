// Nuage de points SVG minimal. points : [{x, y, label, me}],
// x = thune (capacités financières), y = privilèges (entiers, éventuellement négatifs).
// onHover(point|null) est optionnel.

// Pas « rond » (1, 2, 5, 10, 20…) pour environ 4 à 6 graduations.
function niceStep(span) {
  const raw = span / 5, p = 10 ** Math.floor(Math.log10(raw));
  return [1, 2, 5, 10].map(m => m * p).find(s => s >= raw);
}

// Domaine qui contient 0, les valeurs et au moins [-minHalf, minHalf].
function niceDomain(values, minHalf) {
  let lo = Math.min(-minHalf, ...values), hi = Math.max(minHalf, ...values);
  const step = niceStep(hi - lo);
  return { lo: Math.floor(lo / step) * step, hi: Math.ceil(hi / step) * step, step };
}

function drawScatter(container, points, onHover) {
  const W = 600, H = 600, M = { t: 16, r: 16, b: 44, l: 48 };
  const iw = W - M.l - M.r, ih = H - M.t - M.b;
  const dx = niceDomain(points.map(p => p.x), 5);
  const dy = niceDomain(points.map(p => p.y), 18);
  const sx = v => M.l + ((v - dx.lo) / (dx.hi - dx.lo)) * iw;
  const sy = v => M.t + ih - ((v - dy.lo) / (dy.hi - dy.lo)) * ih;
  const ns = "http://www.w3.org/2000/svg";
  const el = (tag, attrs, parent) => {
    const e = document.createElementNS(ns, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    parent && parent.appendChild(e);
    return e;
  };

  container.innerHTML = "";
  container.classList.add("chart");
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img",
    "aria-label": "Nuage de points thune / privilèges" }, container);
  const tip = document.createElement("div");
  tip.className = "tip";
  container.appendChild(tip);

  for (let v = dx.lo; v <= dx.hi; v += dx.step) {
    el("line", { class: v === 0 ? "grid zero" : "grid", x1: sx(v), x2: sx(v), y1: M.t, y2: M.t + ih }, svg);
    el("text", { class: "tick", x: sx(v), y: M.t + ih + 16, "text-anchor": "middle" }, svg).textContent = v;
  }
  for (let v = dy.lo; v <= dy.hi; v += dy.step) {
    el("line", { class: v === 0 ? "grid zero" : "grid", x1: M.l, x2: M.l + iw, y1: sy(v), y2: sy(v) }, svg);
    el("text", { class: "tick", x: M.l - 8, y: sy(v) + 4, "text-anchor": "end" }, svg).textContent = v;
  }
  el("text", { class: "axis-label", x: M.l + iw / 2, y: H - 6, "text-anchor": "middle" }, svg).textContent =
    "Thune →";
  el("text", { class: "axis-label", x: 12, y: M.t + ih / 2, "text-anchor": "middle",
    transform: `rotate(-90 12 ${M.t + ih / 2})` }, svg).textContent = "Privilèges →";

  // « moi » dessiné en dernier pour rester au-dessus
  const sorted = [...points].sort((a, b) => (a.me ? 1 : 0) - (b.me ? 1 : 0));
  const dots = el("g", {}, svg);
  const hits = el("g", {}, svg);
  for (const p of sorted) {
    const cx = sx(p.x), cy = sy(p.y);
    el("circle", { class: "dot" + (p.me ? " me" : ""), cx, cy, r: p.me ? 9 : 6 }, dots);
    const hit = el("circle", { class: "hit", cx, cy, r: 14 }, hits);
    const show = () => {
      const k = svg.getBoundingClientRect().width / W;
      tip.textContent = (p.label ? p.label + " · " : "") + `thune ${p.x}, privilèges ${p.y}`;
      tip.style.left = cx * k + "px";
      tip.style.top = cy * k + "px";
      tip.style.display = "block";
      onHover && onHover(p);
    };
    const hide = () => { tip.style.display = "none"; onHover && onHover(null); };
    hit.addEventListener("pointerenter", show);
    hit.addEventListener("pointerleave", hide);
    hit.addEventListener("pointerdown", show);
  }
}
