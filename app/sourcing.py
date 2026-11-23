"""XAN SHOP - Skaut, Bozor Tahlilchisi & Dizayner-Stilist Agent (TrendSourcingAgent).

Vazifalari:
1) Instagram Reels va O'zbekiston look-bozori (Lookzona, Stylesh) trend tahlilini qabul qiladi.
2) Faqat 4 talik emas — trend va mavsumga qarab 2 qismli (Set), 3 qismli (Kapsula),
   4 qismli (To'liq Look) yoki 5 qismli (VIP + Aksessuar) kombinatsiyalarni yig'adi.
3) Professional dizayner sifatida ranglar palitrasini (Color Harmony HEX) tanlaydi.
4) Rasmiy Pinduoduo (`app/pinduoduo.py`) bazasidan tovarlarni topib, 50%/100% + UZS->CNY
   tranzaksiya komissiyasi bilan narxlaydi.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Any

from .ai import SalesAI, extract_json_dict
from .config import Settings
from .pinduoduo import PinduoduoConnector
from .pricing import Item, PriceBreakdown, PriceParams, Rates, calculate
from .trends import WeatherForecast, analyze_instagram_creative_strategy, fetch_tashkent_weather

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class InstagramTrendBrief:
    """Video/Instagram Tahlilchi Agentdan Skaut Agentga keladigan bozor razvedkasi."""
    trend_name: str
    recommended_piece_count: int          # 2, 3, 4 yoki 5 qismli look
    color_palette_name: str
    color_hex_list: list[str]
    viral_hook_uz: str
    audio_vibe: str                       # "phonk_bass", "luxury_chill", "uk_drill_beat"
    conversion_reason: str


# Instagram Reels (Lookzona / Stylesh / Streetwear UZ) jonli auditoriya-persona trend shablonlari
MARKET_TREND_BRIEFS: list[InstagramTrendBrief] = [
    InstagramTrendBrief(
        trend_name="Diplomatiya va Yuridika Talabalari Old Money Kapsulasi (3-in-1)",
        recommended_piece_count=3,
        color_palette_name="Old Money Espresso & Latte",
        color_hex_list=["#2B211B", "#7A6352", "#C8B8A6", "#F5F0EB"],
        viral_hook_uz="DIPLOMATIYA VA YURIDIKADA O'QIYDIGANLAR UCHUN",
        audio_vibe="diplomat_old_money",
        conversion_reason="Aniq kasb/o'qish auditoriyasiga qaratilgan Old Money obraz o'sha soha yigitlarida 'aynan men uchun' hissini uyg'otadi.",
    ),
    InstagramTrendBrief(
        trend_name="Oversize va Erkin Streetwear Yoqtiradiganlar Seti (4-in-1)",
        recommended_piece_count=4,
        color_palette_name="Monochrome Graphite & Ice",
        color_hex_list=["#18191C", "#34373E", "#8E929B", "#ECEEEF"],
        viral_hook_uz="OVERSIZE KIYISHNI YOQTIRADIGAN YIGITLAR UCHUN",
        audio_vibe="phonk_bass",
        conversion_reason="Oversize kiyadigan yoshlar tayyor moslangan keng bichimli 4 talik setni darhol saqlab oladi va buyurtma beradi.",
    ),
    InstagramTrendBrief(
        trend_name="175–188 sm Bo'yli Klassik Cleanfit Obraz (4-in-1)",
        recommended_piece_count=4,
        color_palette_name="Cleanfit Obsidian & Sand",
        color_hex_list=["#15181E", "#3A3D45", "#C7B8A5", "#F4F3EF"],
        viral_hook_uz="175–188 SM BO'YLI YIGITLAR UCHUN TAYYOR OBRAZ",
        audio_vibe="luxury_chill",
        conversion_reason="Bo'y proportsiyasi aniq aytilgan postlarda izoh va Direct so'rovlari 2 barobar yuqori bo'ladi.",
    ),
    InstagramTrendBrief(
        trend_name="IT, Biznes va Zamonaviy Ofis Smart-Casual Kapsulasi (3-in-1)",
        recommended_piece_count=3,
        color_palette_name="Smart Slate & Oatmeal",
        color_hex_list=["#1C1E24", "#4A4E58", "#D6CBBF"],
        viral_hook_uz="IT, BIZNES VA OFISDA ISHLAYDIGANLAR UCHUN",
        audio_vibe="lofi_editorial",
        conversion_reason="Ofis va uchrashuvlarga kiyishga tayyor 3 talik kapsula to'lov qobiliyati yuqori auditoriyani tortadi.",
    ),
    InstagramTrendBrief(
        trend_name="Universitet va Har Kuni Kiyishga Street Dvoika (2-in-1)",
        recommended_piece_count=2,
        color_palette_name="Obsidian & Steel Grey",
        color_hex_list=["#141518", "#2B2E34", "#D2D4D9"],
        viral_hook_uz="UNIVERSITET VA HAR KUNI KIYISHGA TAYYOR SET",
        audio_vibe="uk_drill_beat",
        conversion_reason="2 qismli dvoika (Xudi + Kargo/Shim) talabalar orasida eng tez sotiladigan hamyonbop format.",
    ),
]


# Turli auditoriya va formatdagi (2, 3, 4, 5 qismli) Pinduoduo Look bazasi
DYNAMIC_LOOK_TEMPLATES: list[dict[str, Any]] = [
    {
        "title": "Diplomatiya va Yuridika Qishki Old Money Kapsulasi",
        "description": "To'q jigarrang ikki qatorli jun palto + to'q qahva kashmir vodolazka + qahva-taupe old money jun shim.",
        "piece_count": 3,
        "palette_name": "Old Money Espresso & Palto",
        "palette_hex": ["#2B211B", "#6E5A4B", "#C8B8A6", "#F4EFE8"],
        "audio_vibe": "diplomat_old_money",
        "viral_hook": "DIPLOMATIYA VA YURIDIKADA O'QIYDIGANLAR UCHUN (QISH-KUZ)",
        "colors": "To'q jigarrang, Qahva-taupe",
        "sizes": "M, L, XL, 2XL",
        "items": [
            {"category": "outerwear", "name": "To'q Jigarrang Ikki Qatorli Jun Palto", "price_cny": 65.0, "weight_kg": 1.15, "cn_keyword": "老钱风双排扣羊毛呢大衣男秋冬加厚英伦外套"},
            {"category": "top", "name": "To'q Qahva Kashmir Vodolazka", "price_cny": 36.0, "weight_kg": 0.48, "cn_keyword": "男秋冬加厚羊绒高领打底毛衣老钱风保暖针织衫"},
            {"category": "bottom", "name": "Qahva-Taupe Old Money Jun Shim", "price_cny": 36.0, "weight_kg": 0.52, "cn_keyword": "老钱风摩卡棕垂感褶皱羊毛西装裤男秋冬加厚"},
        ],
    },
    {
        "title": "Oversize Streetwear To'liq Seti (4-in-1)",
        "description": "Qora bomber kurtka + grafit oversize xudi + zaytun cho'ntakli erkin shim + oq-kulrang retro krossovka.",
        "piece_count": 4,
        "palette_name": "Monochrome Graphite & Ice",
        "palette_hex": ["#18191C", "#34373E", "#8E929B", "#ECEEEF"],
        "audio_vibe": "phonk_bass",
        "viral_hook": "OVERSIZE KIYISHNI YOQTIRADIGAN YIGITLAR UCHUN",
        "colors": "Qora, To'q kulrang (grafit), To'q zaytun, Oq-kulrang",
        "sizes": "M, L, XL, 2XL",
        "items": [
            {"category": "outerwear", "name": "Qora Jun Bomber Kurtka", "price_cny": 56.0, "weight_kg": 0.75, "cn_keyword": "美式复古重磅飞行员夹克男春秋宽松外套"},
            {"category": "top", "name": "Grafit Oversize Xudi", "price_cny": 34.0, "weight_kg": 0.55, "cn_keyword": "420g重磅纯棉连帽卫衣男宽松美式帽衫"},
            {"category": "bottom", "name": "Zaytun Cho'ntakli Erkin Shim", "price_cny": 35.0, "weight_kg": 0.50, "cn_keyword": "美式工装裤男直筒宽松多口袋伞兵休闲裤"},
            {"category": "shoes", "name": "Oq-Kulrang Krossovka", "price_cny": 39.0, "weight_kg": 0.80, "cn_keyword": "复古百搭板鞋男休闲运动鞋防滑厚底潮鞋"},
        ],
    },
    {
        "title": "IT va Biznes Minimalist Blazer Kapsulasi (2-in-1)",
        "description": "To'q ko'k klassik jun blazer + och bej zamokli sviter.",
        "piece_count": 2,
        "palette_name": "Midnight Navy & Cream",
        "palette_hex": ["#1B263B", "#C8B8A6", "#F4EFE8"],
        "audio_vibe": "luxury_chill",
        "viral_hook": "IT, BIZNES VA OFISDA ISHLAYDIGANLAR UCHUN",
        "colors": "To'q ko'k (navy), Och bej",
        "sizes": "M, L, XL, 2XL",
        "items": [
            {"category": "outerwear", "name": "To'q Ko'k Klassik Jun Blazer", "price_cny": 62.0, "weight_kg": 0.78, "cn_keyword": "老钱风藏青色羊毛修身西装外套男秋冬商务夹克"},
            {"category": "top", "name": "Och Bej Zamokli Sviter", "price_cny": 36.0, "weight_kg": 0.50, "cn_keyword": "老钱风半拉链针织毛衣男秋冬加厚立领"},
        ],
    },
    {
        "title": "Qishki Shahar VIP Street-Klassik Kapsulasi (5-in-1)",
        "description": "Qishki qalin jun palto + yoqali svitshot + issiq keng erkin shim + qora-oq retro krossovka + minimalist kepka.",
        "piece_count": 5,
        "palette_name": "Diplomat Obsidian & Cream",
        "palette_hex": ["#18191C", "#2B2D32", "#E8E4DC", "#4A4E58"],
        "audio_vibe": "lofi_editorial",
        "viral_hook": "QISHKI ZAMONAVIY SHAHAR OBRAZI • 5 QISMLI VIP SET",
        "colors": "Qora, Oq, To'q kulrang",
        "sizes": "M, L, XL, 2XL",
        "items": [
            {"category": "outerwear", "name": "Qora Tik Yoqali Jun Palto", "price_cny": 62.0, "weight_kg": 1.05, "cn_keyword": "老钱风双排扣羊毛呢大衣男秋冬加厚英伦外套"},
            {"category": "top", "name": "Oq Yoqali Svitshot", "price_cny": 32.0, "weight_kg": 0.48, "cn_keyword": "半拉链卫衣男潮"},
            {"category": "bottom", "name": "To'q Kulrang Qishki Erkin Shim", "price_cny": 34.0, "weight_kg": 0.52, "cn_keyword": "工装裤男士直筒宽松"},
            {"category": "shoes", "name": "Qora-Oq Retro Krossovka", "price_cny": 39.0, "weight_kg": 0.85, "cn_keyword": "男复古板鞋运动鞋"},
            {"category": "accessory", "name": "Qora Minimalist Kepka", "price_cny": 15.0, "weight_kg": 0.15, "cn_keyword": "美式复古纯色软顶棒球帽男百搭显脸小鸭舌帽"},
        ],
    },
    {
        "title": "Universitet va Kundalik Oversize Set (3-in-1)",
        "description": "Grafit oversize xudi + zaytun cho'ntakli erkin shim + oq-kulrang retro krossovka.",
        "piece_count": 3,
        "palette_name": "Obsidian & Steel Grey",
        "palette_hex": ["#141518", "#383B42", "#D2D4D9"],
        "audio_vibe": "uk_drill_beat",
        "viral_hook": "UNIVERSITET VA HAR KUNI KIYISHGA TAYYOR SET",
        "colors": "To'q kulrang (grafit), To'q zaytun, Oq-kulrang",
        "sizes": "S, M, L, XL, 2XL",
        "items": [
            {"category": "top", "name": "Grafit Oversize Xudi", "price_cny": 36.0, "weight_kg": 0.55, "cn_keyword": "420g重磅纯棉连帽卫衣男宽松美式帽衫"},
            {"category": "bottom", "name": "Zaytun Cho'ntakli Erkin Shim", "price_cny": 35.0, "weight_kg": 0.50, "cn_keyword": "美式工装裤男直筒宽松多口袋伞兵休闲裤"},
            {"category": "shoes", "name": "Oq-Kulrang Krossovka", "price_cny": 42.0, "weight_kg": 0.80, "cn_keyword": "复古百搭板鞋男休闲运动鞋防滑厚底潮鞋"},
        ],
    },
    {
        "title": "Cleanfit Shokolad Zamsh Kurtka va Denim Kapsulasi",
        "description": "Shokolad zamsh kurtka + oq vafli longsliv + to'q ko'k to'g'ri vintage denim shim + jigarrang lofer.",
        "piece_count": 4,
        "palette_name": "Chocolate Suede & Indigo",
        "palette_hex": ["#3D2314", "#EBE6DD", "#1C2D42", "#5C3826"],
        "audio_vibe": "luxury_chill",
        "viral_hook": "BAHOR VA SALQIN KUNLAR UCHUN CLEANFIT OBRAZ",
        "colors": "To'q shokolad, Oq, To'q ko'k denim, Jigarrang",
        "sizes": "M, L, XL, 2XL",
        "items": [
            {"category": "outerwear", "name": "Shokolad Zamsh Kurtka", "price_cny": 58.0, "weight_kg": 0.85, "cn_keyword": "美式复古翻毛皮夹克男秋冬加绒短款外套"},
            {"category": "top", "name": "Oq Vafli Trikotaj Longsliv", "price_cny": 28.0, "weight_kg": 0.40, "cn_keyword": "重磅华夫格长袖t恤男宽松圆领打底衫"},
            {"category": "bottom", "name": "To'q Ko'k Vintage Denim Shim", "price_cny": 38.0, "weight_kg": 0.60, "cn_keyword": "复古水洗深蓝直筒牛仔裤男宽松百搭"},
            {"category": "shoes", "name": "Jigarrang Zamsh Lofer", "price_cny": 45.0, "weight_kg": 0.75, "cn_keyword": "英伦风翻毛皮乐福鞋男加绒一脚蹬豆豆鞋"},
        ],
    },
    {
        "title": "Minimalist Bej Trenj va Drape Shim Kapsulasi",
        "description": "Och bej klassik trenj plash + qora qalin svitshot + to'q grafit keng drape shim + qora lofer.",
        "piece_count": 4,
        "palette_name": "Beige Trench & Graphite",
        "palette_hex": ["#D8CBB5", "#18191C", "#383B42", "#0F1012"],
        "audio_vibe": "lofi_editorial",
        "viral_hook": "MINIMALIST KLASSIK USLUB • PREMIUM TRENJ VA DRAPE",
        "colors": "Och bej, Qora, To'q grafit",
        "sizes": "M, L, XL, 2XL",
        "items": [
            {"category": "outerwear", "name": "Och Bej Klassik Trenj Plash", "price_cny": 68.0, "weight_kg": 1.10, "cn_keyword": "英伦风中长款双排扣风衣男加厚垂感大衣"},
            {"category": "top", "name": "Qora Qalin Svitshot", "price_cny": 32.0, "weight_kg": 0.45, "cn_keyword": "加绒加厚纯色圆领卫衣男宽松保暖内搭"},
            {"category": "bottom", "name": "To'q Grafit Keng Drape Shim", "price_cny": 36.0, "weight_kg": 0.52, "cn_keyword": "垂感西装裤男直筒阔腿宽松加厚休闲长裤"},
            {"category": "shoes", "name": "Qora Klassik Lofer", "price_cny": 46.0, "weight_kg": 0.75, "cn_keyword": "商务正装皮鞋男德比鞋英伦风休闲软底"},
        ],
    },
    {
        "title": "Qishki Qalin Puffer Kurtka va Velvet Shim Kapsulasi",
        "description": "To'q yashil qalin puffer kurtka + krem rangli qovurg'ali sviter + qora velvet shim + qora chelsea botinka.",
        "piece_count": 4,
        "palette_name": "Forest Puffer & Cream",
        "palette_hex": ["#253B2F", "#ECE5D8", "#1E1F22", "#0A0B0D"],
        "audio_vibe": "phonk_bass",
        "viral_hook": "QISHNING ENG SOVUQ KUNLARIGA ISSIQ VA ZAMONAVIY LOOK",
        "colors": "To'q yashil, Krem, Qora",
        "sizes": "M, L, XL, 2XL",
        "items": [
            {"category": "outerwear", "name": "To'q Yashil Qalin Puffer Kurtka", "price_cny": 66.0, "weight_kg": 1.15, "cn_keyword": "冬季连帽加厚保暖棉服男宽松立领短款羽绒棉袄"},
            {"category": "top", "name": "Krem Rangli Qovurg'ali Sviter", "price_cny": 34.0, "weight_kg": 0.50, "cn_keyword": "加厚圆领羊毛衫男冬季保暖针织打底毛衣"},
            {"category": "bottom", "name": "Qora Velvet Erkin Shim", "price_cny": 35.0, "weight_kg": 0.55, "cn_keyword": "灯芯绒条绒直筒裤男秋冬加厚保暖阔腿裤"},
            {"category": "shoes", "name": "Qora Chelsea Qishki Botinka", "price_cny": 48.0, "weight_kg": 0.90, "cn_keyword": "切尔西靴男真皮秋冬英伦短靴加绒马丁靴"},
        ],
    },
    {
        "title": "Retro Bayker Charm Kurtka va Vintage Jinsi",
        "description": "Qora charm bayker kurtka + grafit yoqali sviter + vintage keng denim shim + oq retro krossovka.",
        "piece_count": 4,
        "palette_name": "Obsidian Leather & Vintage Denim",
        "palette_hex": ["#161719", "#3A3D45", "#48586E", "#E8EAED"],
        "audio_vibe": "uk_drill_beat",
        "viral_hook": "RETRO VINTAGE CHARM KURTKA • SOTILADIGAN TREND",
        "colors": "Qora charm, Grafit, Vintage denim, Oq",
        "sizes": "M, L, XL, 2XL",
        "items": [
            {"category": "outerwear", "name": "Qora Charm Bayker Kurtka", "price_cny": 62.0, "weight_kg": 0.95, "cn_keyword": "美式复古PU皮衣外套男加厚机车短款夹克"},
            {"category": "top", "name": "Grafit Half-Zip Sviter", "price_cny": 32.0, "weight_kg": 0.48, "cn_keyword": "半拉链加厚针织衫男高领立领保暖毛衣"},
            {"category": "bottom", "name": "Vintage Keng Denim Shim", "price_cny": 36.0, "weight_kg": 0.58, "cn_keyword": "水洗做旧复古直筒牛仔裤男宽松阔腿长裤"},
            {"category": "shoes", "name": "Oq Retro Krossovka", "price_cny": 42.0, "weight_kg": 0.80, "cn_keyword": "复古运动鞋男轻便舒适防滑厚底百搭板鞋"},
        ],
    },
]


def _detect_garment_color_uz(img_bytes: bytes | None) -> str:
    """Jonli yuklab olingan kiyim rasmining markaziy qismidan asosiy rangni aniqlab, o'zbekcha nomini qaytaradi."""
    if not img_bytes:
        return ""
    try:
        import io
        from PIL import Image

        im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        w, h = im.size
        crop = im.crop((int(w * 0.28), int(h * 0.25), int(w * 0.72), int(h * 0.75))).resize((36, 36))
        pixels = list(crop.getdata())
        fg = [
            (r, g, b)
            for (r, g, b) in pixels
            if not (r > 215 and g > 210 and b > 198 and max(r, g, b) - min(r, g, b) < 35)
        ]
        if not fg:
            fg = pixels
        r_avg = sum(p[0] for p in fg) / len(fg)
        g_avg = sum(p[1] for p in fg) / len(fg)
        b_avg = sum(p[2] for p in fg) / len(fg)
        lum = 0.299 * r_avg + 0.587 * g_avg + 0.114 * b_avg
        spread = max(r_avg, g_avg, b_avg) - min(r_avg, g_avg, b_avg)

        if lum < 45:
            return "Qora"
        if lum > 212 and spread < 26:
            return "Oq"
        if b_avg > r_avg + 10 and b_avg >= g_avg:
            return "To'q ko'k (navy)" if lum < 115 else "Ko'k (denim)"
        if r_avg > b_avg + 12 and r_avg >= g_avg:
            if lum > 165:
                return "Och bej"
            if lum < 110:
                return "To'q jigarrang"
            return "Qahva-taupe"
        if g_avg >= r_avg and g_avg > b_avg + 10:
            return "To'q zaytun (xaki)"
        if spread < 18:
            return "To'q kulrang (grafit)" if lum < 115 else "Kulrang"
        return "To'q kulrang (grafit)" if lum < 125 else "Och bej"
    except Exception:
        return ""


