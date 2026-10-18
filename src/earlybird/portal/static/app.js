/* Earlybird portal interactions. Vanilla JS + htmx; no build step. */
(() => {
  "use strict";
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const narrow = () => window.matchMedia("(max-width: 1180px)").matches;
  const typing = (el) => el && (el.matches("input, textarea, select") || el.isContentEditable);
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
  };
  const icon = (name, cls = "i") => {
    const tpl = document.getElementById(`icon-${name}`);
    return tpl ? `<svg class="${cls}" viewBox="0 0 24 24">${tpl.innerHTML}</svg>` : "";
  };
  const post = async (url, data) => {
    const body = new FormData();
    Object.entries(data).forEach(([k, v]) => v != null && body.append(k, v));
    const res = await fetch(url, { method: "POST", body });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  };

  /* ---------- theme ---------- */
  const applyTheme = (t) => {
    if (t) document.documentElement.dataset.theme = t;
    else delete document.documentElement.dataset.theme;
  };
  applyTheme(store.get("eb-theme"));
  document.addEventListener("click", (e) => {
    if (!e.target.closest("[data-theme-toggle]")) return;
    const dark = document.documentElement.dataset.theme
      ? document.documentElement.dataset.theme === "dark"
      : window.matchMedia("(prefers-color-scheme: dark)").matches;
    const next = dark ? "light" : "dark";
    applyTheme(next);
    store.set("eb-theme", next);
  });

  /* ---------- toasts ---------- */
  const toast = (message, { undo, error = false, timeout = 5000 } = {}) => {
    const host = $("#toasts");
    const el = document.createElement("div");
    el.className = `toast${error ? " error" : ""}`;
    el.setAttribute("role", "status");
    el.innerHTML = `<span class="ok-ic">${icon(error ? "alert" : "check", "i sm")}</span><span></span>`;
    el.children[1].textContent = message;
    const close = () => { el.classList.add("out"); setTimeout(() => el.remove(), 200); };
    if (undo) {
      const btn = document.createElement("button");
      btn.innerHTML = `${icon("undo", "i sm")} Undo`;
      btn.style.display = "inline-flex"; btn.style.alignItems = "center"; btn.style.gap = "5px";
      btn.onclick = () => { close(); undo(); };
      el.append(btn);
    }
    host.append(el);
    setTimeout(close, timeout);
  };
  window.ebToast = toast;

  /* ---------- modals (shortcut help) ---------- */
  const openModal = (id) => {
    const m = document.getElementById(id);
    if (!m) return;
    m.hidden = false;
    $(`[data-overlay-for="${id}"]`).hidden = false;
  };
  const closeModals = () => {
    $$(".modal, [data-overlay-for]").forEach((el) => { el.hidden = true; });
  };
  document.addEventListener("click", (e) => {
    const opener = e.target.closest("[data-open-modal]");
    if (opener) openModal(opener.dataset.openModal);
    if (e.target.closest("[data-close-modal]") || e.target.matches("[data-overlay-for]")) closeModals();
  });

  /* ---------- sync now ---------- */
  document.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-sync]");
    if (!btn) return;
    btn.classList.add("loading");
    try {
      const res = await fetch("/sync", { method: "POST" });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || "sync failed");
      toast(data.new_jobs ? `Synced · ${data.new_jobs} new jobs` : "Synced · already up to date");
      setTimeout(() => location.reload(), 900);
    } catch (err) {
      toast(`Sync failed: ${err.message}`, { error: true });
    } finally {
      btn.classList.remove("loading");
    }
  });

  /* ---------- AI scoring ---------- */
  document.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-score]");
    if (!btn) return;
    btn.classList.add("loading");
    toast("Scoring filtered jobs with AI… this can take a minute.");
    try {
      const res = await fetch("/score", { method: "POST" });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || "scoring failed");
      toast(data.scored ? `Scored ${data.scored} jobs · $${data.cost_usd}` : `Nothing new to score (${data.reason})`);
      if (data.scored) setTimeout(() => location.reload(), 900);
    } catch (err) {
      toast(`Scoring failed: ${err.message}`, { error: true });
    } finally {
      btn.classList.remove("loading");
    }
  });

  /* ---------- "pick at most N" option groups ---------- */
  $$("[data-max-checked]").forEach((group) => {
    const max = Number(group.dataset.maxChecked);
    const boxes = $$("input[type=checkbox]", group);
    const sync = () => {
      const full = boxes.filter((b) => b.checked).length >= max;
      boxes.forEach((b) => { b.disabled = full && !b.checked; b.closest(".option").classList.toggle("disabled", b.disabled); });
    };
    boxes.forEach((b) => b.addEventListener("change", sync));
    sync();
  });

  /* ---------- tag inputs ---------- */
  const escapeHtml = (s) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const initTags = (root) => {
    const hidden = $("input[type=hidden]", root);
    const suggestions = JSON.parse(root.dataset.suggest || "[]").map((s) =>
      typeof s === "string" ? { value: s, label: s } : s);
    const labelOf = (v) => (suggestions.find((s) => s.value === v) || { label: v }).label;
    let values = hidden.value.split(",").map((s) => s.trim()).filter(Boolean);
    let hl = 0;

    const box = document.createElement("div");
    box.className = "tags-box";
    const input = document.createElement("input");
    input.className = "tags-input";
    input.placeholder = root.dataset.placeholder || "Type and press Enter";
    input.autocomplete = "off";
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-expanded", "false");
    if (root.dataset.inputId) input.id = root.dataset.inputId;
    box.append(input);
    const menu = document.createElement("div");
    menu.className = "suggest";
    menu.hidden = true;
    menu.setAttribute("role", "listbox");
    root.append(box, menu);
    let quick = null;
    if (root.hasAttribute("data-quick")) {
      quick = document.createElement("div");
      quick.className = "quick";
      root.after(quick);
    }

    const changed = () => {
      hidden.value = values.join(", ");
      hidden.dispatchEvent(new Event("change", { bubbles: true }));
    };
    const has = (v) => values.some((x) => x.toLowerCase() === v.toLowerCase());
    const add = (v) => {
      v = v.trim().replace(/,+$/, "");
      if (!v || has(v)) return;
      values.push(v);
      render(); changed();
    };
    const removeAt = (i) => { values.splice(i, 1); render(); changed(); };
    const renderQuick = () => {
      if (!quick) return;
      const items = suggestions.filter((s) => !has(s.value)).slice(0, Number(root.dataset.quick) || 8);
      quick.innerHTML = items.length ? "" : "";
      items.forEach((s) => {
        const b = document.createElement("button");
        b.type = "button";
        b.innerHTML = `${icon("plus")}<span></span>`;
        b.lastChild.textContent = s.label;
        b.onclick = () => add(s.value);
        quick.append(b);
      });
    };
    const render = () => {
      $$(".tag", box).forEach((n) => n.remove());
      values.forEach((v, i) => {
        const t = document.createElement("span");
        t.className = "tag";
        t.innerHTML = `<span></span><button type="button" aria-label="Remove">${icon("x")}</button>`;
        t.firstChild.textContent = labelOf(v);
        t.lastChild.onclick = (e) => { e.stopPropagation(); removeAt(i); input.focus(); };
        box.insertBefore(t, input);
      });
      renderQuick();
    };
    const grouped = suggestions.some((s) => s.group);
    const matches = () => {
      const q = input.value.trim().toLowerCase();
      const found = suggestions.filter((s) => !has(s.value) && (!q || s.label.toLowerCase().includes(q) || s.value.toLowerCase().includes(q)));
      if (!q) return grouped ? found : found.slice(0, 12);
      const rank = (s) => (s.label.toLowerCase().startsWith(q) ? 0 : 1) + s.label.toLowerCase().indexOf(q) / 100;
      return found.sort((a, b) => rank(a) - rank(b)).slice(0, 12);
    };
    const showMenu = () => {
      const items = matches();
      const q = input.value.trim();
      if (!items.length && !q) { hideMenu(); return; }
      hl = Math.min(hl, Math.max(items.length - 1, 0));
      menu.innerHTML = "";
      let group = null;
      items.forEach((s, i) => {
        if (!q && s.group && s.group !== group) {
          group = s.group;
          const h = document.createElement("div");
          h.className = "suggest-group";
          h.textContent = group;
          menu.append(h);
        }
        const b = document.createElement("button");
        b.type = "button";
        b.setAttribute("role", "option");
        if (i === hl) b.classList.add("hl");
        const label = escapeHtml(s.label);
        const idx = q ? s.label.toLowerCase().indexOf(q.toLowerCase()) : -1;
        b.innerHTML = idx >= 0
          ? `${escapeHtml(s.label.slice(0, idx))}<mark>${escapeHtml(s.label.slice(idx, idx + q.length))}</mark>${escapeHtml(s.label.slice(idx + q.length))}`
          : label;
        if (s.label !== s.value) b.insertAdjacentHTML("beforeend", `<small>${escapeHtml(s.value)}</small>`);
        else if (q && s.group) b.insertAdjacentHTML("beforeend", `<small>${escapeHtml(s.group)}</small>`);
        b.onmousedown = (e) => { e.preventDefault(); add(s.value); input.value = ""; showMenu(); };
        menu.append(b);
      });
      if (q && !suggestions.some((s) => s.label.toLowerCase() === q.toLowerCase()) && root.dataset.free !== "false") {
        const b = document.createElement("button");
        b.type = "button";
        if (!items.length) b.classList.add("hl");
        b.innerHTML = `${icon("plus")}<span>Add “${escapeHtml(q)}”</span>`;
        b.onmousedown = (e) => { e.preventDefault(); add(q); input.value = ""; showMenu(); };
        menu.append(b);
      }
      menu.hidden = !menu.children.length;
      input.setAttribute("aria-expanded", String(!menu.hidden));
    };
    const hideMenu = () => { menu.hidden = true; input.setAttribute("aria-expanded", "false"); };

    box.addEventListener("click", () => input.focus());
    input.addEventListener("focus", () => { root.classList.add("focus"); showMenu(); });
    input.addEventListener("blur", () => {
      root.classList.remove("focus");
      if (input.value.trim() && root.dataset.free !== "false") { add(input.value); input.value = ""; }
      hideMenu();
    });
    input.addEventListener("input", () => {
      if (input.value.includes(",")) { input.value.split(",").forEach(add); input.value = ""; }
      hl = 0; showMenu();
    });
    input.addEventListener("keydown", (e) => {
      const opts = $$("button", menu);
      if (e.key === "ArrowDown" && opts.length) { e.preventDefault(); hl = (hl + 1) % opts.length; showMenu(); $$("button", menu)[hl]?.scrollIntoView({ block: "nearest" }); }
      else if (e.key === "ArrowUp" && opts.length) { e.preventDefault(); hl = (hl - 1 + opts.length) % opts.length; showMenu(); $$("button", menu)[hl]?.scrollIntoView({ block: "nearest" }); }
      else if (e.key === "Enter" || e.key === "Tab") {
        if (!menu.hidden && opts[hl]) { e.preventDefault(); opts[hl].dispatchEvent(new MouseEvent("mousedown")); }
        else if (input.value.trim()) { e.preventDefault(); add(input.value); input.value = ""; showMenu(); }
        else if (e.key === "Enter") e.preventDefault();
      } else if (e.key === "Backspace" && !input.value && values.length) { removeAt(values.length - 1); }
      else if (e.key === "Escape") { hideMenu(); input.blur(); }
    });
    render();
  };
  $$("[data-tags]").forEach(initTags);

  /* ---------- dream companies (Perch) ---------- */
  const perchSearch = $("[data-perch-search]");
  if (perchSearch) {
    const items = $$(".perch-item");
    const count = $("[data-perch-count]");
    const refresh = () => { count.textContent = `${items.filter((i) => $("input", i).checked).length} watched`; };
    perchSearch.addEventListener("input", () => {
      const q = perchSearch.value.trim().toLowerCase();
      let shown = 0;
      items.forEach((i) => { const hit = !q || i.dataset.name.includes(q); i.hidden = !hit; shown += hit; });
      $(".perch-none").hidden = shown > 0;
    });
    items.forEach((i) => $("input", i).addEventListener("change", refresh));
  }
  document.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-watch]");
    if (!btn) return;
    const watch = btn.dataset.watching !== "true";
    try {
      const res = await post("/profile/watch", { company_slug: btn.dataset.watch, watch });
      if (!res.ok) throw new Error(res.error);
    } catch (err) {
      toast(`Couldn't update dream companies${err.message ? `: ${err.message}` : ""}`, { error: true });
      return;
    }
    btn.dataset.watching = String(watch);
    btn.classList.toggle("primary", watch);
    $("span", btn).textContent = watch ? "Watching" : "Watch company";
    toast(watch ? `${btn.dataset.company} added to dream companies. Relevant roles there will go to the top.` : `${btn.dataset.company} removed from dream companies`);
  });

  /* ---------- range + steppers ---------- */
  const syncRange = (r) => {
    const pct = ((r.value - r.min) / (r.max - r.min)) * 100;
    r.style.setProperty("--pct", `${pct}%`);
    const out = document.getElementById(r.dataset.output);
    if (out) out.textContent = `${r.value} ${Number(r.value) === 1 ? "year" : "years"}`;
  };
  $$("input[type=range]").forEach((r) => { syncRange(r); r.addEventListener("input", () => syncRange(r)); });
  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-step]");
    if (!b) return;
    const input = document.getElementById(b.dataset.target);
    const next = Math.max(Number(input.min || 0), Math.min(Number(input.max || 9999), Number(input.value || 0) + Number(b.dataset.step)));
    input.value = next;
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });

  /* ---------- profile form ---------- */
  const profileForm = $("#profile-form");
  if (profileForm) {
    const bar = $(".savebar");
    const state = $(".savebar .state span");
    const markDirty = () => { bar.classList.add("dirty"); state.textContent = "Unsaved changes"; };
    profileForm.addEventListener("input", markDirty);
    profileForm.addEventListener("change", markDirty);
    $("[data-discard]")?.addEventListener("click", () => location.reload());
    document.addEventListener("keydown", (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "s") { e.preventDefault(); profileForm.requestSubmit(); }
    });
  }

  /* ---------- Dawn ---------- */
  const queue = $("#queue");
  if (queue) {
    const detail = $("#detail");
    const backdrop = $("#sheet-backdrop");
    let current = null;
    let cleared = 0;
    const total = Number(queue.dataset.total || 0);
    const rows = () => $$(".jrow", queue);

    const openSheet = () => { if (narrow()) { detail.classList.add("open"); backdrop.hidden = false; } };
    const closeSheet = () => { detail.classList.remove("open"); backdrop.hidden = true; };
    backdrop?.addEventListener("click", closeSheet);

    const select = (row, { open = false, scroll = true } = {}) => {
      if (!row) return;
      rows().forEach((r) => { r.classList.remove("selected"); r.setAttribute("aria-selected", "false"); });
      row.classList.add("selected");
      row.setAttribute("aria-selected", "true");
      current = row;
      if (scroll) row.scrollIntoView({ block: "nearest", behavior: "smooth" });
      htmx.ajax("GET", `/jobs/${row.dataset.id}/detail`, { target: "#detail-body", swap: "innerHTML" });
      if (open) openSheet();
    };
    const updateProgress = () => {
      const pct = total ? Math.round((cleared / total) * 100) : 0;
      const bar = $("#progress i");
      if (bar) bar.style.width = `${pct}%`;
      const label = $("#progress-label");
      if (label) label.textContent = `${cleared} of ${total} cleared`;
      $$("[data-left]").forEach((el) => { el.textContent = Math.max(0, total - cleared); });
    };
    const emptyState = () => {
      if (rows().length) return;
      $("#queue-empty").hidden = false;
      $("#detail-body").innerHTML = $("#detail-done").innerHTML;
      closeSheet();
    };
    const labels = { saved: "Saved to Nest", shortlisted: "Shortlisted", applied: "Marked as applied", dismissed: "Dismissed" };

    const triage = async (status, reason) => {
      const row = current;
      if (!row) return;
      $("#reason-menu")?.setAttribute("hidden", "");
      const list = rows();
      const idx = list.indexOf(row);
      const next = list[idx + 1] || list[idx - 1];
      const anchor = row.nextElementSibling;
      try {
        await post("/triage", { job_ids: row.dataset.ids, status, reason });
      } catch {
        toast("Couldn't save that. Is the portal still running?", { error: true });
        return;
      }
      row.classList.add("leaving");
      setTimeout(() => {
        row.remove();
        cleared += 1; updateProgress();
        if (next) select(next, { scroll: true }); else emptyState();
      }, 170);
      toast(`${labels[status]}${reason ? ` · ${reason}` : ""}`, {
        undo: async () => {
          await post("/triage", { job_ids: row.dataset.ids, status: "new" });
          row.classList.remove("leaving");
          queue.insertBefore(row, anchor && anchor.isConnected ? anchor : $("#queue-end"));
          $("#queue-empty").hidden = true;
          cleared -= 1; updateProgress();
          select(row);
        },
      });
    };

    queue.addEventListener("click", (e) => {
      const row = e.target.closest(".jrow");
      if (row) select(row, { open: true, scroll: false });
    });
    document.addEventListener("click", (e) => {
      const t = e.target.closest("[data-triage]");
      if (t) { triage(t.dataset.triage, t.dataset.reason); return; }
      if (e.target.closest("[data-reasons-toggle]")) { $("#reason-menu")?.toggleAttribute("hidden"); return; }
      if (e.target.closest("[data-close-sheet]")) closeSheet();
      if (!e.target.closest("#reason-menu")) $("#reason-menu")?.setAttribute("hidden", "");
    });

    document.addEventListener("keydown", (e) => {
      if (typing(document.activeElement) || e.metaKey || e.ctrlKey || e.altKey) return;
      const list = rows();
      const i = list.indexOf(current);
      const menuOpen = $("#reason-menu") && !$("#reason-menu").hidden;
      if (menuOpen && /^[1-6]$/.test(e.key)) { $(`#reason-menu [data-key="${e.key}"]`)?.click(); return; }
      switch (e.key) {
        case "j": case "ArrowDown": e.preventDefault(); select(list[Math.min(i + 1, list.length - 1)]); break;
        case "k": case "ArrowUp": e.preventDefault(); select(list[Math.max(i - 1, 0)]); break;
        case "s": triage("saved"); break;
        case "l": triage("shortlisted"); break;
        case "a": triage("applied"); break;
        case "d": $("#reason-menu")?.toggleAttribute("hidden"); break;
        case "o": if (current) window.open(current.dataset.url, "_blank", "noopener"); break;
        case "Escape": $("#reason-menu")?.setAttribute("hidden", ""); closeSheet(); break;
        default: break;
      }
    });
    updateProgress();
    if (!narrow()) select(rows()[0], { scroll: false });
    emptyState();
  }

  /* ---------- global shortcuts ---------- */
  document.addEventListener("keydown", (e) => {
    if (typing(document.activeElement) || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === "?") { e.preventDefault(); openModal("shortcuts"); }
    else if (e.key === "/") { const s = $("[data-search]"); if (s) { e.preventDefault(); s.focus(); } }
    else if (e.key === "Escape") closeModals();
    else if (e.key === "g") {
      const go = (ev) => {
        const map = { o: "/", d: "/dawn", n: "/nest", e: "/explore", s: "/sources", p: "/profile" };
        if (map[ev.key]) location.href = map[ev.key];
      };
      document.addEventListener("keydown", go, { once: true });
    }
  });

  /* ---------- Nest board ---------- */
  const board = $("#board");
  if (board) {
    const drawer = $("#drawer");
    const backdrop = $("#drawer-backdrop");
    let dragged = null;
    const counts = () => $$(".col", board).forEach((c) => {
      const n = $$(".kcard", c).length;
      $(".n", c).textContent = n;
      $(".col-empty", c).hidden = n > 0;
    });
    const move = async (card, status) => {
      const from = card.closest(".col").dataset.status;
      if (from === status) return;
      const target = $(`.col[data-status="${status}"] .col-body`, board);
      try { await post(`/nest/${card.dataset.id}`, { status }); }
      catch { toast("Couldn't move that card.", { error: true }); return; }
      if (target) target.prepend(card); else card.remove();
      counts();
      const label = $(`.col[data-status="${status}"]`, board)?.dataset.label || status;
      toast(`Moved to ${label}`, {
        undo: async () => {
          await post(`/nest/${card.dataset.id}`, { status: from });
          $(`.col[data-status="${from}"] .col-body`, board).prepend(card);
          counts();
        },
      });
    };
    board.addEventListener("dragstart", (e) => {
      dragged = e.target.closest(".kcard");
      if (!dragged) return;
      dragged.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
    });
    board.addEventListener("dragend", () => { dragged?.classList.remove("dragging"); $$(".col", board).forEach((c) => c.classList.remove("over")); });
    board.addEventListener("dragover", (e) => {
      const col = e.target.closest(".col");
      if (!col || !dragged) return;
      e.preventDefault();
      $$(".col", board).forEach((c) => c.classList.toggle("over", c === col));
    });
    board.addEventListener("drop", (e) => {
      const col = e.target.closest(".col");
      if (!col || !dragged) return;
      e.preventDefault();
      col.classList.remove("over");
      move(dragged, col.dataset.status);
    });

    const openDrawer = (id) => {
      htmx.ajax("GET", `/nest/${id}/drawer`, { target: "#drawer-body", swap: "innerHTML" });
      drawer.classList.add("open");
      backdrop.hidden = false;
    };
    const closeDrawer = () => { drawer.classList.remove("open"); backdrop.hidden = true; };
    board.addEventListener("click", (e) => {
      const card = e.target.closest(".kcard");
      if (card && !e.target.closest("a")) openDrawer(card.dataset.id);
    });
    board.addEventListener("keydown", (e) => {
      const card = e.target.closest(".kcard");
      if (card && e.key === "Enter") openDrawer(card.dataset.id);
    });
    backdrop.addEventListener("click", closeDrawer);
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });
    document.addEventListener("click", async (e) => {
      if (e.target.closest("[data-close-drawer]")) closeDrawer();
      const save = e.target.closest("[data-save-note]");
      if (save) {
        const id = save.dataset.saveNote;
        try { await post(`/nest/${id}`, { note: $("#note").value }); toast("Note saved"); }
        catch { toast("Couldn't save the note.", { error: true }); }
        const card = $(`.kcard[data-id="${id}"]`, board);
        if (card) $(".has-note", card)?.toggleAttribute("hidden", !$("#note").value.trim());
      }
    });
    document.addEventListener("change", (e) => {
      const sel = e.target.closest("[data-move]");
      if (!sel) return;
      const card = $(`.kcard[data-id="${sel.dataset.move}"]`, board);
      if (card) move(card, sel.value);
    });
    counts();
  }

  /* ---------- sources: client-side company filter ---------- */
  const filter = $("[data-filter-table]");
  if (filter) {
    filter.addEventListener("input", () => {
      const q = filter.value.trim().toLowerCase();
      $$(filter.dataset.filterTable).forEach((tr) => { tr.hidden = q && !tr.textContent.toLowerCase().includes(q); });
    });
  }
})();
