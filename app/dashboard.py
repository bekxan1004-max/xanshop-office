"""XAN SHOP - Sodda va Tushunarli, Ichki Ishlashi Murakkab 24/7 AI Agent Office Web-Paneli.

Manzil: http://localhost:8080 (yoki 24/7 Cloud Server domeni).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from aiohttp import web

from .accountant import AccountantAgent
from .ai import check_omniroute_status
from .ceo import apply_ceo_pricing_preset, collect_business_telemetry, run_ceo_strategy_cycle
from .config import Settings, load_settings
from .db import Database
from .ecc_engine import ECCRegistry, build_graphify_context_index, run_ecc_specialist
from .economy import get_params, get_rates
from .logistics import CARGO_LINES, LogisticsAgent, cargo_address_specs
from .office import PHOTO_DIR, AgentOffice
from .pinduoduo import PinduoduoConnector, get_pdd_session_details, import_pdd_session, interactive_browser_login
from .pricing import Item, PriceParams, calculate
from .publisher import format_instagram_caption, generate_premium_channel_kit
from .texts import look_items
from .trends import (
    COMPETITOR_BENCHMARKS,
    COMPETITOR_PROFILES,
    analyze_competitor_with_ai,
    build_reels_strategy_summary,
    fetch_tashkent_weather,
)

log = logging.getLogger(__name__)


def _persist_env_updates(updates: dict[str, str], env_path: str = ".env") -> None:
    """Faqat ko'rsatilgan .env kalitlarini izohlar va boshqa sozlamalarga tegmasdan yangilaydi."""
    p = Path(env_path)
    if not p.is_file():
        return
    lines = p.read_text(encoding="utf-8").splitlines()
    remaining = dict(updates)
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k = stripped.split("=", 1)[0].strip()
            if k in remaining:
                out.append(f"{k}={remaining.pop(k)}")
                continue
        out.append(line)
    for k, v in remaining.items():
        out.append(f"{k}={v}")
    p.write_text("\n".join(out) + "\n", encoding="utf-8")


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="uz">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>XAN SHOP — 24/7 AI AGENT OFFICE</title>
  <style>
    :root {
      --bg: #090b10;
      --card: #121621;
      --card-border: #22293a;
      --text: #f3f5f8;
      --muted: #8b95a7;
      --accent: #eab308;
      --green: #10b981;
      --blue: #3b82f6;
      --purple: #8b5cf6;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
      padding: 20px;
    }
    .container { max-width: 1420px; margin: 0 auto; }
    header {
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
      padding: 20px 24px;
      background: linear-gradient(135deg, #141926 0%, #1c2336 100%);
      border: 1px solid var(--card-border);
      border-radius: 18px;
      margin-bottom: 14px;
    }
    .brand-title { font-size: 23px; font-weight: 800; }
    .brand-title span { color: var(--accent); }
    .subtitle { color: var(--muted); font-size: 13px; margin-top: 3px; }
    .actions { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
    button.btn-primary {
      background: var(--accent);
      color: #090b10;
      border: none;
      padding: 12px 20px;
      border-radius: 12px;
      font-weight: 800;
      font-size: 14px;
      cursor: pointer;
      transition: transform 0.15s, opacity 0.15s;
    }
    button.btn-primary:hover { transform: translateY(-1px); opacity: 0.95; }
    button.btn-primary:disabled { opacity: 0.5; cursor: wait; }
    button.btn-ghost {
      background: #1a2030;
      color: var(--text);
      border: 1px solid var(--card-border);
      padding: 6px 12px;
      border-radius: 8px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
    }
    button.btn-ghost:hover { border-color: var(--accent); color: var(--accent); }
    .rate-pill {
      background: #0d1018;
      border: 1px solid var(--card-border);
      padding: 8px 14px;
      border-radius: 10px;
      font-size: 13px;
      color: var(--muted);
    }
    .rate-pill b { color: var(--text); }

    /* Tabs */
    .tabs {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-bottom: 16px;
    }
    .tab-btn {
      background: var(--card);
      color: var(--muted);
      border: 1px solid var(--card-border);
      padding: 10px 18px;
      border-radius: 12px;
      font-size: 14px;
      font-weight: 700;
      cursor: pointer;
    }
    .tab-btn.active {
      background: var(--accent);
      color: #090b10;
      border-color: var(--accent);
    }
    .tab-pane { display: none; }
    .tab-pane.active { display: block; }

    /* Integration Badges Bar */
    .integrations-bar {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      gap: 10px;
      margin-bottom: 18px;
    }
    .int-pill {
      background: var(--card);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 10px 14px;
      font-size: 12px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .int-ok { color: var(--green); font-weight: 700; }
    .int-wait { color: var(--accent); font-weight: 700; }

    .grid-top {
      display: grid;
      grid-template-columns: 2fr 1fr;
      gap: 20px;
      margin-bottom: 20px;
    }
    @media (max-width: 1024px) { .grid-top { grid-template-columns: 1fr; } }

    .section-card {
      background: var(--card);
      border: 1px solid var(--card-border);
      border-radius: 18px;
      padding: 20px;
      margin-bottom: 18px;
    }
    .section-title {
      font-size: 16px;
      font-weight: 700;
      margin-bottom: 14px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }
    .agents-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(255px, 1fr));
      gap: 12px;
    }
    .agent-box {
      background: #0c0f17;
      border: 1px solid var(--card-border);
      border-radius: 14px;
      padding: 14px;
    }
    .agent-box.subordinate {
      border-left: 4px solid var(--purple);
      background: linear-gradient(90deg, rgba(139,92,246,0.09) 0%, #0c0f17 100%);
    }
    .agent-head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 6px; }
    .agent-name { font-weight: 700; font-size: 14px; }
    .agent-role { color: var(--muted); font-size: 12px; margin-bottom: 8px; }
    .boss-badge {
      display: inline-block;
      background: rgba(139, 92, 246, 0.2);
      color: #c4b5fd;
      font-size: 11px;
      font-weight: 600;
      padding: 2px 8px;
      border-radius: 6px;
      margin-bottom: 6px;
    }
    .status-dot {
      padding: 2px 8px;
      border-radius: 99px;
      font-size: 10px;
      font-weight: 700;
      white-space: nowrap;
    }
    .status-idle { background: rgba(16, 185, 129, 0.15); color: var(--green); }
    .status-working { background: rgba(234, 179, 8, 0.2); color: var(--accent); animation: pulse 1.2s infinite; }
    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.45; } }
    .agent-task {
      font-size: 12px;
      color: #d1d5db;
      background: #131826;
      padding: 8px 10px;
      border-radius: 8px;
      min-height: 42px;
    }
    .agent-foot { margin-top: 8px; font-size: 11px; color: var(--muted); display: flex; justify-content: space-between; }

    /* Calculator */
    .calc-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px; }
    .calc-input {
      width: 100%;
      background: #0c0f17;
      border: 1px solid var(--card-border);
      color: var(--text);
      padding: 9px 12px;
      border-radius: 10px;
      font-size: 14px;
    }
    .calc-label { font-size: 12px; color: var(--muted); margin-bottom: 4px; display: block; }
    .calc-res {
      margin-top: 12px;
      background: #0c0f17;
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 12px;
      font-size: 13px;
    }
    .calc-res div { margin-bottom: 5px; display: flex; justify-content: space-between; }
    .calc-res .highlight {
      color: var(--accent);
      font-weight: 700;
      font-size: 14px;
      border-top: 1px solid var(--card-border);
      padding-top: 7px;
      margin-top: 7px;
    }

    /* Looks & Reels */
    .looks-list {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(310px, 1fr));
      gap: 16px;
    }
    .look-card {
      background: #0c0f17;
      border: 1px solid var(--card-border);
      border-radius: 14px;
      overflow: hidden;
    }
    .look-media {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px;
      background: #07090e;
      padding: 8px;
    }
    .look-media img, .look-media video {
      width: 100%;
      height: 220px;
      object-fit: contain;
      background: #f4f4f6;
      border-radius: 8px;
    }
    .look-body { padding: 14px; font-size: 13px; }
    .look-title { font-weight: 700; font-size: 15px; margin-bottom: 6px; }
    .swatch-row { display: flex; gap: 6px; align-items: center; margin: 6px 0; }
    .swatch-dot { width: 16px; height: 16px; border-radius: 50%; border: 1px solid #444; display: inline-block; }
    .badge-50 {
      display: inline-block;
      background: rgba(234, 179, 8, 0.18);
      color: var(--accent);
      font-weight: 700;
      padding: 3px 8px;
      border-radius: 6px;
      font-size: 12px;
      margin: 4px 0;
    }
    .caption-box {
      background: #131826;
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 8px;
      font-size: 11.5px;
      color: #cbd5e1;
      white-space: pre-wrap;
      max-height: 110px;
      overflow-y: auto;
      margin-top: 8px;
    }

    .logs-box {
      max-height: 460px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .log-item {
      background: #0c0f17;
      border-left: 3px solid var(--blue);
      padding: 10px 12px;
      border-radius: 8px;
      font-size: 12.5px;
    }
    .log-meta { font-size: 11px; color: var(--muted); margin-bottom: 3px; }
    .log-details { font-size: 11.5px; color: var(--muted); margin-top: 4px; }

    /* Orders table */
    table.orders-tbl { width: 100%; border-collapse: collapse; font-size: 13px; }
    table.orders-tbl th, table.orders-tbl td {
      text-align: left;
      padding: 10px 12px;
      border-bottom: 1px solid var(--card-border);
    }
    table.orders-tbl th { color: var(--muted); font-size: 12px; }

    /* Kit Grid */
    .kit-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; }
    .kit-pre {
      background: #0c0f17;
      border: 1px solid var(--card-border);
      padding: 12px;
      border-radius: 10px;
      font-size: 12.5px;
      white-space: pre-wrap;
      color: #e2e8f0;
      margin-top: 8px;
    }

    /* Virtual Pixel Office Canvas */
    .virtual-office-wrap {
      background: #070a12;
      border: 1px solid #26314a;
      border-radius: 16px;
      padding: 12px;
      margin-bottom: 18px;
      position: relative;
    }
    #virtual-office-canvas {
      width: 100%;
      height: auto;
      display: block;
      border-radius: 10px;
      background: #0a0f1d;
      cursor: pointer;
    }
    .office-hud {
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
      margin-top: 10px;
      font-size: 12px;
      color: var(--muted);
    }
    .ecc-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
      gap: 10px;
      max-height: 460px;
      overflow-y: auto;
      padding-right: 4px;
    }
    .ecc-card {
      background: #0c0f17;
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 12px;
      font-size: 12.5px;
      cursor: pointer;
      transition: border-color 0.15s;
    }
    .ecc-card:hover, .ecc-card.selected { border-color: var(--accent); }
    .ecc-badge {
      display: inline-block;
      background: rgba(59, 130, 246, 0.15);
      color: #93c5fd;
      padding: 2px 7px;
      border-radius: 6px;
      font-size: 10.5px;
      font-weight: 700;
    }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div>
        <div class="brand-title">🏢 <span>XAN SHOP</span> — 24/7 VIRTUAL AI AGENT OFFICE</div>
        <div class="subtitle" id="weather-banner">Ob-havo & Bozor razvedkasi yuklanmoqda...</div>
      </div>
      <div class="actions">
        <div class="rate-pill" id="rates-pill">Kurs: yuklanmoqda...</div>
        <button class="btn-primary" id="run-btn" onclick="triggerPipeline()">
          🚀 Yangi Trend Look + Ovozli MP4 Reels + Post
        </button>
      </div>
    </header>

    <div class="integrations-bar" id="integrations-bar"></div>

    <div class="tabs">
      <button class="tab-btn active" onclick="switchTab('tab-office', this)">🏢 Virtual AI Ofis</button>
      <button class="tab-btn" onclick="switchTab('tab-ecc', this); loadEccCatalog();">🤖 ECC 71 Agent & ⚡ OmniRoute</button>
      <button class="tab-btn" onclick="switchTab('tab-studio', this)">🎬 Looklar & Ovozli Reels Studio</button>
      <button class="tab-btn" onclick="switchTab('tab-orders', this)">📦 Buyurtmalar & Avia Kargo</button>
      <button class="tab-btn" onclick="switchTab('tab-launch', this)">🚀 Kanal Paketi & 24/7 Ulash Ro'yxati</button>
    </div>

    <!-- TAB 1: OFFICE -->
    <div id="tab-office" class="tab-pane active">
      <div class="section-card">
        <div class="section-title">
          <span>🎮 Jonli Virtual Ofis Xonasi (Agentlar Harakati, OmniRoute Server & ECC Swarm)</span>
          <span style="font-size:12px;color:var(--muted);" id="office-sim-badge">Simulyatsiya faol ● Agent ustiga bosing</span>
        </div>
        <div class="virtual-office-wrap">
          <canvas id="virtual-office-canvas" width="1280" height="430"></canvas>
          <div class="office-hud">
            <div id="office-selected-info">💡 Istalgan agent ustiga bosing — uning vazifasini ko'ring yoki ECC agent yordamini yuboring.</div>
            <div>
              <span style="color:var(--green);">● Ishlayapti</span> ·
              <span style="color:var(--blue);">● Majlis / Aloqa</span> ·
              <span style="color:var(--accent);">● Kofe / Tayyor</span>
            </div>
          </div>
        </div>
      </div>

      <div class="grid-top">
        <div class="section-card">
          <div class="section-title">
            <span>🤖 Ofis Bo'limlari & Biriktirilgan ECC Mutaxassislar</span>
            <span style="font-size:12px;color:var(--muted);">Har 3 soniyada jonli yangilanadi</span>
          </div>
          <div class="agents-grid" id="agents-container"></div>
        </div>

        <div class="section-card">
          <div class="section-title">
            <span>🧮 50% / 100% + UZS→CNY Tranzaksiya Kalkulyatori</span>
          </div>
          <div class="calc-row">
            <div>
              <label class="calc-label">Pinduoduo narxi (Yuan ¥, + bilan)</label>
              <input class="calc-input" id="calc-cny" value="42" placeholder="42 yoki 89+54+52+42" />
            </div>
            <div>
              <label class="calc-label">Jami vazn (kg)</label>
              <input class="calc-input" id="calc-weight" value="0.8" type="number" step="0.1" />
            </div>
          </div>
          <button class="btn-primary" style="width:100%;padding:9px;" onclick="runCalc()">Hisoblash (50% / 100% model)</button>
          <div class="calc-res" id="calc-output"></div>
        </div>
      </div>

      <div class="section-card">
        <div class="section-title">
          <span>📡 Agentlararo Muloqot Jurnali (Instagram Tahlil ➔ Skaut ➔ SMM ➔ Video Xodim ➔ Kargo)</span>
        </div>
        <div class="logs-box" id="logs-container"></div>
      </div>
    </div>

    <!-- TAB: ECC 71 AGENTS + OMNIROUTE + GRAPHIFY -->
    <div id="tab-ecc" class="tab-pane">
      <div class="grid-top">
        <div class="section-card">
          <div class="section-title">
            <span>⚡ OmniRoute Token Gateway (380 Provayder · 150+ Bepul Tier · Limit Tugamasin)</span>
            <button class="btn-ghost" onclick="startOmniroute()">⚡ OmniRoute Ishga Tushirish</button>
          </div>
          <div id="omniroute-panel" style="font-size:13px;line-height:1.7;">Yuklanmoqda...</div>
        </div>

        <div class="section-card">
          <div class="section-title">
            <span>🕸 Graphify Bilim Grafi (Tokenni ~80% Tejash)</span>
          </div>
          <div id="graphify-panel" style="font-size:13px;line-height:1.7;">Yuklanmoqda...</div>
        </div>
      </div>

      <div class="section-card">
        <div class="section-title">
          <span>🚀 ECC Mutaxassis Agentga Vazifa Berish (71 Agent + 314 Skill)</span>
          <span style="font-size:12px;color:var(--muted);" id="ecc-counts-badge">Yuklanmoqda...</span>
        </div>
        <div class="calc-row">
          <div>
            <label class="calc-label">ECC Agentni tanlang</label>
            <select class="calc-input" id="ecc-agent-select"></select>
          </div>
          <div>
            <label class="calc-label">Qo'shimcha ECC Skill (ixtiyoriy)</label>
            <select class="calc-input" id="ecc-skill-select"></select>
          </div>
        </div>
        <div style="margin-bottom:10px;">
          <label class="calc-label">Topshiriq (o'zbek/rus/ingliz tilida)</label>
          <input class="calc-input" id="ecc-task-input" placeholder="Masalan: Bahorgi 4 qismli Old Money look uchun Instagram Reels ssenariysi va sotuv hooklarini tuz" />
        </div>
        <button class="btn-primary" id="ecc-run-btn" onclick="runEccTask()">⚡ ECC Agentni OmniRoute/AI orqali Ishga Tushirish</button>
        <div class="kit-pre" id="ecc-output-box" style="display:none;margin-top:12px;"></div>
      </div>

      <div class="grid-top">
        <div class="section-card">
          <div class="section-title">
            <span>🤖 71 ta ECC Mutaxassis Agentlar</span>
            <input class="calc-input" style="max-width:220px;padding:6px 10px;font-size:12px;" id="ecc-agent-search" placeholder="Agent qidirish..." oninput="filterEccCatalog()" />
          </div>
          <div class="ecc-grid" id="ecc-agents-grid"></div>
        </div>

        <div class="section-card">
          <div class="section-title">
            <span>🧩 314 ta ECC Skilllar</span>
            <input class="calc-input" style="max-width:220px;padding:6px 10px;font-size:12px;" id="ecc-skill-search" placeholder="Skill qidirish..." oninput="filterEccCatalog()" />
          </div>
          <div class="ecc-grid" id="ecc-skills-grid"></div>
        </div>
      </div>
    </div>

    <!-- TAB 2: STUDIO -->
    <div id="tab-studio" class="tab-pane">
      <div class="section-card">
        <div class="section-title">
          <span>🎬 Tayyor Looklar (1080x1350 Kolaj + Ovozli 9:16 .MP4 Reels + Instagram Tavsif)</span>
          <span style="font-size:12px;color:var(--muted);" id="looks-count"></span>
        </div>
        <div class="looks-list" id="looks-container"></div>
      </div>
    </div>

    <!-- TAB 3: ORDERS & CARGO -->
    <div id="tab-orders" class="tab-pane">
      <div class="section-card">
        <div class="section-title">
          <span>✈️ 2 ta Avia Kargo Liniyasi ($9.5/kg) & Buyurtmalar Nazorati</span>
        </div>
        <div id="cargo-lines-box" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px;margin-bottom:18px;"></div>
        <div style="overflow-x:auto;">
          <table class="orders-tbl">
            <thead>
              <tr>
                <th>#ID</th>
                <th>Manba</th>
                <th>Mijoz</th>
                <th>Look / Razmer</th>
                <th>Reja & Oldindan</th>
                <th>Qolgan 50% + Kargo</th>
                <th>Holat / Trek</th>
              </tr>
            </thead>
            <tbody id="orders-tbody"></tbody>
          </table>
        </div>
      </div>

      <div class="section-card">
        <div class="section-title">
          <span>🧮 AI Hisobchi — Bank Tushumlari Tarixi (@HumoCardBot / @CardXabarBot / SMS Webhook)</span>
        </div>
        <div style="overflow-x:auto;">
          <table class="orders-tbl">
            <thead>
              <tr>
                <th>#TX</th>
                <th>Manba</th>
                <th>Karta</th>
                <th>Kirim Summa</th>
                <th>Holat / Buyurtma</th>
              </tr>
            </thead>
            <tbody id="bank-tx-tbody"></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- TAB 4: CHANNEL KIT & LAUNCH CHECKLIST -->
    <div id="tab-launch" class="tab-pane">
      <div class="section-card">
        <div class="section-title">
          <span>🏆 Instagram & Telegram Kanal Uchun Premium Oformleniya (Lookzona / Stylesh Darajasida)</span>
        </div>
        <div class="kit-grid" id="kit-container"></div>
      </div>

      <div class="section-card">
        <div class="section-title">
          <span>📋 24/7 Serverga Ulash Uchun "Siz Beradigan Narsalar" Ro'yxati</span>
        </div>
        <div id="checklist-container" style="font-size:13.5px;display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px;"></div>
      </div>
    </div>
  </div>

  <script>
    function fmt(n) {
      return Math.round(n || 0).toString().replace(/\\B(?=(\\d{3})+(?!\\d))/g, " ");
    }

    function switchTab(id, btn) {
      document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.getElementById(id).classList.add('active');
      btn.classList.add('active');
    }

    function copyTxt(id) {
      const el = document.getElementById(id);
      if (!el) return;
      navigator.clipboard.writeText(el.innerText || el.textContent);
      alert("Nusxa olindi!");
    }

    async function loadState() {
      try {
        const res = await fetch('/api/state');
        const data = await res.json();

        document.getElementById('rates-pill').innerHTML =
          `1 ¥ = <b>${fmt(data.rates.cny_uzs)} so'm</b> · 1 $ = <b>${fmt(data.rates.usd_uzs)} so'm</b> · Tranzaksiya: <b>${data.params.conversion_fee_percent}%</b>`;

        const w = data.weather;
        document.getElementById('weather-banner').innerHTML =
          `🌤 <b>${w.city}: ${w.temp_c}°C (${w.season_uz})</b> ${w.is_live ? '🟢 Live' : ''} — ${w.clothing_advice}`;

        const conn = data.connections;
        const omni = data.omniroute || {};
        const eccSum = data.ecc_summary || {};
        document.getElementById('integrations-bar').innerHTML = `
          <div class="int-pill"><span>⚡ OmniRoute Gateway</span><span class="${omni.online ? 'int-ok' : 'int-wait'}">${omni.online ? `🟢 Online (${omni.models_count} model)` : '🟡 Oʻchiq (Tab 2 dan yoqing)'}</span></div>
          <div class="int-pill"><span>🤖 ECC Swarm (71 Agent)</span><span class="${eccSum.installed ? 'int-ok' : 'int-wait'}">${eccSum.installed ? `🟢 ${eccSum.agents_count} Agent / ${eccSum.skills_count} Skill` : '🟡 Yuklanmoqda'}</span></div>
          <div class="int-pill"><span>🇨🇳 Pinduoduo Engine</span><span class="int-ok">${conn.pdd ? '🟢 Live PDD API' : '🟢 PDD Katalog + URL'}</span></div>
          <div class="int-pill"><span>👤 Shaxsiy TG Akkaunt</span><span class="${conn.userbot ? 'int-ok' : 'int-wait'}">${conn.userbot ? '🟢 Userbot Tayyor' : '🟡 TG_API_ID kutilmoqda'}</span></div>
          <div class="int-pill"><span>📢 TG Kanal & Botlar</span><span class="${conn.tg_bots ? 'int-ok' : 'int-wait'}">${conn.tg_bots ? '🟢 Botlar Online' : '🟡 Token kutilmoqda'}</span></div>
          <div class="int-pill"><span>📸 Instagram Graph API</span><span class="${conn.instagram ? 'int-ok' : 'int-wait'}">${conn.instagram ? '🟢 Avto-Reels' : '🟡 IG Token kutilmoqda'}</span></div>
        `;

        // Virtual Office State Sync
        window._latestOfficeData = data;
        syncOfficeAvatars(data);

        // Agents with mapped ECC Squad
        const deptMap = (eccSum.departments || {});
        document.getElementById('agents-container').innerHTML = data.agents.map(a => {
          const isSub = a.boss_id === 'smm_manager';
          const bossLabel = isSub
            ? `<div class="boss-badge">↳ SMM Boshlig'ining shaxsiy xodimi</div>`
            : (a.boss_id ? `<div class="boss-badge" style="background:rgba(59,130,246,0.15);color:#93c5fd;">Bo'ysunadi: Bosh Direktor</div>` : '');
          const stClass = a.status === 'working' ? 'status-working' : 'status-idle';
          const stText = a.status === 'working' ? 'ISHLAYAPTI ⚡' : '24/7 ONLINE ●';
          const eccList = (deptMap[a.agent_id] || []).map(e => `<span class="ecc-badge">${e}</span>`).join(' ');
          return `
            <div class="agent-box ${isSub ? 'subordinate' : ''}">
              <div class="agent-head">
                <div class="agent-name">${a.name}</div>
                <span class="status-dot ${stClass}">${stText}</span>
              </div>
              ${bossLabel}
              <div class="agent-role">${a.role}</div>
              ${eccList ? `<div style="margin-bottom:7px;display:flex;gap:4px;flex-wrap:wrap;">${eccList}</div>` : ''}
              <div class="agent-task">${a.current_task}</div>
              <div class="agent-foot">
                <span>ID: ${a.agent_id}</span>
                <span>Bajarildi: <b>${a.tasks_done}</b></span>
              </div>
            </div>
          `;
        }).join('');

        // Update OmniRoute & Graphify cards if visible
        const omniPanel = document.getElementById('omniroute-panel');
        if (omniPanel) {
          omniPanel.innerHTML = `
            <div><b>Holat:</b> ${omni.online ? '<span style="color:var(--green);">🟢 ISHLAYAPTI (http://localhost:20128)</span>' : '<span style="color:var(--accent);">🟡 Ishga tushirilmagan</span>'}</div>
            <div><b>API Endpoint:</b> <code>${omni.base_url || 'http://localhost:20128/v1'}</code></div>
            <div><b>Zaxira Zanjiri:</b> <code>1. OmniRoute (150+ bepul tier) ➔ 2. OpenRouter ➔ 3. Google Gemini</code></div>
            <div><b>Mavjud modellar:</b> <b>${omni.models_count || 0} ta</b> ${omni.sample_models && omni.sample_models.length ? `(${omni.sample_models.slice(0,4).join(', ')})` : ''}</div>
            <div style="margin-top:8px;">
              ${omni.online ? `<a href="${omni.dashboard_url}" target="_blank" style="text-decoration:none;"><button class="btn-ghost">🌐 OmniRoute Boshqaruv Panelini Ochish</button></a>` : '<span style="color:var(--muted);">Boshlash uchun oʻng burchakdagi ⚡ OmniRoute Ishga Tushirish tugmasini bosing.</span>'}
            </div>
          `;
        }
        const graphPanel = document.getElementById('graphify-panel');
        if (graphPanel && eccSum.graphify) {
          const g = eccSum.graphify;
          graphPanel.innerHTML = `
            <div><b>Arxitektura:</b> AST Bilim Grafi (Graphify kesh)</div>
            <div><b>Indekslangan modullar:</b> <b>${g.modules} ta</b> Python moduli</div>
            <div><b>Klasslar / Funksiyalar:</b> <b>${g.classes}</b> klass · <b>${g.functions}</b> funksiya</div>
            <div style="color:var(--green);margin-top:6px;">✅ Har bir ECC agent loyihani noldan o'qish o'rniga shu ixcham grafdan foydalanadi (~80% token tejash).</div>
          `;
        }

        // Looks & MP4 Studio
        document.getElementById('looks-count').textContent = `${data.looks.length} ta to'plam`;
        document.getElementById('looks-container').innerHTML = data.looks.slice().reverse().map(lk => {
          const p50 = lk.prepay_50_uzs || Math.round(lk.prepay_uzs / 2);
          const rem50 = lk.remaining_50_uzs || (lk.prepay_uzs - p50);
          const hasMp4 = (lk.video_path || '').endsWith('.mp4');
          const mediaRight = hasMp4
            ? `<video src="/media/look_${lk.id}_reels.mp4?t=${lk.created_at}" controls playsinline title="9:16 Ovozli MP4 Reels (Play bosing — zvuk bilan!)"></video>`
            : `<img src="/media/look_${lk.id}_reels.gif?t=${lk.created_at}" alt="Reels" />`;
          let swatches = '';
          try {
            const hx = JSON.parse(lk.palette_hex || '[]');
            swatches = hx.map(c => `<span class="swatch-dot" style="background:${c}" title="${c}"></span>`).join('');
          } catch {}
          return `
            <div class="look-card">
              <div class="look-media">
                <img src="/media/look_${lk.id}.jpg?t=${lk.created_at}" alt="Kolaj" title="1080x1350 Kolaj" />
                ${mediaRight}
              </div>
              <div class="look-body">
                <div class="look-title">#${lk.id} ${lk.title}</div>
                ${swatches ? `<div class="swatch-row">${swatches} <span style="font-size:11px;color:var(--muted);">${lk.palette_name || ''} · 🎵 ${lk.audio_vibe || 'beat'}</span></div>` : ''}
                <div class="badge-50">🌗 50% Oldindan: ${fmt(p50)} so'm</div>
                <div>💯 100% Narx: <b>${fmt(lk.prepay_uzs)} so'm</b></div>
                <div style="color:var(--muted);font-size:12px;">✈️ Toshkentda: ${fmt(rem50)} + ~${fmt(lk.cargo_est_uzs)} kargo · 💵 Foyda: ${fmt(lk.profit_uzs)} so'm</div>
                <div class="caption-box" id="cap-${lk.id}">${lk.insta_caption || ''}</div>
                <div style="margin-top:8px;display:flex;gap:8px;">
                  <button class="btn-ghost" onclick="copyTxt('cap-${lk.id}')">📋 Post Matnini Nusxalash</button>
                  ${hasMp4 ? `<a href="/media/look_${lk.id}_reels.mp4" download style="text-decoration:none;"><button class="btn-ghost">⬇️ .MP4 Yuklash</button></a>` : ''}
                </div>
              </div>
            </div>
          `;
        }).join('') || '<div style="color:var(--muted);">Looklar hali yo\\'q. Yuqoridagi tugmani bosing!</div>';

        // Logs
        document.getElementById('logs-container').innerHTML = data.logs.map(l => {
          const d = new Date((l.created_at || 0) * 1000).toLocaleTimeString();
          const arrow = l.target_id ? ` ➔ <b>${l.target_id}</b>` : '';
          return `
            <div class="log-item">
              <div class="log-meta">${d} · <b>${l.agent_id}</b>${arrow}</div>
              <div>${l.action}</div>
              ${l.details ? `<div class="log-details">${l.details}</div>` : ''}
            </div>
          `;
        }).join('');

        // Cargo & Orders
        document.getElementById('cargo-lines-box').innerHTML = Object.values(data.cargo_lines).map(c => `
          <div style="background:#0c0f17;border:1px solid var(--card-border);padding:14px;border-radius:12px;">
            <div style="font-weight:700;color:var(--accent);">✈️ ${c.name} (${c.code}) · ID: ${c.client_id}</div>
            <div style="font-size:12.5px;margin-top:4px;">Narxi: <b>$${c.rate_usd_kg}/kg</b> · Muddat: <b>${c.eta_days}</b> · ${c.mode}</div>
            <div style="font-size:12px;color:#cbd5e1;margin-top:8px;background:#131826;padding:8px;border-radius:8px;">
              🇨🇳 <b>Oluvchi:</b> <code>${c.cn_recipient}</code> · <b>Tel:</b> <code>${c.cn_phone}</code><br/>
              📍 <b>Manzil:</b> <code>${c.cn_address}</code>
            </div>
          </div>
        `).join('');

        document.getElementById('orders-tbody').innerHTML = (data.orders || []).map(o => `
          <tr>
            <td><b>#${o.id}</b></td>
            <td>${o.source === 'userbot' ? '👤 Lichka (Userbot)' : '🤖 Sotuv Bot'}</td>
            <td>${o.full_name || o.username || o.user_id}</td>
            <td>Look #${o.look_id} (${o.size || '-'})</td>
            <td><b>${o.payment_plan || '50'}%</b> (${fmt(o.prepay_due)} so'm)</td>
            <td>${fmt(o.remaining_uzs)} + ${fmt(o.cargo_due)} so'm</td>
            <td>${o.status} ${o.tracking ? `<br/><code>${o.tracking}</code>` : ''}</td>
          </tr>
        `).join('') || '<tr><td colspan="7" style="color:var(--muted);">Hozircha faol buyurtmalar yo\\'q.</td></tr>';

        document.getElementById('bank-tx-tbody').innerHTML = (data.bank_transactions || []).map(t => `
          <tr>
            <td>#${t.id}</td>
            <td>${t.source}</td>
            <td><code>*${t.card_last4 || '????'}</code></td>
            <td style="color:var(--green);font-weight:700;">+${fmt(t.amount_uzs)} so'm</td>
            <td>${t.matched_order_id ? `✅ Buyurtma #${t.matched_order_id}` : '⏳ Chek kutilmoqda'}</td>
          </tr>
        `).join('') || '<tr><td colspan="5" style="color:var(--muted);">Hozircha bank tushumlari yo\\'q.</td></tr>';

        // Channel Kit & Launch Checklist
        const kit = data.channel_kit;
        document.getElementById('kit-container').innerHTML = `
          <div>
            <b>📸 Instagram Bio (Shapka)</b> <button class="btn-ghost" onclick="copyTxt('kit-ig-bio')">Nusxa</button>
            <div class="kit-pre" id="kit-ig-bio">${kit.instagram_bio}</div>
          </div>
          <div>
            <b>⭕ Instagram Aktualnoe (Highlights)</b> <button class="btn-ghost" onclick="copyTxt('kit-hl')">Nusxa</button>
            <div class="kit-pre" id="kit-hl">${kit.instagram_highlights}</div>
          </div>
          <div>
            <b>📢 Telegram Kanal Bio</b> <button class="btn-ghost" onclick="copyTxt('kit-tg-bio')">Nusxa</button>
            <div class="kit-pre" id="kit-tg-bio">${kit.telegram_channel_bio}</div>
          </div>
          <div>
            <b>📌 Telegram Kanal Zakrep (Ishonch Posti)</b> <button class="btn-ghost" onclick="copyTxt('kit-pin')">Nusxa</button>
            <div class="kit-pre" id="kit-pin">${kit.telegram_pinned_post.replace(/<[^>]+>/g, '')}</div>
          </div>
        `;

        document.getElementById('checklist-container').innerHTML = `
          <div style="background:#0c0f17;border:1px solid var(--card-border);padding:14px;border-radius:12px;">
            <b>1. Telegram (@BotFather + Shaxsiy Akkaunt)</b>
            <ul style="margin:8px 0 0 18px;color:var(--muted);line-height:1.7;">
              <li><code>SALES_BOT_TOKEN</code> va <code>ADMIN_BOT_TOKEN</code></li>
              <li><code>ADMIN_IDS</code> (o'z Telegram ID raqamingiz)</li>
              <li><code>CHANNEL_ID</code> (Telegram kanal ID / @username, bot admin qilingan)</li>
              <li><code>TG_API_ID</code> + <code>TG_API_HASH</code> + <code>TG_SESSION_STRING</code> (haqiqiy profilni 24/7 boshqarish uchun)</li>
            </ul>
          </div>
          <div style="background:#0c0f17;border:1px solid var(--card-border);padding:14px;border-radius:12px;">
            <b>2. Pinduoduo, Instagram & AI Kalitlari</b>
            <ul style="margin:8px 0 0 18px;color:var(--muted);line-height:1.7;">
              <li><code>GEMINI_API_KEY</code> (aistudio.google.com)</li>
              <li><code>PDD_CLIENT_ID</code> / <code>PDD_CLIENT_SECRET</code> (yoki <code>PDD_RAPIDAPI_KEY</code>)</li>
              <li><code>IG_USER_ID</code> + <code>IG_ACCESS_TOKEN</code> (Instagram Professional Business API)</li>
              <li><code>CARD_NUMBER</code> va <code>CARD_OWNER</code></li>
            </ul>
          </div>
          <div style="background:#0c0f17;border:1px solid var(--card-border);padding:14px;border-radius:12px;">
            <b>3. 24/7 Cloud Server & Obunachi O'sishi</b>
            <ul style="margin:8px 0 0 18px;color:var(--muted);line-height:1.7;">
              <li>Loyiha ichida tayyor <code>Dockerfile</code> va <code>railway.json</code> bor — Railway.app yoki Render.com ga yuklasangiz kompyuter o'chiq bo'lganda ham 24/7 ishlaydi!</li>
              <li>⚠️ <b>Obunachi (Ishonch):</b> Soxta bot-nakrutka Instagram Reels algoritmini (rekni) o'ldiradi. Buning o'rniga: birinchi 10-15 ta postni Telegram/Insta reklama (Target $10–$20 + Telegram kanallarida birja reklama) va do'stlar/tanishlar orqali jonli obunachi + "50% Oldindan / Qolgani Toshkentda" kafolat posti bilan boshlang!</li>
            </ul>
          </div>
        `;
      } catch (e) {
        console.error(e);
      }
    }

    async function triggerPipeline() {
      const btn = document.getElementById('run-btn');
      btn.disabled = true;
      btn.textContent = '⚡ Ob-havo + Pinduoduo + Ovozli MP4 Reels tayyorlanmoqda...';
      try {
        await fetch('/api/run_pipeline', { method: 'POST' });
        await loadState();
      } finally {
        btn.disabled = false;
        btn.textContent = '🚀 Yangi Trend Look + Ovozli MP4 Reels + Post';
      }
    }

    async function runCalc() {
      const cny = document.getElementById('calc-cny').value;
      const weight = document.getElementById('calc-weight').value;
      const res = await fetch(`/api/calc?cny=${encodeURIComponent(cny)}&weight=${encodeURIComponent(weight)}`);
      const b = await res.json();
      if (b.error) {
        document.getElementById('calc-output').innerHTML = `<span style="color:#ef4444">${b.error}</span>`;
        return;
      }
      document.getElementById('calc-output').innerHTML = `
        <div><span>Pinduoduo narxi (¥${b.goods_cny}) + Vykup:</span> <b>¥${b.total_cny}</b></div>
        <div><span>UZS->CNY tranzaksiya bilan tannarx:</span> <b>${fmt(b.goods_cost_uzs)} so'm</b></div>
        <div class="highlight"><span>🌗 50% Oldindan to'lov (xarid+tranzaksiya ichida):</span> <span>${fmt(b.prepay_50_uzs)} so'm</span></div>
        <div><span>💯 100% Sotuv narxi:</span> <b>${fmt(b.prepay_uzs)} so'm</b></div>
        <div><span>⏳ Qolgan 50% (Toshkentda):</span> <b>${fmt(b.remaining_50_uzs)} so'm</b></div>
        <div><span>✈️ Kargo (${b.weight_kg} kg, Toshkentda):</span> <b>${fmt(b.cargo_client_uzs)} so'm</b></div>
        <div class="highlight" style="color:var(--green);"><span>📦 50% tanlanganda Toshkentda jami:</span> <span>${fmt(b.arrival_50_est_uzs)} so'm</span></div>
        <div><span>💵 Sizning sof foydangiz:</span> <b style="color:var(--green);">${fmt(b.total_profit_uzs)} so'm</b></div>
      `;
    }

    // === 1. VIRTUAL AI AGENT OFIS SIMULYATORI (HTML5 Pixel/Isometric Studio) ===
    const DESKS = {
      director:       { x: 165, y: 120, room: "👑 Boshqaruv & Strategiya", color: "#eab308", label: "Direktor", ecc: "chief-of-staff" },
      skaut:          { x: 470, y: 120, room: "🔍 Pinduoduo & Trend Lab",  color: "#3b82f6", label: "Skaut",    ecc: "spec-miner" },
      smm_manager:    { x: 800, y: 120, room: "📢 SMM & Kontent",          color: "#ec4899", label: "SMM",      ecc: "marketing-agent" },
      video_employee: { x: 1100,y: 125, room: "🎬 Reels & Voice Studio",   color: "#8b5cf6", label: "Video AI", ecc: "video-editing" },
      sales_stylist:  { x: 185, y: 315, room: "💬 Sotuv & VIP Telegram",   color: "#10b981", label: "Stilist",  ecc: "conversation-analyzer" },
      accountant:     { x: 510, y: 315, room: "🧮 Hisobchi & Chek AI",     color: "#06b6d4", label: "Hisobchi", ecc: "security-reviewer" },
      cargo_logistics:{ x: 850, y: 315, room: "✈️ Kargo BP-1 & T-7621",    color: "#f97316", label: "Kargo",    ecc: "loop-operator" }
    };
    const MEETING_SPOT = { x: 640, y: 225 };
    const SERVER_SPOT  = { x: 1135, y: 315 };
    const COFFEE_SPOT  = { x: 345, y: 225 };

    const avatars = {};
    let selectedAgentId = null;

    function syncOfficeAvatars(data) {
      if (!data || !data.agents) return;
      data.agents.forEach((a, idx) => {
        const home = DESKS[a.agent_id] || { x: 200 + idx * 130, y: 210, color: "#94a3b8", label: a.agent_id, ecc: "planner" };
        if (!avatars[a.agent_id]) {
          avatars[a.agent_id] = {
            id: a.agent_id,
            name: a.name,
            label: home.label,
            color: home.color,
            ecc: home.ecc,
            x: home.x,
            y: home.y,
            tx: home.x,
            ty: home.y,
            status: a.status,
            task: a.current_task || "Tayyor",
            done: a.tasks_done || 0,
            bob: Math.random() * 6.28
          };
        }
        const av = avatars[a.agent_id];
        av.status = a.status;
        av.task = a.current_task || "Tayyor";
        av.done = a.tasks_done || 0;
        if (a.status === "working") {
          av.tx = home.x;
          av.ty = home.y + 18;
        } else {
          // Idle holatda stoldan sal nari yoki kofe/uchrashuv zonasi atrofida turadi
          const jitter = ((idx % 3) - 1) * 18;
          av.tx = home.x + jitter;
          av.ty = home.y + 24;
        }
      });
    }

    function drawPixelOffice(ts) {
      const canvas = document.getElementById('virtual-office-canvas');
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      const W = canvas.width, H = canvas.height;
      ctx.clearRect(0, 0, W, H);

      // 1. Ofis pol kataklari (2.5D grid)
      ctx.fillStyle = "#0b1120";
      ctx.fillRect(0, 0, W, H);
      ctx.strokeStyle = "rgba(56, 189, 248, 0.06)";
      ctx.lineWidth = 1;
      for (let gx = 0; gx < W; gx += 32) {
        ctx.beginPath(); ctx.moveTo(gx, 0); ctx.lineTo(gx, H); ctx.stroke();
      }
      for (let gy = 0; gy < H; gy += 32) {
        ctx.beginPath(); ctx.moveTo(0, gy); ctx.lineTo(W, gy); ctx.stroke();
      }

      // 2. Xonalar chegaralari (Rooms)
      const rooms = [
        { x: 24,  y: 22,  w: 280, h: 165, title: "👑 BOSHQARUV & CHIEF-OF-STAFF", col: "rgba(234,179,8,0.18)" },
        { x: 325, y: 22,  w: 300, h: 165, title: "🔍 PINDUODUO & OB-HAVO LAB",   col: "rgba(59,130,246,0.18)" },
        { x: 645, y: 22,  w: 300, h: 165, title: "📢 SMM & MARKETING ECC",       col: "rgba(236,72,153,0.18)" },
        { x: 965, y: 22,  w: 290, h: 165, title: "🎬 REELS & VOICE AI STUDIO",   col: "rgba(139,92,246,0.22)" },
        { x: 24,  y: 245, w: 320, h: 165, title: "💬 SOTUV STILIST (TG + BOT)",  col: "rgba(16,185,129,0.18)" },
        { x: 365, y: 245, w: 300, h: 165, title: "🧮 AI HISOBCHI & CHEK OCR",    col: "rgba(6,182,212,0.18)" },
        { x: 685, y: 245, w: 320, h: 165, title: "✈️ KARGO BP-1 & T-7621",       col: "rgba(249,115,22,0.18)" },
        { x: 1025,y: 245, w: 230, h: 165, title: "⚡ OMNIROUTE + ECC 71x",       col: "rgba(34,197,94,0.22)" }
      ];

      rooms.forEach(r => {
        ctx.fillStyle = "rgba(17, 24, 39, 0.85)";
        ctx.strokeStyle = r.col;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.roundRect(r.x, r.y, r.w, r.h, 12);
        ctx.fill();
        ctx.stroke();
        ctx.fillStyle = "#94a3b8";
        ctx.font = "bold 11px Segoe UI, sans-serif";
        ctx.fillText(r.title, r.x + 12, r.y + 20);
      });

      // Markaziy yo'lak (Meeting & Coffee Lounge)
      ctx.fillStyle = "rgba(30, 41, 59, 0.5)";
      ctx.beginPath();
      ctx.roundRect(570, 194, 140, 44, 14);
      ctx.fill();
      ctx.fillStyle = "#64748b";
      ctx.font = "bold 10px Segoe UI";
      ctx.fillText("🤝 ECC UCHRASHUV STOLI", 582, 220);

      ctx.fillStyle = "rgba(30, 41, 59, 0.5)";
      ctx.beginPath();
      ctx.roundRect(275, 194, 140, 44, 14);
      ctx.fill();
      ctx.fillStyle = "#64748b";
      ctx.fillText("☕ KOFE & DAM ZONASI", 290, 220);

      // OmniRoute & ECC Server Rack chiroqlari
      const omniOnline = !!(window._latestOfficeData && window._latestOfficeData.omniroute && window._latestOfficeData.omniroute.online);
      for (let sr = 0; sr < 3; sr++) {
        const rx = 1045 + sr * 65, ry = 280;
        ctx.fillStyle = "#0f172a";
        ctx.strokeStyle = "#334155";
        ctx.fillRect(rx, ry, 48, 88);
        ctx.strokeRect(rx, ry, 48, 88);
        for (let led = 0; led < 4; led++) {
          const blink = Math.sin(ts * 0.008 + sr * 2 + led) > 0;
          ctx.fillStyle = omniOnline ? (blink ? "#10b981" : "#065f46") : (blink ? "#eab308" : "#78350f");
          ctx.fillRect(rx + 8, ry + 12 + led * 18, 10, 6);
          ctx.fillStyle = "#38bdf8";
          ctx.fillRect(rx + 24, ry + 12 + led * 18, 16, 4);
        }
      }
      ctx.fillStyle = omniOnline ? "#34d399" : "#fbbf24";
      ctx.font = "bold 11px Consolas, monospace";
      ctx.fillText(omniOnline ? "● OMNIROUTE :20128 OK" : "● OMNIROUTE STANDBY", 1042, 392);

      // Video Studio Green Screen (o'ng yuqorida)
      ctx.fillStyle = "rgba(16, 185, 129, 0.25)";
      ctx.fillRect(1185, 42, 54, 72);
      ctx.strokeStyle = "#10b981";
      ctx.strokeRect(1185, 42, 54, 72);
      ctx.fillStyle = "#6ee7b7";
      ctx.font = "9px sans-serif";
      ctx.fillText("GREEN", 1196, 75);
      ctx.fillText("SCREEN", 1193, 88);

      // 3. Ish stollari va monitorlar
      Object.entries(DESKS).forEach(([id, d]) => {
        // Stol
        ctx.fillStyle = "#1e293b";
        ctx.beginPath();
        ctx.roundRect(d.x - 42, d.y - 44, 84, 34, 6);
        ctx.fill();
        ctx.strokeStyle = "#334155";
        ctx.stroke();

        // Monitor
        const av = avatars[id];
        const isWorking = av && av.status === "working";
        ctx.fillStyle = isWorking ? d.color : "#0f172a";
        ctx.fillRect(d.x - 18, d.y - 54, 36, 20);
        ctx.strokeStyle = "#64748b";
        ctx.strokeRect(d.x - 18, d.y - 54, 36, 20);
        if (isWorking) {
          ctx.fillStyle = "rgba(255,255,255,0.65)";
          ctx.fillRect(d.x - 14, d.y - 50, 20, 3);
          ctx.fillRect(d.x - 14, d.y - 44, 28, 3);
        }
      });

      // 4. Harakatlanuvchi Pixel Agentlar
      Object.values(avatars).forEach(av => {
        av.x += (av.tx - av.x) * 0.08;
        av.y += (av.ty - av.y) * 0.08;
        const bounce = av.status === "working" ? Math.abs(Math.sin(ts * 0.015 + av.bob)) * 4 : Math.sin(ts * 0.004 + av.bob) * 1.5;
        const ax = av.x, ay = av.y - bounce;

        // Tanlangan ramka
        if (selectedAgentId === av.id) {
          ctx.strokeStyle = "#eab308";
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.arc(ax, ay, 24, 0, Math.PI * 2);
          ctx.stroke();
        }

        // Soya
        ctx.fillStyle = "rgba(0,0,0,0.45)";
        ctx.beginPath();
        ctx.ellipse(av.x, av.y + 18, 13, 5, 0, 0, Math.PI * 2);
        ctx.fill();

        // Tana (pixel kurtka)
        ctx.fillStyle = av.color;
        ctx.beginPath();
        ctx.roundRect(ax - 11, ay - 2, 22, 18, 5);
        ctx.fill();

        // Bosh
        ctx.fillStyle = "#fde68a";
        ctx.beginPath();
        ctx.roundRect(ax - 9, ay - 18, 18, 16, 6);
        ctx.fill();

        // Soch / Quloqchin
        ctx.fillStyle = "#1e293b";
        ctx.fillRect(ax - 9, ay - 20, 18, 5);

        // Ko'zlar
        ctx.fillStyle = "#0f172a";
        ctx.fillRect(ax - 5, ay - 11, 3, 3);
        ctx.fillRect(ax + 2, ay - 11, 3, 3);

        // Ism va status nishoni
        ctx.fillStyle = "#e2e8f0";
        ctx.font = "bold 11px Segoe UI";
        ctx.textAlign = "center";
        ctx.fillText(av.label, ax, ay + 32);

        // Qisqa nutq pufagi (Speech Bubble)
        const shortTask = (av.task || "").slice(0, 26) + ((av.task || "").length > 26 ? "..." : "");
        if (av.status === "working" || selectedAgentId === av.id) {
          ctx.font = "10px Segoe UI";
          const tw = Math.min(200, ctx.measureText(shortTask).width + 16);
          ctx.fillStyle = av.status === "working" ? "#eab308" : "#1e293b";
          ctx.beginPath();
          ctx.roundRect(ax - tw / 2, ay - 46, tw, 20, 6);
          ctx.fill();
          ctx.fillStyle = av.status === "working" ? "#090b10" : "#f8fafc";
          ctx.fillText(shortTask, ax, ay - 33);
        }
        ctx.textAlign = "left";
      });

      requestAnimationFrame(drawPixelOffice);
    }

    document.getElementById('virtual-office-canvas').addEventListener('click', (e) => {
      const canvas = e.currentTarget;
      const rect = canvas.getBoundingClientRect();
      const cx = (e.clientX - rect.left) * (canvas.width / rect.width);
      const cy = (e.clientY - rect.top) * (canvas.height / rect.height);
      let hit = null;
      Object.values(avatars).forEach(av => {
        if (Math.hypot(cx - av.x, cy - av.y) < 36) hit = av;
      });
      if (hit) {
        selectedAgentId = hit.id;
        document.getElementById('office-selected-info').innerHTML =
          `🤖 <b>${hit.name}</b> | ECC Mutaxassis: <code>${hit.ecc}</code> | Bajarildi: <b>${hit.done}</b> | Vazifa: <i>${hit.task}</i>`;
      }
    });
    requestAnimationFrame(drawPixelOffice);

    // === 2. ECC 71 AGENT + 314 SKILL & OMNIROUTE CONTROLLER ===
    let _eccCatalog = null;
    async function loadEccCatalog() {
      if (_eccCatalog) return;
      const res = await fetch('/api/ecc/catalog');
      _eccCatalog = await res.json();
      document.getElementById('ecc-counts-badge').textContent =
        `${_eccCatalog.agents_count} ta Agent · ${_eccCatalog.skills_count} ta Skill tayyor`;

      const agentSel = document.getElementById('ecc-agent-select');
      agentSel.innerHTML = _eccCatalog.agents.map(a =>
        `<option value="${a.id}">${a.id} (${a.department}) — ${(a.description || '').slice(0, 55)}</option>`
      ).join('');
      if (_eccCatalog.agents.some(a => a.id === 'marketing-agent')) agentSel.value = 'marketing-agent';

      const skillSel = document.getElementById('ecc-skill-select');
      skillSel.innerHTML = `<option value="">-- Skillsiz (faqat agent) --</option>` + _eccCatalog.skills.map(s =>
        `<option value="${s.id}">${s.recommended ? '⭐ ' : ''}${s.id} — ${(s.description || '').slice(0, 50)}</option>`
      ).join('');

      filterEccCatalog();
    }

    function filterEccCatalog() {
      if (!_eccCatalog) return;
      const aq = (document.getElementById('ecc-agent-search').value || '').toLowerCase();
      const sq = (document.getElementById('ecc-skill-search').value || '').toLowerCase();

      const filteredAgents = _eccCatalog.agents.filter(a =>
        a.id.toLowerCase().includes(aq) || (a.description || '').toLowerCase().includes(aq) || a.department.toLowerCase().includes(aq)
      );
      document.getElementById('ecc-agents-grid').innerHTML = filteredAgents.map(a => `
        <div class="ecc-card" onclick="document.getElementById('ecc-agent-select').value='${a.id}'">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
            <b>🤖 ${a.id}</b>
            <span class="ecc-badge">${a.department}</span>
          </div>
          <div style="color:var(--muted);font-size:11.5px;">${(a.description || '').slice(0, 125)}</div>
        </div>
      `).join('') || '<div style="color:var(--muted);">Agent topilmadi</div>';

      const filteredSkills = _eccCatalog.skills.filter(s =>
        s.id.toLowerCase().includes(sq) || (s.description || '').toLowerCase().includes(sq)
      );
      document.getElementById('ecc-skills-grid').innerHTML = filteredSkills.slice(0, 90).map(s => `
        <div class="ecc-card" onclick="document.getElementById('ecc-skill-select').value='${s.id}'">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
            <b>${s.recommended ? '⭐ ' : '🧩 '}${s.id}</b>
          </div>
          <div style="color:var(--muted);font-size:11.5px;">${(s.description || '').slice(0, 125)}</div>
        </div>
      `).join('') || '<div style="color:var(--muted);">Skill topilmadi</div>';
    }

    async function runEccTask() {
      const btn = document.getElementById('ecc-run-btn');
      const outBox = document.getElementById('ecc-output-box');
      const agentId = document.getElementById('ecc-agent-select').value;
      const skillId = document.getElementById('ecc-skill-select').value;
      const prompt = document.getElementById('ecc-task-input').value.trim();
      if (!prompt) { alert("Iltimos, topshiriq matnini kiriting!"); return; }
      btn.disabled = true;
      btn.textContent = `⚡ ${agentId} ishlamoqda...`;
      outBox.style.display = 'block';
      outBox.textContent = "ECC Agent + Graphify kontekst yuklanmoqda...";
      try {
        const res = await fetch('/api/ecc/run', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ agent_id: agentId, skills: skillId ? [skillId] : [], prompt })
        });
        const data = await res.json();
        if (data.ok) {
          outBox.innerHTML = `✅ <b>Agent:</b> ${data.agent_id} | <b>Provayder:</b> ${data.provider}\n\n${data.answer}`;
          await loadState();
        } else {
          outBox.textContent = `⚠️ Xatolik: ${data.error || 'Nomaʼlum xato'}`;
        }
      } finally {
        btn.disabled = false;
        btn.textContent = '⚡ ECC Agentni OmniRoute/AI orqali Ishga Tushirish';
      }
    }

    async function startOmniroute() {
      const res = await fetch('/api/omniroute/start', { method: 'POST' });
      const data = await res.json();
      if (data.ok) {
        alert("⚡ OmniRoute ishga tushdi! Endi http://localhost:20128/dashboard orqali bepul provayderlarni ulashingiz mumkin.");
        await loadState();
      } else {
        alert("⚠️ " + (data.error || "OmniRoute ishga tushmadi"));
      }
    }

    loadState();
    runCalc();
    setInterval(loadState, 3000);
  </script>
</body>
</html>
"""


def build_dashboard_app(
    db: Database,
    settings: Settings,
    office: AgentOffice,
) -> web.Application:
    app = web.Application()
    weather_cache: dict[str, object] = {"ts": 0.0, "data": None}
    ecc_registry = ECCRegistry(getattr(settings, "ecc_root", "vendor/ecc"))
    graph_index = build_graphify_context_index("app")
    pdd_login_state: dict[str, object] = {"status": "idle", "message": "", "started_at": 0, "task": None}

    def _pdd_aux_path(filename: str) -> str:
        return os.path.join(os.path.dirname(settings.pdd_session_path) or "data", filename)

    def _current_pdd() -> PinduoduoConnector:
        return PinduoduoConnector(
            settings.pdd_client_id,
            settings.pdd_client_secret,
            settings.pdd_rapidapi_key,
            settings.pdd_session_path,
            apify_token=settings.pdd_apify_token,
        )

    async def health(_request: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "shop": settings.shop_name})

    async def index(_request: web.Request) -> web.Response:
        v2_file = Path(__file__).resolve().parent / "static" / "dashboard_v2.html"
        if v2_file.is_file():
            return web.Response(text=v2_file.read_text(encoding="utf-8"), content_type="text/html")
        return web.Response(text=DASHBOARD_HTML, content_type="text/html")

    async def api_state(_request: web.Request) -> web.Response:
        now = time.time()
        if not weather_cache["data"] or (now - float(weather_cache["ts"])) > 900:
            weather_cache["data"] = await fetch_tashkent_weather()
            weather_cache["ts"] = now

        rates = await get_rates(db, settings)
        params = await get_params(db, settings)
        agents_raw = await db.list_agents()
        agents = []
        for ag in agents_raw:
            ad = dict(ag)
            ad["id"] = ad.get("agent_id", "")
            try:
                ad["learnings"] = json.loads(ad.get("learnings_json") or "[]")
            except Exception:
                ad["learnings"] = []
            agents.append(ad)
        omni_status = await check_omniroute_status(
            getattr(settings, "omniroute_base_url", "http://localhost:20128/v1"),
            getattr(settings, "omniroute_api_key", "omniroute-local"),
        )
        looks_raw = await db.list_looks(only_active=False)
        looks = []
        for lk in looks_raw:
            d = dict(lk)
            raw_img = (d.get("photo_path") or "").replace("\\", "/")
            raw_vid = (d.get("video_path") or "").replace("\\", "/")
            img_name = os.path.basename(raw_img) if raw_img else f"look_{d['id']}.jpg"
            vid_name = os.path.basename(raw_vid) if raw_vid else f"look_{d['id']}_reels.mp4"
            img_full = os.path.join(office.media_dir, img_name) if img_name else ""
            vid_full = os.path.join(office.media_dir, vid_name) if vid_name else ""
            if vid_name and not os.path.isfile(vid_full):
                alt_vid = f"look_{d['id']}_reel.mp4"
                if os.path.isfile(os.path.join(office.media_dir, alt_vid)):
                    vid_name = alt_vid
                    vid_full = os.path.join(office.media_dir, alt_vid)
            d["photo_file"] = img_name
            d["video_file"] = vid_name
            d["photo_exists"] = bool(img_full and os.path.isfile(img_full))
            d["video_exists"] = bool(vid_full and os.path.isfile(vid_full))
            d["photo_url"] = f"/media/{img_name}" if d["photo_exists"] else ""
            d["video_url"] = f"/media/{vid_name}" if d["video_exists"] else ""
            d["insta_caption"] = format_instagram_caption(
                d,
                office.sales_username,
                settings.shop_name,
                manager_username=settings.manager_username,
            )
            looks.append(d)

        from .omniroute_server import OMNIROUTE_MODELS
        available_models = omni_status.get("models") or OMNIROUTE_MODELS

        logs = await db.list_agent_logs(limit=35)
        orders = await db.active_orders(limit=25)
        bank_transactions = await db.list_bank_transactions(limit=20)
        raw_ceo_brief = await db.get_setting("latest_ceo_brief")
        latest_ceo_brief = None
        if raw_ceo_brief:
            try:
                latest_ceo_brief = json.loads(raw_ceo_brief)
            except Exception:
                latest_ceo_brief = None
        raw_insta_analysis = await db.get_setting("latest_insta_analysis")
        latest_insta_analysis = None
        if raw_insta_analysis:
            try:
                latest_insta_analysis = json.loads(raw_insta_analysis)
            except Exception:
                latest_insta_analysis = None
        pdd_conn = _current_pdd()
        pdd_sess = get_pdd_session_details(settings.pdd_session_path)
        card_digits = "".join(ch for ch in (settings.card_number or "") if ch.isdigit())
        card_ok = len(card_digits) >= 16 and not card_digits.endswith("0000")
        connections = {
            "pdd": pdd_conn.is_live_api,
            "pdd_mode": pdd_conn.connection_mode,
            "pdd_user_id": pdd_sess.get("user_id") or "",
            "userbot": bool(settings.tg_api_id and settings.tg_api_hash and (settings.tg_session_string or settings.tg_phone)),
            "tg_bots": bool(
                ":" in settings.sales_bot_token
                and not settings.sales_bot_token.startswith("123456:")
                and ":" in settings.admin_bot_token
            ),
            "instagram": bool(settings.ig_user_id and settings.ig_access_token),
            "omniroute": omni_status["online"],
            "ecc": len(ecc_registry.agents) > 0,
            "bank_card": card_ok,
            "card_number": settings.card_number,
            "card_owner": settings.card_owner,
            "card_last4": card_digits[-4:] if len(card_digits) >= 4 else "",
        }
        return web.json_response({
            "shop_name": settings.shop_name,
            "rates": rates.__dict__,
            "params": params.__dict__,
            "weather": weather_cache["data"].__dict__,
            "benchmarks": COMPETITOR_BENCHMARKS,
            "competitor_profiles": COMPETITOR_PROFILES,
            "creative_strategy": build_reels_strategy_summary(weather_cache["data"]),
            "cargo_lines": {k: v.__dict__ for k, v in CARGO_LINES.items()},
            "connections": connections,
            "omniroute": omni_status,
            "available_models": available_models,
            "latest_ceo_brief": latest_ceo_brief,
            "latest_insta_analysis": latest_insta_analysis,
            "graphify": {
                "modules": graph_index["modules"],
                "classes": graph_index["classes"],
                "functions": graph_index["functions"],
            },
            "ecc_summary": (lambda cs: {
                "installed": len(ecc_registry.agents) > 0,
                "agents_count": cs["agents_count"],
                "skills_count": cs["skills_count"],
                "repo_agents_count": cs["repo_agents_count"],
                "repo_skills_count": cs["repo_skills_count"],
                "domain_filter": cs["domain_filter"],
                "departments": cs["departments"],
                "graphify": {
                    "modules": graph_index["modules"],
                    "classes": graph_index["classes"],
                    "functions": graph_index["functions"],
                },
            })(ecc_registry.summary_for_dashboard()),
            "channel_kit": generate_premium_channel_kit(settings.shop_name, settings.manager_username),
            "agents": agents,
            "looks": looks,
            "logs": logs,
            "orders": orders,
            "bank_transactions": bank_transactions,
        })

    async def api_ecc_catalog(request: web.Request) -> web.Response:
        include_all = request.query.get("scope") == "all"
        data = ecc_registry.summary_for_dashboard(include_all=include_all)
        data["graphify"] = {
            "modules": graph_index["modules"],
            "classes": graph_index["classes"],
            "functions": graph_index["functions"],
            "nodes": graph_index.get("nodes", []),
        }
        return web.json_response(data)

    async def api_ecc_run(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            body = {}
        agent_id = str(body.get("agent_id") or "marketing-agent").strip()
        prompt = str(body.get("prompt") or body.get("task") or "").strip()
        model = str(body.get("model") or "").strip()
        skills = body.get("skills") or []
        if not isinstance(skills, list):
            skills = [str(skills)]
        if not prompt:
            return web.json_response({"ok": False, "error": "Topshiriq matni bo'sh"}, status=400)
        res = await run_ecc_specialist(
            ecc_registry,
            settings,
            agent_id=agent_id,
            task_prompt=prompt,
            skill_ids=[str(s) for s in skills if s],
            db=db,
            model=model,
        )
        return web.json_response(res)

    async def api_omniroute_start(_request: web.Request) -> web.Response:
        omni_url = getattr(settings, "omniroute_base_url", "http://localhost:20128/v1")
        omni_key = getattr(settings, "omniroute_api_key", "omniroute-local")
        st = await check_omniroute_status(omni_url, omni_key)
        if st["online"]:
            return web.json_response({"ok": True, "already_running": True, **st})
        omni_bin = shutil.which("omniroute") or shutil.which("omniroute.cmd")
        if not omni_bin:
            return web.json_response(
                {"ok": False, "error": "omniroute CLI topilmadi. Terminalda: npm install -g omniroute"},
                status=404,
            )
        try:
            subprocess.Popen(
                [omni_bin],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            await asyncio.sleep(2.5)
            st2 = await check_omniroute_status(omni_url, omni_key)
            return web.json_response({"ok": True, "started": True, **st2})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def api_office_briefing(_request: web.Request) -> web.Response:
        res = await run_ceo_strategy_cycle(
            ecc_registry,
            db,
            settings,
            focus_topic="Kunlik AI Majlis: bozor narxlari, bo'limlar yuklamasi va navbatdagi vazifalar",
            apply_directives=True,
        )
        return web.json_response({
            "ok": True,
            "summary": res["diagnosis"],
            "directives": res["directives"],
            "provider": res.get("provider", "OmniRoute"),
        })

    async def api_ceo_analyze(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            body = {}
        focus = str(body.get("focus") or "").strip()
        apply_orders = bool(body.get("apply_directives", True))
        res = await run_ceo_strategy_cycle(
            ecc_registry,
            db,
            settings,
            focus_topic=focus,
            apply_directives=apply_orders,
        )
        return web.json_response(res)

    async def api_ceo_apply_pricing(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            body = {}
        mode = str(body.get("mode") or "competitive").strip()
        res = await apply_ceo_pricing_preset(db, settings, mode=mode)
        return web.json_response(res)

    async def api_delete_look(request: web.Request) -> web.Response:
        try:
            lid = int(request.match_info["id"])
        except ValueError:
            return web.json_response({"ok": False, "error": "Noto'g'ri ID"}, status=400)
        look = await db.get_look(lid)
        if look:
            for k in ("photo_path", "video_path"):
                p = look.get(k)
                if p and os.path.exists(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass
            await db.delete_look(lid)
        return web.json_response({"ok": True, "deleted_id": lid})

    async def api_clear_looks(_request: web.Request) -> web.Response:
        cnt = await db.clear_all_looks()
        if os.path.isdir(office.media_dir):
            for fname in os.listdir(office.media_dir):
                if fname.startswith("look_"):
                    try:
                        os.remove(os.path.join(office.media_dir, fname))
                    except OSError:
                        pass
        await db.log_agent_action("director", f"Ombor tozalandi ({cnt} ta test look o'chirildi)", "Pinduoduo bosqichiga tayyor")
        return web.json_response({"ok": True, "cleared": cnt})

    async def api_bank_webhook(request: web.Request) -> web.Response:
        raw_body = await request.text()
        payload: dict = {}
        try:
            parsed = json.loads(raw_body)
            if isinstance(parsed, dict):
                payload = parsed
        except Exception:
            pass
        if settings.bank_webhook_secret:
            hdr_secret = request.headers.get("X-Webhook-Secret", "").strip()
            body_secret = str(payload.get("secret") or "").strip()
            if hdr_secret != settings.bank_webhook_secret and body_secret != settings.bank_webhook_secret:
                return web.json_response({"ok": False, "error": "unauthorized"}, status=403)
        text = str(payload.get("text") or payload.get("message") or payload.get("msg") or raw_body)
        source = str(payload.get("source") or "bank_webhook")
        res = await AccountantAgent(db, settings).process_bank_notification(
            text,
            source=source,
            sales_bot=office.sales_bot,
            admin_bot=office.admin_bot,
            userbot=getattr(office, "userbot", None),
        )
        return web.json_response({"ok": True, **res})

    async def api_run_pipeline(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            body = {}
        season = body.get("season", "avtomatik ob-havo")
        res = await office.run_look_pipeline(season=season)
        return web.json_response({
            "ok": True,
            "look_id": res.look_id,
            "title": res.title,
            "piece_count": res.piece_count,
            "palette_name": res.palette_name,
            "prepay_uzs": res.prepay_uzs,
            "prepay_50_uzs": res.prepay_50_uzs,
            "remaining_50_uzs": res.remaining_50_uzs,
            "mp4_path": res.mp4_path,
        })

    async def api_calc(request: web.Request) -> web.Response:
        raw_cny = request.query.get("cny", "42")
        raw_w = request.query.get("weight", "0.8")
        mode = request.query.get("mode", "").strip()
        try:
            parts = [float(x.strip()) for x in re.split(r"[+\s]+", raw_cny.replace(",", ".")) if x.strip()]
            w = float(raw_w.replace(",", "."))
            rates = await get_rates(db, settings)
            base_params = await get_params(db, settings)

            discount = float(request.query.get("wholesale_discount", "0") or "0")
            if mode == "yatt_customs" and not request.query.get("wholesale_discount"):
                discount = 25.0  # 1688/fabrika ulgurji chegirmasi (~25%)
            scale = max(0.2, 1.0 - discount / 100.0)
            items = [Item(f"Buyum #{i}", round(p * scale, 2), 0.0) for i, p in enumerate(parts, 1)]
            items[0].weight_kg = w

            if mode == "safe_50":
                calc_params = PriceParams(
                    vykup_percent=0.0,
                    profit_percent=float(request.query.get("profit", "105") or 105),
                    payment_fee_percent=base_params.payment_fee_percent,
                    china_shipping_cny_per_item=0.0,
                    cargo_usd_per_kg=base_params.cargo_usd_per_kg,
                    cargo_client_uzs_per_kg=float(request.query.get("cargo_uzs_kg", base_params.cargo_client_uzs_per_kg)),
                    conversion_fee_percent=base_params.conversion_fee_percent,
                    ensure_50_covers_cost=True,
                )
            elif mode == "yatt_customs":
                calc_params = PriceParams(
                    vykup_percent=0.0,
                    profit_percent=float(request.query.get("profit", "45") or 45),
                    payment_fee_percent=base_params.payment_fee_percent,
                    china_shipping_cny_per_item=0.0,
                    cargo_usd_per_kg=4.5,  # Tijoriy avto/konsolidatsiya (~$4.5/kg)
                    cargo_client_uzs_per_kg=float(request.query.get("cargo_uzs_kg", "60000")),
                    conversion_fee_percent=base_params.conversion_fee_percent,
                    ensure_50_covers_cost=False,
                    customs_duty_percent=float(request.query.get("duty", "15") or 15),
                    vat_percent=float(request.query.get("vat", "12") or 12),
                    tax_percent=float(request.query.get("tax", "4") or 4),
                )
            elif mode == "competitive":
                calc_params = PriceParams(
                    vykup_percent=0.0,
                    profit_percent=float(request.query.get("profit", "65") or 65),
                    payment_fee_percent=base_params.payment_fee_percent,
                    china_shipping_cny_per_item=0.0,
                    cargo_usd_per_kg=base_params.cargo_usd_per_kg,
                    cargo_client_uzs_per_kg=float(request.query.get("cargo_uzs_kg", "115000")),
                    prepay_round_to=base_params.prepay_round_to or 50000,
                    conversion_fee_percent=2.5,
                    ensure_50_covers_cost=False,
                )
            else:
                calc_params = base_params
                if request.query.get("profit"):
                    calc_params = PriceParams(**{**base_params.__dict__, "profit_percent": float(request.query["profit"])})

            b = calculate(items, rates, calc_params)
            return web.json_response({
                **b.__dict__,
                "mode": mode or "current",
                "profit_percent": calc_params.profit_percent,
                "customs_duty_percent": calc_params.customs_duty_percent,
                "vat_percent": calc_params.vat_percent,
                "tax_percent": calc_params.tax_percent,
                "wholesale_discount": discount,
            })
        except Exception as e:
            return web.json_response({"error": str(e)}, status=400)

    async def api_pdd_status(_request: web.Request) -> web.Response:
        pdd = _current_pdd()
        sess = get_pdd_session_details(settings.pdd_session_path)
        raw_addr_status = await db.get_setting("pdd_addresses_status")
        addr_status = None
        if raw_addr_status:
            try:
                addr_status = json.loads(raw_addr_status)
            except Exception:
                addr_status = None
        task = pdd_login_state.get("task")
        task_running = bool(task and hasattr(task, "done") and not task.done())
        disk_status: dict[str, object] = {}
        st_file = _pdd_aux_path("pdd_login_status.json")
        if os.path.exists(st_file):
            try:
                disk_status = json.loads(Path(st_file).read_text(encoding="utf-8"))
            except Exception:
                disk_status = {}
        if not task_running and sess["connected"]:
            pdd_login_state["status"] = "connected"
            pdd_login_state["message"] = "Pinduoduo sessiyasi ulandi!"
            eff_status = "connected"
            eff_msg = "Pinduoduo sessiyasi ulandi!"
        else:
            eff_status = str(disk_status.get("status") or ("waiting_login" if task_running else pdd_login_state["status"]))
            eff_msg = str(disk_status.get("message") or pdd_login_state["message"])
        return web.json_response({
            "ok": True,
            "connected": pdd.is_live_api,
            "mode": pdd.connection_mode,
            "session": sess,
            "login_state": {
                "status": eff_status,
                "message": eff_msg,
                "running": task_running,
            },
            "has_official_api": bool(settings.pdd_client_id and settings.pdd_client_secret),
            "has_apify": bool(settings.pdd_apify_token),
            "has_rapidapi": bool(settings.pdd_rapidapi_key),
            "cargo_addresses": cargo_address_specs(),
            "addresses_sync": addr_status,
        })

    async def api_pdd_connect(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            body = {}
        force = bool(body.get("force", False))
        phone = str(body.get("phone") or settings.tg_phone or "998200080769").strip()
        send_sms = bool(body.get("send_sms", True))
        pdd = _current_pdd()
        if pdd.is_live_api and not force and pdd.connection_mode == "browser_session":
            return web.json_response({
                "ok": True,
                "status": "already_connected",
                "session": get_pdd_session_details(settings.pdd_session_path),
            })

        existing_task = pdd_login_state.get("task")
        if existing_task and hasattr(existing_task, "done") and not existing_task.done():
            return web.json_response({
                "ok": True,
                "status": "waiting_login",
                "message": "Pinduoduo login oynasi allaqachon ochilgan — SMS kodni kiriting.",
            })

        pdd_login_state["status"] = "waiting_login"
        pdd_login_state["started_at"] = int(time.time())
        pdd_login_state["message"] = f"Chrome oynasi ochildi — {phone} raqamiga SMS yuborilmoqda."

        async def _login_worker() -> None:
            try:
                ok = await interactive_browser_login(
                    settings.pdd_session_path,
                    timeout_sec=300,
                    phone=phone,
                    send_sms=send_sms,
                    status_path=_pdd_aux_path("pdd_login_status.json"),
                    otp_file=_pdd_aux_path("pdd_otp.txt"),
                )
                if ok:
                    pdd_login_state["status"] = "connected"
                    pdd_login_state["message"] = "Pinduoduo sessiyasi muvaffaqiyatli saqlandi!"
                    await db.log_agent_action(
                        "skaut",
                        "Pinduoduo shaxsiy akkaunti muvaffaqiyatli ulandi",
                        f"Sessiya fayli: {settings.pdd_session_path}",
                    )
                else:
                    pdd_login_state["status"] = "timeout"
                    pdd_login_state["message"] = "Vaqt tugadi yoki oyna yopildi — qayta urinib ko'ring."
            except Exception as err:
                pdd_login_state["status"] = "error"
                pdd_login_state["message"] = str(err)[:180]

        pdd_login_state["task"] = asyncio.create_task(_login_worker())
        return web.json_response({
            "ok": True,
            "status": "waiting_login",
            "message": pdd_login_state["message"],
        })

    async def api_pdd_submit_otp(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            body = {}
        code = re.sub(r"\D", "", str(body.get("code") or ""))[:6]
        if len(code) < 4:
            return web.json_response({"ok": False, "error": "4–6 xonali SMS kod kiriting"}, status=400)
        otp_path = _pdd_aux_path("pdd_otp.txt")
        os.makedirs(os.path.dirname(otp_path) or "data", exist_ok=True)
        Path(otp_path).write_text(code, encoding="utf-8")
        return web.json_response({"ok": True, "message": "SMS kod brauzerga uzatildi — tekshirilmoqda..."})

    async def api_pdd_import_session(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            body = {}
        raw = str(body.get("session_data") or body.get("cookie") or body.get("raw") or "").strip()
        res = import_pdd_session(raw, settings.pdd_session_path)
        if not res.get("ok"):
            return web.json_response(res, status=400)
        pdd_login_state["status"] = "connected"
        pdd_login_state["message"] = "Pinduoduo sessiyasi muvaffaqiyatli ulandi!"
        st_path = _pdd_aux_path("pdd_login_status.json")
        try:
            Path(st_path).write_text(
                json.dumps({"status": "connected", "message": pdd_login_state["message"], "ts": int(time.time())}, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass
        await db.log_agent_action(
            "skaut",
            "Pinduoduo sessiyasi import qilindi",
            f"User ID: {res.get('user_id') or '-'} | Sessiya: {settings.pdd_session_path}",
        )
        return web.json_response(res)

    async def api_pdd_credentials(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            body = {}
        env_updates: dict[str, str] = {}
        for field_name, attr_name, env_key in (
            ("client_id", "pdd_client_id", "PDD_CLIENT_ID"),
            ("client_secret", "pdd_client_secret", "PDD_CLIENT_SECRET"),
            ("apify_token", "pdd_apify_token", "APIFY_API_TOKEN"),
            ("rapidapi_key", "pdd_rapidapi_key", "PDD_RAPIDAPI_KEY"),
        ):
            if field_name in body and body[field_name] is not None:
                val = str(body[field_name]).strip()
                object.__setattr__(settings, attr_name, val)
                os.environ[env_key] = val
                env_updates[env_key] = val
        if env_updates and not os.environ.get("PYTEST_CURRENT_TEST") and settings.db_path != ":memory:":
            _persist_env_updates(env_updates)
        pdd = _current_pdd()
        if pdd.is_live_api:
            await db.log_agent_action("skaut", f"Pinduoduo API kalitlari saqlandi ({pdd.connection_mode})")
        return web.json_response({
            "ok": True,
            "connected": pdd.is_live_api,
            "mode": pdd.connection_mode,
        })

    async def api_pdd_sync_addresses(_request: web.Request) -> web.Response:
        pdd = _current_pdd()
        specs = cargo_address_specs()
        res = await pdd.inspect_saved_addresses(specs)
        await db.set_setting("pdd_addresses_status", json.dumps({
            "ts": int(time.time()),
            "ok": bool(res.get("ok")),
            "matched_codes": res.get("matched_codes", []),
            "all_synced": bool(res.get("all_synced")),
        }, ensure_ascii=False))
        await db.log_agent_action(
            "cargo_logistics",
            f"Pinduoduo manzillari tekshirildi: {', '.join(res.get('matched_codes') or []) or 'yangi qo`shish kerak'}",
            f"Kutilgan omborlar: TUJJOR-AVIA (T-7621) + DOOR-AVIA (ID BP-1)",
        )
        return web.json_response({**res, "cargo_addresses": specs})

    async def api_pdd_test_search(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            body = {}
        kw = str(body.get("keyword") or "卫衣男").strip()
        save_wl = bool(body.get("save_wishlist", False))
        pdd = _current_pdd()
        if not pdd.is_live_api:
            return web.json_response({"ok": False, "error": "Avval Pinduoduo akkaunti yoki API ni ulang"}, status=400)
        products = await pdd.search_live(kw, page_size=3)
        wl_res = None
        if save_wl and products and pdd.connection_mode == "browser_session":
            wl_res = await pdd.save_to_wishlist(products[0].goods_id)
        err_msg = ""
        last_err = getattr(pdd, "last_error", "")
        if not products and last_err == "verification_required":
            err_msg = (
                "Pinduoduo qidiruvda ilova orqali QR xavfsizlik tasdig'ini so'radi (psnl_verification). "
                "Chrome'da Pinduoduo ilovasi bilan QR ni bir marta tasdiqlang yoki Cookie-Editor JSON ni import qiling "
                "(manzil kitobi va buyurtma tayyorlash esa allaqachon ishlamoqda)."
            )
        elif not products and last_err == "search_app_only":
            err_msg = (
                "Pinduoduo veb-qidiruvi (mobile.yangkeduo.com) faqat mobil ilova uchun cheklangan ('系统繁忙'). "
                "Akkaunt sessiyangiz va kargo manzillari (TUJJOR-AVIA, DOOR-AVIA) esa ulangan va to'g'ridan-to'g'ri tovar sahifasi / manzil kitobi ishlamoqda; "
                "avto-kalit qidiruv uchun ixtiyoriy RapidAPI yoki Duoduo Jinbao API ulanishi mumkin."
            )
        elif not products and last_err == "session_expired":
            err_msg = (
                "Pinduoduo sessiyasi eskirgan yoki anti-bot tizimi tomonidan bekor qilingan ('session_expired'). "
                "Chrome'da mobile.yangkeduo.com ga kirib Cookie-Editor JSON ni qayta import qiling."
            )
        elif not products:
            err_msg = (
                "Pinduoduo veb-qidiruvidan mahsulot ro'yxati olinmadi "
                "(mobile.yangkeduo.com qidiruvi ilova cheklovi sababli bloklangan; RapidAPI yoki Duoduo Jinbao API kerak)."
            )
        return web.json_response({
            "ok": len(products) > 0,
            "mode": pdd.connection_mode,
            "keyword": kw,
            "items": [pr.__dict__ for pr in products],
            "wishlist_test": wl_res,
            "error": err_msg,
        })

    async def api_order_prepare_pdd(request: web.Request) -> web.Response:
        try:
            oid = int(request.match_info["id"])
        except ValueError:
            return web.json_response({"ok": False, "error": "Noto'g'ri buyurtma ID"}, status=400)
        order = await db.get_order(oid)
        if not order:
            return web.json_response({"ok": False, "error": "Buyurtma topilmadi"}, status=404)
        look = await db.get_look(int(order["look_id"])) if order.get("look_id") else None
        items = look_items(look) if look else []
        logistics = LogisticsAgent(db, settings)
        line = logistics.select_cargo_line(order.get("address") or "")
        spec = next((s for s in cargo_address_specs() if s["code"] == line.code), {
            "code": line.code,
            "name": line.name,
            "client_id": line.client_id,
            "cn_recipient": line.cn_recipient,
            "cn_phone": line.cn_phone,
            "cn_address": line.cn_address,
        })
        pdd = _current_pdd()
        packet = pdd.prepare_order_checkout(order, items, spec)
        await db.log_agent_action(
            "cargo_logistics",
            f"Buyurtma #{oid} Pinduoduo to'lov paketi tayyorlandi ({line.code})",
            f"Razmer: {packet['client_size']} | Rang: {packet['client_color']} | Tovarlar: {len(packet['items'])} ta",
        )
        return web.json_response(packet)

    async def serve_media(request: web.Request) -> web.StreamResponse:
        name = os.path.basename(request.match_info["name"])
        full = os.path.join(office.media_dir, name)
        if not os.path.isfile(full):
            if name.endswith("_reels.mp4"):
                alt = os.path.join(office.media_dir, name.replace("_reels.mp4", "_reel.mp4"))
                if os.path.isfile(alt):
                    full = alt
                else:
                    raise web.HTTPNotFound()
            else:
                raise web.HTTPNotFound()
        low = full.lower()
        headers = {"Cache-Control": "public, max-age=300", "Accept-Ranges": "bytes"}
        if low.endswith(".mp4"):
            headers["Content-Type"] = "video/mp4"
        elif low.endswith(".jpg") or low.endswith(".jpeg"):
            headers["Content-Type"] = "image/jpeg"
        elif low.endswith(".png"):
            headers["Content-Type"] = "image/png"
        return web.FileResponse(full, headers=headers)

    async def api_office_diagnostics(_request: web.Request) -> web.Response:
        omni = await check_omniroute_status(
            getattr(settings, "omniroute_base_url", "http://localhost:20128/v1"),
            getattr(settings, "omniroute_api_key", "omniroute-local"),
        )
        agents = await db.list_agents()
        looks_raw = await db.list_looks(only_active=False)
        playable = 0
        for lk in looks_raw:
            vp = os.path.join(office.media_dir, os.path.basename((lk.get("video_path") or "").replace("\\", "/")))
            if os.path.isfile(vp) and vp.lower().endswith(".mp4"):
                playable += 1
        cs = ecc_registry.summary_for_dashboard()
        pdd = _current_pdd()
        return web.json_response({
            "ok": True,
            "core_agents_count": len(agents),
            "core_agents": [
                {"id": a["agent_id"], "name": a["name"], "status": a["status"], "tasks_done": a["tasks_done"]}
                for a in agents
            ],
            "specialists_count": cs["agents_count"],
            "skills_count": cs["skills_count"],
            "omniroute_online": omni["online"],
            "omniroute_models": len(omni.get("models") or []),
            "looks_total": len(looks_raw),
            "looks_playable_mp4": playable,
            "pdd_connected": pdd.is_live_api,
            "pdd_mode": pdd.connection_mode,
        })

    async def api_analyze_competitor(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            body = {}
        target = str(body.get("target") or body.get("handle") or "_tima_shop").strip()
        w = weather_cache["data"] or await fetch_tashkent_weather()
        weather_cache["data"] = w
        weather_cache["ts"] = time.time()
        res = await analyze_competitor_with_ai(target, settings, db=db, weather=w)
        await db.set_setting("latest_insta_analysis", json.dumps(res, ensure_ascii=False))
        return web.json_response({"ok": True, "analysis": res})

    app.router.add_get("/health", health)
    app.router.add_get("/", index)
    app.router.add_get("/api/state", api_state)
    app.router.add_post("/api/trends/analyze_competitor", api_analyze_competitor)
    app.router.add_get("/api/pdd/status", api_pdd_status)
    app.router.add_post("/api/pdd/connect", api_pdd_connect)
    app.router.add_post("/api/pdd/submit_otp", api_pdd_submit_otp)
    app.router.add_post("/api/pdd/import_session", api_pdd_import_session)
    app.router.add_post("/api/pdd/credentials", api_pdd_credentials)
    app.router.add_post("/api/pdd/sync_addresses", api_pdd_sync_addresses)
    app.router.add_post("/api/pdd/test_search", api_pdd_test_search)
    app.router.add_post("/api/orders/{id}/prepare_pdd", api_order_prepare_pdd)
    app.router.add_get("/api/ecc/catalog", api_ecc_catalog)
    app.router.add_post("/api/ecc/run", api_ecc_run)
    app.router.add_get("/api/office/diagnostics", api_office_diagnostics)
    app.router.add_post("/api/office/briefing", api_office_briefing)
    app.router.add_post("/api/ceo/analyze", api_ceo_analyze)
    app.router.add_post("/api/ceo/apply_pricing", api_ceo_apply_pricing)
    app.router.add_post("/api/looks/{id}/delete", api_delete_look)
    app.router.add_post("/api/looks/clear", api_clear_looks)
    app.router.add_post("/api/omniroute/start", api_omniroute_start)
    app.router.add_post("/api/bank_webhook", api_bank_webhook)
    app.router.add_post("/api/run_pipeline", api_run_pipeline)
    app.router.add_get("/api/calc", api_calc)
    app.router.add_get("/media/{name}", serve_media)
    static_dir = Path(__file__).resolve().parent / "static"
    if static_dir.is_dir():
        app.router.add_static("/static", str(static_dir))
    return app


async def start_dashboard_server(
    db: Database,
    settings: Settings,
    office: AgentOffice,
) -> web.AppRunner:
    os.makedirs(office.media_dir, exist_ok=True)
    app = build_dashboard_app(db, settings, office)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", settings.office_port)
    await site.start()
    log.info("🏢 XAN SHOP 24/7 AI Agent Office Web-Paneli ishga tushdi: http://localhost:%d", settings.office_port)
    return runner


async def _standalone() -> None:
    s = load_settings()
    db = Database(s.db_path)
    await db.connect()
    office = AgentOffice(db=db, settings=s)
    if not await db.list_looks(only_active=False):
        await office.run_look_pipeline()
    runner = await start_dashboard_server(db, s, office)
    print(f"🏢 XAN SHOP AI Agent Office ochildi: http://localhost:{s.office_port}")
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await runner.cleanup()
        await db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(_standalone())
