const $ = (id) => document.getElementById(id);

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  Object.entries(attrs).forEach(([k, v]) => {
    if (k === "className") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k === "html") node.innerHTML = v;
    else node.setAttribute(k, v);
  });
  children.forEach((c) => node.appendChild(c));
  return node;
}

const mdBuffers = new Map();

function escapeHtml(s) {
  if (s == null) return "";
  const d = document.createElement("div");
  d.textContent = String(s);
  return d.innerHTML;
}

function getMarked() {
  if (typeof marked !== "undefined") return marked;
  return globalThis.marked;
}

function getDOMPurify() {
  if (typeof DOMPurify !== "undefined") return DOMPurify;
  return globalThis.DOMPurify;
}

function safeMd(src) {
  const str = String(src ?? "");
  const m = getMarked();
  const p = getDOMPurify();
  if (!m || typeof m.parse !== "function" || !p || typeof p.sanitize !== "function") {
    return escapeHtml(str).replace(/\n/g, "<br>");
  }
  try {
    const raw = m.parse(str, { breaks: true, async: false });
    if (raw != null && typeof raw.then === "function") {
      return escapeHtml(str).replace(/\n/g, "<br>");
    }
    return p.sanitize(String(raw));
  } catch {
    return escapeHtml(str).replace(/\n/g, "<br>");
  }
}

function mdKey(branch, role, pathIndex) {
  if (pathIndex !== undefined && pathIndex !== null) {
    return `${branch}:${role}:${pathIndex}`;
  }
  return `${branch}:${role}`;
}

function appendMd(el, key, chunk) {
  const next = (mdBuffers.get(key) || "") + (chunk || "");
  mdBuffers.set(key, next);
  el.innerHTML = safeMd(next);
}

function resetMdBuffers() {
  mdBuffers.clear();
}

/** @type {{ mode: string | null, grid: HTMLElement | null, columns: Map<string, ColumnUI>, pathRounds: Map<string, PathRoundUI> }} */
const state = {
  mode: null,
  grid: null,
  columns: new Map(),
  pathRounds: new Map(),
};

function defaultBranchTitle(branch) {
  if (branch === "baseline") return "纯 R1（无思考路径预处理）";
  if (branch === "tech") return "技术：多路径 × 并行 R1 + Chat 综合";
  return branch;
}

/**
 * @typedef {object} PathRoundUI
 * @property {HTMLElement} wrap
 * @property {HTMLElement} thinkBody
 * @property {HTMLElement} answerEl
 * @property {HTMLElement} thinkSection
 * @property {HTMLElement} thinkLabel
 * @property {HTMLElement} thinkCaret
 */

/**
 * @typedef {object} ColumnUI
 * @property {HTMLElement} root
 * @property {HTMLElement} pathsEl
 * @property {HTMLElement} roundsEl
 * @property {HTMLElement} thinkBody
 * @property {HTMLElement} thinkSection
 * @property {HTMLElement} thinkLabel
 * @property {HTMLElement} thinkCaret
 * @property {HTMLElement} answerEl
 * @property {HTMLElement} answerLabel
 * @property {HTMLElement} synthesisBlock
 * @property {HTMLElement} synthAnswerEl
 */

function roundKey(branch, index) {
  return `${branch}-${index}`;
}

function resetOutput() {
  const out = $("output");
  out.innerHTML = "";
  out.classList.remove("hidden");
  state.mode = null;
  state.grid = null;
  state.columns.clear();
  state.pathRounds.clear();
  resetMdBuffers();
}

function ensureGridForMode(mode) {
  const out = $("output");
  if (state.grid) return state.grid;
  const grid = el("div", {
    className: mode === "compare" ? "grid-compare ds-grid" : "grid-single ds-grid",
  });
  out.appendChild(grid);
  state.grid = grid;
  return grid;
}

/**
 * @param {string} branch
 * @param {string} title
 * @returns {ColumnUI}
 */
