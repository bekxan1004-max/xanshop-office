/* XAN SHOP V2 — Frontend Controller */
(function () {
  "use strict";

  const state = {
    data: null,
    catalog: null,
    selectedAgentId: "marketing-agent",
    selectedModel: "auto",
    selectedSkills: new Set(["marketing-campaign"]),
    inspectorDept: null,
    inspectorSpecId: null,
    briefingOn: false,
    deptFilter: "all",
    calcMode: "competitive",
    lastLooksSig: "",
    lastModelsSig: "",
  };

  const $ = (id) => document.getElementById(id);
  const fmtSum = (n) => Number(n || 0).toLocaleString("ru-RU") + " so'm";

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  let office3d = null;

  function initTabs() {
    document.querySelectorAll(".nav-tab").forEach((btn) => {
      btn.addEventListener("click", () => {
        const target = btn.dataset.tab;
        document.querySelectorAll(".nav-tab").forEach((b) => b.classList.toggle("active", b === btn));
        document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === target));
        if (target === "tab-office" && office3d) {
          setTimeout(() => office3d.handleResize(), 40);
        }
      });
    });
  }

  async function fetchState() {
    try {
      const r = await fetch("/api/state");
      if (!r.ok) return;
      state.data = await r.json();
      renderState();
    } catch (e) {
      console.warn("State fetch xato:", e);
    }
  }

  async function fetchCatalog() {
    try {
      const r = await fetch("/api/ecc/catalog");
      if (!r.ok) return;
      state.catalog = await r.json();
      renderCatalog();
    } catch (e) {
      console.warn("Catalog fetch xato:", e);
    }
  }

  function renderState() {
    const d = state.data;
    if (!d) return;

    // Top Pinduoduo, OmniRoute & Currency Pills
    const conn = d.connections || {};
    const pddDot = $("pdd-dot");
    const pddLabel = $("pdd-label");
    if (pddDot && pddLabel) {
      if (conn.pdd) {
        pddDot.className = "dot";
        pddLabel.textContent = conn.pdd_user_id ? `PDD • ${conn.pdd_user_id}` : "Pinduoduo • Ulandi";
      } else {
        pddDot.className = "dot warn";
        pddLabel.textContent = "Pinduoduo • Ulash";
      }
    }

    const omni = d.omniroute || {};
    const dot = $("omni-dot");
    if (omni.online && (omni.models_count || 0) > 0) {
      dot.className = "dot";
      $("omni-label").textContent = `OmniRoute • ${omni.models_count} model`;
    } else if (omni.online) {
      dot.className = "dot warn";
      $("omni-label").textContent = "OmniRoute • sozlanmoqda";
    } else {
      dot.className = "dot off";
      $("omni-label").textContent = "OmniRoute • uzilgan";
    }

    const rates = d.rates || {};
    $("rates-pill").textContent = `1¥=${rates.cny_uzs || 1680}`;

    // 4 Compact KPI Cards
    const orders = d.orders || [];
    const paidOrders = orders.filter((o) => ["paid", "ordered_cn", "arrived", "completed"].includes(o.status));
    const totalProfit = paidOrders.reduce((s, o) => s + Number(o.profit_uzs || 0), 0);
    $("kpi-orders-val").textContent = `${orders.length} ta`;
    $("kpi-orders-sub").textContent = paidOrders.length
      ? `${paidOrders.length} to'langan • ${fmtSum(totalProfit)} foyda`
      : "50% oldindan to'lov himoyasi";

    const looks = d.looks || [];
    $("kpi-looks-val").textContent = `${looks.length} ta look`;
    const activeLooks = looks.filter((l) => l.status === "posted" || l.video_path).length;
    $("kpi-looks-sub").textContent = `${activeLooks} ta V3 Reels tayyor • Studio Beat (TTS siz)`;

    const eccSum = d.ecc_summary || {};
    const graph = d.graphify || {};
    $("kpi-ai-val").textContent = `${eccSum.agents_count || 15} agent / ${eccSum.skills_count || 25} skill`;
    $("kpi-ai-sub").textContent = `Graphify (${graph.modules || 21} modul) • ~80% token tejash`;

    // Customs $200 Monthly Tracker
    const estUsedUsd = Math.round(paidOrders.reduce((s, o) => s + Number(o.goods_cost_uzs || 0), 0) / Math.max(1, rates.usd_uzs || 12150));
    $("kpi-cargo-val").textContent = `$${estUsedUsd} / $200`;
    $("kpi-cargo-sub").textContent = "TUJJOR-AVIA ($9.5/kg) • Door-to-Door ($9.5/kg)";

    // Live 3D Office Update
    if (office3d) {
      office3d.updateState(d);
    }

    // Bottom Ticker
    const logs = d.logs || [];
    if (logs.length > 0) {
      const top = logs[0];
      $("ticker-msg").textContent = `[${top.agent_id}] ${top.action} ${top.detail ? "— " + top.detail : ""}`;
    }

    // Update Inspector if open (refresh status only without wiping user inputs)
    if (state.inspectorDept) {
      populateInspector(state.inspectorDept, true);
    }

    renderModelSelectors(d.available_models || (omni && omni.models) || []);
    renderLooks(looks);
    renderCompetitorIntel(d);
    renderOrders(orders, d.bank_transactions || []);
    renderSettingsModal(d);
  }

  function renderModelSelectors(models) {
    if (!Array.isArray(models) || !models.length) return;
    const sig = models.map((m) => (typeof m === "string" ? m : m.id)).join("|");
    if (sig === state.lastModelsSig) return;
    state.lastModelsSig = sig;
    const optsHtml = models
      .map((m) => {
        const id = typeof m === "string" ? m : m.id;
        const label = (typeof m === "object" && m.label) ? m.label : id;
        return `<option value="${escapeHtml(id)}">${escapeHtml(label)}</option>`;
      })
      .join("");
    ["insp-model-select", "ecc-model-select"].forEach((selId) => {
      const sel = $(selId);
      if (!sel) return;
      const prev = sel.value || state.selectedModel || "auto";
      sel.innerHTML = optsHtml;
      if ([...sel.options].some((o) => o.value === prev)) {
        sel.value = prev;
      }
    });
  }

  function renderCompetitorIntel(d, customAnalysis = null) {
    const out = $("comp-analysis-output");
    if (!out) return;
    const w = d.weather || {};
    const strat = d.creative_strategy || {};
    const badge = $("weather-horizon-badge");
    if (badge && w.city) {
      badge.textContent = `${w.city}: bugun ${w.temp_c}°C → 5–10 kunda ~${w.future_temp_c || w.temp_c}°C (${w.season_uz})`;
    }
    const profiles = d.competitor_profiles || {};
    const rep = customAnalysis || d.latest_insta_analysis || profiles._tima_shop;
    if (!rep) return;

    const aiRec = rep.ai_recommendations || {};
    const hooksHtml = (rep.hook_patterns || [])
      .map((h) => `<span class="badge" style="margin:2px">${escapeHtml(h)}</span>`)
      .join("");

    out.innerHTML = `
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:8px">
        <div class="card" style="padding:9px;background:rgba(15,23,42,.65)">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
            <b>🎯 ${escapeHtml(rep.handle || "@_tima_shop")}</b>
            <span class="badge ok">${escapeHtml(rep.provider || "Benchmark")}</span>
          </div>
          <div style="color:var(--text-3)">${escapeHtml(rep.stats_snapshot || "")}</div>
          <div style="margin-top:4px;color:var(--text-2)"><b>Bio:</b> ${escapeHtml(rep.bio_formula || "")}</div>
        </div>
        <div class="card" style="padding:9px;background:rgba(15,23,42,.65)">
          <b>💬 Opisaniya & Koment Triggerlari:</b>
          <div style="margin-top:4px;color:var(--text-2)">${escapeHtml(rep.opisaniya_formula || "")}</div>
          <div style="margin-top:4px;color:var(--accent)"><b>Koment:</b> ${escapeHtml(rep.koment_triggers || "")}</div>
        </div>
        <div class="card" style="padding:9px;background:rgba(15,23,42,.65)">
          <b>🎵 Hooklar & Zvuk (Reels):</b>
          <div style="margin-top:4px">${hooksHtml}</div>
          <div style="margin-top:4px;color:var(--text-2)"><b>Zvuk:</b> ${escapeHtml(rep.zvuk_style || "")}</div>
        </div>
        <div class="card" style="padding:9px;background:rgba(15,23,42,.65)">
          <b>💰 Narx, 5–10 Kunlik Ob-Havo & Og'dirish:</b>
          <div style="margin-top:4px;color:var(--text-2)">${escapeHtml(rep.narx_psychology || "")}</div>
          <div style="margin-top:4px;color:#34d399">${escapeHtml(rep.xan_shop_counter_strategy || strat.clothing_advice || "")}</div>
        </div>
      </div>
      ${
        aiRec.winning_hook
          ? `<div class="card" style="padding:9px;border-left:3px solid #ec4899;background:rgba(236,72,153,0.08)">
               <b>⚡ Insta Tahlilchi AI Tavsiyasi:</b>
               <div>• <b>Kuchli Hook:</b> ${escapeHtml(aiRec.winning_hook)}</div>
               <div>• <b>Caption/CTA:</b> ${escapeHtml(aiRec.caption_cta || "")}</div>
               <div>• <b>Odamlarni og'dirish:</b> ${escapeHtml(aiRec.persuasion_angle || "")}</div>
             </div>`
          : ""
      }`;
  }

  function renderCatalog() {
    const c = state.catalog;
    if (!c) return;
    $("ecc-count-badge").textContent = `${c.agents_count} XAN SHOP Mutaxassisi • ${c.skills_count} Skill`;

    const agents = (c.agents || []).filter((a) => state.deptFilter === "all" || a.department === state.deptFilter);
    const agWrap = $("ecc-agents-grid");
    agWrap.innerHTML = agents
      .map(
        (a) => `
      <div class="spec-card ${state.selectedAgentId === a.id ? "selected" : ""}" data-agent="${escapeHtml(a.id)}">
        <div class="spec-name">${escapeHtml(a.name)}</div>
        <div class="spec-dept">${escapeHtml(a.department_uz || a.department)}</div>
        <div class="spec-desc">${escapeHtml(a.description)}</div>
      </div>`
      )
      .join("");

    agWrap.querySelectorAll(".spec-card").forEach((el) => {
      el.addEventListener("click", () => {
        state.selectedAgentId = el.dataset.agent;
        renderCatalog();
      });
    });

    const skillsWrap = $("ecc-skills-chips");
    skillsWrap.innerHTML = (c.skills || [])
      .map(
        (s) => `
      <button type="button" class="skill-chip ${state.selectedSkills.has(s.id) ? "selected" : ""}"
        title="${escapeHtml(s.description)}" data-skill="${escapeHtml(s.id)}">
        ${escapeHtml(s.category)}: ${escapeHtml(s.name)}
      </button>`
      )
      .join("");

    skillsWrap.querySelectorAll(".skill-chip").forEach((el) => {
      el.addEventListener("click", () => {
        const sid = el.dataset.skill;
        if (state.selectedSkills.has(sid)) state.selectedSkills.delete(sid);
        else state.selectedSkills.add(sid);
        el.classList.toggle("selected");
      });
    });

    const curAgent = (c.agents || []).find((a) => a.id === state.selectedAgentId);
    $("selected-agent-pill").textContent = curAgent ? curAgent.name : state.selectedAgentId;
  }

  function populateInspector(deptId, isRefresh = false) {
    const deptChanged = state.inspectorDept !== deptId;
    state.inspectorDept = deptId;
    const drawer = $("inspector-drawer");
    drawer.classList.add("open");

    const agents = (state.data && state.data.agents) || [];
    const core = agents.find((a) => a.agent_id === deptId || a.id === deptId) || {
      id: deptId,
      name: deptId,
      status: "idle",
      current_task: "Tayyor",
      tasks_done: 0,
      version: "v3.0",
      level: 10,
      xp: 1000,
      learnings: [],
    };
    const def = (window.XanVirtualOffice3D && window.XanVirtualOffice3D.AGENT_DEFS.find((x) => x.id === deptId)) || {};

    $("insp-name").textContent = `${def.label || core.name || deptId} (${core.version || "v3.0"})`;
    $("insp-role").textContent = `${core.mastery_title || "10-Yillik Pro Ekspert"} • ${def.role || core.role || "AI Bo'lim"}`;
    $("insp-status").textContent = core.status === "working" ? "🟢 Ishlamoqda" : "🔵 Tayyor (24/7)";
    $("insp-task").textContent = core.current_task || "Vazifa kutilmoqda";
    $("insp-done").textContent = `${core.tasks_done || 0} ta vazifa • Lvl ${core.level || 10} (${core.xp || 1000} XP)`;

    if (isRefresh && !deptChanged) {
      return;
    }

    const learnings = Array.isArray(core.learnings) ? core.learnings : [];
    const learningsHtml = learnings.length
      ? `<div style="padding:8px 10px;border-radius:9px;background:rgba(16,185,129,.08);border:1px solid rgba(16,185,129,.3);margin-bottom:8px;">
           <div style="font-size:11.5px;font-weight:700;color:#34d399;margin-bottom:4px">🧠 O'z-o'zini Rivojlantirish Xotirasi (V3 Self-Learning):</div>
           ${learnings
             .slice(-4)
             .map((l) => `<div style="font-size:11px;color:var(--text-2);margin-bottom:3px">• ${escapeHtml(l)}</div>`)
             .join("")}
         </div>`
      : "";

    const allSpecs = (state.catalog && state.catalog.agents) || [];
    const specialists = allSpecs.filter((x) => x.department === deptId);
    const activeSpecId =
      (specialists.some((s) => s.id === state.inspectorSpecId) ? state.inspectorSpecId : null) ||
      (specialists[0] ? specialists[0].id : deptId);
    state.inspectorSpecId = activeSpecId;

    $("insp-specialists").innerHTML =
      learningsHtml +
      (specialists.length
        ? specialists
            .map(
              (s) => `
        <div class="insp-spec-item" data-pick-spec="${escapeHtml(s.id)}" style="cursor:pointer;padding:7px 9px;border-radius:9px;background:${s.id === activeSpecId ? "rgba(56,189,248,.16)" : "rgba(15,23,42,.75)"};border:1px solid ${s.id === activeSpecId ? "var(--accent)" : "var(--border)"};margin-bottom:6px;">
          <div style="font-size:12px;font-weight:700">${escapeHtml(s.name)}</div>
          <div style="font-size:11px;color:var(--text-3)">${escapeHtml(s.description)}</div>
        </div>`
            )
            .join("")
        : `<div style="font-size:11.5px;color:var(--text-3)">Bo'lim V3 avtonom rejimda ishlamoqda</div>`);

    const specSel = $("insp-spec-select");
    if (specSel) {
      const listForSelect = specialists.length ? specialists : allSpecs;
      specSel.innerHTML = listForSelect.length
        ? listForSelect.map((s) => `<option value="${escapeHtml(s.id)}">${escapeHtml(s.name)}</option>`).join("")
        : `<option value="${escapeHtml(deptId)}">${escapeHtml(def.label || deptId)}</option>`;
      specSel.value = activeSpecId;
    }

    $("insp-specialists").querySelectorAll("[data-pick-spec]").forEach((el) => {
      el.addEventListener("click", () => {
        state.inspectorSpecId = el.dataset.pickSpec;
        if (specSel) specSel.value = state.inspectorSpecId;
        $("insp-specialists").querySelectorAll("[data-pick-spec]").forEach((card) => {
          const isSel = card.dataset.pickSpec === state.inspectorSpecId;
          card.style.borderColor = isSel ? "var(--accent)" : "var(--border)";
          card.style.background = isSel ? "rgba(56,189,248,.16)" : "rgba(15,23,42,.75)";
        });
      });
    });
  }

  function openLookModal(look) {
    const rawVid = look.video_file || look.video_path || look.mp4_path || "";
    const videoFile = rawVid ? rawVid.split(/[\\/]/).pop() : "";
    const rawImg = look.photo_file || look.photo_path || look.image_path || "";
    const imgFile = rawImg ? rawImg.split(/[\\/]/).pop() : "";
    const hasVideo = look.video_exists !== false && Boolean(videoFile);
    const vUrl = look.video_url || (videoFile ? `/media/${encodeURIComponent(videoFile)}` : "");
    const pUrl = look.photo_url || (imgFile ? `/media/${encodeURIComponent(imgFile)}` : "");

    let items = [];
    try {
      items = typeof look.items_json === "string" ? JSON.parse(look.items_json) : (look.items_json || []);
    } catch (_) {
      items = [];
    }

    const mediaHtml = hasVideo && videoFile.toLowerCase().endsWith(".mp4")
      ? `<div style="position:relative;background:#020617;border-radius:12px;overflow:hidden">
           <video id="modal-look-video" style="width:100%;max-height:420px;display:block;background:#020617" controls autoplay loop playsinline preload="auto" poster="${pUrl}">
             <source src="${vUrl}?t=${look.created_at || 1}" type="video/mp4" />
             Brauzeringiz MP4 videoni qo'llab-quvvatlamaydi.
           </video>
           <div id="modal-video-err" style="display:none;padding:12px;text-align:center;color:#fbbf24;font-size:12px">
             ⚠️ Video yuklanmadi — <a href="${vUrl}" target="_blank" style="color:#38bdf8">to'g'ridan-to'g'ri ochish</a>
           </div>
         </div>`
      : hasVideo && videoFile
      ? `<img style="width:100%;max-height:360px;object-fit:contain;border-radius:12px;background:#020617" src="${vUrl}" alt="${escapeHtml(look.title)}" />`
      : pUrl
      ? `<img style="width:100%;max-height:360px;object-fit:contain;border-radius:12px;background:#020617" src="${pUrl}" alt="${escapeHtml(look.title)}" />`
      : `<div style="padding:20px;text-align:center;color:var(--text-3)">Media topilmadi</div>`;

    const itemsHtml = items.length
      ? items
          .map(
            (it) =>
              `<div style="display:flex;justify-content:space-between;font-size:12px;padding:6px 0;border-bottom:1px solid var(--border)"><span>${escapeHtml(it.name || "-")}</span><span style="color:var(--accent)">¥${it.price_cny || it.cny || "-"} • ${it.weight_kg || "-"} kg</span></div>`
          )
          .join("")
      : `<div style="font-size:12px;color:var(--text-3)">Tarkib ma'lumotlari mavjud emas</div>`;

    const captionHtml = look.insta_caption
      ? `<div class="ai-output" style="max-height:180px;margin-top:8px">${escapeHtml(look.insta_caption)}</div>`
      : "";

    openModal(
      `👔 ${look.title}`,
      `<div style="display:grid;gap:12px">
        ${mediaHtml}
        <div class="card"><b>To'plam tarkibi (${items.length} ta buyum):</b>${itemsHtml}</div>
        ${captionHtml}
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap">
          ${hasVideo ? `<a class="btn-primary btn-sm" href="${vUrl}" download>📥 .MP4 Videoni Yuklab Olish</a>` : `<span></span>`}
          <button type="button" class="btn-secondary" id="btn-modal-del-look">🗑️ Ushbu Lookni O'chirish</button>
        </div>
      </div>`
    );
    const vidEl = $("modal-look-video");
    if (vidEl) {
      vidEl.addEventListener("error", () => {
        const errBox = $("modal-video-err");
        if (errBox) errBox.style.display = "block";
      });
    }
    const delBtn = $("btn-modal-del-look");
    if (delBtn) {
      delBtn.addEventListener("click", async () => {
        delBtn.disabled = true;
        await fetch(`/api/looks/${look.id}/delete`, { method: "POST" });
        $("v2-modal").classList.remove("open");
        state.lastLooksSig = "";
        fetchState();
      });
    }
  }

  function renderLooks(looks) {
    const grid = $("looks-grid");
    const sig = looks.map((l) => `${l.id}:${l.photo_exists}:${l.video_exists}:${l.active}:${l.created_at}`).join("|");
    if (sig === state.lastLooksSig && grid.children.length > 0) return;
    state.lastLooksSig = sig;

    if (!looks.length) {
      grid.innerHTML = `<div class="card" style="grid-column:1/-1;text-align:center;padding:28px;color:var(--text-2)">
        <div style="font-size:28px;margin-bottom:8px">📦</div>
        <div style="font-size:15px;font-weight:700;margin-bottom:4px">Ombor toza — Pinduoduo ulanishiga tayyor</div>
        <div style="font-size:12.5px;color:var(--text-3)">Oldingi test looklar o'chirildi. Yangi look yaratish uchun yuqoridagi tugmani bosing.</div>
      </div>`;
      return;
    }
    const visible = looks.slice(0, 12);
    grid.innerHTML = visible
      .map((l) => {
        const rawVid = l.video_file || l.video_path || l.mp4_path || "";
        const videoFile = rawVid ? rawVid.split(/[\\/]/).pop() : "";
        const rawImg = l.photo_file || l.photo_path || l.image_path || "";
        const imgFile = rawImg ? rawImg.split(/[\\/]/).pop() : "";
        const hasVideo = l.video_exists !== false && Boolean(videoFile) && videoFile.toLowerCase().endsWith(".mp4");
        const hasImg = l.photo_exists !== false && Boolean(imgFile);
        const vUrl = l.video_url || (videoFile ? `/media/${encodeURIComponent(videoFile)}` : "");
        const pUrl = l.photo_url || (imgFile ? `/media/${encodeURIComponent(imgFile)}` : "");

        const visualHtml = hasVideo
          ? `<div style="position:relative;background:#020617">
               <video class="look-media" controls playsinline preload="metadata" poster="${hasImg ? pUrl : ""}" style="width:100%;display:block;object-fit:contain;background:#020617">
                 <source src="${vUrl}?t=${l.created_at || 1}" type="video/mp4" />
               </video>
             </div>`
          : hasImg
          ? `<img class="look-media" src="${pUrl}" alt="${escapeHtml(l.title)}" loading="lazy" />`
          : `<div class="look-media" style="display:grid;place-items:center;color:var(--text-3)">👔 ${escapeHtml(l.title)}</div>`;

        const badgeClass = l.active === 0 ? "warn" : "ok";
        const badgeText = l.ig_media_id ? "IG Joylangan" : hasVideo ? "🎬 MP4 Tayyor" : "Tayyor Look";
        const dlBtn = hasVideo
          ? `<a class="btn-secondary btn-sm" href="${vUrl}" download>📥 MP4</a>`
          : "";
        return `
        <div class="look-card">
          ${visualHtml}
          <div class="look-body">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:6px">
              <strong style="font-size:13.5px;line-height:1.3">#${l.id} ${escapeHtml(l.title)}</strong>
              <span class="badge ${badgeClass}">${badgeText}</span>
            </div>
            <div style="font-size:11.5px;color:var(--text-3)">O'lcham: ${escapeHtml(l.sizes || "-")} • Rang: ${escapeHtml(l.colors || "-")}</div>
            <div style="display:flex;justify-content:space-between;font-size:12px;margin-top:2px;padding-top:6px;border-top:1px solid var(--border)">
              <span>100%: <b>${fmtSum(l.prepay_uzs)}</b></span>
              <span style="color:var(--accent)">50%: <b>${fmtSum(l.prepay_50_uzs)}</b></span>
            </div>
            <div class="look-actions">
              <button type="button" class="btn-primary btn-sm" data-view-look="${l.id}">🎬 Katta Ekran & Tarkib</button>
              ${dlBtn}
            </div>
          </div>
        </div>`;
      })
      .join("");

    grid.querySelectorAll("[data-view-look]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const lid = Number(btn.dataset.viewLook);
        const found = visible.find((x) => x.id === lid);
        if (found) openLookModal(found);
      });
    });
  }

  function renderOrders(orders, bankTx) {
    const tbody = $("orders-tbody");
    tbody.innerHTML = orders.length
      ? orders
          .slice(0, 20)
          .map(
            (o) => `
        <tr>
          <td><b>#${o.id}</b></td>
          <td>${escapeHtml(o.full_name || o.username || "Mijoz")}</td>
          <td>${escapeHtml(o.size || "-")} / ${escapeHtml(o.color || "-")}</td>
          <td>${fmtSum(o.prepay_due)}</td>
          <td><span class="badge ${o.status === "paid" ? "ok" : "warn"}">${escapeHtml(o.status)}</span></td>
          <td style="font-size:11px;color:var(--text-3)">${escapeHtml(o.address || "-")}</td>
          <td><button type="button" class="btn-secondary btn-sm" data-pdd-order="${o.id}">🛒 Tayyorlash</button></td>
        </tr>`
          )
          .join("")
      : `<tr><td colspan="7" style="text-align:center;color:var(--text-3)">Hozircha buyurtmalar yo'q — Telegram bot va Userbot orqali kelgan zakazlar shu yerda ko'rinadi.</td></tr>`;

    tbody.querySelectorAll("[data-pdd-order]").forEach((btn) => {
      btn.addEventListener("click", () => openOrderPddPrepModal(Number(btn.dataset.pddOrder)));
    });

    const txBody = $("bank-tx-list");
    txBody.innerHTML = bankTx.length
      ? bankTx
          .slice(0, 8)
          .map(
            (t) => `
        <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border);font-size:12px">
          <div><b>${fmtSum(t.amount_uzs)}</b> <span style="color:var(--text-3)">(*${escapeHtml(t.card_last4 || "----")})</span></div>
          <span class="badge ${t.matched_order_id ? "ok" : ""}">${t.matched_order_id ? "Buyurtma #" + t.matched_order_id : "Kutilmoqda"}</span>
        </div>`
          )
          .join("")
      : `<div style="font-size:12px;color:var(--text-3)">Bank SMS/Webhook kirim xabarlari avtomatik tahlil qilinadi (soxta cheklarga qarshi).</div>`;
  }

  function renderSettingsModal(d) {
    const conn = d.connections || {};
    const cardLabel = conn.card_last4
      ? `HUMO Bank Kartasi (*${conn.card_last4} • ${conn.card_owner || "POLVONOV BEKMUROD"})`
      : "HUMO Bank Kartasi (AI Hisobchi)";
    const items = [
      [cardLabel, Boolean(conn.bank_card), null],
      ["Telegram Botlar (@XanShopUzBot / Admin)", Boolean(conn.tg_bots || conn.sales_bot), null],
      ["Userbot (@Bekshop_style)", Boolean(conn.userbot), null],
      ["OmniRoute AI Router", Boolean(d.omniroute && d.omniroute.online), null],
      ["Pinduoduo API / Sessiya", Boolean(conn.pdd || conn.pinduoduo), "pdd"],
      ["Instagram Graph API (@xan_styles)", Boolean(conn.instagram), null],
    ];
    $("settings-conn-list").innerHTML = items
      .map(
        ([label, ok, action]) => `
      <div style="display:flex;justify-content:space-between;align-items:center;padding:9px 12px;background:rgba(15,23,42,.7);border:1px solid var(--border);border-radius:10px;margin-bottom:8px;gap:8px">
        <span style="font-size:13px">${escapeHtml(label)}</span>
        <div style="display:flex;align-items:center;gap:6px">
          <span class="badge ${ok ? "ok" : "warn"}">${ok ? "Ulangan" : "Ulanmagan"}</span>
          ${action === "pdd" ? `<button type="button" class="btn-secondary btn-sm" id="btn-open-pdd-from-settings">Sozlash</button>` : ""}
        </div>
      </div>`
      )
      .join("");
    const openBtn = $("btn-open-pdd-from-settings");
    if (openBtn) {
      openBtn.addEventListener("click", () => {
        $("settings-modal").classList.remove("open");
        openPddModal();
      });
    }
  }

  function openModal(title, htmlBody) {
    $("v2-modal-title").textContent = title;
    $("v2-modal-body").innerHTML = htmlBody;
    $("v2-modal").classList.add("open");
  }

  function handleWallAction(actionId) {
    const d = state.data || {};
    if (actionId === "doska") {
      const looks = d.looks || [];
      const orders = d.orders || [];
      openModal(
        "📋 XAN SHOP — Ish Doskasi (Kanban)",
        `<div class="kanban-cols">
          <div class="kanban-col"><strong>1. Skaut & G'oya</strong><div class="kanban-card">Pinduoduo trend kiyimlar saralanmoqda</div></div>
          <div class="kanban-col"><strong>2. Reels Studio</strong>${looks.slice(0, 3).map((l) => `<div class="kanban-card">${escapeHtml(l.title)}</div>`).join("")}</div>
          <div class="kanban-col"><strong>3. Sotuv & Chek</strong>${orders.slice(0, 3).map((o) => `<div class="kanban-card">#${o.id} — ${escapeHtml(o.status)}</div>`).join("") || `<div class="kanban-card">Mijozlar kutilmoqda</div>`}</div>
          <div class="kanban-col"><strong>4. Kargo & Toshkent</strong><div class="kanban-card">TUJJOR-AVIA ($9.5/kg) / Door ($9.5/kg)</div></div>
        </div>`
      );
    } else if (actionId === "reyting") {
      const agents = [...((d.agents) || [])].sort((a, b) => (b.tasks_done || 0) - (a.tasks_done || 0));
      openModal(
        "📊 Bo'limlar Samaradorlik Reytingi",
        agents
          .map(
            (a, idx) => `
          <div style="display:flex;justify-content:space-between;padding:10px 12px;border-bottom:1px solid var(--border)">
            <div><b>#${idx + 1} ${escapeHtml(a.name)}</b> <span style="color:var(--text-3);font-size:12px">(${escapeHtml(a.status)})</span></div>
            <span class="badge ok">${a.tasks_done || 0} ta vazifa</span>
          </div>`
          )
          .join("")
      );
    } else if (actionId === "server") {
      const omni = d.omniroute || {};
      const graph = d.graphify || {};
      openModal(
        "🖥️ Server & OmniRoute AI Gateway",
        `<div style="display:grid;gap:10px">
          <div class="card"><b>OmniRoute Holati:</b> ${omni.online ? "🟢 Faol (" + omni.models_count + " model)" : "🔴 O'chiq"}<br><small style="color:var(--text-3)">Manzil: ${escapeHtml(omni.base_url || "http://localhost:20128/v1")}</small></div>
          <div class="card"><b>Graphify Kesh & AST Xarita:</b> ${graph.modules || 21} modul, ${graph.functions || 78} funksiya (AI so'rovlarda ~80% token tejash)</div>
          <div class="card"><b>Tavsiya Modellari:</b> ${(omni.sample_models || []).slice(0, 6).map((m) => `<span class="badge" style="margin:2px">${escapeHtml(m)}</span>`).join("")}</div>
        </div>`
      );
    }
  }

  async function runEccTask(agentId, skillIds, prompt, model, btnEl, outEl) {
    if (!prompt || !prompt.trim()) {
      outEl.style.display = "block";
      outEl.innerHTML = `<span class="badge warn">Diqqat</span> Iltimos, vazifa matnini yozing!`;
      return;
    }
    btnEl.disabled = true;
    const orig = btnEl.textContent;
    btnEl.textContent = "⏳ AI ishlamoqda...";
    outEl.style.display = "block";
    outEl.textContent = `Tanlangan model (${model || "auto"}) va agent (${agentId}) ishga tushirildi...`;
    try {
      const r = await fetch("/api/ecc/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent_id: agentId, skills: skillIds, prompt, model: model || "auto" }),
      });
      const res = await r.json();
      if (res.ok) {
        const msTag = res.duration_ms ? ` <span class="badge">${(res.duration_ms / 1000).toFixed(1)}s</span>` : "";
        outEl.innerHTML = `<div style="margin-bottom:8px;display:flex;gap:5px;flex-wrap:wrap"><span class="badge ok">${escapeHtml(res.provider || "OmniRoute")}</span> <span class="badge">${escapeHtml(res.agent_name || res.agent_id)}</span>${msTag}</div><div style="white-space:pre-wrap">${escapeHtml(res.answer)}</div>`;
      } else {
        outEl.innerHTML = `<span class="badge warn">Xatolik</span> ${escapeHtml(res.error || "Javob olinmadi")}`;
      }
      fetchState();
    } catch (e) {
      outEl.textContent = "Server bilan aloqa xatosi: " + e.message;
    } finally {
      btnEl.disabled = false;
      btnEl.textContent = orig;
    }
  }

  async function calcPrice() {
    const cny = $("calc-cny").value || "45+48+42";
    const weight = $("calc-kg").value || "1.3";
    const mode = state.calcMode || "competitive";
    try {
      const r = await fetch(`/api/calc?cny=${encodeURIComponent(cny)}&weight=${encodeURIComponent(weight)}&mode=${encodeURIComponent(mode)}`);
      const res = await r.json();
      const modeNames = {
        competitive: "Optimal 65% + 50k",
        safe_50: "Xavfsiz 50% (105%)",
        yatt_customs: "YaTT + Bojxona",
      };
      if ($("calc-mode-badge")) {
        $("calc-mode-badge").textContent = modeNames[mode] || "Jonli";
      }
      const yattNote =
        mode === "yatt_customs"
          ? `<div style="grid-column:1/-1;font-size:11.5px;color:var(--text-3);padding:6px 8px;border-radius:8px;background:rgba(56,189,248,0.08)">
               🏢 <b>YaTT + 1688 Optom (-25%):</b> Bojxona + 12% QQS zaxirasi: <b>${fmtSum(res.customs_uzs)}</b> • Soliq (${res.tax_percent}%): <b>${fmtSum(res.tax_uzs)}</b>
             </div>`
          : "";
      $("calc-result").innerHTML = `
        <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-top:10px">
          <div class="card" style="padding:10px"><small style="color:var(--text-3)">Sotuv narxi (100%, 50k/100k)</small><div style="font-size:16px;font-weight:800">${fmtSum(res.prepay_uzs)}</div><small style="color:var(--text-3)">Xitoy tannarx: ${fmtSum(res.goods_cost_uzs)}</small></div>
          <div class="card" style="padding:10px"><small style="color:var(--text-3)">50% Oldindan To'lov</small><div style="font-size:16px;font-weight:800;color:var(--accent)">${fmtSum(res.prepay_50_uzs)}</div><small style="color:var(--text-3)">Foyda: ${res.profit_percent ?? 65}% (${fmtSum(res.profit_uzs)})</small></div>
          <div class="card" style="padding:10px"><small style="color:var(--text-3)">Kargo (${weight} kg)</small><div style="font-size:15px;font-weight:700">${fmtSum(res.cargo_client_uzs)}</div></div>
          <div class="card" style="padding:10px"><small style="color:var(--text-3)">Jami Mijozga (Tovar + Kargo)</small><div style="font-size:15px;font-weight:800;color:#34d399">${fmtSum(res.total_client_uzs)}</div></div>
          ${yattNote}
        </div>`;
    } catch (e) {
      console.warn(e);
    }
  }

  function openCeoCommandModal(res) {
    const dirs = (res.directives || [])
      .map(
        (d) => `
      <div class="roadmap-step" style="border-left:3px solid #f59e0b">
        <div style="display:flex;justify-content:space-between;margin-bottom:3px">
          <b>🎯 ${escapeHtml(d.target_agent)}</b>
          <span class="badge ${d.priority === "yuqori" ? "warn" : "ok"}">${escapeHtml(d.priority || "faol")}</span>
        </div>
        <div>${escapeHtml(d.command)}</div>
        ${d.reason ? `<div style="font-size:11px;color:var(--text-3);margin-top:3px">Sabab: ${escapeHtml(d.reason)}</div>` : ""}
      </div>`
      )
      .join("");

    openModal(
      "🧠 Boshqaruvchi AI — Strategik Tahlil & Ijro Buyruqlari",
      `<div style="display:grid;gap:10px">
        <div class="card" style="padding:12px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
            <b>📊 Bozor & Narx Auditi</b>
            <span class="badge ok">${escapeHtml(res.provider || "OmniRoute")}</span>
          </div>
          <div style="font-size:12.5px;line-height:1.5;color:var(--text-1)">${escapeHtml(res.diagnosis || "")}</div>
        </div>
        <div class="card" style="padding:12px">
          <b>📘 Bojxona ($200 limit) & YaTT Rivojlanish Rejasi</b>
          <div style="font-size:12px;line-height:1.5;color:var(--text-2);margin-top:4px">${escapeHtml(res.customs_yatt_plan || "")}</div>
          ${res.growth_plan ? `<div style="font-size:12px;line-height:1.5;color:var(--accent);margin-top:6px">🚀 ${escapeHtml(res.growth_plan)}</div>` : ""}
        </div>
        <div>
          <small style="color:var(--text-3);font-weight:700;display:block;margin-bottom:6px">Bo'limlarga yuborilgan va ishga tushirilgan buyruqlar:</small>
          <div style="display:grid;gap:7px">${dirs}</div>
        </div>
        <div style="display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap;padding-top:6px">
          <button type="button" class="btn-secondary" id="btn-ceo-apply-comp">💰 Optimal narxni qo'llash (65% foyda + 50k yaxlitlash)</button>
        </div>
      </div>`
    );

    const applyBtn = $("btn-ceo-apply-comp");
    if (applyBtn) {
      applyBtn.addEventListener("click", async () => {
        applyBtn.disabled = true;
        applyBtn.textContent = "⏳ Qo'llanmoqda...";
        const r = await fetch("/api/ceo/apply_pricing", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ mode: "competitive" }),
        });
        const applied = await r.json();
        applyBtn.textContent = applied.ok ? "✅ 65% Optimal rejim saqlandi!" : "Xatolik";
        fetchState();
        calcPrice();
      });
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    initTabs();

    if (window.XanVirtualOffice3D) {
      office3d = window.XanVirtualOffice3D.create("virtual-office-canvas", "office-labels-layer", {
        onSelectAgent: (id) => populateInspector(id),
        onWallAction: (act) => handleWallAction(act),
      });
    }

    // Room Switcher Pills
    document.querySelectorAll(".room-pill").forEach((pill) => {
      pill.addEventListener("click", () => {
        document.querySelectorAll(".room-pill").forEach((p) => p.classList.toggle("active", p === pill));
        const room = pill.dataset.room;
        state.briefingOn = room === "briefing";
        $("btn-briefing").classList.toggle("active", state.briefingOn);
        if (office3d) {
          if (state.briefingOn) office3d.setBriefingMode(true);
          else {
            office3d.setBriefingMode(false);
            office3d.focusRoom(room);
          }
        }
      });
    });

    // Top HUD Controls
    $("office-search").addEventListener("input", (e) => {
      if (office3d) office3d.setSearch(e.target.value);
    });
    $("btn-view-iso").addEventListener("click", () => {
      if (office3d) {
        office3d.setBriefingMode(false);
        office3d.focusRoom("all");
      }
    });
    $("btn-view-top").addEventListener("click", () => {
      if (office3d) office3d.focusRoom("top");
    });

    const ceoBtn = $("btn-ceo-analyze");
    if (ceoBtn) {
      ceoBtn.addEventListener("click", async () => {
        ceoBtn.disabled = true;
        const orig = ceoBtn.textContent;
        ceoBtn.textContent = "⏳ Direktor tahlili...";
        try {
          const r = await fetch("/api/ceo/analyze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ apply_directives: true }),
          });
          const res = await r.json();
          if (office3d && office3d.triggerCeoCommandPulse) {
            office3d.triggerCeoCommandPulse();
          }
          if (res.ok) {
            $("ticker-msg").textContent = "🧠 Direktor: " + res.diagnosis;
            openCeoCommandModal(res);
          }
          fetchState();
        } finally {
          ceoBtn.disabled = false;
          ceoBtn.textContent = orig;
        }
      });
    }

    $("btn-briefing").addEventListener("click", async () => {
      state.briefingOn = !state.briefingOn;
      $("btn-briefing").classList.toggle("active", state.briefingOn);
      if (office3d) office3d.setBriefingMode(state.briefingOn);
      if (state.briefingOn) {
        try {
          const r = await fetch("/api/office/briefing", { method: "POST" });
          const res = await r.json();
          if (res.ok && res.summary) {
            $("ticker-msg").textContent = "📢 Brifing: " + res.summary;
          }
          fetchState();
        } catch (e) {}
      }
    });

    // Inspector Drawer Events
    $("insp-close").addEventListener("click", () => {
      state.inspectorDept = null;
      state.inspectorSpecId = null;
      $("inspector-drawer").classList.remove("open");
    });
    const inspSpecSel = $("insp-spec-select");
    if (inspSpecSel) {
      inspSpecSel.addEventListener("change", () => {
        state.inspectorSpecId = inspSpecSel.value;
      });
    }
    const inspModelSel = $("insp-model-select");
    if (inspModelSel) {
      inspModelSel.addEventListener("change", () => {
        state.selectedModel = inspModelSel.value;
      });
    }
    const eccModelSel = $("ecc-model-select");
    if (eccModelSel) {
      eccModelSel.addEventListener("change", () => {
        state.selectedModel = eccModelSel.value;
      });
    }
    const triggerInspRun = () => {
      const aid = ($("insp-spec-select") && $("insp-spec-select").value) || state.inspectorDept || "chief-of-staff";
      const mod = ($("insp-model-select") && $("insp-model-select").value) || state.selectedModel || "auto";
      runEccTask(aid, [], $("insp-prompt").value, mod, $("insp-run-btn"), $("insp-output"));
    };
    $("insp-run-btn").addEventListener("click", triggerInspRun);
    $("insp-prompt").addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        triggerInspRun();
      }
    });

    // Department Filter in Mutaxassislar Tab
    document.querySelectorAll("[data-dept-filter]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.deptFilter = btn.dataset.deptFilter;
        document.querySelectorAll("[data-dept-filter]").forEach((b) => b.classList.toggle("selected", b === btn));
        renderCatalog();
      });
    });

    // Quick Prompt Chips
    document.querySelectorAll("[data-quick-prompt]").forEach((btn) => {
      btn.addEventListener("click", () => {
        $("ecc-prompt-input").value = btn.dataset.quickPrompt;
        if (btn.dataset.quickAgent) {
          state.selectedAgentId = btn.dataset.quickAgent;
          renderCatalog();
        }
      });
    });

    $("ecc-run-btn").addEventListener("click", () => {
      const mod = ($("ecc-model-select") && $("ecc-model-select").value) || state.selectedModel || "auto";
      runEccTask(
        state.selectedAgentId,
        Array.from(state.selectedSkills),
        $("ecc-prompt-input").value,
        mod,
        $("ecc-run-btn"),
        $("ecc-run-output")
      );
    });

    // Look Generator & Clear Looks
    const genBtn = $("btn-generate-look");
    if (genBtn) {
      genBtn.addEventListener("click", async () => {
        genBtn.disabled = true;
        genBtn.textContent = "⏳ Yaratilmoqda...";
        try {
          await fetch("/api/run_pipeline", { method: "POST" });
          await fetchState();
        } finally {
          genBtn.disabled = false;
          genBtn.textContent = "🎬 +1 Look & Reels Yaratish";
        }
      });
    }
    const clearBtn = $("btn-clear-looks");
    if (clearBtn) {
      clearBtn.addEventListener("click", async () => {
        clearBtn.disabled = true;
        try {
          await fetch("/api/looks/clear", { method: "POST" });
          await fetchState();
        } finally {
          clearBtn.disabled = false;
        }
      });
    }

    const compBtn = $("btn-analyze-competitor");
    if (compBtn) {
      compBtn.addEventListener("click", async () => {
        const inp = $("comp-target-input");
        const target = (inp && inp.value.trim()) || "_tima_shop";
        compBtn.disabled = true;
        compBtn.textContent = "⏳ Tahlil qilinmoqda...";
        try {
          const r = await fetch("/api/trends/analyze_competitor", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ target }),
          });
          const res = await r.json();
          if (res.ok && res.analysis) {
            renderCompetitorIntel(state.data || {}, res.analysis);
          }
          await fetchState();
        } finally {
          compBtn.disabled = false;
          compBtn.textContent = "🔍 Tahlil Qilish";
        }
      });
    }

    function copyText(text, btn) {
      if (!navigator.clipboard) return;
      navigator.clipboard.writeText(text).then(() => {
        if (btn) {
          const orig = btn.textContent;
          btn.textContent = "✓ Nusxalandi";
          setTimeout(() => { btn.textContent = orig; }, 1400);
        }
      });
    }

    async function openPddModal() {
      openModal("🇨🇳 Pinduoduo Integratsiya Markazi", `<div class="card">Holat yuklanmoqda...</div>`);
      try {
        const r = await fetch("/api/pdd/status");
        const st = await r.json();
        const cargos = st.cargo_addresses || [];
        const sess = st.session || {};
        const addrSync = st.addresses_sync || {};
        const modeBadge = st.connected
          ? `<span class="badge ok">🟢 Ulangan (${escapeHtml(st.mode)})</span>`
          : `<span class="badge warn">🟡 Ulanmagan</span>`;

        $("v2-modal-body").innerHTML = `
          <div style="display:grid;gap:12px">
            <div class="card">
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;gap:8px;flex-wrap:wrap">
                <b>1. Shaxsiy Pinduoduo Akkaunt (Brauzer Sessiyasi — Bepul)</b>
                ${modeBadge}
              </div>
              <div style="font-size:12px;color:var(--text-2);line-height:1.55;margin-bottom:10px">
                Pinduoduo sizning O'zbekiston (<code>+998</code>) raqamingizni avtomatik aniqlaydi.<br>
                <b>Qadamlar:</b> 1) Tugmani bosing → Chrome ochiladi · 2) <code>998</code> yoniga 9 ta raqamingizni yozing ·
                3) <code>发送验证码</code> bosing va SMS kodni kiriting · 4) Shartnomaga rozilik berib kiring.
              </div>
              <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
                <button type="button" class="btn-primary" id="btn-pdd-browser-connect">${sess.connected ? "🔄 Sessiyani Yangilash" : "🚀 Chrome orqali +998 Kirish"}</button>
                <button type="button" class="btn-secondary" id="btn-pdd-test-live" ${st.connected ? "" : "disabled"}>🔍 Jonli Qidiruv + Wishlist Sinovi</button>
              </div>
              <div id="pdd-connect-msg" style="font-size:12px;color:var(--accent);margin-top:8px">${st.login_state && st.login_state.message ? escapeHtml(st.login_state.message) : (sess.user_id ? "Akkaunt ID: " + escapeHtml(sess.user_id) : "")}</div>
              <div id="pdd-otp-row" style="display:${st.login_state && (st.login_state.running || ["sms_sent", "waiting_user", "phone_filled", "waiting_login"].includes(st.login_state.status)) ? "flex" : "none"};gap:6px;margin-top:8px">
                <input id="inp-pdd-otp" class="form-control" maxlength="6" placeholder="SMS kod (4-6 raqam)" style="max-width:170px" />
                <button type="button" class="btn-primary btn-sm" id="btn-pdd-otp-send">✅ Kodni Kiritish</button>
              </div>
              <details style="margin-top:10px;padding-top:8px;border-top:1px solid var(--border)">
                <summary style="cursor:pointer;font-size:12px;font-weight:700;color:var(--text-2)">🔑 O'z Chrome / Telefon ilovangizdan sessiya ulash (muqobil usul)</summary>
                <div style="font-size:11.5px;color:var(--text-3);margin:6px 0;line-height:1.5">
                  Agar avtomatik Chrome’da SMS kelmasa: o'z Chrome’ingizda (yoki Pinduoduo App’da kirib Chrome’da) <code>mobile.yangkeduo.com</code> ga kiring → <b>F12 → Application → Cookies → mobile.yangkeduo.com</b> dan <code>PDDAccessToken</code> qiymatini (yoki <b>Console</b>’da <code>copy(document.cookie)</code>) olib pastga tashlang:
                </div>
                <textarea id="inp-pdd-session-raw" class="form-control" rows="2" placeholder="PDDAccessToken=...; pdd_user_id=..." style="font-size:11.5px;margin-bottom:6px"></textarea>
                <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
                  <button type="button" class="btn-secondary btn-sm" id="btn-pdd-import-session">💾 Sessiyani Saqlash & Ulash</button>
                  <button type="button" class="btn-secondary btn-sm" data-copy="copy(document.cookie)">📋 Console buyrug'ini nusxalash</button>
                </div>
              </details>
              <div id="pdd-test-out" class="ai-output" style="display:none;margin-top:8px;max-height:140px"></div>
            </div>

            <div class="card">
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;gap:8px;flex-wrap:wrap">
                <b>2. Pinduoduo'ga Ulash Uchun 2 ta Kargo Manzili</b>
                <button type="button" class="btn-secondary btn-sm" id="btn-pdd-sync-addr" ${sess.connected ? "" : "disabled"}>✈️ Manzillarni Tekshirish</button>
              </div>
              <div style="font-size:11.5px;color:var(--text-3);margin-bottom:8px">
                ${addrSync.matched_codes && addrSync.matched_codes.length ? "Topilgan omborlar: " + escapeHtml(addrSync.matched_codes.join(", ")) : "Skaut Look yig'ganda Wishlist (收藏) ga saqlaydi, buyurtmada shu 2 manzildan mosini tanlaydi."}
              </div>
              <div style="display:grid;gap:8px">
                ${cargos.map((c) => `
                  <div style="padding:9px;border-radius:10px;background:rgba(15,23,42,.7);border:1px solid var(--border);font-size:11.5px">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
                      <b>${escapeHtml(c.name)} (${escapeHtml(c.client_id)})</b>
                      <span class="badge">${escapeHtml(c.route_rule || "")}</span>
                    </div>
                    <div style="color:var(--text-2)">收件人: <code>${escapeHtml(c.cn_recipient)}</code> • 手机: <code>${escapeHtml(c.cn_phone)}</code></div>
                    <div style="color:var(--text-3);margin:4px 0">地址: ${escapeHtml(c.cn_address)}</div>
                    <div style="display:flex;gap:6px;flex-wrap:wrap">
                      <button type="button" class="btn-secondary btn-sm" data-copy="${escapeHtml(c.cn_recipient)}">📋 Oluvchi</button>
                      <button type="button" class="btn-secondary btn-sm" data-copy="${escapeHtml(c.cn_phone)}">📋 Telefon</button>
                      <button type="button" class="btn-secondary btn-sm" data-copy="${escapeHtml(c.cn_address)}">📋 To'liq Manzil</button>
                    </div>
                  </div>
                `).join("")}
              </div>
              <div id="pdd-addr-out" style="font-size:11.5px;color:var(--text-2);margin-top:8px"></div>
            </div>

            <details class="card" style="cursor:pointer" ${st.has_apify ? "open" : ""}>
              <summary style="font-size:12.5px;font-weight:700">3. Jonli Pinduoduo Server API (Apify Live Server ${st.has_apify ? "✅ Ulangan" : ""} / Duoduo Jinbao)</summary>
              <div style="display:grid;gap:7px;margin-top:10px">
                <input id="inp-pdd-apify" type="password" class="form-control" placeholder="${st.has_apify ? "APIFY_API_TOKEN (✅ ulangan — yangilash uchun yozing)" : "APIFY_API_TOKEN (jonli Pinduoduo qidiruv serveri)"}" />
                <input id="inp-pdd-cid" class="form-control" placeholder="PDD_CLIENT_ID (ixtiyoriy)" />
                <input id="inp-pdd-csec" type="password" class="form-control" placeholder="PDD_CLIENT_SECRET (ixtiyoriy)" />
                <input id="inp-pdd-rapi" type="password" class="form-control" placeholder="PDD_RAPIDAPI_KEY (ixtiyoriy)" />
                <button type="button" class="btn-secondary" id="btn-pdd-save-keys">💾 API Kalitlarni Saqlash</button>
              </div>
            </details>
          </div>`;

        $("v2-modal-body").querySelectorAll("[data-copy]").forEach((b) => {
          b.addEventListener("click", () => copyText(b.dataset.copy, b));
        });

        const otpBtn = $("btn-pdd-otp-send");
        if (otpBtn) {
          otpBtn.addEventListener("click", async () => {
            const code = ($("inp-pdd-otp").value || "").trim();
            if (!code) return;
            otpBtn.disabled = true;
            const or = await fetch("/api/pdd/submit_otp", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ code }),
            });
            const ores = await or.json();
            $("pdd-connect-msg").textContent = ores.message || ores.error || "Yuborildi";
            otpBtn.disabled = false;
          });
        }

        const impBtn = $("btn-pdd-import-session");
        if (impBtn) {
          impBtn.addEventListener("click", async () => {
            const raw = ($("inp-pdd-session-raw").value || "").trim();
            if (!raw) return;
            impBtn.disabled = true;
            const ir = await fetch("/api/pdd/import_session", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ session_data: raw }),
            });
            const ires = await ir.json();
            impBtn.disabled = false;
            if (ires.ok) {
              fetchState();
              openPddModal();
            } else {
              $("pdd-connect-msg").textContent = ires.error || "Import xatosi";
            }
          });
        }

        const connBtn = $("btn-pdd-browser-connect");
        if (connBtn) {
          connBtn.addEventListener("click", async () => {
            connBtn.disabled = true;
            const cr = await fetch("/api/pdd/connect", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ force: Boolean(sess.connected) }),
            });
            const cres = await cr.json();
            $("pdd-connect-msg").textContent = cres.message || "Chrome oynasi ochildi — kirish kutilmoqda...";
            if ($("pdd-otp-row")) $("pdd-otp-row").style.display = "flex";
            const poll = setInterval(async () => {
              const sr = await fetch("/api/pdd/status");
              const sst = await sr.json();
              if (sst.login_state && sst.login_state.message) {
                $("pdd-connect-msg").textContent = sst.login_state.message;
              }
              if (sst.connected) {
                clearInterval(poll);
                fetchState();
                openPddModal();
              } else if (sst.login_state && !sst.login_state.running && sst.login_state.status !== "waiting_login") {
                clearInterval(poll);
                connBtn.disabled = false;
                $("pdd-connect-msg").textContent = sst.login_state.message || "Ulanish tugamadi";
              }
            }, 2500);
          });
        }

        const testBtn = $("btn-pdd-test-live");
        if (testBtn) {
          testBtn.addEventListener("click", async () => {
            testBtn.disabled = true;
            const out = $("pdd-test-out");
            out.style.display = "block";
            out.textContent = "Pinduoduo'dan jonli qidiruv va Wishlist sinovi o'tkazilmoqda...";
            const tr = await fetch("/api/pdd/test_search", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ keyword: "卫衣男", save_wishlist: true }),
            });
            const tres = await tr.json();
            testBtn.disabled = false;
            if (tres.ok) {
              out.innerHTML = (tres.items || [])
                .map((it) => `<div>• <b>¥${it.price_cny}</b> — ${escapeHtml(it.title_uz)} (<code>${escapeHtml(it.goods_id)}</code>)</div>`)
                .join("") + (tres.wishlist_test ? `<div style="margin-top:6px;color:var(--accent)">Wishlist (收藏): ${escapeHtml(tres.wishlist_test.status || String(tres.wishlist_test.ok))}</div>` : "");
            } else {
              out.textContent = tres.error || "Jonli natija kelmadi (sessiya yoki kalitni tekshiring)";
            }
          });
        }

        const syncBtn = $("btn-pdd-sync-addr");
        if (syncBtn) {
          syncBtn.addEventListener("click", async () => {
            syncBtn.disabled = true;
            $("pdd-addr-out").textContent = "Pinduoduo manzil kitobi tekshirilmoqda...";
            const ar = await fetch("/api/pdd/sync_addresses", { method: "POST" });
            const ares = await ar.json();
            syncBtn.disabled = false;
            $("pdd-addr-out").textContent = ares.all_synced
              ? "✅ Ikkala kargo ombori ham Pinduoduo akkountingizda topildi!"
              : ares.ok
                ? `Topildi: ${(ares.matched_codes || []).join(", ") || "yo'q"}. Qolganini yuqoridagi nusxa tugmasi bilan Pinduoduo manziliga qo'shing.`
                : `Tekshirib bo'lmadi: ${ares.reason || "xato"}`;
            fetchState();
          });
        }

        const saveKeysBtn = $("btn-pdd-save-keys");
        if (saveKeysBtn) {
          saveKeysBtn.addEventListener("click", async () => {
            const payload = {};
            const apify = $("inp-pdd-apify") ? $("inp-pdd-apify").value.trim() : "";
            const cid = $("inp-pdd-cid").value.trim();
            const csec = $("inp-pdd-csec").value.trim();
            const rapi = $("inp-pdd-rapi").value.trim();
            if (apify) payload.apify_token = apify;
            if (cid) payload.client_id = cid;
            if (csec) payload.client_secret = csec;
            if (rapi) payload.rapidapi_key = rapi;
            await fetch("/api/pdd/credentials", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(payload),
            });
            fetchState();
            openPddModal();
          });
        }
      } catch (err) {
        $("v2-modal-body").textContent = "Xatolik: " + err.message;
      }
    }

    async function openOrderPddPrepModal(orderId) {
      openModal(`🛒 Buyurtma #${orderId} — Pinduoduo To'lov Paketi`, `<div class="card">Tayyorlanmoqda...</div>`);
      try {
        const r = await fetch(`/api/orders/${orderId}/prepare_pdd`, { method: "POST" });
        const pkt = await r.json();
        if (!pkt.ok) {
          $("v2-modal-body").textContent = pkt.error || "Tayyorlab bo'lmadi";
          return;
        }
        const cargo = pkt.cargo || {};
        $("v2-modal-body").innerHTML = `
          <div style="display:grid;gap:10px">
            <div class="card">
              <b>Mijoz tanlovi:</b> Razmer <code>${escapeHtml(pkt.client_size)}</code> • Rang <code>${escapeHtml(pkt.client_color)}</code> • Jami Xitoy narxi: <b>¥${pkt.total_goods_cny}</b>
            </div>
            <div class="card" style="font-size:12px">
              <b>Tanlangan Kargo Ombori (${escapeHtml(cargo.code || "-")}):</b><br>
              Oluvchi: <code>${escapeHtml(cargo.cn_recipient || "")}</code> • Tel: <code>${escapeHtml(cargo.cn_phone || "")}</code><br>
              Manzil: ${escapeHtml(cargo.cn_address || "")}
            </div>
            <div class="card" style="display:grid;gap:6px">
              <b>Pinduoduo'da ochish va to'lov qilish uchun buyumlar:</b>
              ${(pkt.items || []).map((it) => `
                <div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid var(--border);font-size:12px;gap:8px">
                  <div><b>${it.index}. ${escapeHtml(it.name)}</b> (¥${it.price_cny}) · <span>${escapeHtml(it.size)} / ${escapeHtml(it.color)}</span></div>
                  ${it.url ? `<a class="btn-primary btn-sm" href="${escapeHtml(it.url)}" target="_blank" rel="noopener">🛒 Ochish</a>` : ""}
                </div>
              `).join("") || `<div style="font-size:12px;color:var(--text-3)">Buyurtma buyumlari topilmadi</div>`}
            </div>
          </div>`;
      } catch (err) {
        $("v2-modal-body").textContent = "Xatolik: " + err.message;
      }
    }

    // Calculator Mode & Run
    document.querySelectorAll("[data-calc-mode]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.calcMode = btn.dataset.calcMode;
        document.querySelectorAll("[data-calc-mode]").forEach((b) => b.classList.toggle("selected", b === btn));
        calcPrice();
      });
    });
    $("btn-calc-run").addEventListener("click", calcPrice);
    calcPrice();

    // Modals & Settings
    if ($("pdd-pill")) $("pdd-pill").addEventListener("click", openPddModal);
    $("btn-settings").addEventListener("click", () => $("settings-modal").classList.add("open"));
    $("omni-pill").addEventListener("click", () => handleWallAction("server"));
    $("v2-modal-close").addEventListener("click", () => $("v2-modal").classList.remove("open"));
    $("settings-modal-close").addEventListener("click", () => $("settings-modal").classList.remove("open"));

    fetchState();
    fetchCatalog();
    setInterval(fetchState, 6000);
  });
})();
