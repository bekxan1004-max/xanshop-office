"""Bo'y, vazn, oyoq uzunligi va Pinduoduo do'kon razmer jadvali bo'yicha aqlli o'lcham tavsiyasi."""
from __future__ import annotations

import re
from typing import Any

ORDER = ["XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL", "6XL"]
# (vazn chegarasi kg, o'lcham)
WEIGHT_TABLE = [(50, "S"), (57, "M"), (65, "L"), (72, "XL"), (80, "2XL"),
                (87, "3XL"), (95, "4XL"), (105, "5XL"), (999, "6XL")]
ALIASES = {"XXL": "2XL", "XXXL": "3XL", "XXXXL": "4XL", "XXXXXL": "5XL"}

# Erkaklar oyoq kiyimi (oyoq uzunligi sm -> EU/CN razmer)
SHOE_CM_TABLE = [
    (24.0, "38"), (24.5, "39"), (25.0, "40"), (25.5, "41"),
    (26.0, "42"), (26.5, "43"), (27.0, "44"), (27.5, "45"), (28.5, "46"),
]


def normalize(size: str) -> str:
    s = size.strip().upper().replace(" ", "")
    return ALIASES.get(s, s)


def _parse_range(raw: str) -> tuple[float, float] | None:
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", str(raw or ""))]
    if not nums:
        return None
    if len(nums) == 1:
        return (nums[0] - 4.0, nums[0] + 4.0)
    return (min(nums[0], nums[1]), max(nums[0], nums[1]))


def is_shoe_item(item: dict[str, Any]) -> bool:
    cat = str(item.get("category") or "").lower()
    if cat == "shoes":
        return True
    txt = f"{item.get('name', '')} {item.get('title_cn', '')} {item.get('cn_keyword', '')}".lower()
    return any(w in txt for w in ("etik", "lofer", "krossovka", "poyabzal", "tufli", "chelsea", "sneaker", "靴", "鞋", "皮鞋", "乐福"))


def needs_size_up_hint(item: dict[str, Any]) -> tuple[bool, str]:
    """Qishki qalin kiyim yoki do'kon tor bichim (偏小/修身) bo'lsa 1 razmer kattaroq tavsiya sababini qaytaradi."""
    fit_note = str(item.get("fit_note") or "")
    txt = f"{item.get('name', '')} {item.get('title_cn', '')} {item.get('cn_keyword', '')} {fit_note}".lower()
    if is_shoe_item(item) and any(w in txt for w in ("qishki", "mo'ynali", "加绒", "保暖", "冬季", "chelsea")):
        return True, "qishki ichi issiq/mo'ynali oyoq kiyim — qalin paypoq bilan qisib qo'ymasligi uchun 1 razmer kattaroq olish qulay"
    if any(w in txt for w in ("偏小", "修身", "tor bichim", "ixcham")):
        return True, "do'kon izohida bichimi biroz tor/ixcham deyilgan — 1 razmer kattaroq olsangiz bemalol turadi"
    if any(w in txt for w in ("palto", "kurtka", "puxovik", "qishki", "jun", "bomber", "羽绒", "加厚", "加绒", "大衣", "棉衣")):
        if not any(w in txt for w in ("oversize", "宽松", "keng bichim")):
            return True, "qishki qalin ustki kiyim — ichidan sviter yoki vodolazka kiyilganda yelkada siqmasligi uchun 1 razmer kattaroq olish yaxshiroq"
    return False, ""


def recommend_shoe_size(foot_cm: float, available: list[str] | None = None, winter_lined: bool = False) -> str:
    adj_cm = foot_cm + (0.5 if winter_lined else 0.0)
    picked = next((sz for lim, sz in SHOE_CM_TABLE if adj_cm <= lim), "45")
    if available:
        avail_norm = [str(a).strip() for a in available if str(a).strip()]
        if picked in avail_norm:
            return picked
        num_avail = [(int(re.search(r"\d+", a).group(0)), a) for a in avail_norm if re.search(r"\d+", a)]
        if num_avail:
            target_n = int(picked)
            ge = [a for n, a in sorted(num_avail) if n >= target_n]
            return ge[0] if ge else sorted(num_avail)[-1][1]
    return picked


def recommend(height_cm: float, weight_kg: float, available: list[str]) -> str | None:
    idx = next(ORDER.index(s) for limit, s in WEIGHT_TABLE if weight_kg <= limit)
    if height_cm >= 185:
        idx += 1
    if height_cm >= 195:
        idx += 1
    idx = min(idx, len(ORDER) - 1)
    wanted = ORDER[idx]
    if not available:
        return wanted

    letter = {normalize(a): a for a in available if normalize(a) in ORDER}
    if not letter:
        return None  # raqamli o'lchamlar (44, 46, 30...) — operator/jadval kerak
    if wanted in letter:
        return letter[wanted]
    bigger = [s for s in ORDER[idx:] if s in letter]
    if bigger:
        return letter[bigger[0]]
    return letter[max(letter, key=ORDER.index)]