function ensureColumn(branch, title) {
  const existing = state.columns.get(branch);
  if (existing) {
    const h = existing.root.querySelector(".ds-card-title");
    if (h) h.textContent = title;
    return existing;
  }

  const thinkSection = el("section", { className: "ds-think" });
  const thinkLabel = el("span", { className: "ds-think-label", text: "深度思考" });
  const thinkCaret = el("span", { className: "ds-think-caret", text: "▼" });
  const thinkHead = el("button", {
    type: "button",
    className: "ds-think-head",
    "aria-expanded": "true",
  });
  thinkHead.appendChild(thinkLabel);
  thinkHead.appendChild(
    el("span", { className: "ds-think-meta" }, [
      el("span", { className: "ds-think-pulse", text: "" }),
      thinkCaret,
    ]),
  );
  const thinkBody = el("div", { className: "ds-think-body markdown-body" });
  thinkSection.appendChild(thinkHead);
  thinkSection.appendChild(thinkBody);

  thinkHead.addEventListener("click", () => {
    const open = thinkSection.classList.toggle("ds-think-collapsed");
    thinkHead.setAttribute("aria-expanded", open ? "false" : "true");
    thinkCaret.textContent = open ? "▶" : "▼";
  });

  const answerLabel = el("div", { className: "ds-answer-label", text: "回答" });
  const answerEl = el("div", { className: "ds-answer markdown-body" });
  const pathsEl = el("div", { className: "ds-paths-wrap hidden" });
  const roundsEl = el("div", { className: "ds-path-rounds" });

  const synthesisBlock = el("div", { className: "ds-synthesis hidden" });
  synthesisBlock.appendChild(
    el("div", { className: "ds-answer-label", text: "综合回答（Chat）" }),
  );
  const synthAnswerEl = el("div", { className: "ds-answer ds-answer-synth markdown-body" });
  synthesisBlock.appendChild(synthAnswerEl);

  const card = el("article", { className: "ds-card", "data-branch": branch });
  card.appendChild(el("h2", { className: "ds-card-title", text: title }));
  card.appendChild(pathsEl);
  card.appendChild(roundsEl);
  card.appendChild(thinkSection);
  card.appendChild(answerLabel);
  card.appendChild(answerEl);
  card.appendChild(synthesisBlock);

  if (branch === "tech") {
    thinkSection.style.display = "none";
    answerLabel.style.display = "none";
    answerEl.style.display = "none";
  } else {
    roundsEl.style.display = "none";
    synthesisBlock.classList.add("hidden");
  }

  ensureGridForMode(state.mode || "baseline_only").appendChild(card);

  const ui = {
    root: card,
    pathsEl,
    roundsEl,
    thinkBody,
    thinkSection,
    thinkLabel,
    thinkCaret,
    answerEl,
    answerLabel,
    synthesisBlock,
    synthAnswerEl,
  };
  state.columns.set(branch, ui);
  return ui;
}

function createPathRound(branch, pathIndex, pathTitle, detail) {
  const col = ensureColumn(branch, defaultBranchTitle(branch));
  const wrap = el("div", { className: "ds-path-round" });
  wrap.appendChild(
    el("div", { className: "ds-path-round-title", text: `路径 ${pathIndex + 1}：${pathTitle}` }),
  );
  if (detail) {
    const dd = el("div", { className: "ds-path-round-detail markdown-body" });
    dd.innerHTML = safeMd(detail);
    wrap.appendChild(dd);
  }

  const subThink = el("section", { className: "ds-think ds-think-sub" });
  const sl = el("span", { className: "ds-think-label", text: "R1 深度思考" });
  const sc = el("span", { className: "ds-think-caret", text: "▼" });
  const sh = el("button", { type: "button", className: "ds-think-head", "aria-expanded": "true" });
  sh.appendChild(sl);
  sh.appendChild(
    el("span", { className: "ds-think-meta" }, [
      el("span", { className: "ds-think-pulse", text: "" }),
      sc,
    ]),
  );
  const sb = el("div", { className: "ds-think-body markdown-body" });
  subThink.appendChild(sh);
  subThink.appendChild(sb);
  sh.addEventListener("click", () => {
    const open = subThink.classList.toggle("ds-think-collapsed");
    sh.setAttribute("aria-expanded", open ? "false" : "true");
    sc.textContent = open ? "▶" : "▼";
  });

  wrap.appendChild(subThink);
  wrap.appendChild(el("div", { className: "ds-sub-answer-label", text: "该路径 R1 小结" }));
  const subAns = el("div", { className: "ds-answer ds-answer-sub markdown-body" });
  wrap.appendChild(subAns);

  col.roundsEl.appendChild(wrap);

  const pr = {
    wrap,
    thinkBody: sb,
    answerEl: subAns,
    thinkSection: subThink,
    thinkLabel: sl,
    thinkCaret: sc,
  };
  state.pathRounds.set(roundKey(branch, pathIndex), pr);
  return pr;
}

