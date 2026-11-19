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


def item_size_group(item: dict[str, Any]) -> str:
    """Buyumni 3 ta alohida razmer turkumidan biriga ajratadi: 'shoes' | 'bottom' | 'top'."""
    if is_shoe_item(item):
        return "shoes"
    cat = str(item.get("category") or "").lower()
    if cat == "bottom":
        return "bottom"
    txt = f"{item.get('name', '')} {item.get('title_cn', '')} {item.get('cn_keyword', '')}".lower()
    if any(w in txt for w in ("shim", "jinsi", "bryuk", "kargo", "joger", "裤", "西裤", "工装裤", "牛仔裤", "休闲裤")):
        return "bottom"
    return "top"


def is_outerwear_item(item: dict[str, Any]) -> bool:
    cat = str(item.get("category") or "").lower()
    if cat == "outerwear":
        return True
    txt = f"{item.get('name', '')} {item.get('title_cn', '')} {item.get('cn_keyword', '')}".lower()
    return any(w in txt for w in ("palto", "kurtka", "puxovik", "bomber", "trench", "vetrovka", "blazer", "大衣", "羽绒", "夹克", "外套", "棉衣", "风衣"))


def needs_size_up_hint(item: dict[str, Any]) -> tuple[bool, bool, str]:
    """(force_size_up, is_optional_hint, reason_uz) qaytaradi.

    Qoida:
    - Oyoq kiyimga bo'y/vazn yoki avtomatik +1 razmer qo'shilmaydi (faqat do'kon o'zi aniq '偏小' desa eslatiladi).
    - Asosan kiyimlarda (ayniqsa qishki tashqi kiyimda) faqat DO'KON IZOHIDA yozilgan bo'lsa +1 razmer suriladi;
      qishki qalin tashqi kiyimda do'kon izohi bo'lmasa ham yumshoq ixtiyoriy maslahat beriladi.
    """
    fit_note = str(item.get("fit_note") or "")
    title_cn = str(item.get("title_cn") or item.get("cn_keyword") or "")
    low_note = f"{fit_note} {title_cn}".lower()

    # 1) Do'kon izohida aniq "tor bichim / 1 razmer katta oling" (偏小 / 拍大一码 / 修身) yozilgan bo'lsa:
    if any(w in low_note for w in ("偏小", "拍大一码", "大一码", "tor bichim", "ixcham", "修身")):
        if is_shoe_item(item):
            return False, True, "do'kon izohida qolipi biroz torroq deyilgan — qulay turishi uchun 1 razmer kattasini olishingiz mumkin"
        return True, False, "do'kon izohida bichimi sal torroq deyilgan, shuning uchun 1 razmer kattaroq olsangiz bemalol turadi"

    # 2) Oyoq kiyim uchun o'z-o'zidan +1 qo'shmaymiz!
    if is_shoe_item(item):
        return False, False, ""

    # 3) Qishki qalin tashqi kiyim (palto, kurtka, puxovik): majburiy emas, lekin insoniy ixtiyoriy eslatma
    if is_outerwear_item(item) and any(
        w in f"{item.get('name', '')} {low_note}".lower()
        for w in ("qishki", "palto", "puxovik", "jun", "羽绒", "加厚", "加绒", "大衣", "棉衣", "冬季")
    ):
        if not any(w in low_note for w in ("oversize", "宽松", "keng bichim")):
            return False, True, "qishki tashqi kiyim bo'lgani uchun tagidan qalin sviter kiysangiz, 1 razmer kattaroq olish ham qulayroq bo'lishi mumkin"
    return False, False, ""


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
    """Aynan bitta Pinduoduo tovarining o'z razmer jadvali (size_chart) va do'kon bichim izohiga qarab razmer topadi.

    MUHIM: Oyoq kiyim HECH QACHON bo'y-vaznga qarab hisoblanmaydi! Faqat oyoq uzunligi (sm) yoki mijozning o'z oyoq razmeri so'raladi.
    """
    name = str(item.get("name") or "Buyum")
    group = item_size_group(item)
    avail = [str(s).strip() for s in (item.get("store_sizes") or []) if str(s).strip()]
    force_up, optional_hint, hint_reason = needs_size_up_hint(item)

    if group == "shoes":
        if foot_cm:
            sz = recommend_shoe_size(foot_cm, avail or ["39", "40", "41", "42", "43", "44"], winter_lined=False)
            note = f"Oyoq uzunligi {foot_cm:g} sm bo'yicha {sz} razmer mos"
            if hint_reason:
                note += f" ({hint_reason})"
            return {"name": name, "group": "shoes", "is_shoe": True, "size": sz, "source": "shoe_cm_table", "reason_uz": note}
        return {
            "name": name,
            "group": "shoes",
            "is_shoe": True,
            "size": None,
            "source": "need_shoe_size",
            "reason_uz": (
                f"Oyoq kiyim bo'y-vaznga qaralmaydi — o'zingiz kiyadigan razmerni tanlang ({', '.join(avail or ['39','40','41','42','43','44'])})"
                + (f" ({hint_reason})" if hint_reason else "")
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
            picked_idx = min(len(chart) - 1, best_idx + (1 if force_up else 0))
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
            if force_up and picked_idx > best_idx and hint_reason:
                reason += f" — {hint_reason}"
            elif optional_hint and hint_reason:
                reason += f" (eslatma: {hint_reason})"
            return {"name": name, "group": group, "is_shoe": False, "size": sz, "source": "store_size_chart", "reason_uz": reason}

    # 2) Agar do'kon jadvali hali o'qilmagan bo'lsa, Osiyo jadvali (faqat do'kon izohi talab qilsagina +1)
    eff_weight = weight_kg + (5.5 if force_up else 0.0)
    sz = recommend(height_cm, eff_weight, avail)
    reason = f"Bo'y {height_cm:g} sm / vazn {weight_kg:g} kg bo'yicha {sz or 'XL'} razmer mos"
    if hint_reason:
        reason += f" ({hint_reason})"
    return {"name": name, "group": group, "is_shoe": False, "size": sz, "source": "store_fit_adjusted" if force_up else "asia_standard", "reason_uz": reason}


def recommend_for_look(
    height_cm: float,
    weight_kg: float,
    look: dict[str, Any],
    foot_cm: float | None = None,
) -> dict[str, Any]:
    """Butun look tarkibidagi ust kiyim, shim va oyoq kiyim uchun ALOHIDA razmer tavsiyasi beradi."""
    import json

    try:
        items = json.loads(look.get("items_json") or "[]")
    except Exception:
        items = []
    avail_look = [x.strip() for x in str(look.get("sizes") or "").split(",") if x.strip()]
    per_item = [recommend_for_item(height_cm, weight_kg, it, foot_cm=foot_cm) for it in items]
    top_recs = [r for r in per_item if r.get("group") == "top" and r.get("size")]
    bottom_recs = [r for r in per_item if r.get("group") == "bottom" and r.get("size")]
    shoe_recs = [r for r in per_item if r.get("group") == "shoes"]

    def _pick_group_size(recs: list[dict[str, Any]]) -> str | None:
        if not recs:
            return None
        letters = [r["size"] for r in recs if normalize(r["size"]) in ORDER]
        if letters:
            return max(letters, key=lambda s: ORDER.index(normalize(s)))
        return recs[0]["size"]

    top_size = _pick_group_size(top_recs) or recommend(height_cm, weight_kg, avail_look)
    bottom_size = _pick_group_size(bottom_recs)
    primary_size = top_size or bottom_size or recommend(height_cm, weight_kg, avail_look)

    advice_lines = [f"• {r['name']}: <b>{r['size'] or 'alohida tanlanadi'}</b> — {r['reason_uz']}" for r in per_item]
    return {
        "primary_clothing_size": primary_size,
        "top_size": top_size,
        "bottom_size": bottom_size,
        "has_bottom": bool(bottom_recs),
        "has_shoes": bool(shoe_recs),
        "shoe_sizes": (items[[i for i, x in enumerate(items) if is_shoe_item(x)][0]].get("store_sizes") if shoe_recs else []) or ["39", "40", "41", "42", "43", "44"],
        "per_item": per_item,
        "advice_html": "\n".join(advice_lines),
    }