def recommend_for_item(
    height_cm: float,
    weight_kg: float,
    item: dict[str, Any],
    foot_cm: float | None = None,
) -> dict[str, Any]:
    """Aynan bitta Pinduoduo tovarining o'z razmer jadvali (size_chart) va qishki bichim eslatmasiga qarab razmer topadi."""
    name = str(item.get("name") or "Buyum")
    avail = [str(s).strip() for s in (item.get("store_sizes") or []) if str(s).strip()]
    size_up, size_up_reason = needs_size_up_hint(item)

    if is_shoe_item(item):
        if foot_cm:
            sz = recommend_shoe_size(foot_cm, avail or ["39", "40", "41", "42", "43", "44"], winter_lined=size_up)
            note = f"Oyoq uzunligi {foot_cm:g} sm bo'yicha {sz} razmer mos"
            if size_up:
                note += f" ({size_up_reason})"
            return {"name": name, "is_shoe": True, "size": sz, "source": "shoe_cm_table", "reason_uz": note}
        return {
            "name": name,
            "is_shoe": True,
            "size": None,
            "source": "need_shoe_size",
            "reason_uz": (
                f"Oyoq kiyim razmeringizni alohida tanlang ({', '.join(avail or ['39','40','41','42','43','44'])})"
                + (f" — {size_up_reason}" if size_up else "")
            ),
        }

    # 1) Avval aynan Pinduoduo do'konidagi haqiqiy razmer jadvalidan (size_chart) qidiramiz!
    chart = item.get("size_chart") or []
    if isinstance(chart, list) and chart:
        best_idx = -1
        best_dist = 1e9
        for i, row in enumerate(chart):
            if not isinstance(row, dict) or not row.get("size"):
                continue
            hr = _parse_range(str(row.get("height_cm") or ""))
            wr = _parse_range(str(row.get("weight_kg") or ""))
            dist = 0.0
            if hr:
                mid_h = (hr[0] + hr[1]) / 2.0
                dist += abs(height_cm - mid_h) * 0.6 + (0.0 if hr[0] <= height_cm <= hr[1] else 12.0)
            if wr:
                mid_w = (wr[0] + wr[1]) / 2.0
                dist += abs(weight_kg - mid_w) * 1.4 + (0.0 if wr[0] <= weight_kg <= wr[1] else 15.0)
            if hr or wr:
                if dist < best_dist:
                    best_dist = dist
                    best_idx = i
        if best_idx >= 0:
            picked_idx = min(len(chart) - 1, best_idx + (1 if size_up else 0))
            picked_row = chart[picked_idx]
            sz = str(picked_row.get("size") or "").strip()
            detail_parts = []
            if picked_row.get("height_cm"):
                detail_parts.append(f"bo'y {picked_row['height_cm']} sm")
            if picked_row.get("weight_kg"):
                detail_parts.append(f"vazn {picked_row['weight_kg']} kg")
            if picked_row.get("chest_cm"):
                detail_parts.append(f"ko'krak {picked_row['chest_cm']} sm")
            spec_str = f" ({', '.join(detail_parts)})" if detail_parts else ""
            reason = f"Do'konning o'z jadvali bo'yicha {sz}{spec_str} mos tushadi"
            if size_up and picked_idx > best_idx:
                reason += f" — {size_up_reason}"
            return {"name": name, "is_shoe": False, "size": sz, "source": "store_size_chart", "reason_uz": reason}

    # 2) Agar do'kon jadvali hali o'qilmagan bo'lsa, Osiyo jadvali + qishki/tor bichim tuzatishi
    eff_weight = weight_kg + (5.5 if size_up else 0.0)
    sz = recommend(height_cm, eff_weight, avail)
    reason = f"Bo'y {height_cm:g} sm / vazn {weight_kg:g} kg bo'yicha {sz or 'XL'} razmer mos"
    if size_up:
        reason += f" ({size_up_reason})"
    return {"name": name, "is_shoe": False, "size": sz, "source": "winter_adjusted" if size_up else "asia_standard", "reason_uz": reason}


def recommend_for_look(
    height_cm: float,
    weight_kg: float,
    look: dict[str, Any],
    foot_cm: float | None = None,
) -> dict[str, Any]:
    """Butun look tarkibidagi har bir kiyim va oyoq kiyim uchun alohida razmer va insoniy izoh beradi."""
    import json

    try:
        items = json.loads(look.get("items_json") or "[]")
    except Exception:
        items = []
    avail_look = [x.strip() for x in str(look.get("sizes") or "").split(",") if x.strip()]
    per_item = [recommend_for_item(height_cm, weight_kg, it, foot_cm=foot_cm) for it in items]
    clothing_recs = [r for r in per_item if not r["is_shoe"] and r.get("size")]
    shoe_recs = [r for r in per_item if r["is_shoe"]]

    primary_size = clothing_recs[0]["size"] if clothing_recs else recommend(height_cm, weight_kg, avail_look)
    # Agar kiyimlar ichida qishki/tor bichim bo'lib kattaroq razmer chiqqan bo'lsa, ustki kiyimnikini asos qilamiz
    if len(clothing_recs) > 1:
        letter_recs = [r["size"] for r in clothing_recs if normalize(r["size"]) in ORDER]
        if letter_recs:
            primary_size = max(letter_recs, key=lambda s: ORDER.index(normalize(s)))

    advice_lines = [f"• {r['name']}: <b>{r['size'] or 'alohida tanlanadi'}</b> — {r['reason_uz']}" for r in per_item]
    return {
        "primary_clothing_size": primary_size,
        "has_shoes": bool(shoe_recs),
        "shoe_sizes": (items[[i for i, x in enumerate(items) if is_shoe_item(x)][0]].get("store_sizes") if shoe_recs else []) or ["39", "40", "41", "42", "43", "44"],
        "per_item": per_item,
        "advice_html": "\n".join(advice_lines),
    }