function setSubThinkStreaming(pr, on) {
  pr.thinkSection.classList.toggle("ds-think-streaming", on);
  pr.thinkLabel.textContent = on ? "R1 思考中…" : "已深度思考";
}

function renderPathsInto(container, paths) {
  container.innerHTML = "";
  container.classList.remove("hidden");
  if (!paths || paths.length === 0) {
    container.appendChild(el("p", { className: "ds-path-empty", text: "（无思考路径）" }));
    return;
  }
  const ul = el("ul", { className: "ds-paths" });
  paths.forEach((p) => {
    const detail = p.detail != null ? p.detail : p.reason;
    const line = el("div", { className: "ds-path-line", text: p.path });
    const det = el("div", { className: "ds-path-detail markdown-body" });
    det.innerHTML = safeMd(detail || "");
    ul.appendChild(el("li", {}, [line, det]));
  });
  container.appendChild(el("div", { className: "ds-paths-title", text: "思考路径（Chat 生成）" }));
  container.appendChild(ul);
}

function setThinkStreaming(ui, on) {
  ui.thinkSection.classList.toggle("ds-think-streaming", on);
  if (on) {
    ui.thinkLabel.textContent = "深度思考中…";
  } else {
    ui.thinkLabel.textContent = "已深度思考";
  }
}