def _uz_name_from_real_pdd(title_cn: str, color_uz: str, fallback_name: str) -> str:
    """Haqiqiy Pinduoduo xitoycha nomidan 100% rost, qisqa o'zbekcha nom (brend + rang + haqiqiy tur) tuzadi."""
    t = (title_cn or "").strip()
    if not t:
        return fallback_name
    col_clean = (color_uz or "").split("(")[0].split("/")[0].strip()
    if col_clean:
        col_clean = col_clean[0].upper() + col_clean[1:]

    brand = ""
    for cn_b, uz_b in (
        ("李宁", "Li-Ning"),
        ("安踏", "Anta"),
        ("特步", "Xtep"),
        ("阿迪达斯", "Adidas"),
        ("adidas", "Adidas"),
        ("JEEP", "Jeep"),
        ("Dickies", "Dickies"),
        ("皮尔卡丹", "Pierre Cardin"),
        ("回力", "Warrior"),
    ):
        if cn_b.lower() in t.lower():
            brand = uz_b
            break

    kind = ""
    if any(k in t for k in ("手表", "腕表", "机械表", "石英表")):
        kind = "Klassik Soat"
    elif any(k in t for k in ("皮带", "腰带")):
        kind = "Charm Kamar"
    elif any(k in t for k in ("围巾", "披肩")):
        kind = "Kashmir Sharf"
    elif any(k in t for k in ("墨镜", "太阳镜")):
        kind = "Quyosh Ko'zoynagi"
    elif any(k in t for k in ("斜挎包", "单肩包", "手提包", "挎包", "背包")):
        kind = "Yelka Sumkasi"
    elif any(k in t for k in ("鸭舌帽", "棒球帽", "冷帽", "帽子")):
        kind = "Minimalist Kepka"
    elif any(k in t for k in ("切尔西靴", "马丁靴", "皮靴", "短靴")):
        kind = "Chelsea Etik"
    elif any(k in t for k in ("乐福鞋", "德比鞋", "皮鞋")):
        kind = "Klassik Lofer"
    elif any(k in t for k in ("德训", "板鞋", "运动鞋", "休闲鞋", "小白鞋", "鞋")):
        kind = "Retro Krossovka"
    elif any(k in t for k in ("工装裤", "伞兵")):
        kind = "Qishki Cho'ntakli Shim" if any(w in t for w in ("加绒", "加厚", "秋冬", "冬")) else "Cho'ntakli Erkin Shim"
    elif "牛仔裤" in t:
        kind = "To'g'ri Jinsi Shim"
    elif any(k in t for k in ("西装裤", "西裤")):
        kind = "Klassik Drape Shim"
    elif any(k in t for k in ("阔腿裤", "休闲裤", "卫裤", "长裤", "裤")):
        kind = "Erkin Keng Shim"
    elif any(k in t for k in ("皮衣", "真皮夹克", "皮夹克")):
        kind = "Charm Kurtka"
    elif any(k in t for k in ("麂皮", "翻毛皮", "鹿皮绒")):
        kind = "Zamsh Kurtka"
    elif any(k in t for k in ("马甲", "背心")):
        kind = "Qishki Jilet"
    elif any(k in t for k in ("羊毛呢大衣", "呢子大衣", "毛呢大衣", "羊毛大衣", "大衣")):
        kind = "Jun Palto"
    elif "风衣" in t:
        kind = "Trench Palto"
    elif any(k in t for k in ("羽绒服", "棉服", "棉衣", "棉袄")):
        kind = "Qishki Puxovik Kurtka"
    elif any(k in t for k in ("冲锋衣", "防风")):
        kind = "Shamolto'sar Kurtka"
    elif any(k in t for k in ("西装", "西服")):
        kind = "Klassik Jun Blazer"
    elif any(k in t for k in ("夹克", "外套")):
        kind = "Bomber Kurtka"
    elif "开衫" in t:
        kind = "Trikotaj Kardigan"
    elif "半拉链" in t:
        kind = "Zamokli Sviter"
    elif any(k in t for k in ("高领", "羊绒")):
        kind = "Kashmir Vodolazka"
    elif "polo" in t.lower():
        kind = "Trikotaj Polo"
    elif "灯芯绒" in t:
        kind = "Velvyet Ko'ylak"
    elif any(k in t for k in ("连帽卫衣", "帽衫")):
        kind = "Oversize Xudi"
    elif any(k in t for k in ("卫衣", "衬衫")):
        kind = "Yoqali Svitshot" if "衬衫" in t or "翻领" in t else "Oversize Svitshot"
    elif any(k in t for k in ("毛衣", "针织")):
        kind = "Trikotaj Sviter"

    if not kind:
        return fallback_name
    parts = [p for p in (brand, col_clean, kind) if p]
    return " ".join(parts)


