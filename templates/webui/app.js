(() => {
  const transcript = document.getElementById("transcript");
  const input = document.getElementById("input");
  const sendBtn = document.getElementById("send-btn");
  const clearBtn = document.getElementById("clear-btn");
  const saveMdBtn = document.getElementById("save-md-btn");
  const statusEl = document.getElementById("status");
  const healthEl = document.getElementById("health");
  const modelNameEl = document.getElementById("model-name");
  const pathFilter = document.getElementById("path-filter");
  const modeAsk = document.getElementById("mode-ask");
  const modeDeep = document.getElementById("mode-deep");
  const langFilters = document.getElementById("lang-filters");
  const excludeFilters = document.getElementById("exclude-filters");
  const excludeGeneratedBtn = document.getElementById("exclude-generated");
  const chatSearch = document.getElementById("chat-search");
  const chatSearchBtn = document.getElementById("chat-search-btn");
  const renderBtn = document.getElementById("render-btn");

  /** @type {{role: string, content: string}[]} */
  let messages = [];
  /** @type {{role: string, content: string, sources?: any[], statsLine?: string, mode?: string}[]} */
  let exportLog = [];
  let mode = "ask";
  /** Selected include extensions; empty = Any */
  let selectedExts = new Set();
  /** Exclude list as CSV (e.g. ".md,.txt,.rst") — default docs off */
  let excludeExts = ".md,.txt,.rst";
  /** Drop MkDocs site/ and search_index.json unless the user turns it off. */
  let excludeGenerated = true;
  let busy = false;
  let lastAnswer = "";
  let apiKey = localStorage.getItem("spock_rag_api_key") || "";

  // llama.cpp WebUI uses #/chat/<uuid>. Spock Ask AI is plain index.html —
  // strip that hash so a restored tab URL doesn't look like the wrong shell.
  if (location.hash && location.hash.indexOf("#/") === 0) {
    history.replaceState(null, "", location.pathname + location.search);
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function setMode(next) {
    mode = next === "deep_dive" ? "deep_dive" : "ask";
    modeAsk.classList.toggle("active", mode === "ask");
    modeDeep.classList.toggle("active", mode === "deep_dive");
  }

  modeAsk.addEventListener("click", () => setMode("ask"));
  modeDeep.addEventListener("click", () => setMode("deep_dive"));

  function syncLangButtons() {
    langFilters.querySelectorAll(".lang-btn").forEach((btn) => {
      const ext = btn.getAttribute("data-ext") || "";
      if (!ext) {
        btn.classList.toggle("active", selectedExts.size === 0);
      } else {
        btn.classList.toggle("active", selectedExts.has(ext));
      }
    });
  }

  langFilters.addEventListener("click", (e) => {
    const btn = e.target.closest(".lang-btn");
    if (!btn) return;
    const ext = btn.getAttribute("data-ext") || "";
    if (!ext) {
      selectedExts.clear();
    } else {
      if (selectedExts.has(ext)) selectedExts.delete(ext);
      else selectedExts.add(ext);
    }
    syncLangButtons();
  });

  function extensionFilterValue() {
    const parts = [];
    if (selectedExts.size > 0) {
      for (const ext of selectedExts) {
        // Buttons may carry comma lists (.ts,.tsx)
        for (const piece of String(ext).split(",")) {
          const p = piece.trim();
          if (p) parts.push(p);
        }
      }
    }
    if (excludeExts) {
      for (const piece of String(excludeExts).split(",")) {
        const p = piece.trim();
        if (!p) continue;
        parts.push(p.startsWith("!") ? p : "!" + p);
      }
    }
    return parts.join(",");
  }

  if (excludeFilters) {
    excludeFilters.addEventListener("click", (e) => {
      const btn = e.target.closest(".lang-btn");
      if (!btn) return;
      excludeExts = btn.getAttribute("data-excl") || "";
      excludeFilters.querySelectorAll(".lang-btn").forEach((b) => {
        b.classList.toggle("active", b === btn);
      });
    });
  }

  if (excludeGeneratedBtn) {
    excludeGeneratedBtn.addEventListener("click", () => {
      excludeGenerated = !excludeGenerated;
      excludeGeneratedBtn.classList.toggle("active", excludeGenerated);
    });
  }

  function searchChat() {
    const needle = (chatSearch && chatSearch.value ? chatSearch.value : "").trim();
    if (!needle) return;
    const bubbles = transcript.querySelectorAll(".bubble");
    let hit = null;
    for (const b of bubbles) {
      if ((b.textContent || "").toLowerCase().includes(needle.toLowerCase())) {
        if (b.classList.contains("search-hit")) continue;
        hit = b;
        break;
      }
    }
    if (!hit) {
      // wrap: clear prior hits and search again
      transcript.querySelectorAll(".search-hit").forEach((b) => {
        b.classList.remove("search-hit");
      });
      for (const b of bubbles) {
        if ((b.textContent || "").toLowerCase().includes(needle.toLowerCase())) {
          hit = b;
          break;
        }
      }
    }
    transcript.querySelectorAll(".search-hit").forEach((b) => {
      b.classList.remove("search-hit");
    });
    if (!hit) {
      statusEl.textContent = `No match for “${needle}”`;
      return;
    }
    hit.classList.add("search-hit");
    hit.scrollIntoView({ behavior: "smooth", block: "center" });
    statusEl.textContent = `Found “${needle}”`;
  }

  function answerToHtml(text) {
    const raw = String(text || "");
    const lower = raw.trim().toLowerCase();
    const fence = raw.match(/```(?:html|htm)\s*\n([\s\S]*?)```/i);
    if (fence) return { html: fence[1], kind: "HTML" };
    if (lower.startsWith("<!doctype html") || lower.startsWith("<html")) {
      return { html: raw, kind: "HTML" };
    }
    let html = escapeHtml(raw);
    html = html.replace(
      /```[\w]*\n([\s\S]*?)```/g,
      (_, code) => `<pre><code>${code}</code></pre>`
    );
    html = html.replace(/^### (.*)$/gm, "<h3>$1</h3>");
    html = html.replace(/^## (.*)$/gm, "<h2>$1</h2>");
    html = html.replace(/^# (.*)$/gm, "<h1>$1</h1>");
    html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
    html = html.replace(/\n\n/g, "</p><p>");
    const page = `<!DOCTYPE html><html><head><meta charset="utf-8"/><title>Spock Ask AI</title>
<style>body{font-family:Segoe UI,system-ui,sans-serif;max-width:860px;margin:2rem auto;padding:0 1rem;line-height:1.5;background:#0f1419;color:#e6edf3}
pre{background:#1c2128;padding:12px;overflow:auto;border-radius:8px} code{font-family:Consolas,monospace}
a{color:#5ec8b8}</style></head><body><p>${html}</p></body></html>`;
    return { html: page, kind: "Markdown" };
  }

  function latestAssistantText() {
    if (lastAnswer && lastAnswer.trim()) return lastAnswer;
    // Fall back to transcript / export log after refresh
    for (let i = exportLog.length - 1; i >= 0; i--) {
      if (exportLog[i].role === "assistant" && (exportLog[i].content || "").trim()) {
        return exportLog[i].content;
      }
    }
    const bubbles = transcript.querySelectorAll(".bubble.assistant");
    if (bubbles.length) {
      const last = bubbles[bubbles.length - 1];
      const clone = last.cloneNode(true);
      clone.querySelectorAll(".role, .sources").forEach((n) => n.remove());
      return (clone.textContent || "").trim();
    }
    return "";
  }

  let _renderBlobUrl = "";

  function closeRenderModal() {
    const modal = document.getElementById("render-modal");
    const frame = document.getElementById("render-frame");
    if (modal) modal.hidden = true;
    if (frame) frame.removeAttribute("srcdoc");
    if (_renderBlobUrl) {
      URL.revokeObjectURL(_renderBlobUrl);
      _renderBlobUrl = "";
    }
  }

  function showRenderModal(html, kind) {
    const modal = document.getElementById("render-modal");
    const frame = document.getElementById("render-frame");
    const title = document.getElementById("render-title");
    if (!modal || !frame) return false;
    if (_renderBlobUrl) {
      URL.revokeObjectURL(_renderBlobUrl);
      _renderBlobUrl = "";
    }
    // srcdoc avoids about:blank + noopener document.write failure
    frame.srcdoc = html;
    if (title) title.textContent = `Rendered ${kind}`;
    modal.hidden = false;
    return true;
  }

  function openRenderTab(html) {
    // Blob URL works with noopener; about:blank + document.write does not.
    if (_renderBlobUrl) URL.revokeObjectURL(_renderBlobUrl);
    const blob = new Blob([html], { type: "text/html;charset=utf-8" });
    _renderBlobUrl = URL.createObjectURL(blob);
    const win = window.open(_renderBlobUrl, "_blank");
    if (!win) {
      statusEl.textContent = "Popup blocked — use the in-page Render panel.";
      return false;
    }
    return true;
  }

  function renderLastAnswer() {
    const text = latestAssistantText();
    if (!text.trim()) {
      statusEl.textContent = "Nothing to render yet — ask a question first.";
      return;
    }
    const { html, kind } = answerToHtml(text);
    if (showRenderModal(html, kind)) {
      statusEl.textContent = `Showing ${kind} render`;
      return;
    }
    // Fallback if modal markup missing
    if (openRenderTab(html)) {
      statusEl.textContent = `Opened ${kind} in new tab`;
    }
  }

  if (chatSearchBtn) chatSearchBtn.addEventListener("click", searchChat);
  if (chatSearch) {
    chatSearch.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        searchChat();
      }
    });
  }
  if (renderBtn) renderBtn.addEventListener("click", renderLastAnswer);
  const renderClose = document.getElementById("render-close");
  const renderOpenTab = document.getElementById("render-open-tab");
  const renderModal = document.getElementById("render-modal");
  if (renderClose) renderClose.addEventListener("click", closeRenderModal);
  if (renderModal) {
    renderModal.addEventListener("click", (e) => {
      if (e.target === renderModal) closeRenderModal();
    });
  }
  if (renderOpenTab) {
    renderOpenTab.addEventListener("click", () => {
      const text = latestAssistantText();
      if (!text.trim()) return;
      const { html, kind } = answerToHtml(text);
      if (openRenderTab(html)) {
        statusEl.textContent = `Opened ${kind} in new tab`;
      }
    });
  }
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeRenderModal();
  });

  function appendBubble(role, text, extras) {
    const div = document.createElement("div");
    div.className = `bubble ${role}`;
    const roleLabel =
      role === "user" ? "You" : role === "assistant" ? "Computer" : "System";
    let html = `<span class="role">${escapeHtml(roleLabel)}</span>${escapeHtml(text)}`;
    if (extras && extras.statsLine) {
      html += `\n\n<span class="role">Deep Dive</span>${escapeHtml(extras.statsLine)}`;
    }
    if (extras && extras.sources && extras.sources.length) {
      html += `<div class="sources"><strong>Sources</strong><ul>`;
      for (const s of extras.sources.slice(0, 12)) {
        const title = escapeHtml(s.title || s.path || "doc");
        const path = escapeHtml(s.path || "");
        const score =
          typeof s.score === "number" ? s.score.toFixed(2) : "";
        html += `<li>${title}${score ? ` · ${score}` : ""}<br/><span>${path}</span></li>`;
      }
      html += `</ul></div>`;
    }
    div.innerHTML = html;
    transcript.appendChild(div);
    transcript.scrollTop = transcript.scrollHeight;

    if (role !== "system" || (extras && extras.keepExport)) {
      exportLog.push({
        role,
        content: text,
        sources: (extras && extras.sources) || [],
        statsLine: (extras && extras.statsLine) || "",
        mode: (extras && extras.mode) || mode,
      });
    }
  }

  function setBusy(on, label) {
    busy = on;
    sendBtn.disabled = on;
    input.disabled = on;
    saveMdBtn.disabled = on;
    statusEl.textContent = label || (on ? "Working…" : "");
  }

  function buildMarkdown() {
    const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
    const pathF = (pathFilter.value || "").trim() || "(none)";
    const langF = extensionFilterValue() || "Any";
    const lines = [
      `# Spock Ask AI — ${stamp}`,
      "",
      `- **Mode**: ${mode}`,
      `- **Path filter**: \`${pathF}\``,
      `- **Language filter**: \`${langF}\``,
      `- **Generated site**: ${excludeGenerated ? "excluded" : "included"}`,
      "",
      "## Conversation",
      "",
    ];
    for (const entry of exportLog) {
      if (entry.role === "system") {
        lines.push(`> ${entry.content}`, "");
        continue;
      }
      if (entry.role === "user") {
        const prefix =
          entry.mode === "deep_dive" ? "[Deep Dive] " : "";
        lines.push(`### You`, "", prefix + entry.content, "");
        continue;
      }
      if (entry.role === "assistant") {
        lines.push(`### Computer`, "", entry.content, "");
        if (entry.statsLine) {
          lines.push(`*${entry.statsLine}*`, "");
        }
        if (entry.sources && entry.sources.length) {
          lines.push(`#### Sources`, "");
          for (const s of entry.sources) {
            const score =
              typeof s.score === "number" ? ` (${s.score.toFixed(2)})` : "";
            lines.push(
              `- **${s.title || "doc"}**${score} — \`${s.path || ""}\``
            );
          }
          lines.push("");
        }
      }
    }
    return lines.join("\n");
  }

  function saveAsMarkdown() {
    if (!exportLog.some((e) => e.role === "user" || e.role === "assistant")) {
      statusEl.textContent = "Nothing to save yet — ask a question first.";
      return;
    }
    const stamp = new Date()
      .toISOString()
      .replace(/[-:TZ.]/g, "")
      .slice(0, 14);
    const name = `spock-${mode === "deep_dive" ? "deep-dive" : "ask"}-${stamp}.md`;
    const blob = new Blob([buildMarkdown()], {
      type: "text/markdown;charset=utf-8",
    });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(a.href);
    statusEl.textContent = `Saved ${name}`;
  }

  async function refreshHealth() {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 4000);
    try {
      const r = await fetch("/health", { cache: "no-store", signal: ctrl.signal });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error?.message || r.statusText);
      const provider = data.llm_provider || "None";
      const emb = data.embeddings_url || "";
      const model = (data.model || "").trim();
      if (modelNameEl) {
        modelNameEl.textContent = model
          ? `Model: ${model}`
          : `Model: ${provider !== "None" ? provider : "—"}`;
        modelNameEl.title = model
          ? `Ask AI chat model: ${model}`
          : "Ask AI chat model (from /health)";
      }
      healthEl.className = "health ok";
      healthEl.innerHTML = `LLM: ${escapeHtml(provider)}<br/>Emb: ${escapeHtml(emb)}`;
      if (data.api_key_required && !apiKey) {
        const entered = window.prompt(
          "RAG API key required (saved in this browser only):",
          ""
        );
        if (entered) {
          apiKey = entered.trim();
          localStorage.setItem("spock_rag_api_key", apiKey);
        }
      }
    } catch (e) {
      if (modelNameEl) {
        modelNameEl.textContent = "Model: —";
      }
      healthEl.className = "health bad";
      const msg =
        e && e.name === "AbortError"
          ? "Health timed out — API may be busy"
          : `Health failed: ${e.message || e}`;
      healthEl.textContent = msg;
    } finally {
      clearTimeout(timer);
    }
  }

  async function send() {
    const text = (input.value || "").trim();
    if (!text || busy) return;

    appendBubble("user", text, { mode });
    messages.push({ role: "user", content: text });
    input.value = "";

    const headers = { "Content-Type": "application/json" };
    if (apiKey) headers.Authorization = `Bearer ${apiKey}`;

    const body = {
      model: "spock-ships-computer",
      messages: messages.slice(),
      spock_mode: mode,
      spock_path_filter: (pathFilter.value || "").trim(),
      spock_extension: extensionFilterValue(),
      spock_exclude_generated: excludeGenerated,
    };

    setBusy(true, mode === "deep_dive" ? "Deep Dive…" : "Asking…");
    try {
      const r = await fetch("/v1/chat/completions", {
        method: "POST",
        headers,
        body: JSON.stringify(body),
      });
      const data = await r.json();
      if (!r.ok) {
        const err =
          data.error?.message || data.error || `HTTP ${r.status}`;
        appendBubble("system", String(err));
        messages.pop();
        exportLog.pop();
        return;
      }
      const answer =
        data.choices?.[0]?.message?.content ||
        "(empty response)";
      lastAnswer = answer;
      messages.push({ role: "assistant", content: answer });
      if (messages.length > 24) {
        messages = messages.slice(-24);
      }
      appendBubble("assistant", answer, {
        sources: data.spock_sources || [],
        statsLine: data.spock_stats?.summary || "",
        mode,
      });
    } catch (e) {
      appendBubble("system", `Network error: ${e.message || e}`);
      messages.pop();
      exportLog.pop();
    } finally {
      setBusy(false, "");
    }
  }

  sendBtn.addEventListener("click", send);
  saveMdBtn.addEventListener("click", saveAsMarkdown);
  clearBtn.addEventListener("click", () => {
    messages = [];
    exportLog = [];
    transcript.innerHTML = "";
    appendBubble(
      "system",
      "Chat cleared. Ask for hybrid RAG, or Deep Dive for budgeted multi-file context."
    );
  });

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  });

  appendBubble(
    "system",
    "Ready. Use Ask or Deep Dive. Include languages + Exclude docs narrow retrieval. Search Chat finds text in the transcript; Save as .MD / Render preview the reply."
  );
  syncLangButtons();
  refreshHealth();
  setInterval(refreshHealth, 30000);
})();
