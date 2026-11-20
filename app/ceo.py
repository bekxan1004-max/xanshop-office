"""XAN SHOP — Avtonom Boshqaruvchi AI (Strategik Direktor & Buyruq Tizimi).

Oddiy kuzatuvchi emas: do'konning real iqtisodiyoti, raqobatchi narxlari (~380k look),
oylik $200 bojxona limiti -> YaTT/1688 o'sish rejasi va bo'limlar holatini tahlil qilib,
har bir AI bo'limga aniq ijro buyruqlarini (`directives`) yuboradi va bajarilishini nazorat qiladi.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from .config import Settings
from .db import Database
from .ecc_engine import ECCRegistry, run_ecc_specialist
from .economy import get_params, get_rates
from .pinduoduo import has_valid_pdd_session
from .pricing import Item, PriceParams, Rates, calculate

log = logging.getLogger(__name__)

MARKET_BENCHMARK_LOOK_UZS = 550_000
CUSTOMS_MONTHLY_LIMIT_USD = 200.0

PRICING_PRESETS: dict[str, dict[str, Any]] = {
    "competitive": {
        "label": "Bozorga mos raqobatbardosh (35% foyda, 12 000 so'm/100gr kargo)",
        "profit_percent": 35,
        "vykup_percent": 0,
        "china_shipping_cny_per_item": 0,
        "conversion_fee_percent": 2.5,
        "ensure_50_covers_cost": "0",
        "cargo_client_uzs_per_kg": 120000,
    },
    "safe_50": {
        "label": "Yuqori marjali (45% foyda, 12 000 so'm/100gr kargo)",
        "profit_percent": 45,
        "vykup_percent": 0,
        "china_shipping_cny_per_item": 0,
        "conversion_fee_percent": 2.5,
        "ensure_50_covers_cost": "0",
        "cargo_client_uzs_per_kg": 120000,
    },
    "yatt_customs": {
        "label": "YaTT + Tijoriy Bojxona (>$200/oy reja)",
        "profit_percent": 35,
        "vykup_percent": 0,
        "china_shipping_cny_per_item": 0,
        "conversion_fee_percent": 2.5,
        "ensure_50_covers_cost": "0",
        "cargo_client_uzs_per_kg": 120000,
    },
}


async def collect_business_telemetry(db: Database, settings: Settings) -> dict[str, Any]:
    """Boshqaruvchi AI qaror qabul qilishi uchun jonli do'kon va bozor metrikalarini yig'adi."""
    rates = await get_rates(db, settings)
    params = await get_params(db, settings)
    looks = await db.list_looks(only_active=False)
    orders = await db.all_orders()
    agents = await db.list_agents()

    paid_orders = [
        o for o in orders if o.get("status") in ("paid", "bought", "china_warehouse", "in_transit", "arrived", "completed")
    ]
    used_usd = round(
        sum(float(o.get("goods_cost_uzs") or 0) for o in paid_orders) / max(1.0, rates.usd_uzs),
        1,
    )
    total_profit_uzs = sum(int(o.get("profit_uzs") or 0) for o in paid_orders)
    avg_look_prepay = int(sum(int(l.get("prepay_uzs") or 0) for l in looks) / len(looks)) if looks else 0

    # Namuna 3 qismli kapsula (¥135, 1.3 kg) joriy parametrlarda nechaga tushishini tekshirish
    sample_capsule = calculate(
        [Item("Xudi", 45, 0.5), Item("Shim", 48, 0.45), Item("Lofer", 42, 0.35)],
        rates,
        params,
    )
    single_100k = calculate([Item("100k Kiyim", 55, 0.45)], rates, params)

    pdd_ok = bool(
        (settings.pdd_client_id and settings.pdd_client_secret)
        or getattr(settings, "pdd_apify_token", "")
        or settings.pdd_rapidapi_key
        or has_valid_pdd_session(settings.pdd_session_path)
    )
    ig_ok = bool(settings.ig_user_id and settings.ig_access_token)

    return {
        "looks_count": len(looks),
        "avg_look_prepay_uzs": avg_look_prepay,
        "orders_count": len(orders),
        "paid_orders_count": len(paid_orders),
        "total_profit_uzs": total_profit_uzs,
        "customs_used_usd": used_usd,
        "customs_limit_usd": CUSTOMS_MONTHLY_LIMIT_USD,
        "customs_pct": min(100, round(used_usd / CUSTOMS_MONTHLY_LIMIT_USD * 100)),
        "yatt_recommended": used_usd >= 160.0 or len(paid_orders) >= 8,
        "rates": {"cny_uzs": rates.cny_uzs, "usd_uzs": rates.usd_uzs},
        "params": {
            "profit_percent": params.profit_percent,
            "vykup_percent": params.vykup_percent,
            "china_shipping_cny_per_item": params.china_shipping_cny_per_item,
            "conversion_fee_percent": params.conversion_fee_percent,
            "ensure_50_covers_cost": params.ensure_50_covers_cost,
            "cargo_client_uzs_per_kg": params.cargo_client_uzs_per_kg,
        },
        "sample_capsule_uzs": sample_capsule.prepay_uzs,
        "sample_100k_item_uzs": single_100k.prepay_uzs,
        "market_benchmark_uzs": MARKET_BENCHMARK_LOOK_UZS,
        "connections": {"pinduoduo": pdd_ok, "instagram": ig_ok},
        "agents": [
            {
                "id": a["agent_id"],
                "name": a["name"],
                "status": a["status"],
                "tasks_done": a["tasks_done"],
                "current_task": a["current_task"],
            }
            for a in agents
        ],
    }


def build_default_directives(t: dict[str, Any]) -> dict[str, Any]:
    """Telemetriya asosida bo'limlar uchun aniq, ijro etiladigan CEO buyruqlarini tuzadi."""
    p = t["params"]
    price_too_high = p["profit_percent"] > 85 or p["ensure_50_covers_cost"]
    pdd_ok = t["connections"]["pinduoduo"]
    ig_ok = t["connections"]["instagram"]
    used_usd = t["customs_used_usd"]

    directives: list[dict[str, str]] = [
        {
            "target_agent": "insta_analyst",
            "priority": "yuqori",
            "command": "@_tima_shop, @stylesh_shop va @lookzona.uz Reels hooklari, zvuk, jonli narxlar va komment triggerlarini kuzatib 5–12 kun oldingi trendni uzat",
            "reason": "Raqobatchilar jonli ishchilar jamoasi qilayotgan kontent va bozor narxlarini real vaqtda tahlil qilamiz.",
        },
        {
            "target_agent": "skaut",
            "priority": "yuqori",
            "command": (
                "5–12 kunlik ob-havo prognozi va jonli raqobatchi narxlariga qarab Pinduoduo'dan eng sifatli va hamyonbop (35% marja) yangi kapsulalarni sarala"
                if pdd_ok
                else "Pinduoduo API ulangach sifatli va arzon buyumlarni 5–12 kun oldingi ob-havoga moslab yig'ishga tayyor tur"
            ),
            "reason": f"Look narxlari raqobatchilardan hamyonbop ({t['sample_capsule_uzs']:,} so'm) chiqishi savdo tezligini oshiradi.".replace(",", " "),
        },
        {
            "target_agent": "smm_manager",
            "priority": "yuqori",
            "command": (
                "5–12 kun Avia muddati, 12 000 so'm/100gr kargo va Insta Tahlilchi topgan hooklarni Telegram + Instagram Reels kampaniyasida yurgiz"
                if ig_ok
                else "Telegram kanal va @xans_styles uchun 5–12 kun Avia sharti va 12 000 so'm/100gr kargo bilan saqlanadigan (Save) kapsula postlarini tayyorla"
            ),
            "reason": "5–12 kunlik real muddat va 12 000 so'm/100gr kargo raqobatchilardan (13 000 so'm/100gr) ustun turadi.",
        },
        {
            "target_agent": "video_employee",
            "priority": "yuqori",
            "command": "Haqiqiy Pinduoduo kiyim rasmlaridan yuz va fonni qirqib, Insta Tahlilchi tanlagan trend zvuk (TTS ovozsiz!) bilan 9:16 montajni qo'lla",
            "reason": "Reels videoda sun'iy TTS ovoz bo'lmasligi, haqiqiy yangi kiyimlar ko'rinishi va mijoz olganda 100% rozi bo'lishi shart.",
        },
        {
            "target_agent": "sales_stylist",
            "priority": "yuqori",
            "command": "Mijozlarga do'kon jadvali bo'yicha alohida (ust/shim/oyoq kiyim) aniq razmer ber, 5–12 kun Avia va 12 000 so'm/100gr kargoni halol tushuntir",
            "reason": "Mijoz buyurtmani qo'liga olganda 100% mamnun bo'lishi va hech qachon hafsalasi pir bo'lmasligi kerak.",
        },
        {
            "target_agent": "accountant",
            "priority": "yuqori",
            "command": (
                f"Foyda ustamasi ({p['profit_percent']:g}%) juda yuqori — 35% raqobatbardosh marjaga mosla"
                if price_too_high
                else "HUMO 9860 3501 4182 4135 (*4135, POLVONOV BEKMUROD) tushumlari, 35% marja va 12 000 so'm/100gr kargo nazoratini ushla"
            ),
            "reason": "Rasmiy HUMO *4135 kartasi ulangan; raqobatbardosh narx ko'proq buyurtma va barqaror foyda keltiradi.",
        },
        {
            "target_agent": "cargo_logistics",
            "priority": "yuqori" if used_usd >= 140 else "o'rta",
            "command": (
                f"Oylik limit ${used_usd}/$200 ga yetmoqda: YaTT + tijoriy oq bojxona rejasini tayyorla"
                if used_usd >= 140
                else f"TUJJOR-AVIA ($9.5/kg) va Door-to-Door ($9.5/kg, 5–12 kun) orasida $200 limitni (${used_usd}/$200) kuzat"
            ),
            "reason": "Xitoy ichki 1–4 kun + Avia 4–8 kun = jami 5–12 kunlik real logistika nazorati.",
        },
    ]

    market_verdict = (
        f"Narx va raqobat auditi: hozirgi parametrlarda ({p['profit_percent']:g}% ustama, 12 000 so'm/100gr kargo) 3 qismli kapsula {t['sample_capsule_uzs']:,} so'm, "
        f"1 dona tovar {t['sample_100k_item_uzs']:,} so'mga chiqmoqda."
    ).replace(",", " ")

    customs_plan = (
        f"Bojxona & YaTT ($200 limit, hozir ${used_usd}/$200): "
        "1) 0–$200/oy — Pinduoduo + Avia kuryer (5–12 kun, 0% boj). "
        "2) $200+ oshganda — YaTT ochib tijoriy kargo ga o'tish."
    )

    growth_plan = (
        "Keyingi harakat: Insta Tahlilchi (@_tima_shop / @stylesh_shop) jonli narxlari va trend zvuklari -> Pinduoduo sifatli/arzon yangi look (35% marja) -> 5–12 kun Avia + 12 000 so'm/100gr kargo bilan Telegram & Instagram Reels."
    )

    return {
        "diagnosis": market_verdict,
        "market_verdict": market_verdict,
        "customs_yatt_plan": customs_plan,
        "growth_plan": growth_plan,
        "recommended_profit_percent": 35 if price_too_high else round(p["profit_percent"]),
        "directives": directives,
    }