function handleEvent(obj) {
  const t = obj.type;
  if (t === "meta") {
    resetOutput();
    state.mode = obj.mode;
    ensureGridForMode(obj.mode);
    return;
  }
  if (t === "branch") {
    ensureColumn(obj.branch, obj.title);
    return;
  }
  if (t === "phase") {
    const ui =
      state.columns.get(obj.branch) ?? ensureColumn(obj.branch, defaultBranchTitle(obj.branch));
    if (obj.phase === "paths_loading") {
      ui.pathsEl.classList.remove("hidden");
      ui.pathsEl.innerHTML = "";
      ui.pathsEl.appendChild(
        el("div", { className: "ds-paths-skel", text: "正在生成多条思考路径（含详细阐明）…" }),
      );
    }
    return;
  }
  if (t === "paths") {
    const ui =
      state.columns.get(obj.branch) ?? ensureColumn(obj.branch, defaultBranchTitle(obj.branch));
    renderPathsInto(ui.pathsEl, obj.paths);
    return;
  }
  if (t === "path_round_start") {
    mdBuffers.delete(mdKey(obj.branch, "think", obj.path_index));
    mdBuffers.delete(mdKey(obj.branch, "pathAns", obj.path_index));
    createPathRound(obj.branch, obj.path_index, obj.path, obj.detail);
    const pr = state.pathRounds.get(roundKey(obj.branch, obj.path_index));
    if (pr) setSubThinkStreaming(pr, true);
    return;
  }
  if (t === "path_round_end") {
    const pr = state.pathRounds.get(roundKey(obj.branch, obj.path_index));
    if (pr) {
      setSubThinkStreaming(pr, false);
      const tk = mdKey(obj.branch, "think", obj.path_index);
      if (!(mdBuffers.get(tk) || "").trim()) {
        pr.thinkSection.style.display = "none";
      }
    }
    return;
  }
  if (t === "reasoning_delta") {
    if (obj.path_index !== undefined && obj.path_index !== null) {
      const pr = state.pathRounds.get(roundKey(obj.branch, obj.path_index));
      if (pr) {
        setSubThinkStreaming(pr, true);
        appendMd(pr.thinkBody, mdKey(obj.branch, "think", obj.path_index), obj.text || "");
        pr.thinkBody.scrollTop = pr.thinkBody.scrollHeight;
      }
    } else {
      const ui =
        state.columns.get(obj.branch) ?? ensureColumn(obj.branch, defaultBranchTitle(obj.branch));
      setThinkStreaming(ui, true);
      appendMd(ui.thinkBody, mdKey(obj.branch, "think", null), obj.text || "");
      ui.thinkBody.scrollTop = ui.thinkBody.scrollHeight;
    }
    return;
  }
  if (t === "path_answer_delta") {
    const pr = state.pathRounds.get(roundKey(obj.branch, obj.path_index));
    if (pr) {
      appendMd(pr.answerEl, mdKey(obj.branch, "pathAns", obj.path_index), obj.text || "");
    }
    return;
  }
  if (t === "answer_delta") {
    const ui =
      state.columns.get(obj.branch) ?? ensureColumn(obj.branch, defaultBranchTitle(obj.branch));
    appendMd(ui.answerEl, mdKey(obj.branch, "ans", null), obj.text || "");
    return;
  }
  if (t === "synthesis_start") {
    const ui =
      state.columns.get(obj.branch) ?? ensureColumn(obj.branch, defaultBranchTitle(obj.branch));
    ui.synthesisBlock.classList.remove("hidden");
    mdBuffers.delete(mdKey(obj.branch, "synth", null));
    ui.synthAnswerEl.innerHTML = "";
    return;
  }
  if (t === "synthesis_delta") {
    const ui =
      state.columns.get(obj.branch) ?? ensureColumn(obj.branch, defaultBranchTitle(obj.branch));
    ui.synthesisBlock.classList.remove("hidden");
    appendMd(ui.synthAnswerEl, mdKey(obj.branch, "synth", null), obj.text || "");
    return;
  }
  if (t === "branch_end") {
    const ui = state.columns.get(obj.branch);
    if (ui && ui.thinkSection.style.display !== "none") {
      setThinkStreaming(ui, false);
      if (!(mdBuffers.get(mdKey(obj.branch, "think", null)) || "").trim()) {
        ui.thinkSection.style.display = "none";
      }
    }
    return;
  }
  if (t === "done") {
    return;
  }
  if (t === "error") {
    throw new Error(obj.message || "流式错误");
  }
}

async function run() {
  const question = $("question").value.trim();
  const mode = $("mode").value;
  const btn = $("run");
  const status = $("status");

  if (!question) {
    status.textContent = "请先输入问题。";
    status.className = "status error";
    return;
  }

  btn.disabled = true;
  status.textContent = "流式连接中…";
  status.className = "status loading";

  resetOutput();

  let lineBuf = "";

  try {
    const res = await fetch("/api/run/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, mode }),
    });

    if (!res.ok) {
      const payload = await res.json().catch(() => ({}));
      const detail = payload.detail || res.statusText || "请求失败";
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }

    const reader = res.body?.getReader();
    if (!reader) throw new Error("无法读取响应流");

    const dec = new TextDecoder();
    status.textContent = "正在接收流式输出（对比并行 / 多路径并行 R1 + 综合）…";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      lineBuf += dec.decode(value, { stream: true });
      const lines = lineBuf.split("\n");
      lineBuf = lines.pop() ?? "";
      for (const line of lines) {
        const s = line.trim();
        if (!s) continue;
        handleEvent(JSON.parse(s));
      }
    }

    const tail = lineBuf.trim();
    if (tail) handleEvent(JSON.parse(tail));

    status.textContent = "完成";
    status.className = "status";
  } catch (e) {
    status.textContent = e instanceof Error ? e.message : String(e);
    status.className = "status error";
  } finally {
    btn.disabled = false;
  }
}

$("run").addEventListener("click", run);