def _sync_item_with_studio_photo_color(name: str, category: str = "", idx: int = 0) -> tuple[str, str]:
    """Lokal studiya rasmidagi HAQIQIY rang va kiyim turi bilan nomni 100% sinxronlaydi."""
    low = (name or "").lower()
    cat = (category or "").lower()
    if any(k in low for k in ("palto", "overcoat", "trench", "ikki qatorli")):
        return "To'q Jigarrang Ikki Qatorli Jun Palto", "To'q jigarrang"
    if any(k in low for k in ("blazer", "pidjak", "kostyum", "ko'k jun")):
        return "To'q Ko'k Klassik Jun Blazer", "To'q ko'k (navy)"
    if any(k in low for k in ("bomber", "kurtka", "vetrovka", "jaket", "jilet")) or cat == "outerwear":
        return "Qora Jun Bomber Kurtka", "Qora"
    if any(k in low for k in ("vodolazka", "turtleneck", "kashemir", "kashmir", "qahva sviter", "to'q jigarrang sviter")):
        return "To'q Qahva Kashmir Vodolazka", "To'q jigarrang"
    if any(k in low for k in ("sviter", "kardigan", "polo", "zip", "half-zip", "jemper", "pullover")):
        return "Bej Zamokli Sviter", "Och bej"
    if any(k in low for k in ("xudi", "hud", "hood", "tolstovka", "svitshot")) or cat == "top":
        return "Grafit Oversize Xudi", "To'q kulrang (grafit)"
    if any(k in low for k in ("kargo", "parashyut", "jinsi", "jeans", "cargo", "cho'ntakli")):
        return "Zaytun Cho'ntakli Erkin Shim", "To'q zaytun (xaki)"
    if any(k in low for k in ("taupe", "jigarrang", "mocha", "qahva", "brown")) and any(k in low for k in ("shim", "bryuk", "trouser", "pants")):
        return "Qahva-Taupe Old Money Jun Shim", "Qahva-taupe"
    if any(k in low for k in ("shim", "bryuk", "drape", "triko", "shalvar")) or cat == "bottom":
        return "Grafit Klassik Drape Shim", "To'q kulrang (grafit)"
    if any(k in low for k in ("chelsea", "etik", "botinka", "qishki poyabzal")):
        return "Qora Charm Qishki Chelsea Etik", "Qora"
    if any(k in low for k in ("lofer", "tufli", "zamsh", "klassik oyoq", "loafer")):
        return "Espresso Zamsh Lofer", "To'q jigarrang"
    if any(k in low for k in ("krossovka", "oyoq", "keda", "sneaker")) or cat == "shoes":
        return "Oq-Kulrang Krossovka", "Oq-kulrang"
    if any(k in low for k in ("kepka", "shapka", "sumka", "soat", "kamar", "ochki")) or cat == "accessory":
        return "Qora Minimalist Kepka", "Qora"
    fallbacks = [
        ("To'q Jigarrang Ikki Qatorli Jun Palto", "To'q jigarrang"),
        ("To'q Qahva Kashmir Vodolazka", "To'q jigarrang"),
        ("Qahva-Taupe Old Money Jun Shim", "Qahva-taupe"),
        ("Qora Charm Qishki Chelsea Etik", "Qora"),
    ]
    return fallbacks[idx % len(fallbacks)]