def _extract_json_block(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    cleaned = text.strip()
    if "```json" in cleaned:
        cleaned = cleaned.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in cleaned:
        cleaned = cleaned.split("```", 1)[1].split("```", 1)[0].strip()
    try:
        obj = json.loads(cleaned)
        return obj if isinstance(obj, dict) else None
    except Exception:
        m = re.search(r"\{[\s\S]*\}", cleaned)
        if m:
            try:
                obj = json.loads(m.group(0))
                return obj if isinstance(obj, dict) else None
            except Exception:
                return None
    return None


async def run_ceo_strategy_cycle(
    ecc_registry: ECCRegistry,
    db: Database,
    settings: Settings,
    focus_topic: str = "",
    apply_directives: bool = True,
) -> dict[str, Any]:
    """Boshqaruvchi AI butun biznesni tahlil qilib, strategik qaror va bo'limlarga buyruq beradi."""
    telemetry = await collect_business_telemetry(db, settings)
    fallback = build_default_directives(telemetry)

    await db.set_agent_status("director", "working", "Bozor, narx, $200 bojxona va bo'limlar auditi...")

    prompt = (
        "Sen XAN SHOP erkaklar kiyimi e-commerce kompaniyasining avtonom Bosh Direktorisan.\n"
        "Shunchaki xodimlar holatini so'rama — kommersiya, narx, raqobat va rivojlanish qarorlarini chiqar va bo'limlarga BUYRUQ ber!\n\n"
        f"JONLI TELEMETRIYA:\n{json.dumps(telemetry, ensure_ascii=False)}\n\n"
        f"QO'SHIMCHA FOKUS: {focus_topic or 'Narxlarni bozorga moslash (~380k look), Pinduoduo ulash va $200+ YaTT bojxona rejasi'}\n\n"
        "FAQAT JSON qaytar (o'zbek tilida, aniq va qisqa):\n"
        "{\n"
        '  "diagnosis": "3 jumlali chuqur biznes va raqobat tahlili",\n'
        '  "customs_yatt_plan": "$200 limit oshganda YaTT + 1688 ulgurji + bojxona strategiyasi (2-3 jumla)",\n'
        '  "growth_plan": "Kompaniyani keyingi bosqichga olib chiqish bo\'yicha aniq 3 qadam",\n'
        '  "recommended_profit_percent": 65,\n'
        '  "directives": [\n'
        '    {"target_agent": "insta_analyst|skaut|smm_manager|video_employee|sales_stylist|accountant|cargo_logistics", "priority": "yuqori|o\'rta", "command": "Aniq ijro buyrug\'i", "reason": "Nega kerakligi"}\n'
        "  ]\n"
        "}"
    )

    try:
        res = await run_ecc_specialist(
            ecc_registry,
            settings,
            "chief-of-staff",
            prompt,
            skill_ids=["team-agent-orchestration", "market-research"],
            db=None,
        )
    except Exception as e:
        log.warning("CEO LLM chaqiruvida zaxiraga o'tildi: %s", e)
        res = {"ok": False, "provider": "Strategik Tahlil (Telemetry)"}

    parsed = _extract_json_block(res.get("answer") or "") if res.get("ok") else None
    diagnosis = (parsed or {}).get("diagnosis") or fallback["diagnosis"]
    customs_plan = (parsed or {}).get("customs_yatt_plan") or fallback["customs_yatt_plan"]
    growth_plan = (parsed or {}).get("growth_plan") or fallback["growth_plan"]
    rec_profit = int((parsed or {}).get("recommended_profit_percent") or fallback["recommended_profit_percent"])
    rec_profit = max(25, min(150, rec_profit))

    raw_dirs = (parsed or {}).get("directives")
    valid_targets = {"insta_analyst", "skaut", "smm_manager", "video_employee", "sales_stylist", "accountant", "cargo_logistics"}
    directives: list[dict[str, str]] = []
    if isinstance(raw_dirs, list):
        for d in raw_dirs:
            if not isinstance(d, dict):
                continue
            tgt = str(d.get("target_agent") or "").strip()
            cmd = str(d.get("command") or "").strip()
            if tgt in valid_targets and cmd:
                directives.append({
                    "target_agent": tgt,
                    "priority": str(d.get("priority") or "yuqori"),
                    "command": cmd[:180],
                    "reason": str(d.get("reason") or "")[:180],
                })
    if len(directives) < 3:
        directives = fallback["directives"]

    if apply_directives:
        for d in directives:
            tgt = d["target_agent"]
            cmd = d["command"]
            await db.set_agent_status(tgt, "working", f"📌 {cmd}")
            await db.record_agent_learning(tgt, f"CEO V3 Direktivasi: {cmd}", xp_gain=15)
            await db.log_agent_action(
                "director",
                f"📌 Buyruq [{tgt}]: {cmd}",
                d.get("reason") or f"Prioritet: {d['priority']}",
                target_id=tgt,
            )
        await db.record_agent_learning("director", f"Strategik audit: {diagnosis[:140]}", xp_gain=25)
        await db.log_agent_action(
            "director",
            "🧠 Boshqaruvchi AI (v3.0) Strategik Tahlil & Buyruqlar Paketi Chiqarildi",
            diagnosis[:240],
        )

    await db.set_agent_status("director", "idle", diagnosis[:140], increment_done=True)

    payload = {
        "ok": True,
        "timestamp": int(time.time()),
        "provider": res.get("provider", "Strategik Tahlil"),
        "diagnosis": diagnosis,
        "market_verdict": fallback["market_verdict"],
        "customs_yatt_plan": customs_plan,
        "growth_plan": growth_plan,
        "recommended_profit_percent": rec_profit,
        "directives": directives,
        "telemetry": telemetry,
    }
    await db.set_setting("latest_ceo_brief", json.dumps(payload, ensure_ascii=False))
    return payload


async def apply_ceo_pricing_preset(db: Database, settings: Settings, mode: str = "competitive") -> dict[str, Any]:
    """Boshqaruvchi AI tasdiqlagan narx rejimini DB sozlamalariga qo'llaydi."""
    preset = PRICING_PRESETS.get(mode) or PRICING_PRESETS["competitive"]
    for key in (
        "profit_percent",
        "vykup_percent",
        "china_shipping_cny_per_item",
        "conversion_fee_percent",
        "ensure_50_covers_cost",
        "cargo_client_uzs_per_kg",
    ):
        await db.set_setting(key, preset[key])

    await db.log_agent_action(
        "director",
        f"💰 Narx Siyosati Yangilandi: {preset['label']}",
        f"Foyda: {preset['profit_percent']}% | Vykup: {preset['vykup_percent']}% | 50% qulf: {preset['ensure_50_covers_cost']}",
        target_id="accountant",
    )
    await db.set_agent_status(
        "accountant",
        "idle",
        f"Yangi narx rejimi qabul qilindi ({preset['profit_percent']}% foyda)",
        increment_done=True,
    )
    new_params = await get_params(db, settings)
    return {
        "ok": True,
        "mode": mode,
        "label": preset["label"],
        "params": {
            "profit_percent": new_params.profit_percent,
            "vykup_percent": new_params.vykup_percent,
            "china_shipping_cny_per_item": new_params.china_shipping_cny_per_item,
            "conversion_fee_percent": new_params.conversion_fee_percent,
            "ensure_50_covers_cost": new_params.ensure_50_covers_cost,
            "cargo_client_uzs_per_kg": new_params.cargo_client_uzs_per_kg,
        },
    }
