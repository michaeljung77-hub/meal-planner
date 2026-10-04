"use strict";

const S = { state: null, page: "home", pantry: [], saveTimer: null };
const $ = (sel) => document.querySelector(sel);
const view = $("#view"), bar = $("#bar");

const STEP_ORDER = ["rate", "pantry", "ideas", "prepare", "review", "done"];
const VERDICTS = [
  ["loved", "\u{1F60D}", "Loved"], ["good", "\u{1F642}", "Good"],
  ["meh", "\u{1F610}", "Meh"], ["miss", "\u{1F44E}", "Miss"],
];
const EMOJI = { loved: "\u{1F60D}", good: "\u{1F642}", meh: "\u{1F610}", miss: "\u{1F44E}", not_cooked: "–" };

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function toast(msg, isErr = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast" + (isErr ? " err" : "");
  t.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (t.hidden = true), isErr ? 7000 : 2800);
}

function busy(on, text = "Working...", sub = "") {
  $("#busy").hidden = !on;
  $("#busyText").textContent = text;
  $("#busySub").textContent = sub;
}

async function api(path, body, { method, busyText, busySub } = {}) {
  if (busyText) busy(true, busyText, busySub);
  try {
    const res = await fetch(path, {
      method: method || (body !== undefined ? "POST" : "GET"),
      headers: { "Content-Type": "application/json" },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
    return data;
  } finally {
    if (busyText) busy(false);
  }
}

async function load() {
  S.state = await api("/api/state");
}

function go(page) {
  S.page = page;
  window.scrollTo(0, 0);
  render();
}

function setBar(html) {
  bar.hidden = !html;
  bar.innerHTML = html || "";
}

function setHeader(title, showBack, step) {
  $("#title").textContent = title;
  $("#backBtn").hidden = !showBack;
  const steps = $("#steps");
  if (step) {
    const order = STEP_ORDER.filter((s) => s !== "done");
    const idx = order.indexOf(step);
    steps.innerHTML = order.map((s, i) => `<span class="${i <= idx || step === "done" ? "on" : ""}"></span>`).join("");
    steps.hidden = false;
  } else steps.hidden = true;
}

$("#backBtn").onclick = async () => { await load(); go("home"); };

async function setStep(step) {
  await api("/api/plan/step", { step });
  S.state.week.step = step;
  window.scrollTo(0, 0);
  render();
}

// ------------------------------------------------------------------ render

function render() {
  const st = S.state;
  if (S.page === "plan" && st.week) return renderStep(st.week.step);
  if (S.page === "plan" && !st.week) S.page = "home";
  ({ home: renderHome, pantry: renderPantryPage, profile: renderProfile,
     settings: renderSettings, history: renderHistory, rate: renderRatePage,
     done: () => renderStep("done") }[S.page] || renderHome)();
}

function renderStep(step) {
  setHeader(
    { rate: "Rate last week", pantry: "Pantry check", ideas: "This week's ideas", prepare: "Recipes",
      review: "Review & shop", done: "All set" }[step], true, step);
  ({ rate: renderRate, pantry: renderPantryStep, ideas: renderIdeas, prepare: renderPrepare,
     review: renderReview, done: renderDone }[step])();
}

// -------------------------------------------------------------------- home

function renderHome() {
  setHeader("Meal Planner", false);
  const st = S.state;
  const missing = st.missing.length
    ? `<div class="warn">Some settings are still empty: <b>${st.missing.map(esc).join(", ")}</b>.
       Add them in CasaOS (app settings) and restart the app.</div>` : "";
  const toRate = st.to_rate.filter((m) => !m.rating).length;
  const last = st.last_week
    ? `<p class="muted small">Last plan: ${new Date(st.last_week.confirmed_at).toLocaleDateString()} &middot; ${st.last_week.meals} meals</p>` : "";
  view.innerHTML = `
    ${missing}
    <div class="hero">
      <h2>${st.week ? "Planning in progress" : "Ready when you are"}</h2>
      <p>${st.week ? "Pick up where you left off." : "Rate last week, check the pantry, pick meals, and everything lands on the Skylight."}</p>
      ${last}
      <button class="primary big" id="startBtn" style="margin-top:12px">${st.week ? "Continue planning" : "Start planning"}</button>
    </div>
    <div class="tile-grid">
      <button class="tile" data-go="rate"><span class="t">Rate meals</span><span class="s">${toRate ? toRate + " waiting" : "Change a verdict"}</span></button>
      <button class="tile" data-go="pantry"><span class="t">Pantry</span><span class="s">Staples & running low</span></button>
      <button class="tile" data-go="profile"><span class="t">Taste profile</span><span class="s">What the AI has learned</span></button>
      <button class="tile" data-go="history"><span class="t">History</span><span class="s">Past weeks</span></button>
      <button class="tile" data-go="settings"><span class="t">House rules</span><span class="s">Mix, times, connections</span></button>
      <a class="tile" href="${esc(st.mealie_url)}" target="_blank" style="text-decoration:none;color:inherit"><span class="t">Open Mealie</span><span class="s">Recipe library</span></a>
    </div>`;
  setBar("");
  $("#startBtn").onclick = async () => {
    S.state = await api("/api/plan/start", {});
    go("plan");
  };
  view.querySelectorAll("[data-go]").forEach((b) => (b.onclick = () => go(b.dataset.go)));
}

// ------------------------------------------------------------------ rating

function ratingCards() {
  const meals = S.state.to_rate;
  if (!meals.length) return `<p class="muted">Nothing to rate yet. After your first planned week, the meals show up here.</p>`;
  return meals.map((m) => `
    <div class="card" data-meal="${m.id}">
      <div class="row spread"><h3>${esc(m.name)}</h3>${m.link ? `<a class="small" href="${esc(m.link)}" target="_blank">Recipe</a>` : ""}</div>
      <div class="verdicts">
        ${VERDICTS.map(([k, e, l]) => `<button data-v="${k}" class="${m.rating === k ? "on" : ""}"><span class="e">${e}</span>${l}</button>`).join("")}
      </div>
      <div class="row spread" style="margin-top:8px">
        <input type="text" class="note" placeholder="Note, e.g. too spicy for Sebastian" value="${esc(m.note)}" style="flex:1">
        <button class="ghost small nc ${m.rating === "not_cooked" ? "pick-btn on" : ""}" data-v="not_cooked">Didn't cook</button>
      </div>
    </div>`).join("");
}

function wireRatings() {
  view.querySelectorAll("[data-meal]").forEach((card) => {
    const id = +card.dataset.meal;
    const meal = S.state.to_rate.find((m) => m.id === id);
    const save = async (rating) => {
      const note = card.querySelector(".note").value;
      await api(`/api/meals/${id}/rate`, { rating, note });
      meal.rating = rating; meal.note = note;
    };
    card.querySelectorAll("[data-v]").forEach((b) => (b.onclick = async () => {
      const v = meal.rating === b.dataset.v ? null : b.dataset.v;
      try { await save(v); } catch (e) { return toast(e.message, true); }
      card.querySelectorAll("[data-v]").forEach((x) => x.classList.toggle("on", x.dataset.v === v));
      card.querySelector(".nc").classList.toggle("pick-btn", v === "not_cooked");
    }));
    card.querySelector(".note").onchange = () => save(meal.rating).catch((e) => toast(e.message, true));
  });
}

function renderRate() {
  view.innerHTML = `<p class="muted">One tap per meal. This is how the planner learns your family's favorite flavors.</p>${ratingCards()}`;
  wireRatings();
  setBar(`<span class="grow info">${S.state.to_rate.filter((m) => m.rating).length}/${S.state.to_rate.length} rated</span>
          <button class="primary" id="next">Next: pantry</button>`);
  $("#next").onclick = () => setStep("pantry");
}

function renderRatePage() {
  setHeader("Rate meals", true);
  view.innerHTML = `<p class="muted">Recent meals. Tap again to clear a verdict.</p>${ratingCards()}`;
  wireRatings();
  setBar("");
}

// ------------------------------------------------------------------ pantry

async function pantryBody(withHint) {
  S.pantry = await api("/api/pantry");
  const cats = {};
  S.pantry.forEach((p) => (cats[p.category] = cats[p.category] || []).push(p));
  return `
    ${withHint ? `<p class="muted">Tap anything that's running low. It goes on this week's grocery list. Everything else is left off.</p>` : `<p class="muted">Your staples. Tap to mark running low; long-press an item to remove it.</p>`}
    ${Object.entries(cats).map(([c, items]) => `
      <div class="cat">${esc(c)}</div>
      <div class="chips">${items.map((p) => `<button class="chip ${p.low ? "on" : ""}" data-p="${p.id}">${esc(p.name)}</button>`).join("")}</div>`).join("")}
    <div class="card">
      <label>Add a staple</label>
      <div class="row"><input type="text" id="newStaple" placeholder="e.g. Coconut milk" style="flex:1"><button id="addStaple">Add</button></div>
    </div>`;
}

function wirePantry(rerender) {
  view.querySelectorAll("[data-p]").forEach((b) => {
    const id = +b.dataset.p;
    b.onclick = async () => {
      const p = S.pantry.find((x) => x.id === id);
      p.low = p.low ? 0 : 1;
      b.classList.toggle("on", !!p.low);
      api(`/api/pantry/${id}/low`, { low: !!p.low }).catch((e) => toast(e.message, true));
    };
    let t;
    b.addEventListener("touchstart", () => (t = setTimeout(async () => {
      if (confirm(`Remove "${b.textContent}" from your staples?`)) {
        await api(`/api/pantry/${id}`, undefined, { method: "DELETE" });
        rerender();
      }
    }, 700)), { passive: true });
    b.addEventListener("touchend", () => clearTimeout(t));
    b.addEventListener("touchmove", () => clearTimeout(t), { passive: true });
  });
  $("#addStaple").onclick = async () => {
    const name = $("#newStaple").value.trim();
    if (!name) return;
    await api("/api/pantry", { name, category: "Other" });
    rerender();
  };
}

async function renderPantryStep() {
  view.innerHTML = await pantryBody(true);
  wirePantry(renderPantryStep);
  const hasIdeas = S.state.ideas.some((i) => i.status !== "skipped");
  setBar(`<span class="grow info">${S.pantry.filter((p) => p.low).length} running low</span>
          <button class="primary" id="next">${hasIdeas ? "Next: ideas" : "Get ideas"}</button>`);
  $("#next").onclick = async () => {
    if (hasIdeas) return setStep("ideas");
    try {
      S.state = await api("/api/plan/ideas", { direction: "" },
        { busyText: "Cooking up ideas...", busySub: "Claude is reading your family's taste profile. This takes about a minute." });
      render();
    } catch (e) { toast(e.message, true); }
  };
}

async function renderPantryPage() {
  setHeader("Pantry", true);
  view.innerHTML = await pantryBody(false);
  wirePantry(renderPantryPage);
  setBar("");
}

// ------------------------------------------------------------------- ideas

function badgeRow(i) {
  const kind = { favorite: "Favorite", remix: "Remix", new: "New", wildcard: "Wildcard", ours: "Our idea" }[i.kind] || "";
  return `<div class="badges">
    ${i.adventure ? `<span class="badge b-${esc(i.adventure)}">${esc(i.adventure[0].toUpperCase() + i.adventure.slice(1))}</span>` : ""}
    ${kind ? `<span class="badge ${i.kind === "favorite" || i.kind === "ours" ? "b-fav" : ""}">${kind}</span>` : ""}
    ${i.cook_minutes ? `<span class="badge">${esc(i.cook_minutes)} min</span>` : ""}
    ${i.cuisine ? `<span class="badge">${esc(i.cuisine)}</span>` : ""}
  </div>`;
}

function ideaCard(i) {
  const picked = i.status === "picked";
  return `<div class="card ${picked ? "picked" : ""}" data-idea="${i.id}">
    ${badgeRow(i)}
    <h3>${esc(i.name)}</h3>
    <p>${esc(i.pitch)}</p>
    ${i.why ? `<p class="why">${esc(i.why)}</p>` : ""}
    ${i.kid_note ? `<div class="kid"><b>For Sebastian:</b> ${esc(i.kid_note)}</div>` : ""}
    <div class="row" style="margin-top:10px">
      <button class="pick-btn ${picked ? "on" : ""}" data-act="pick" style="flex:1">${picked ? "✓ Picked" : "Pick"}</button>
      ${i.kind !== "ours" ? `<button class="ghost" data-act="more">More like this</button>` : ""}
    </div>
  </div>`;
}

function renderIdeas() {
  const ideas = S.state.ideas.filter((i) => i.status !== "skipped");
  const weeknight = ideas.filter((i) => i.day_type !== "weekend" && i.kind !== "ours");
  const weekend = ideas.filter((i) => i.day_type === "weekend" && i.kind !== "ours");
  const ours = ideas.filter((i) => i.kind === "ours");
  view.innerHTML = `
    <div class="card">
      <label style="margin-top:0">Want a different direction?</label>
      <div class="row"><input type="text" id="direction" placeholder="e.g. more fish, something German" value="${esc(S.state.week.direction)}" style="flex:1">
      <button id="regen">New ideas</button></div>
      <p class="muted small">New ideas replace the ones you haven't picked. Picked meals stay.</p>
    </div>
    ${ours.length ? `<div class="cat">Our ideas</div>${ours.map(ideaCard).join("")}` : ""}
    <div class="cat">Weeknights</div>${weeknight.map(ideaCard).join("") || `<p class="muted">None in this batch.</p>`}
    <div class="cat">Weekend</div>${weekend.map(ideaCard).join("") || `<p class="muted">None in this batch.</p>`}
    <div class="card">
      <h3>Add our own idea</h3>
      <p class="muted small">Type a dish ("something with salmon") or paste a recipe link.</p>
      <div class="row"><input type="text" id="ownIdea" placeholder="Idea or https://..." style="flex:1"><button id="addOwn">Add</button></div>
    </div>`;
  const update = () => {
    const n = S.state.ideas.filter((i) => i.status === "picked").length;
    setBar(`<span class="grow info">${n} picked</span><button class="primary" id="next" ${n ? "" : "disabled"}>Next: recipes</button>`);
    $("#next").onclick = () => setStep("prepare");
  };
  update();
  view.querySelectorAll("[data-idea]").forEach((card) => {
    const id = +card.dataset.idea;
    const idea = S.state.ideas.find((i) => i.id === id);
    card.querySelector('[data-act="pick"]').onclick = async (ev) => {
      const picked = idea.status !== "picked";
      try { await api(`/api/ideas/${id}/pick`, { picked }); } catch (e) { return toast(e.message, true); }
      idea.status = picked ? "picked" : "new";
      card.classList.toggle("picked", picked);
      ev.target.classList.toggle("on", picked);
      ev.target.textContent = picked ? "✓ Picked" : "Pick";
      update();
    };
    const more = card.querySelector('[data-act="more"]');
    if (more) more.onclick = async () => {
      try {
        S.state = await api(`/api/ideas/${id}/more`, {}, { busyText: "Finding variations...", busySub: "About 30 seconds." });
        render();
        toast("3 variations added");
      } catch (e) { toast(e.message, true); }
    };
  });
  $("#regen").onclick = async () => {
    try {
      S.state = await api("/api/plan/ideas", { direction: $("#direction").value },
        { busyText: "Fresh ideas coming...", busySub: "About a minute." });
      window.scrollTo(0, 0);
      render();
    } catch (e) { toast(e.message, true); }
  };
  $("#addOwn").onclick = async () => {
    const text = $("#ownIdea").value.trim();
    if (!text) return;
    try {
      S.state = await api("/api/ideas/custom", { text }, { busyText: "Adding your idea..." });
      render();
      toast("Added and picked");
    } catch (e) { toast(e.message, true); }
  };
}

// ----------------------------------------------------------------- prepare

const SOURCES = [["web", "Real recipe"], ["ai", "Write one"], ["library", "Our library"]];

function prepCard(i) {
  const done = i.prep_status === "done", err = i.prep_status === "error";
  const sources = SOURCES.filter(([k]) => k !== "library" || i.library_slug);
  return `<div class="card" data-prep="${i.id}">
    ${badgeRow(i)}
    <div class="row" style="flex-wrap:nowrap;align-items:flex-start"><h3 style="flex:1">${esc(i.final_name || i.name)}</h3><button class="ghost small danger" data-act="drop" style="min-height:34px;padding:4px 10px">Remove</button></div>
    ${done ? "" : `
      <div class="seg">${sources.map(([k, l]) => `<button data-src="${k}" class="${i.source === k ? "on" : ""}">${l}</button>`).join("")}</div>
      <input type="text" class="tweaks" placeholder="Changes? e.g. less spicy, sheet-pan, swap chicken for pork" value="${esc(i.tweaks)}">`}
    <div class="status ${done ? "ok" : err ? "err" : ""}" data-status>
      ${done ? `✓ ${esc(i.prep_note)} &middot; <a href="${esc(i.link)}" target="_blank">View in Mealie</a> &middot; <a href="#" data-act="redo">Redo</a>` : err ? `⚠ ${esc(i.prep_note)}` : ""}
    </div>
  </div>`;
}

function renderPrepare() {
  const picked = S.state.ideas.filter((i) => i.status === "picked");
  view.innerHTML = `
    <p class="muted"><b>Real recipe</b> finds a proven recipe online and imports it into Mealie. <b>Write one</b> has Claude write it for you.
    Add changes and the recipe is adjusted before it's saved.</p>
    ${picked.map(prepCard).join("")}`;
  const update = () => {
    const p = S.state.ideas.filter((i) => i.status === "picked");
    const done = p.filter((i) => i.prep_status === "done").length;
    const all = p.length && done === p.length;
    setBar(`<span class="grow info">${done}/${p.length} ready</span>
      ${all ? `<button class="primary" id="grocery">Build grocery list</button>` : `<button class="primary" id="prep" ${p.length ? "" : "disabled"}>Prepare recipes</button>`}`);
    if (all) $("#grocery").onclick = buildGrocery;
    else $("#prep").onclick = prepareAll;
  };
  update();
  S.updatePrepBar = update;
  view.querySelectorAll("[data-prep]").forEach((card) => {
    const id = +card.dataset.prep;
    const idea = S.state.ideas.find((i) => i.id === id);
    const saveOpts = () => api(`/api/ideas/${id}/options`, { source: idea.source, tweaks: idea.tweaks }).catch((e) => toast(e.message, true));
    card.querySelectorAll("[data-src]").forEach((b) => (b.onclick = () => {
      idea.source = b.dataset.src;
      card.querySelectorAll("[data-src]").forEach((x) => x.classList.toggle("on", x === b));
      saveOpts();
    }));
    const tw = card.querySelector(".tweaks");
    if (tw) tw.onchange = () => { idea.tweaks = tw.value; saveOpts(); };
    card.querySelector('[data-act="drop"]').onclick = async () => {
      await api(`/api/ideas/${id}/pick`, { picked: false });
      idea.status = "new";
      renderPrepare();
    };
    const redo = card.querySelector('[data-act="redo"]');
    if (redo) redo.onclick = async (ev) => {
      ev.preventDefault();
      idea.prep_status = ""; idea.final_name = null;
      await api(`/api/ideas/${id}/options`, { source: idea.source, tweaks: idea.tweaks });
      renderPrepare();
    };
  });
}

async function prepareAll() {
  const todo = S.state.ideas.filter((i) => i.status === "picked" && i.prep_status !== "done");
  $("#prep").disabled = true;
  for (const idea of todo) {
    const card = view.querySelector(`[data-prep="${idea.id}"]`);
    const status = card.querySelector("[data-status]");
    status.className = "status";
    status.innerHTML = `<span class="spinner" style="width:16px;height:16px;border-width:3px;display:inline-block;vertical-align:middle;margin:0 6px 0 0"></span>${
      idea.source === "web" ? "Searching the web and importing..." : "Writing the recipe..."}`;
    card.scrollIntoView({ behavior: "smooth", block: "center" });
    try {
      const updated = await api(`/api/ideas/${idea.id}/prepare`, {});
      Object.assign(idea, updated);
    } catch (e) {
      idea.prep_status = "error"; idea.prep_note = e.message;
    }
    card.outerHTML = prepCard(idea);
  }
  renderPrepare();
  const failed = S.state.ideas.filter((i) => i.status === "picked" && i.prep_status === "error").length;
  if (failed) toast(`${failed} recipe(s) need another try. Switch to "Write one" or tap Prepare again.`, true);
}

async function buildGrocery() {
  try {
    S.state = await api("/api/plan/grocery", {}, { busyText: "Building the grocery list...", busySub: "Combining ingredients and checking your pantry." });
    window.scrollTo(0, 0);
    render();
  } catch (e) { toast(e.message, true); }
}

// ------------------------------------------------------------------ review

function saveGrocerySoon() {
  clearTimeout(S.saveTimer);
  S.saveTimer = setTimeout(() => api("/api/plan/grocery/save", S.state.grocery).catch(() => {}), 600);
}

function renderReview() {
  const meals = S.state.ideas.filter((i) => i.status === "picked" && i.prep_status === "done");
  const g = S.state.grocery || { aisles: [] };
  let count = 0;
  view.innerHTML = `
    <div class="card">
      <h3>This week's meals</h3>
      ${meals.map((m) => `<div class="item"><span class="name">${esc(m.final_name || m.name)}</span><a class="small" href="${esc(m.link)}" target="_blank">Recipe</a></div>`).join("")}
    </div>
    <p class="muted small">Tap &#10005; for anything you already have. Items marked <span class="flag">Publix/Ingles</span> are usually not at Aldi or Lidl.</p>
    ${g.aisles.map((a, ai) => `
      <div class="aisle"><div class="cat">${esc(a.aisle)}</div>
      ${a.items.map((it, ii) => { if (!it.removed) count++; return `
        <div class="item ${it.removed ? "removed" : ""}" data-a="${ai}" data-i="${ii}">
          <div class="name">${esc(it.item)}${it.qty ? ` <span class="muted">(${esc(it.qty)})</span>` : ""}${it.other_store ? `<span class="flag">Publix/Ingles</span>` : ""}
            ${it.used_in && it.used_in.length ? `<div class="used">${it.used_in.length > 1 ? `Used in ${it.used_in.length} meals: ` : ""}${esc(it.used_in.join(", "))}</div>` : ""}</div>
          <button class="ghost">${it.removed ? "Undo" : "✕"}</button>
        </div>`; }).join("")}</div>`).join("")}
    <div class="card">
      <label style="margin-top:0">Add an item</label>
      <div class="row"><input type="text" id="extra" placeholder="e.g. Coffee" style="flex:1"><button id="addExtra">Add</button></div>
    </div>`;
  view.querySelectorAll("[data-a]").forEach((row) => {
    row.querySelector("button").onclick = () => {
      const it = g.aisles[+row.dataset.a].items[+row.dataset.i];
      it.removed = !it.removed;
      saveGrocerySoon();
      renderReview();
    };
  });
  $("#addExtra").onclick = () => {
    const name = $("#extra").value.trim();
    if (!name) return;
    let other = g.aisles.find((a) => a.aisle === "Other");
    if (!other) g.aisles.push((other = { aisle: "Other", items: [] }));
    other.items.push({ item: name, qty: "", used_in: [], other_store: false, removed: false });
    saveGrocerySoon();
    renderReview();
  };
  setBar(`<span class="grow info">${meals.length} meals &middot; ${count} items</span>
          <button class="primary" id="confirm">Send to Skylight</button>`);
  $("#confirm").onclick = async () => {
    try {
      const res = await api("/api/plan/confirm", g, { busyText: "Sending everything to the Skylight...", busySub: "Recipes by email, groceries to the list." });
      S.results = res.results;
      await load();
      S.page = "done";
      renderStep("done");
    } catch (e) { toast(e.message, true); }
  };
}

function renderDone() {
  const r = S.results || (S.state.last_week && S.state.last_week.results) || { recipes: [], grocery: null };
  const icon = (s) => (s === "error" ? "⚠" : "✓");
  view.innerHTML = `
    <div class="hero"><h2>Plan sent!</h2><p>Recipes are on their way to the Skylight Recipe Box. Happy cooking.</p></div>
    <div class="card"><h3>Recipes</h3>
      ${r.recipes.map((x) => `<div class="status ${x.status === "error" ? "err" : "ok"}">${icon(x.status)} <b>${esc(x.name)}</b>: ${esc(x.detail)}</div>`).join("")}
    </div>
    <div class="card"><h3>Grocery list</h3>
      ${r.grocery ? `<div class="status ${r.grocery.status === "error" ? "err" : "ok"}">${icon(r.grocery.status)} ${esc(r.grocery.detail)}</div>` : ""}
      ${r.grocery && r.grocery.status === "error" && r.grocery_text ? `<p class="small">Here's the list to copy instead:</p><pre class="copy">${esc(r.grocery_text)}</pre>` : ""}
    </div>
    <p class="muted small">Next Saturday, the planner will ask how these meals went.</p>`;
  setBar(`<button class="primary big" id="home">Done</button>`);
  $("#home").onclick = () => { S.results = null; go("home"); };
}

// ---------------------------------------------------------------- profile

async function renderProfile() {
  setHeader("Taste profile", true);
  const p = await api("/api/profile");
  const chips = (arr, cls) => arr.map(([k, v]) => `<span class="chip ${cls}">${esc(k)}</span>`).join("") || `<span class="muted small">Not enough ratings yet.</span>`;
  view.innerHTML = `
    <div class="card">
      <h3>What the planner has learned</h3>
      <p class="muted small">${p.refreshed_at ? "Updated " + new Date(p.refreshed_at).toLocaleDateString() + ". " : ""}Rewritten by Claude after new ratings. Edit anything that's wrong.</p>
      <textarea id="profile" style="min-height:180px">${esc(p.profile)}</textarea>
    </div>
    <div class="card">
      <h3>Family notes</h3>
      <p class="muted small">Your own rules the AI always follows, e.g. "Sebastian loves anything with rice", "no mushrooms on weeknights".</p>
      <textarea id="notes">${esc(p.notes)}</textarea>
    </div>
    <div class="card"><h3>Flavors you love</h3><div class="chips" style="margin-top:8px">${chips(p.likes, "on")}</div></div>
    <div class="card"><h3>Tends to miss</h3><div class="chips" style="margin-top:8px">${chips(p.dislikes, "")}</div></div>`;
  setBar(`<button id="refresh" class="grow">Refresh with AI</button><button class="primary" id="save">Save</button>`);
  $("#save").onclick = async () => {
    await api("/api/profile", { profile: $("#profile").value, notes: $("#notes").value });
    toast("Saved");
  };
  $("#refresh").onclick = async () => {
    try {
      await api("/api/profile/refresh", {}, { busyText: "Updating the taste profile...", busySub: "Reading your ratings." });
      renderProfile();
    } catch (e) { toast(e.message, true); }
  };
}

// --------------------------------------------------------------- settings

const RULE_FIELDS = [
  ["ideas_count", "Ideas per batch", "number"],
  ["weeknight_max_minutes", "Weeknight max minutes", "number"],
  ["weeknight_stretch", "Weeknight adventure", "text"],
  ["favorites_share", "Favorites vs. new", "text"],
  ["wildcards", "Wildcards per week", "number"],
  ["max_pasta", "Max pasta dishes per week", "number"],
  ["favorite_rest_weeks", "Weeks before a favorite returns", "number"],
  ["servings", "Servings per recipe", "number"],
  ["cuisines", "Cuisines to rotate", "area"],
  ["stores", "Stores", "area"],
  ["household", "About the family", "area"],
];

async function renderSettings() {
  setHeader("House rules", true);
  const r = await api("/api/rules");
  view.innerHTML = `
    <div class="card">
      ${RULE_FIELDS.map(([k, l, t]) => `<label>${l}</label>${t === "area"
        ? `<textarea data-k="${k}">${esc(r[k])}</textarea>`
        : `<input type="${t}" data-k="${k}" value="${esc(r[k])}">`}`).join("")}
      <label class="row" style="gap:10px"><input type="checkbox" data-k="kid_mild_option" ${r.kid_mild_option ? "checked" : ""} style="width:22px;height:22px"> Mild option for Sebastian on adventurous dishes</label>
      <div class="row" style="margin-top:14px"><button class="primary" id="saveRules">Save rules</button><button class="ghost" id="resetRules">Reset to defaults</button></div>
    </div>
    <div class="card">
      <h3>Connections</h3>
      <p class="muted small">Checks Mealie, Claude, Gmail and the Skylight. Takes about 20 seconds.</p>
      <button id="test">Test connections</button>
      <div id="testOut"></div>
    </div>
    ${S.state.week ? `<div class="card"><h3>Start over</h3><p class="muted small">Throws away this week's unfinished plan.</p><button class="danger" id="cancel">Discard this week's plan</button></div>` : ""}`;
  setBar("");
  $("#saveRules").onclick = async () => {
    const body = {};
    view.querySelectorAll("[data-k]").forEach((el) => (body[el.dataset.k] = el.type === "checkbox" ? el.checked : el.value));
    try { await api("/api/rules", body); toast("Rules saved"); } catch (e) { toast(e.message, true); }
  };
  $("#resetRules").onclick = async () => { if (confirm("Reset all house rules?")) { await api("/api/rules/reset", {}); renderSettings(); } };
  $("#test").onclick = async () => {
    const res = await api("/api/test", {}, { busyText: "Testing connections..." });
    $("#testOut").innerHTML = res.checks.map((c) => `<div class="status ${c.ok ? "ok" : "err"}">${c.ok ? "✓" : "✕"} <b>${esc(c.name)}</b>: ${esc(c.detail)}</div>`).join("");
  };
  const cancel = $("#cancel");
  if (cancel) cancel.onclick = async () => {
    if (!confirm("Discard this week's plan?")) return;
    S.state = await api("/api/plan/cancel", {});
    go("home");
  };
}

// ---------------------------------------------------------------- history

async function renderHistory() {
  setHeader("History", true);
  const weeks = await api("/api/history");
  view.innerHTML = weeks.length ? weeks.map((w) => `
    <div class="card"><h3>${new Date(w.confirmed_at).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}</h3>
      ${w.meals.map((m) => `<div class="item"><span class="name">${esc(m.name)}${m.note ? `<div class="used">${esc(m.note)}</div>` : ""}</span><span>${EMOJI[m.rating] || ""}</span></div>`).join("")}
    </div>`).join("") : `<p class="muted">No weeks planned yet.</p>`;
  setBar("");
}

// ------------------------------------------------------------------- boot

(async function boot() {
  try {
    await load();
    if (S.state.week) S.page = "plan";
    render();
  } catch (e) {
    view.innerHTML = `<div class="warn">Could not reach the planner: ${esc(e.message)}</div>`;
  }
})();