def _synchronize_look_title_with_items(raw_title: str, norm_items: list[dict[str, Any]]) -> str:
    """Look sarlavhasini keraksiz so'zlardan ('Toshkent', 'Shahar') tozalaydi va haqiqiy buyumlar bilan 100% moslashtiradi."""
    cleaned = re.sub(r"\b(?:Toshkent(?:da|lik|ga|dan)?|Shahar|O'zbekiston(?:da|lik)?)\b", "", raw_title or "", flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -–—,:;")

    item_names = [str(it.get("name") or "").strip() for it in norm_items if str(it.get("name") or "").strip()]
    joined_items_low = " ".join(n.lower() for n in item_names)
    title_low = cleaned.lower()

    specific_types = ("palto", "kurtka", "blazer", "jilet", "kardigan", "sviter", "vodolazka", "xudi", "svitshot")
    mentioned_types = [gt for gt in specific_types if gt in title_low]
    has_mismatch = any(gt not in joined_items_low for gt in mentioned_types)

    if (not cleaned or len(cleaned) < 8 or has_mismatch) and item_names:
        if len(item_names) >= 2:
            return f"{item_names[0]} va {item_names[1]} Kapsulasi"
        return f"{item_names[0]} Kapsulasi"
    return cleaned


@dataclass(frozen=True)
class GeneratedLook:
    title: str
    description: str
    items_json: str
    colors: str
    sizes: str
    weight_kg: float
    prepay_uzs: int
    prepay_50_uzs: int
    remaining_50_uzs: int
    goods_cost_uzs: int
    cargo_est_uzs: int
    profit_est_uzs: int
    raw_items: list[dict[str, Any]]
    breakdown: PriceBreakdown
    piece_count: int = 4
    palette_name: str = "Monochrome Graphite"
    palette_hex: list[str] | None = None
    audio_vibe: str = "phonk_bass"
    viral_hook: str = "50% OLDINDAN • QOLGANI TOSHKENTDA"
    weather_summary: str = ""
    downloaded_images: list[bytes | None] | None = None


class TrendSourcingAgent:
    def __init__(self, settings: Settings, rates: Rates | None = None, params: PriceParams | None = None):
        self.s = settings
        self.rates = rates or Rates(cny_uzs=settings.cny_uzs, usd_uzs=settings.usd_uzs)
        self.params = params
        self.ai = SalesAI(settings)
        self.client = self.ai.client
        self.pdd = PinduoduoConnector(
            client_id=getattr(settings, "pdd_client_id", ""),
            client_secret=getattr(settings, "pdd_client_secret", ""),
            rapidapi_key=getattr(settings, "pdd_rapidapi_key", ""),
            session_path=getattr(settings, "pdd_session_path", "data/pdd_session.json"),
            apify_token=getattr(settings, "pdd_apify_token", ""),
        )
        self._fallback_idx = 0

    def analyze_instagram_trends(self, idx: int | None = None) -> InstagramTrendBrief:
        """Instagram Reels va Look-bozorda hozir qaysi format va ranglar rekka chiqayotganini aniqlaydi."""
        pick = self._fallback_idx if idx is None else idx
        return MARKET_TREND_BRIEFS[pick % len(MARKET_TREND_BRIEFS)]

    def _params(self) -> PriceParams:
        if self.params is not None:
            return self.params
        return PriceParams(
            vykup_percent=self.s.vykup_percent,
            profit_percent=self.s.profit_percent,
            payment_fee_percent=self.s.payment_fee_percent,
            china_shipping_cny_per_item=self.s.china_shipping_cny_per_item,
            cargo_usd_per_kg=self.s.cargo_usd_per_kg,
            cargo_client_uzs_per_kg=self.s.cargo_client_uzs_per_kg,
            prepay_round_to=getattr(self.s, "prepay_round_to", 50000),
            conversion_fee_percent=self.s.conversion_fee_percent,
            ensure_50_covers_cost=self.s.ensure_50_covers_cost,
        )

    def _calculate_pricing(self, raw_items: list[dict[str, Any]]) -> tuple[PriceBreakdown, list[dict[str, Any]]]:
        normalized: list[dict[str, Any]] = []
        items: list[Item] = []
        for idx, i in enumerate(raw_items):
            cny = float(i.get("price_cny", i.get("cny", 50)))
            w = float(i.get("weight_kg", 0.5))
            nm = str(i.get("name", "Buyum"))
            kw = str(i.get("cn_keyword", ""))
            cat = str(i.get("category", ""))

            pdd_enriched = self.pdd.match_verified_item(
                category=cat,
                name_uz=nm,
                cn_keyword=kw,
                price_cny=cny,
                weight_kg=w,
                idx=idx,
            )
            if i.get("pdd_goods_id"):
                pdd_enriched["pdd_goods_id"] = str(i["pdd_goods_id"])
            if i.get("sales_tip"):
                pdd_enriched["sales_tip"] = str(i["sales_tip"])
            if i.get("image_url"):
                pdd_enriched["image_url"] = str(i["image_url"])
            if i.get("url") and "yangkeduo.com" in str(i.get("url")):
                pdd_enriched["url"] = str(i["url"])
            for meta_key in (
                "title_cn",
                "store_colors",
                "store_sizes",
                "size_chart",
                "fit_note",
                "studio_prompt",
                "studio_regen_prompt",
                "color_uz",
                "_preserve_custom_spec",
            ):
                if i.get(meta_key):
                    pdd_enriched[meta_key] = i[meta_key]
            normalized.append(pdd_enriched)
            items.append(
                Item(
                    name=pdd_enriched["name"],
                    price_cny=pdd_enriched["price_cny"],
                    weight_kg=pdd_enriched["weight_kg"],
                    url=pdd_enriched["url"],
                )
            )

        calc = calculate(items, self.rates, self._params())
        return calc, normalized

    def _build_look_prompt(
        self,
        brief: InstagramTrendBrief,
        weather_line: str,
        gender: str,
        playbooks_text: str = "",
        recent_titles: list[str] | None = None,
        market_benchmark_note: str = "",
    ) -> str:
        playbook_section = f"\n{playbooks_text}\n" if playbooks_text else ""
        recent_block = ""
        if recent_titles:
            clean_rec = [str(t).strip() for t in recent_titles if str(t).strip()][:8]
            if clean_rec:
                recent_block = (
                    "\nTAQIQLANGAN TAKRORLASH (oxirgi chiqqan looklar — bularni va xuddi shu kiyimlarni QAYTA YOZMA! "
                    "Mutlaqo yangi, boshqa fason va yangi nom o'ylab top):\n- "
                    + "\n- ".join(clean_rec)
                    + "\n"
                )
        market_block = f"\nRAQOBATCHI BOZOR NARXLARI (Telegram/Instagram jonli tahlil): {market_benchmark_note}\n" if market_benchmark_note else ""
        return f"""Sen "XAN SHOP" moda brendining Bosh Bozor Tahlilchisi, Dizayner-Stilisti va Pinduoduo Skaut Agentisan.
Instagram & Telegram tahlilchisi quyidagi trend hisobotini yubordi:
- Trend yo'nalishi: {brief.trend_name}
- Tavsiya etilgan buyumlar soni: {brief.recommended_piece_count} ta buyum (qotib qolmasdan aynan {brief.recommended_piece_count} ta uyg'un buyum yig')
- Dizayner ranglar palitrasi: {brief.color_palette_name} ({', '.join(brief.color_hex_list)})
- Toshkent ob-havosi va mavsumi: {weather_line}
- Auditoriya: {gender}
{market_block}{recent_block}{playbook_section}
Vazifang: Pinduoduo (拼多多) da haqiqatda ko'p sotilayotgan, sifati baland va narxi hamyonbop (ust kiyim 38–65 CNY, ichki/shim 24–45 CNY, oyoq kiyim 32–54 CNY, aksessuar 12–25 CNY; BUTUN KAPSULA ~110–168 CNY jami!) bo'lgan mutlaqo YANGI va uyg'un Look yig'.
100+ yuanlik qimmat buyumlar tanlab lookni qimmatlashtirma va raqobatdan chiqarib yuborma — sifatli + arzon "oltin o'rtalik" top!
Har safar har xil kiyim turlarini tanla (masalan: zamsh/teri kurtka, yengil puxovik, kardigan, polo sviter, yarim-zamokli sviter, jun palto, klassik shim, to'g'ri jinsi, cho'ntakli erkin shim, chelsea etik, zamsh lofer, retro krossovka, soat, kamar, sharf).
MUHIM QOIDA: "title" va har bir buyumning "name" maydoni FAQAT O'ZBEK TILIDA, qisqa va tushunarli (2–4 so'z) bo'lsin! Inglizcha so'zlar yozma va HECH QACHON 'kargo shim' deb yozma!
Har bir buyum uchun real Pinduoduo narxi (yuan - CNY), vazni (kg), kategoriyasi (outerwear, top, bottom, shoes, accessory) va aniq xitoycha qidiruv so'zini ber.

FAQAT JSON QAYTAR:
{{
  "title": "O'zbekcha qisqa va yangi Look nomi",
  "description": "Sotuvbop professional tavsif",
  "colors": "Ranglar uyg'unligi",
  "sizes": "M, L, XL, 2XL",
  "palette_name": "{brief.color_palette_name}",
  "palette_hex": {json.dumps(brief.color_hex_list)},
  "viral_hook": "{brief.viral_hook_uz}",
  "audio_vibe": "{brief.audio_vibe}",
  "items": [
    {{"category": "top", "name": "Qora Oversize Xudi", "price_cny": 54.0, "weight_kg": 0.5, "cn_keyword": "xitoycha qidiruv"}}
  ]
}}"""

    def _pick_template_if_invalid(
        self,
        data: dict[str, Any] | None,
        recent_titles: list[str] | None = None,
    ) -> dict[str, Any]:
        if isinstance(data, dict) and isinstance(data.get("items"), list) and len(data["items"]) >= 2:
            return data
        total = len(DYNAMIC_LOOK_TEMPLATES)
        pick_idx = self._fallback_idx % total
        recent_set = {t.strip().lower() for t in (recent_titles or []) if t}
        for offset in range(total):
            cand = DYNAMIC_LOOK_TEMPLATES[(self._fallback_idx + offset) % total]
            if str(cand.get("title", "")).strip().lower() not in recent_set:
                pick_idx = (self._fallback_idx + offset) % total
                break
        tpl = json.loads(json.dumps(DYNAMIC_LOOK_TEMPLATES[pick_idx], ensure_ascii=False))
        self._fallback_idx += 1
        return tpl

    def _enforce_seasonal_and_persona_rules(
        self,
        data: dict[str, Any],
        brief: InstagramTrendBrief,
        weather: WeatherForecast | None = None,
        ig_intel: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Qish/kuz ob-havosi, Diplomat/Old Money klassik qoidalari va arzon futbolkani bloklash."""
        from urllib.parse import quote
        from app.ig_analytics import evaluate_seasonal_styling_rules

        out = json.loads(json.dumps(data, ensure_ascii=False))
        w_dict = None
        if ig_intel and isinstance(ig_intel.get("seasonal_rules"), dict):
            rules = ig_intel["seasonal_rules"]
        else:
            if weather is not None:
                w_dict = {
                    "cur_temp": weather.temp_c,
                    "forecast_5_10d_min": weather.future_temp_c or weather.temp_c,
                    "forecast_5_10d_max": weather.temp_c,
                }
            rules = evaluate_seasonal_styling_rules(w_dict)

        context_text = (
            f"{out.get('title', '')} {out.get('description', '')} "
            f"{getattr(brief, 'trend_name', '')} {getattr(brief, 'target_audience', '')} "
            f"{getattr(brief, 'conversion_reason', '')}"
        ).lower()
        is_diplomat_old_money = any(
            k in context_text
            for k in ("diplomat", "yurid", "old money", "klassik", "ofis", "biznes", "quiet luxury")
        )

        # Har siklda bir xil 4 buyumni takrorlamaslik uchun xilma-xil qishki qatlamlar ro'yxati
        var_idx = max(0, self._fallback_idx)
        old_money_outer_alts = [
            {
                "name": "To'q Jigarrang Ikki Qatorli Jun Palto",
                "cn_keyword": "老钱风双排扣羊毛呢大衣男秋冬加厚英伦外套",
                "price_cny": 65.0,
                "weight_kg": 1.15,
                "color_uz": "To'q jigarrang",
            },
            {
                "name": "To'q Ko'k Klassik Jun Blazer",
                "cn_keyword": "老钱风藏青色羊毛修身西装外套男秋冬商务夹克",
                "price_cny": 62.0,
                "weight_kg": 0.78,
                "color_uz": "To'q ko'k",
            },
            {
                "name": "Qora Jun Bomber Kurtka",
                "cn_keyword": "老钱风重磅羊毛飞行员夹克男秋冬外套",
                "price_cny": 56.0,
                "weight_kg": 0.78,
                "color_uz": "Qora",
            },
        ]
        warm_knit_alts = [
            {
                "name": "To'q Qahva Kashmir Vodolazka",
                "cn_keyword": "男秋冬加厚羊绒高领打底毛衣老钱风保暖针织衫",
                "price_cny": 36.0,
                "weight_kg": 0.48,
                "color_uz": "To'q jigarrang",
            },
            {
                "name": "Och Bej Zamokli Sviter",
                "cn_keyword": "老钱风半拉链针织毛衣男秋冬加厚立领",
                "price_cny": 34.0,
                "weight_kg": 0.50,
                "color_uz": "Och bej",
            },
        ]
        classic_bottom_alts = [
            {
                "name": "Qahva-Taupe Old Money Jun Shim",
                "cn_keyword": "老钱风摩卡棕垂感褶皱羊毛西装裤男秋冬加厚",
                "price_cny": 36.0,
                "weight_kg": 0.52,
                "color_uz": "Qahva-taupe",
            },
            {
                "name": "Grafit Klassik Drape Shim",
                "cn_keyword": "垂感羊毛西装裤男直筒老钱风秋冬加厚长裤",
                "price_cny": 35.0,
                "weight_kg": 0.50,
                "color_uz": "To'q kulrang (grafit)",
            },
        ]
        classic_shoe_alts = [
            {
                "name": "Qora Charm Qishki Chelsea Etik",
                "cn_keyword": "切尔西靴男真皮英伦风复古短靴秋冬加绒皮靴",
                "price_cny": 52.0,
                "weight_kg": 0.92,
                "color_uz": "Qora",
            },
            {
                "name": "Espresso Zamsh Lofer",
                "cn_keyword": "老钱风翻毛皮乐福鞋男英伦休闲皮鞋加绒",
                "price_cny": 44.0,
                "weight_kg": 0.76,
                "color_uz": "To'q jigarrang",
            },
        ]

        fixed_items: list[dict[str, Any]] = []
        for idx, raw_it in enumerate(out.get("items") or []):
            it = dict(raw_it)
            name_low = f"{it.get('name', '')} {it.get('cn_keyword', '')}".lower()
            price_val = float(it.get("price_cny") or 0)

            # Erkin va ochiq tizim: qattiq majburlov yo'q, faqat sovuqda arzon yozgi futbolkani yumshoq almashtirish + 1688 ni tozalash
            if rules.get("forbid_tshirts") and price_val < 40.0 and any(
                w in name_low for w in ("futbolka", "t-shirt", "mayka", "短袖", "t恤", "tee")
            ):
                rep = warm_knit_alts[(var_idx + idx) % len(warm_knit_alts)]
                it.update(rep)
                it["category"] = "top"

            # Har doim toza Pinduoduo qidiruv havolasi (1688/taobao olib tashlanadi)
            cn_kw = str(it.get("cn_keyword") or it.get("name") or "").strip()
            if not it.get("url") or "1688.com" in str(it.get("url", "")) or "taobao.com" in str(it.get("url", "")):
                it["url"] = f"https://mobile.yangkeduo.com/search_result.html?search_key={quote(cn_kw)}"
            fixed_items.append(it)

        out["items"] = fixed_items
        if fixed_items:
            cols = []
            for x in fixed_items:
                c = str(x.get("color_uz") or "").strip()
                if c and c not in cols:
                    cols.append(c)
            if cols:
                out["colors"] = ", ".join(cols)
        return out

    def _build_generated_look(
        self,
        data: dict[str, Any],
        brief: InstagramTrendBrief,
        weather_line: str,
        raw_items_override: list[dict[str, Any]] | None = None,
        downloaded_images: list[bytes | None] | None = None,
    ) -> GeneratedLook:
        items_input = raw_items_override if raw_items_override is not None else data["items"]
        calc, norm_items = self._calculate_pricing(items_input)
        palette_hex = data.get("palette_hex") or brief.color_hex_list

        has_live_imgs = bool(downloaded_images and any(downloaded_images))
        exact_colors: list[str] = []
        for idx, it in enumerate(norm_items):
            live_img = downloaded_images[idx] if (downloaded_images and idx < len(downloaded_images)) else None
            if live_img:
                # Jonli Pinduoduo rasmi bor: maxsus buyruq (custom look) bo'lmasa kiyim nomini Pinduoduo tovariga moslaymiz
                if it.get("_preserve_custom_spec") and str(it.get("name") or "").strip():
                    det_col = str(it.get("color_uz") or "").strip() or _detect_garment_color_uz(live_img) or "Qora"
                    it["color_uz"] = det_col
                else:
                    st_cols = it.get("store_colors") or []
                    det_col = (st_cols[0] if len(st_cols) == 1 else "") or _detect_garment_color_uz(live_img) or str(it.get("color_uz") or "Qora")
                    it["name"] = _uz_name_from_real_pdd(str(it.get("title_cn") or ""), det_col, str(it.get("name") or "Buyum"))
                    it["color_uz"] = det_col
                it.pop("_preserve_custom_spec", None)
                if det_col and det_col not in exact_colors:
                    exact_colors.append(det_col)
            else:
                # Agar nom allaqachon aniq (masalan 'Jigarrang Zamsh Kurtka', 'Klassik Charm Soat') bo'lsa, uni buzmaymiz!
                orig_name = str(it.get("name") or "").strip()
                if orig_name and orig_name.lower() not in ("buyum", "kiyim", ""):
                    synced_name = orig_name
                    _, inferred_col = _sync_item_with_studio_photo_color(orig_name, str(it.get("category", "")), idx)
                    synced_col = str(it.get("color_uz") or "").strip() or inferred_col
                else:
                    synced_name, synced_col = _sync_item_with_studio_photo_color(
                        orig_name,
                        str(it.get("category", "")),
                        idx,
                    )
                it["name"] = synced_name
                it["color_uz"] = synced_col
                if synced_col and synced_col not in exact_colors:
                    exact_colors.append(synced_col)

        colors_str = ", ".join(exact_colors) if exact_colors else str(data.get("colors", "Qora, Grafit"))
        final_title = _synchronize_look_title_with_items(data.get("title", "Yangi Trend Look"), norm_items)

        return GeneratedLook(
            title=final_title,
            description=data.get("description", ""),
            items_json=json.dumps(norm_items, ensure_ascii=False),
            colors=colors_str,
            sizes=data.get("sizes", "M, L, XL, 2XL"),
            weight_kg=calc.weight_kg,
            prepay_uzs=calc.prepay_uzs,
            prepay_50_uzs=calc.prepay_50_uzs,
            remaining_50_uzs=calc.remaining_50_uzs,
            goods_cost_uzs=calc.goods_cost_uzs,
            cargo_est_uzs=calc.cargo_client_uzs,
            profit_est_uzs=calc.total_profit_uzs,
            raw_items=norm_items,
            breakdown=calc,
            piece_count=len(norm_items),
            palette_name=data.get("palette_name", brief.color_palette_name),
            palette_hex=palette_hex,
            audio_vibe=data.get("audio_vibe", brief.audio_vibe),
            viral_hook=data.get("viral_hook", brief.viral_hook_uz),
            weather_summary=weather_line,
            downloaded_images=downloaded_images if has_live_imgs else None,
        )

    def generate_look(
        self,
        season: str = "sovuq havo / kuz-qish",
        gender: str = "yoshlar / erkaklar",
        style: str = "Instagram Reels Trend (Lookzona / Stylesh)",
        trend_brief: InstagramTrendBrief | None = None,
        weather: WeatherForecast | None = None,
    ) -> GeneratedLook:
        """Bozor tahlili, ob-havo, ranglar palitrasi va Pinduoduo ma'lumotlari asosida Look yaratadi (2, 3, 4 yoki 5 qismli)."""
        brief = trend_brief or self.analyze_instagram_trends()
        weather_line = (
            f"{weather.city}: {weather.temp_c}°C ({weather.season_uz}) — {weather.clothing_advice}"
            if weather
            else season
        )
        data = None

        if self.client:
            prompt = self._build_look_prompt(brief, weather_line, gender)
            for candidate in self.ai._gemini_model_candidates():
                try:
                    res = self.client.interactions.create(model=candidate, input=prompt)
                    parsed = extract_json_dict(getattr(res, "output_text", None) or "")
                    if parsed and isinstance(parsed.get("items"), list) and len(parsed["items"]) >= 2:
                        data = parsed
                        break
                except Exception as e:
                    log.warning("Gemini (%s) orqali trend olishda xatolik (%s)", candidate, e)

        enforced = self._enforce_seasonal_and_persona_rules(
            self._pick_template_if_invalid(data),
            brief,
            weather=weather,
        )
        return self._build_generated_look(enforced, brief, weather_line)

    async def analyze_instagram_trends_async(
        self,
        weather: WeatherForecast | None = None,
        idx: int | None = None,
    ) -> InstagramTrendBrief:
        """OmniRoute/OpenRouter/Gemini + Ob-havo + Raqobatchilar asosida Instagram trend brief yaratadi."""
        w = weather or await fetch_tashkent_weather()
        ai_strat = await analyze_instagram_creative_strategy(self.client, self.s.gemini_model, w, settings=self.s)
        if ai_strat:
            cnt = int(ai_strat.get("recommended_piece_count") or 4)
            cnt = max(2, min(5, cnt))
            vibe = str(ai_strat.get("audio_vibe") or "phonk_bass")
            if vibe not in ("diplomat_old_money", "phonk_bass", "luxury_chill", "lofi_editorial", "uk_drill_beat"):
                vibe = "phonk_bass"
            return InstagramTrendBrief(
                trend_name=str(ai_strat.get("trend_name") or "Instagram Viral Streetwear"),
                recommended_piece_count=cnt,
                color_palette_name=str(ai_strat.get("color_palette_name") or "Monochrome Slate"),
                color_hex_list=list(ai_strat.get("color_hex_list") or ["#16171B", "#3C3732", "#C7B8A5"]),
                viral_hook_uz=str(ai_strat.get("viral_hook_uz") or "BU OBRAZ SIZNI KO'CHADA AJRATADI!"),
                audio_vibe=vibe,
                conversion_reason=str(ai_strat.get("conversion_reason") or "FOMO + 50% qulay to'lov konversiyani oshiradi."),
            )
        return self.analyze_instagram_trends(idx)

    @staticmethod
    def _extract_video_frame_jpeg(video_bytes: bytes) -> bytes | None:
        """Admin yuklagan MP4/MOV videodan o'rta kadrni FFmpeg bilan JPEG sifatida ajratib oladi."""
        if not video_bytes or len(video_bytes) < 512:
            return None
        from .media import find_ffmpeg_binary

        ffmpeg_bin = find_ffmpeg_binary()
        if not ffmpeg_bin:
            return None
        vid_tmp = None
        img_tmp = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as vf:
                vf.write(video_bytes)
                vid_tmp = vf.name
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as imf:
                img_tmp = imf.name
            for seek_ts in ("00:00:01.0", "00:00:00.2"):
                proc = subprocess.run(
                    [ffmpeg_bin, "-y", "-ss", seek_ts, "-i", vid_tmp, "-frames:v", "1", "-q:v", "2", img_tmp],
                    capture_output=True,
                    timeout=20,
                )
                if proc.returncode == 0 and os.path.isfile(img_tmp) and os.path.getsize(img_tmp) > 1500:
                    with open(img_tmp, "rb") as rf:
                        return rf.read()
        except Exception as exc:
            log.warning("Yuklangan videodan kadr olish xatosi: %s", exc)
        finally:
            for p_rm in (vid_tmp, img_tmp):
                if p_rm and os.path.isfile(p_rm):
                    try:
                        os.remove(p_rm)
                    except OSError:
                        pass
        return None

    @staticmethod
    def _parse_custom_prompt_fallback(
        prompt_text: str = "",
        piece_count: int | None = None,
    ) -> dict[str, Any]:
        """AI Vision/LLM oflayn bo'lganda ham foydalanuvchining matn buyrug'idan aniq kiyim tarkibini tuzadi."""
        low = (prompt_text or "").lower()
        picked_items: list[dict[str, Any]] = []

        def _detect_color(snippet: str, default_col: str) -> str:
            for kw_c, label in (
                ("to'q jigarrang", "To'q jigarrang"),
                ("jigarrang", "Jigarrang"),
                ("qahva", "Qahva rang"),
                ("qora", "Qora"),
                ("to'q ko'k", "To'q ko'k"),
                ("ko'k", "Ko'k"),
                ("kulrang", "Grafit"),
                ("grafit", "Grafit"),
                ("och bej", "Och bej"),
                ("bej", "Bej"),
                ("krem", "Krem"),
                ("yashil", "Zaytun"),
                ("zaytun", "Zaytun"),
                ("oq", "Oq"),
                ("коричнев", "Jigarrang"),
                ("черн", "Qora"),
                ("сер", "Grafit"),
                ("беж", "Bej"),
                ("brown", "Jigarrang"),
                ("black", "Qora"),
                ("navy", "To'q ko'k"),
                ("grey", "Grafit"),
                ("beige", "Bej"),
            ):
                if kw_c in snippet:
                    return label
            return default_col

        def _match_spec(keys: tuple[str, ...]) -> str | None:
            for m in re.finditer(r"[^,;\.\n]+", low):
                seg = m.group(0)
                if any(k in seg for k in keys):
                    return seg
            return None

        seg_outer = _match_spec(("zamsh", "kurtka", "palto", "blazer", "pidjak", "bomber", "jacket", "coat", "куртк", "пальт"))
        if seg_outer:
            col = _detect_color(seg_outer, "Jigarrang")
            if any(k in seg_outer for k in ("palto", "coat", "пальт")):
                picked_items.append({"category": "outerwear", "name": f"{col} Jun Palto", "color_uz": col, "price_cny": 62.0, "weight_kg": 1.05, "cn_keyword": "羊毛呢大衣男秋冬加厚"})
            elif any(k in seg_outer for k in ("blazer", "pidjak")):
                picked_items.append({"category": "outerwear", "name": f"{col} Klassik Blazer", "color_uz": col, "price_cny": 58.0, "weight_kg": 0.78, "cn_keyword": "老钱风羊毛西装外套男"})
            elif any(k in seg_outer for k in ("zamsh", "suede")):
                picked_items.append({"category": "outerwear", "name": f"{col} Zamsh Kurtka", "color_uz": col, "price_cny": 54.0, "weight_kg": 0.85, "cn_keyword": "麂皮绒翻领羊羔毛夹克男秋冬"})
            else:
                picked_items.append({"category": "outerwear", "name": f"{col} Bomber Kurtka", "color_uz": col, "price_cny": 54.0, "weight_kg": 0.82, "cn_keyword": "美式复古飞行员夹克男秋冬"})

        seg_top = _match_spec(("svitshot", "vodolazka", "sviter", "xudi", "hoodie", "ko'ylak", "polo", "futbolka", "свитшот", "водолазк", "свитер", "худи"))
        if seg_top:
            col = _detect_color(seg_top, "Qora")
            if any(k in seg_top for k in ("vodolazka", "turtleneck", "водолазк")):
                picked_items.append({"category": "top", "name": f"{col} Kashmir Vodolazka", "color_uz": col, "price_cny": 34.0, "weight_kg": 0.45, "cn_keyword": "羊绒高领打底毛衣男秋冬"})
            elif any(k in seg_top for k in ("xudi", "hoodie", "худи")):
                picked_items.append({"category": "top", "name": f"{col} Oversize Xudi", "color_uz": col, "price_cny": 36.0, "weight_kg": 0.55, "cn_keyword": "重磅纯色连帽卫衣男秋冬"})
            elif any(k in seg_top for k in ("ko'ylak", "shirt")):
                picked_items.append({"category": "top", "name": f"{col} Klassik Ko'ylak", "color_uz": col, "price_cny": 32.0, "weight_kg": 0.35, "cn_keyword": "修身长袖衬衫男商务"})
            else:
                picked_items.append({"category": "top", "name": f"{col} Oversize Svitshot", "color_uz": col, "price_cny": 34.0, "weight_kg": 0.52, "cn_keyword": "纯色重磅加绒圆领卫衣男"})

        seg_bot = _match_spec(("shim", "bryuk", "jinsi", "jeans", "drape", "trousers", "pants", "брюк", "джинс"))
        if seg_bot:
            col = _detect_color(seg_bot, "Qora")
            if any(k in seg_bot for k in ("jinsi", "jeans", "джинс")):
                picked_items.append({"category": "bottom", "name": f"{col} To'g'ri Jinsi Shim", "color_uz": col, "price_cny": 38.0, "weight_kg": 0.62, "cn_keyword": "直筒宽松牛仔裤男垂感"})
            else:
                picked_items.append({"category": "bottom", "name": f"{col} Klassik Drape Shim", "color_uz": col, "price_cny": 36.0, "weight_kg": 0.50, "cn_keyword": "垂感宽松直筒西裤男秋冬"})

        seg_shoe = _match_spec(("botinka", "etik", "chelsea", "lofer", "krossovka", "tufli", "poyabzal", "boots", "loafer", "sneaker", "ботинк", "кроссов", "лофер"))
        if seg_shoe:
            col = _detect_color(seg_shoe, "Qora")
            if any(k in seg_shoe for k in ("lofer", "loafer", "лофер")):
                picked_items.append({"category": "shoes", "name": f"{col} Zamsh Lofer", "color_uz": col, "price_cny": 44.0, "weight_kg": 0.78, "cn_keyword": "翻毛皮乐福鞋男英伦"})
            elif any(k in seg_shoe for k in ("krossovka", "sneaker", "кроссов")):
                picked_items.append({"category": "shoes", "name": f"{col} Retro Krossovka", "color_uz": col, "price_cny": 46.0, "weight_kg": 0.80, "cn_keyword": "复古运动休闲鞋男"})
            else:
                picked_items.append({"category": "shoes", "name": f"{col} Qishki Botinka", "color_uz": col, "price_cny": 48.0, "weight_kg": 0.90, "cn_keyword": "工装马丁靴男秋冬季厚底"})

        if not picked_items:
            picked_items = [
                {"category": "outerwear", "name": "Jigarrang Zamsh Kurtka", "color_uz": "Jigarrang", "price_cny": 54.0, "weight_kg": 0.85, "cn_keyword": "麂皮绒羊羔毛夹克男"},
                {"category": "top", "name": "Qora Kashmir Vodolazka", "color_uz": "Qora", "price_cny": 34.0, "weight_kg": 0.45, "cn_keyword": "羊绒高领毛衣男"},
                {"category": "bottom", "name": "Grafit Klassik Drape Shim", "color_uz": "Grafit", "price_cny": 36.0, "weight_kg": 0.50, "cn_keyword": "垂感西装裤男直筒"},
                {"category": "shoes", "name": "Qora Chelsea Etik", "color_uz": "Qora", "price_cny": 48.0, "weight_kg": 0.90, "cn_keyword": "切尔西靴男加绒"},
            ]

        defaults = [
            {"category": "outerwear", "name": "Qora Bomber Kurtka", "color_uz": "Qora", "price_cny": 52.0, "weight_kg": 0.82, "cn_keyword": "复古夹克外套男"},
            {"category": "top", "name": "Qora Oversize Svitshot", "color_uz": "Qora", "price_cny": 34.0, "weight_kg": 0.50, "cn_keyword": "重磅圆领卫衣男"},
            {"category": "bottom", "name": "Qora Klassik Drape Shim", "color_uz": "Qora", "price_cny": 36.0, "weight_kg": 0.50, "cn_keyword": "垂感直筒西裤男"},
            {"category": "shoes", "name": "Qora Qishki Botinka", "color_uz": "Qora", "price_cny": 46.0, "weight_kg": 0.88, "cn_keyword": "马丁靴男秋冬"},
        ]
        target_cnt = max(2, min(4, int(piece_count))) if piece_count else len(picked_items)
        if len(picked_items) < max(2, target_cnt):
            have_cats = {x["category"] for x in picked_items}
            for d_it in defaults:
                if len(picked_items) >= max(2, target_cnt):
                    break
                if d_it["category"] not in have_cats:
                    picked_items.append(d_it)
                    have_cats.add(d_it["category"])
        picked_items = picked_items[:4]

        title_hint = re.sub(r"\s+", " ", (prompt_text or "").strip())
        if "old money" in low or "diplomat" in low or "klassik" in low:
            title = "Maxsus Old Money Klassik Kapsulasi"
            vibe = "diplomat_old_money"
        elif title_hint and 8 <= len(title_hint) <= 46:
            title = title_hint.rstrip(".,!?").capitalize()
            vibe = "phonk_bass"
        else:
            title = f"Maxsus AI Obraz ({len(picked_items)}-in-1)"
            vibe = "phonk_bass"

        colors = ", ".join(dict.fromkeys(x.get("color_uz", "Qora") for x in picked_items))
        return {
            "title": title,
            "description": prompt_text.strip() or "Admin buyrug'i va AI Vision asosida Pinduoduo'dan saralangan maxsus kapsula.",
            "colors": colors,
            "sizes": "M, L, XL, 2XL",
            "palette_name": "Maxsus Studio Palitra",
            "palette_hex": ["#1C1D22", "#5C4738", "#D6CFC4"],
            "viral_hook": f"{title.upper()} — SIZ SO'RAGAN MAXSUS OBRAZ",
            "audio_vibe": vibe,
            "items": picked_items,
        }

    async def build_custom_look_blueprint_async(
        self,
        prompt_text: str = "",
        media_bytes: bytes | None = None,
        media_mime: str = "",
        piece_count: int | None = None,
        max_prepay_50_uzs: int | None = None,
        weather: WeatherForecast | None = None,
    ) -> dict[str, Any]:
        """Admin yuborgan rasm, video yoki matn buyrug'idan AI Vision + Skaut orqali to'liq Look rejasi tuzadi."""
        if self.client is not self.ai.client:
            self.ai.client = self.client

        image_bytes: bytes | None = None
        image_mime = "image/jpeg"
        if media_bytes:
            is_video = (
                (media_mime or "").lower().startswith("video/")
                or b"ftyp" in media_bytes[:64]
                or media_bytes[:4] == b"\x1aE\xdf\xa3"
            )
            if is_video:
                image_bytes = await asyncio.to_thread(self._extract_video_frame_jpeg, media_bytes)
            else:
                image_bytes = media_bytes
                if media_mime and media_mime.lower().startswith("image/"):
                    image_mime = media_mime

        w_line = (
            f"{weather.city}: {weather.temp_c}°C ({weather.season_uz})"
            if weather
            else "Toshkent mavsumi"
        )
        budget_note = (
            f"Maqsadli 50% oldindan to'lov <= {max_prepay_50_uzs:,} so'm (butun kapsula <= {int(max_prepay_50_uzs / 1900)} CNY)."
            if max_prepay_50_uzs
            else "Hamyoнbop oltin o'rtalik: ust kiyim 40–65 CNY, shim/sviter 24–45 CNY, oyoq kiyim 32–52 CNY."
        )
        count_note = f"Aynan {piece_count} ta buyum bo'lsin." if piece_count in (2, 3, 4) else "2 dan 4 tagacha uyg'un buyum bo'lsin."

        img_extract_rule = (
            "MUHIM RASM/VIDEO TAHLIL QOIDASI (Obrazets yuborildi!):\n"
            "- Yuklangan rasm/videodagi HAR BIR kiyim, poyabzal va aksessuarni ko'rib aniq ajratib chiq "
            "(nechta qism, aniq kiyim turi, aniq rangi `color_uz`, mato qalinligi va mavsumi).\n"
            "- Har bir buyumning `cn_keyword` maydonida Xitoycha aniq rang so'zini (黑色, 深灰, 棕色, 咖色, 米色, 卡其, 藏青, 白色, 军绿) "
            "+ yagona buyum kalit so'zini (男 单件, masalan: `男羊毛大衣 黑色单件` — `2件`/`两件`/`中老年`/`爸爸` QAT'IYAN YOZMA!) kirit.\n"
            if image_bytes
            else ""
        )

        ai_prompt = f"""Sen "XAN SHOP" Bosh Dizayneri, Instagram Trend Tahlilchisi va Pinduoduo Skaut Agentisan.
Admin senga quyidagi MAXSUS BUYRUQ va/yoki namunaviy rasm/video yubordi:
- Admin buyrug'i: "{prompt_text or "Yuklangan rasm/videodagi lookka aynan o'xshash kapsula yig'"}"
- Buyumlar soni: {count_note}
- Byudjet talabi: {budget_note}
- Ob-havo: {w_line}

{img_extract_rule}VAZIFANG:
1. Agar rasm/video berilgan bo'lsa, undagi HAR BIR kiyim, poyabzal va aksessuarni aniq ajratib chiq (rangi, matosi, fasoni, yoqasi, bichimi).
2. Admin matnida so'ralgan talablarni 100% inobatga ol. HECH QACHON 'title' ichida 'Toshkent', 'Shahar', 'O'zbekiston' kabi keraksiz so'zlarni yozma — sarlavha faqat obrazdagi kiyimlar nomi va uslubidan iborat bo'lsin.
3. Har bir buyum uchun:
   - `category`: FAQAT `outerwear`, `top`, `bottom`, `shoes`, yoki `accessory`
   - `name`: FAQAT O'ZBEK TILIDA qisqa nom (masalan `Jigarrang Zamsh Kurtka`, `Qora Oversize Svitshot`, `Qora Klassik Drape Shim`, `Qora Chelsea Etik`). HECH QACHON `kargo shim` deb yozma (`Cho'ntakli Erkin Shim` deb yoz)!
   - `color_uz`: asosiy rangi (masalan `Jigarrang`, `Qora`, `Grafit`)
   - `cn_keyword`: Pinduoduo'dan aynan o'shanday rangi va fasonidagi YAGONA kiyimni topish uchun aniq xitoycha qidiruv so'zi (rang + turi, lekin `中老年`/`爸爸`/`2件` yozma)
   - `price_cny`: real Pinduoduo narxi (yuan)
   - `weight_kg`: taxminiy vazni (kg)
   - `studio_regen_prompt`: ingliz tilida 25-40 so'zlik aniq vizual tavsif (FLUX Image-to-Image studio regeneratsiyasi uchun rangi, matosi va fasoni).

FAQAT JSON QAYTAR:
{{
  "title": "O'zbekcha chiroyli Look nomi",
  "description": "Qisqa sotuv tavsifi",
  "colors": "Ranglar ro'yxati",
  "sizes": "M, L, XL, 2XL",
  "palette_name": "Palitra nomi",
  "palette_hex": ["#1C1D22", "#5C4738", "#D6CFC4"],
  "viral_hook": "O'ZBEKCHA QISQA HOOK",
  "audio_vibe": "diplomat_old_money yoki phonk_bass",
  "items": [
    {{"category": "outerwear", "name": "Jigarrang Zamsh Kurtka", "color_uz": "Jigarrang", "price_cny": 54.0, "weight_kg": 0.85, "cn_keyword": "麂皮绒夹克男", "studio_regen_prompt": "vintage dark brown suede bomber jacket with cream shearling collar lining"}}
  ]
}}"""

        parsed: dict[str, Any] | None = None
        if (self.ai.enabled or self.client) and (not os.getenv("PYTEST_CURRENT_TEST") or os.getenv("XAN_AI_CUSTOM_LOOK_IN_TESTS") == "1"):
            try:
                parsed = await self.ai.ask_json(
                    ai_prompt,
                    media_bytes=image_bytes,
                    mime_type=image_mime,
                    timeout_sec=20.0,
                )
            except Exception as exc:
                log.warning("Custom look Gemini Vision/AI xatosi: %s", exc)

        bp = (
            parsed
            if isinstance(parsed, dict) and isinstance(parsed.get("items"), list) and len(parsed["items"]) >= 2
            else self._parse_custom_prompt_fallback(prompt_text, piece_count=piece_count)
        )

        # Kargo shim taqiqi + maydonlarni normallashtirish + custom spetsifikatsiyani saqlash flagi
        bp["title"] = re.sub(r"kargo\s+shim", "Cho'ntakli Erkin Shim", str(bp.get("title") or "Maxsus AI Look"), flags=re.I)
        clean_items: list[dict[str, Any]] = []
        for idx_c, raw_it in enumerate(bp.get("items") or []):
            if not isinstance(raw_it, dict):
                continue
            it = dict(raw_it)
            it["name"] = re.sub(r"kargo\s+shim", "Cho'ntakli Erkin Shim", str(it.get("name") or f"Buyum {idx_c + 1}"), flags=re.I)
            cat_val = str(it.get("category") or "top").lower()
            if cat_val not in ("outerwear", "top", "bottom", "shoes", "accessory"):
                cat_val = "top"
            it["category"] = cat_val
            it["color_uz"] = str(it.get("color_uz") or "Qora").strip()
            it["price_cny"] = float(it.get("price_cny") or 38.0)
            it["weight_kg"] = float(it.get("weight_kg") or 0.55)
            it["cn_keyword"] = str(it.get("cn_keyword") or it["name"]).strip()
            it["_preserve_custom_spec"] = True
            clean_items.append(it)
            if len(clean_items) >= 5:
                break

        if piece_count in (2, 3, 4) and len(clean_items) > piece_count:
            clean_items = clean_items[:piece_count]
        elif piece_count in (2, 3, 4) and len(clean_items) < piece_count:
            fb_pad = self._parse_custom_prompt_fallback(prompt_text, piece_count=piece_count)["items"]
            have = {x["category"] for x in clean_items}
            for pad_it in fb_pad:
                if len(clean_items) >= piece_count:
                    break
                if pad_it["category"] not in have:
                    pad_it["_preserve_custom_spec"] = True
                    clean_items.append(pad_it)
                    have.add(pad_it["category"])

        bp["items"] = clean_items
        return bp

    async def generate_look_async(
        self,
        season: str = "avtomatik ob-havo",
        gender: str = "yoshlar / erkaklar",
        style: str = "Instagram Reels Trend (Lookzona / Stylesh)",
        trend_brief: InstagramTrendBrief | None = None,
        weather: WeatherForecast | None = None,
        ig_intel: dict[str, Any] | None = None,
        exclude_goods_ids: set[str] | None = None,
        exclude_titles_cn: set[str] | None = None,
        custom_blueprint: dict[str, Any] | None = None,
        max_prepay_50_uzs: int | None = None,
    ) -> GeneratedLook:
        """Jonli Toshkent ob-havosi + Raqobatchi narx tahlili + OmniRoute/Gemini AI + haqiqiy Pinduoduo API bilan asinxron Look yaratadi."""
        weather = weather or await fetch_tashkent_weather()
        eff_brief = trend_brief or await self.analyze_instagram_trends_async(weather)
        eff_season = weather.season_uz if season in ("", "avtomatik ob-havo") else season
        weather_line = (
            f"{weather.city}: bugun {weather.temp_c}°C, {weather.lead_time_days}dan keyin "
            f"~{weather.future_temp_c or weather.temp_c}°C ({eff_season}) — {weather.clothing_advice}"
        )

        if self.client is not self.ai.client:
            self.ai.client = self.client
        from .photo_studio import build_scout_studio_prompt, derive_insta_pose_direction

        pb_txt = str((ig_intel or {}).get("learned_playbooks_text") or "")
        recent_titles = list((ig_intel or {}).get("recent_titles") or [])
        halol = (ig_intel or {}).get("halol_ogri") or {}
        comp_avg = int(halol.get("competitor_avg_price_uzs") or 0)
        market_note = ""
        if comp_avg > 0:
            market_note = (
                f"@stylesh_shop va @tima_shop_uz da o'rtacha look narxi ~{comp_avg:,} so'm "
                f"(bizning 50% oldindan to'lov Xitoy narxi + o'tkazma foizini 100% qoplaydi, kelganda yana shuncha foyda + kargo 12 000 so'm/100gr)."
            ).replace(",", " ")

        is_custom = isinstance(custom_blueprint, dict) and isinstance(custom_blueprint.get("items"), list) and len(custom_blueprint["items"]) >= 2
        dyn_bp = halol.get("dynamic_look_blueprint") if not os.getenv("PYTEST_CURRENT_TEST") else None
        if is_custom:
            raw_data = json.loads(json.dumps(custom_blueprint, ensure_ascii=False))
            for cit in raw_data.get("items") or []:
                if isinstance(cit, dict):
                    cit["_preserve_custom_spec"] = True
        elif isinstance(dyn_bp, dict) and isinstance(dyn_bp.get("items"), list) and len(dyn_bp["items"]) >= 2:
            raw_data = json.loads(json.dumps(dyn_bp, ensure_ascii=False))
        else:
            prompt = self._build_look_prompt(
                eff_brief,
                weather_line,
                gender,
                playbooks_text=pb_txt,
                recent_titles=recent_titles,
                market_benchmark_note=market_note,
            )
            ai_data = await self.ai.ask_json(prompt, timeout_sec=16.0) if (self.ai.enabled or self.client) else None
            raw_data = self._pick_template_if_invalid(ai_data, recent_titles=recent_titles)
        if not is_custom:
            raw_data = self._enforce_seasonal_and_persona_rules(raw_data, eff_brief, weather=weather, ig_intel=ig_intel)

        # Agar jonli API ulanmagan bo'lsa ham to'xtamaymiz: 900+ lik real Pinduoduo kesh tovarlari bilan boyitamiz!
        CATEGORY_SWEET_BOUNDS: dict[str, tuple[float, float, float]] = {
            "outerwear": (24.0, 68.0, 82.0),
            "top": (16.0, 46.0, 56.0),
            "bottom": (18.0, 48.0, 58.0),
            "shoes": (22.0, 56.0, 68.0),
            "accessory": (9.0, 28.0, 36.0),
        }
        CATEGORY_SWEET_MEDIAN: dict[str, float] = {
            "outerwear": 58.0,
            "top": 36.0,
            "bottom": 36.0,
            "shoes": 45.0,
            "accessory": 20.0,
        }

        _, base_items = self._calculate_pricing(raw_data["items"])
        enriched_items: list[dict[str, Any]] = []
        downloaded_imgs: list[bytes | None] = []
        candidate_pools: list[list[Any]] = []
        used_urls: set[str] = set()
        used_gids: set[str] = {str(x).strip() for x in (exclude_goods_ids or set()) if str(x).strip()}
        used_titles_cn: set[str] = {str(t).strip()[:28] for t in (exclude_titles_cn or set()) if str(t).strip()}

        vision_state = {"alive": bool(self.ai.enabled), "fails": 0}

        async def _is_usable_pdd_garment_photo(img_bytes: bytes, target_cat: str = "") -> bool:
            """Haqiqiy Pinduoduo kiyim rasmini tekshiradi:
            - katta xitoycha reklama banner / olov stiker / infografikani rad etadi
            - 2 ta buklangan kofta, 2 ta yonma-yon shim kabi ko'plik rasmlarni rad etadi
            - buklangan yengsiz kiyim yoki odam oyog'ida qiyshayib turgan poyabzalni rad etadi"""
            if not img_bytes:
                return False
            if not vision_state["alive"]:
                return True
            try:
                qc = await self.ai.ask_json(
                    f"Inspect this Pinduoduo product photo (target category: {target_cat or 'clothing'}). "
                    "Return strict JSON: "
                    "{\"shows_target_garment\": bool, \"has_heavy_promo_text_or_collage\": bool, "
                    "\"shows_multiple_duplicate_items\": bool, \"is_folded_or_cut_badly\": bool}. "
                    "Rules:\n"
                    "- shows_target_garment=true ONLY if ONE clear target garment or ONE pair of shoes is clearly shown.\n"
                    "- shows_multiple_duplicate_items=true if the image shows 2+ stacked sweaters, 2+ side-by-side trousers, or multi-pack/color options together.\n"
                    "- is_folded_or_cut_badly=true if a top/jacket is neatly folded hiding its sleeves, OR shoes are photographed sideways/tilted while worn on human ankles/legs/trousers, OR half the garment is cut off.\n"
                    "- has_heavy_promo_text_or_collage=true if it has big Chinese yellow banners, bright red/orange fire badges overlapping the product, size tables, or multi-grid collages.",
                    media_bytes=img_bytes,
                    mime_type="image/jpeg",
                    timeout_sec=5.0,
                )
                if isinstance(qc, dict) and qc:
                    vision_state["fails"] = 0
                    return bool(
                        qc.get("shows_target_garment")
                        and not qc.get("has_heavy_promo_text_or_collage")
                        and not qc.get("shows_multiple_duplicate_items")
                        and not qc.get("is_folded_or_cut_badly")
                    )
                vision_state["fails"] += 1
                if vision_state["fails"] >= 2:
                    vision_state["alive"] = False
            except Exception:
                vision_state["fails"] += 1
                if vision_state["fails"] >= 2:
                    vision_state["alive"] = False
            return True

        async def _fetch_cand_image(cand: Any, target_cat: str, allow_fallback: bool = False) -> bytes | None:
            gal = list(getattr(cand, "gallery_images", None) or [])
            img_u = getattr(cand, "image_url", "")
            if img_u and img_u not in gal:
                gal.append(img_u)
            probe_urls = gal[1:4] + gal[:1]
            fb_b = None
            for g_url in probe_urls[:4]:
                if not g_url or g_url in used_urls:
                    continue
                img_b = await self.pdd.fetch_image_bytes(g_url)
                if not img_b:
                    continue
                if fb_b is None:
                    fb_b = img_b
                if await _is_usable_pdd_garment_photo(img_b, target_cat=target_cat):
                    used_urls.add(g_url)
                    return img_b
            return fb_b if allow_fallback else None

        async def _apply_picked_product(base_item: dict[str, Any], prod: Any, img_b: bytes | None, cat_name: str) -> dict[str, Any]:
            if getattr(prod, "goods_id", ""):
                used_gids.add(str(prod.goods_id).strip())
            if getattr(prod, "title_cn", ""):
                used_titles_cn.add(str(prod.title_cn).strip()[:28])
            updated = dict(base_item)
            updated["price_cny"] = float(prod.price_cny)
            updated["cny"] = float(prod.price_cny)
            updated["pdd_goods_id"] = prod.goods_id or updated.get("pdd_goods_id", "")
            updated["pdd_id"] = updated["pdd_goods_id"]
            updated["goods_id"] = updated["pdd_goods_id"]
            updated["title_cn"] = prod.title_cn or updated.get("cn_keyword", "")
            updated["sales_tip"] = prod.sales_tip
            updated["_from_live_pdd"] = True
            if prod.product_url:
                updated["url"] = prod.product_url
            if prod.image_url:
                updated["image_url"] = prod.image_url
            chart_info: dict[str, Any] = {}
            if not prod.size_chart and prod.detail_images and vision_state["alive"]:
                chart_info = await self.pdd.extract_store_size_chart(
                    prod.detail_images,
                    prod.title_cn,
                    ai=self.ai,
                )
            store_colors = list(dict.fromkeys([*(prod.store_colors or []), *(chart_info.get("store_colors") or [])]))
            store_sizes = list(chart_info.get("store_sizes") or prod.store_sizes or [])
            size_chart = list(chart_info.get("size_chart") or prod.size_chart or [])
            fit_parts = [p for p in (prod.fit_note, chart_info.get("fit_note")) if p]
            updated["store_colors"] = store_colors
            updated["store_sizes"] = store_sizes
            updated["size_chart"] = size_chart
            updated["fit_note"] = " | ".join(dict.fromkeys(fit_parts))
            insta_pose = derive_insta_pose_direction(ig_intel, category=cat_name)
            updated["studio_prompt"] = build_scout_studio_prompt(updated, insta_pose_direction=insta_pose)
            return updated

        def _load_bucket_cache_sweet_candidates(target_cat: str, min_cny: float, max_cny: float) -> list[Any]:
            cache_path = "data/pdd_live_cache.json"
            if not os.path.exists(cache_path):
                return []
            try:
                raw_cache = json.load(open(cache_path, encoding="utf-8")) or {}
            except Exception:
                return []
            out: list[Any] = []
            seen_l: set[str] = set()
            want_bucket = target_cat if target_cat in ("outerwear", "top", "bottom", "shoes", "accessory") else "top"
            for rows in raw_cache.values():
                if not isinstance(rows, list):
                    continue
                for r in rows:
                    if not isinstance(r, dict) or not r.get("goods_id"):
                        continue
                    gid_s = str(r["goods_id"]).strip()
                    t_cn = str(r.get("title_cn") or "")
                    if gid_s in used_gids or gid_s in seen_l or t_cn[:28] in used_titles_cn:
                        continue
                    if "pddpic.com" not in str(r.get("image_url") or ""):
                        continue
                    if self.pdd._category_bucket(t_cn) != want_bucket:
                        continue
                    p_val = float(r.get("price_cny") or 0)
                    if min_cny <= p_val <= max_cny:
                        seen_l.add(gid_s)
                        out.append(self.pdd._row_to_product(r))
            out.sort(key=lambda pr: (-self.pdd._score_value_quality(pr, [], True), pr.price_cny))
            return out

        _CN_COLOR_TOKENS = (
            ("qora", ("黑", "纯黑", "炭黑")),
            ("to'q ko'k", ("藏青", "深蓝", "藏蓝")),
            ("ko'k", ("蓝", "藏青", "牛仔蓝")),
            ("jigarrang", ("棕", "咖", "驼", "焦糖", "摩卡")),
            ("qahva", ("咖", "摩卡", "棕")),
            ("grafit", ("深灰", "炭灰", "灰")),
            ("kulrang", ("灰", "深灰", "浅灰")),
            ("och bej", ("米", "杏", "卡其", "浅驼")),
            ("bej", ("米", "卡其", "杏")),
            ("krem", ("米白", "奶白", "米")),
            ("oq", ("白", "纯白", "米白")),
            ("zaytun", ("绿", "军绿", "墨绿", "橄榄")),
            ("yashil", ("绿", "军绿", "墨绿")),
        )

        def _candidate_rank_key(cand: Any, kw_str: str, target_col_uz: str, want_sub: str) -> tuple[float, float]:
            t_cn = str(getattr(cand, "title_cn", "") or "")
            sc = self.pdd._score_value_quality(cand, [w for w in kw_str.split() if w], True)
            if want_sub and self.pdd._subtype_key(t_cn) == want_sub:
                sc += 6.5
            col_low = (target_col_uz or "").lower()
            for uz_k, cn_chars in _CN_COLOR_TOKENS:
                if uz_k in col_low:
                    st_cols_low = " ".join(str(x).lower() for x in (getattr(cand, "store_colors", None) or []))
                    if any(ch in t_cn for ch in cn_chars) or uz_k in st_cols_low:
                        sc += 4.5
                    break
            return (-sc, float(getattr(cand, "price_cny", 0) or 0))

        for item_idx, item in enumerate(base_items):
            kw = item.get("cn_keyword") or item.get("name", "")
            cat = str(item.get("category") or "top").lower()
            target_sub = self.pdd._subtype_key(str(kw))
            target_col_uz = str(item.get("color_uz") or item.get("name") or "")
            min_p, sweet_max, hard_max = CATEGORY_SWEET_BOUNDS.get(cat, (18.0, 48.0, 62.0))

            live_matches = await self.pdd.search_live(kw, page_size=14, exclude_goods_ids=used_gids)
            picked_prod = None
            picked_bytes = None
            fallback_prod = None
            fallback_bytes = None
            pool: list[Any] = []

            if live_matches:
                fresh_pool = [
                    m for m in live_matches
                    if m.goods_id and m.goods_id not in used_gids and str(m.title_cn or "").strip()[:28] not in used_titles_cn
                ]
                base_pool = fresh_pool if fresh_pool else live_matches
                sweet_pool = [m for m in base_pool if min_p <= float(m.price_cny or 0) <= sweet_max]
                hard_pool = [m for m in base_pool if min_p <= float(m.price_cny or 0) <= hard_max]
                if not hard_pool:
                    bucket_sweet = _load_bucket_cache_sweet_candidates(cat, min_p, sweet_max)
                    if bucket_sweet:
                        hard_pool = bucket_sweet
                pool = sweet_pool if sweet_pool else (hard_pool if hard_pool else base_pool)
                pool.sort(key=lambda pr: _candidate_rank_key(pr, str(kw), target_col_uz, target_sub))
                picked_prod = pool[0]

                for cand in pool[:4]:
                    img_b = await _fetch_cand_image(cand, cat, allow_fallback=False)
                    if not img_b:
                        continue
                    picked_prod = cand
                    picked_bytes = img_b
                    break

                if picked_bytes is None:
                    for cand in pool[:2]:
                        img_fb = await _fetch_cand_image(cand, cat, allow_fallback=True)
                        if img_fb:
                            picked_prod = cand
                            picked_bytes = img_fb
                            break

            if not pool or picked_prod is None:
                # Agar jonli API tovar topolmasa, 900+ lik haqiqiy Pinduoduo tovarlar keshidan to'ldiramiz!
                pool = _load_bucket_cache_sweet_candidates(cat, min_p, hard_max)
                if not pool:
                    pool = _load_bucket_cache_sweet_candidates(cat, 12.0, 95.0)
                if pool:
                    pool.sort(key=lambda pr: _candidate_rank_key(pr, str(kw), target_col_uz, target_sub))
                    picked_prod = pool[0]
                    for cand in pool[:3]:
                        img_b = await _fetch_cand_image(cand, cat, allow_fallback=True)
                        if img_b:
                            picked_prod = cand
                            picked_bytes = img_b
                            break

            candidate_pools.append(pool)
            if picked_prod is not None:
                updated = await _apply_picked_product(item, picked_prod, picked_bytes, cat)
                downloaded_imgs.append(picked_bytes)
                enriched_items.append(updated)
            else:
                insta_pose = derive_insta_pose_direction(ig_intel, category=cat)
                item_with_prompt = dict(item)
                item_with_prompt["price_cny"] = min(float(item_with_prompt.get("price_cny") or hard_max), sweet_max)
                item_with_prompt["cny"] = item_with_prompt["price_cny"]
                item_with_prompt["studio_prompt"] = build_scout_studio_prompt(item_with_prompt, insta_pose_direction=insta_pose)
                downloaded_imgs.append(None)
                enriched_items.append(item_with_prompt)

        # Aqlli Insoncha Kapsula Byudjeti Muvofiqlashtirgichi (Capsule Budget Rebalancer)
        default_cap = 115.0 if len(enriched_items) <= 2 else (148.0 if len(enriched_items) == 3 else 172.0)
        max_capsule_cny = float(halol.get("max_capsule_cny") or default_cap)
        if max_prepay_50_uzs and int(max_prepay_50_uzs) > 0:
            target_budget_cny = max(65.0, float(max_prepay_50_uzs) / (max(self.rates.cny_uzs, 1750.0) * 1.055))
            max_capsule_cny = min(max_capsule_cny, target_budget_cny)
        drop_indices: set[int] = set()
        ranked_indices = sorted(range(len(enriched_items)), key=lambda idx: -float(enriched_items[idx].get("price_cny") or 0))
        for r_idx in ranked_indices:
            cur_it = enriched_items[r_idx]
            cur_cat = str(cur_it.get("category") or "top").lower()
            cur_price = float(cur_it.get("price_cny") or 0)
            min_p, sweet_max, hard_max = CATEGORY_SWEET_BOUNDS.get(cur_cat, (18.0, 48.0, 62.0))
            live_total = sum(float(it.get("price_cny") or 0) for i_l, it in enumerate(enriched_items) if i_l not in drop_indices)
            is_overpriced_acc = (cur_cat == "accessory" and cur_price > hard_max)
            if live_total <= max_capsule_cny and not is_overpriced_acc:
                continue

            # 1) Avval shu tovarning o'z nomzodlar poolidan yoki bucket keshdan arzonroq (<= sweet_max) va sifatli variant qidiramiz
            max_alt_price = sweet_max if cur_price > sweet_max else max(min_p, cur_price - 5.0)
            alt_cands = [
                c for c in (candidate_pools[r_idx] if r_idx < len(candidate_pools) else [])
                if min_p <= float(c.price_cny or 0) <= max_alt_price
                and str(getattr(c, "goods_id", "")) not in used_gids
            ]
            if not alt_cands:
                alt_cands = _load_bucket_cache_sweet_candidates(cur_cat, min_p, max_alt_price)
            swapped = False
            for cand in alt_cands[:3]:
                img_b = await _fetch_cand_image(cand, cur_cat)
                if img_b:
                    enriched_items[r_idx] = await _apply_picked_product(base_items[r_idx], cand, img_b, cur_cat)
                    downloaded_imgs[r_idx] = img_b
                    swapped = True
                    break
            if not swapped:
                active_count = len(enriched_items) - len(drop_indices)
                if cur_cat == "accessory" and cur_price > hard_max and active_count >= 3:
                    # Aqlli sotuvchi: qimmat ixtiyoriy aksessuarni (¥70 kamar / ¥139 sharf) olib tashlab, obraz narxini saqlab qoladi!
                    drop_indices.add(r_idx)
                elif active_count >= 5 and cur_price > sweet_max:
                    drop_indices.add(r_idx)
                elif not cur_it.get("_from_live_pdd"):
                    med = CATEGORY_SWEET_MEDIAN.get(cur_cat, 36.0)
                    if cur_price > med:
                        cur_it["price_cny"] = med
                        cur_it["cny"] = med

        if drop_indices:
            enriched_items = [it for i_l, it in enumerate(enriched_items) if i_l not in drop_indices]
            downloaded_imgs = [im for i_l, im in enumerate(downloaded_imgs) if i_l not in drop_indices]

        # Tozalash: vaqtinchalik ichki flagni saqlamaslik
        for it in enriched_items:
            it.pop("_from_live_pdd", None)

        res_look = self._build_generated_look(
            raw_data,
            eff_brief,
            weather_line,
            raw_items_override=enriched_items,
            downloaded_images=downloaded_imgs,
        )
        for it in res_look.raw_items:
            it.pop("_preserve_custom_spec", None)
        return res_look
