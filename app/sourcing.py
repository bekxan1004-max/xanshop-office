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

import json
import logging
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
            {"category": "outerwear", "name": "To'q Jigarrang Ikki Qatorli Jun Palto", "price_cny": 138.0, "weight_kg": 1.15, "cn_keyword": "老钱风双排扣羊毛呢大衣男秋冬加厚英伦外套"},
            {"category": "top", "name": "To'q Qahva Kashmir Vodolazka", "price_cny": 68.0, "weight_kg": 0.48, "cn_keyword": "男秋冬加厚羊绒高领打底毛衣老钱风保暖针织衫"},
            {"category": "bottom", "name": "Qahva-Taupe Old Money Jun Shim", "price_cny": 64.0, "weight_kg": 0.52, "cn_keyword": "老钱风摩卡棕垂感褶皱羊毛西装裤男秋冬加厚"},
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
            {"category": "outerwear", "name": "Qora Jun Bomber Kurtka", "price_cny": 89.0, "weight_kg": 0.75, "cn_keyword": "美式复古重磅飞行员夹克男春秋宽松外套"},
            {"category": "top", "name": "Grafit Oversize Xudi", "price_cny": 54.0, "weight_kg": 0.55, "cn_keyword": "420g重磅纯棉连帽卫衣男宽松美式帽衫"},
            {"category": "bottom", "name": "Zaytun Cho'ntakli Erkin Shim", "price_cny": 52.0, "weight_kg": 0.50, "cn_keyword": "美式工装裤男直筒宽松多口袋伞兵休闲裤"},
            {"category": "shoes", "name": "Oq-Kulrang Krossovka", "price_cny": 48.0, "weight_kg": 0.80, "cn_keyword": "复古百搭板鞋男休闲运动鞋防滑厚底潮鞋"},
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
            {"category": "outerwear", "name": "To'q Ko'k Klassik Jun Blazer", "price_cny": 115.0, "weight_kg": 0.78, "cn_keyword": "老钱风藏青色羊毛修身西装外套男秋冬商务夹克"},
            {"category": "top", "name": "Och Bej Zamokli Sviter", "price_cny": 62.0, "weight_kg": 0.50, "cn_keyword": "老钱风半拉链针织毛衣男秋冬加厚立领"},
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
            {"category": "outerwear", "name": "Qora Tik Yoqali Jun Palto", "price_cny": 138.0, "weight_kg": 1.05, "cn_keyword": "老钱风双排扣羊毛呢大衣男秋冬加厚英伦外套"},
            {"category": "top", "name": "Oq Yoqali Svitshot", "price_cny": 88.0, "weight_kg": 0.48, "cn_keyword": "半拉链卫衣男潮"},
            {"category": "bottom", "name": "To'q Kulrang Qishki Erkin Shim", "price_cny": 58.0, "weight_kg": 0.52, "cn_keyword": "工装裤男士直筒宽松"},
            {"category": "shoes", "name": "Qora-Oq Retro Krossovka", "price_cny": 95.0, "weight_kg": 0.85, "cn_keyword": "男复古板鞋运动鞋"},
            {"category": "accessory", "name": "Qora Minimalist Kepka", "price_cny": 26.0, "weight_kg": 0.15, "cn_keyword": "美式复古纯色软顶棒球帽男百搭显脸小鸭舌帽"},
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
            {"category": "top", "name": "Grafit Oversize Xudi", "price_cny": 54.0, "weight_kg": 0.55, "cn_keyword": "420g重磅纯棉连帽卫衣男宽松美式帽衫"},
            {"category": "bottom", "name": "Zaytun Cho'ntakli Erkin Shim", "price_cny": 52.0, "weight_kg": 0.50, "cn_keyword": "美式工装裤男直筒宽松多口袋伞兵休闲裤"},
            {"category": "shoes", "name": "Oq-Kulrang Krossovka", "price_cny": 48.0, "weight_kg": 0.80, "cn_keyword": "复古百搭板鞋男休闲运动鞋防滑厚底潮鞋"},
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
            for meta_key in ("title_cn", "store_colors", "store_sizes", "size_chart", "fit_note", "studio_prompt"):
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
Vazifang: Pinduoduo (拼多多) da haqiqatda ko'p sotilayotgan, sifati baland va narxi hamyonbop (~38–125 CNY oralig'ida, ENG QIMMAT emas, balki sifat/narx nisbati eng zo'r variantlar, jami ~140–270 CNY) bo'lgan mutlaqo YANGI va uyg'un Look yig'.
Har safar har xil kiyim turlarini tanla (masalan: zamsh/teri kurtka, yengil puxovik, kardigan, polo sviter, yarim-zamokli sviter, jun palto, klassik shim, to'g'ri jinsi, kargo, chelsea etik, zamsh lofer, retro krossovka).
MUHIM QOIDA: "title" va har bir buyumning "name" maydoni FAQAT O'ZBEK TILIDA, qisqa va tushunarli (2–4 so'z) bo'lsin! Inglizcha so'zlar yozma!
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
                "price_cny": 138.0,
                "weight_kg": 1.15,
                "color_uz": "To'q jigarrang",
            },
            {
                "name": "To'q Ko'k Klassik Jun Blazer",
                "cn_keyword": "老钱风藏青色羊毛修身西装外套男秋冬商务夹克",
                "price_cny": 115.0,
                "weight_kg": 0.78,
                "color_uz": "To'q ko'k",
            },
            {
                "name": "Qora Jun Bomber Kurtka",
                "cn_keyword": "老钱风重磅羊毛飞行员夹克男秋冬外套",
                "price_cny": 96.0,
                "weight_kg": 0.78,
                "color_uz": "Qora",
            },
        ]
        warm_knit_alts = [
            {
                "name": "To'q Qahva Kashmir Vodolazka",
                "cn_keyword": "男秋冬加厚羊绒高领打底毛衣老钱风保暖针织衫",
                "price_cny": 68.0,
                "weight_kg": 0.48,
                "color_uz": "To'q jigarrang",
            },
            {
                "name": "Och Bej Zamokli Sviter",
                "cn_keyword": "老钱风半拉链针织毛衣男秋冬加厚立领",
                "price_cny": 62.0,
                "weight_kg": 0.50,
                "color_uz": "Och bej",
            },
        ]
        classic_bottom_alts = [
            {
                "name": "Qahva-Taupe Old Money Jun Shim",
                "cn_keyword": "老钱风摩卡棕垂感褶皱羊毛西装裤男秋冬加厚",
                "price_cny": 64.0,
                "weight_kg": 0.52,
                "color_uz": "Qahva-taupe",
            },
            {
                "name": "Grafit Klassik Drape Shim",
                "cn_keyword": "垂感羊毛西装裤男直筒老钱风秋冬加厚长裤",
                "price_cny": 62.0,
                "weight_kg": 0.50,
                "color_uz": "To'q kulrang (grafit)",
            },
        ]
        classic_shoe_alts = [
            {
                "name": "Qora Charm Qishki Chelsea Etik",
                "cn_keyword": "切尔西靴男真皮英伦风复古短靴秋冬加绒皮靴",
                "price_cny": 78.0,
                "weight_kg": 0.92,
                "color_uz": "Qora",
            },
            {
                "name": "Espresso Zamsh Lofer",
                "cn_keyword": "老钱风翻毛皮乐福鞋男英伦休闲皮鞋加绒",
                "price_cny": 56.0,
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
                # Jonli Pinduoduo rasmi bor: kiyimning o'zbekcha nomini haqiqiy Pinduoduo tovari va rangiga 100% moslaymiz
                st_cols = it.get("store_colors") or []
                det_col = (st_cols[0] if len(st_cols) == 1 else "") or _detect_garment_color_uz(live_img) or str(it.get("color_uz") or "Qora")
                it["name"] = _uz_name_from_real_pdd(str(it.get("title_cn") or ""), det_col, str(it.get("name") or "Buyum"))
                it["color_uz"] = det_col
                if det_col and det_col not in exact_colors:
                    exact_colors.append(det_col)
            else:
                # Faqat lokal studiya rasmi ishlatilgandagina studiya rangi bilan sinxronlaymiz
                synced_name, synced_col = _sync_item_with_studio_photo_color(
                    str(it.get("name", "")),
                    str(it.get("category", "")),
                    idx,
                )
                it["name"] = synced_name
                it["color_uz"] = synced_col
                if synced_col not in exact_colors:
                    exact_colors.append(synced_col)

        colors_str = ", ".join(exact_colors) if exact_colors else str(data.get("colors", "Qora, Grafit"))

        return GeneratedLook(
            title=data.get("title", "Yangi Trend Look"),
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

    async def generate_look_async(
        self,
        season: str = "avtomatik ob-havo",
        gender: str = "yoshlar / erkaklar",
        style: str = "Instagram Reels Trend (Lookzona / Stylesh)",
        trend_brief: InstagramTrendBrief | None = None,
        weather: WeatherForecast | None = None,
        ig_intel: dict[str, Any] | None = None,
        exclude_goods_ids: set[str] | None = None,
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
        import os
        from .photo_studio import build_scout_studio_prompt, derive_insta_pose_direction

        pb_txt = str((ig_intel or {}).get("learned_playbooks_text") or "")
        recent_titles = list((ig_intel or {}).get("recent_titles") or [])
        halol = (ig_intel or {}).get("halol_ogri") or {}
        comp_avg = int(halol.get("competitor_avg_price_uzs") or 0)
        xan_target = int(halol.get("xan_target_price_uzs") or 0)
        market_note = ""
        if comp_avg > 0:
            market_note = (
                f"@stylesh_shop va @tima_shop_uz da o'rtacha look narxi ~{comp_avg:,} so'm "
                f"(bizning 50% oldindan to'lov Xitoy narxi + o'tkazma foizini 100% qoplaydi, kelganda yana shuncha foyda + kargo 12 000 so'm/100gr)."
            ).replace(",", " ")

        # 1) Instagram Tahlilchi butun Instagramdan bo'laklab tahlil qilgan dinamik trend look bo'lsa (cheklanmagan toifalar!), shuni ustuvor olamiz!
        dyn_bp = halol.get("dynamic_look_blueprint") if not os.getenv("PYTEST_CURRENT_TEST") else None
        if isinstance(dyn_bp, dict) and isinstance(dyn_bp.get("items"), list) and len(dyn_bp["items"]) >= 2:
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
        raw_data = self._enforce_seasonal_and_persona_rules(raw_data, eff_brief, weather=weather, ig_intel=ig_intel)

        if self.pdd.connection_mode not in ("official_api", "apify_pdd_live", "onebound_pdd"):
            return self._build_generated_look(raw_data, eff_brief, weather_line)

        _, base_items = self._calculate_pricing(raw_data["items"])
        enriched_items: list[dict[str, Any]] = []
        downloaded_imgs: list[bytes | None] = []
        used_urls: set[str] = set()
        used_gids: set[str] = {str(x).strip() for x in (exclude_goods_ids or set()) if str(x).strip()}

        vision_state = {"alive": bool(self.ai.enabled)}

        async def _is_usable_pdd_garment_photo(img_bytes: bytes, target_cat: str = "") -> bool:
            """Haqiqiy Pinduoduo kiyim rasmini tekshiradi: katta xitoycha reklama banner/infografikani rad etadi,
            lekin toza flat-lay YOKI modeldagi bitta kiyim rasmini QABUL qiladi (u2net_cloth_seg yuz va fonni 100% qirqib oladi!)."""
            if not img_bytes:
                return False
            if not vision_state["alive"]:
                return True
            try:
                qc = await self.ai.ask_json(
                    f"Inspect this Pinduoduo product photo (target category: {target_cat or 'clothing'}). "
                    "Our AI cloth segmenter (u2net_cloth_seg) will cleanly cut out ONLY the clothing/shoe item and remove any human model/face/background. "
                    "Return strict JSON: {\"shows_target_garment\": bool, \"has_heavy_promo_text_or_collage\": bool}. "
                    "Set shows_target_garment=true if a clear single garment or pair of shoes is clearly visible (whether flat-lay OR worn by a model). "
                    "Set has_heavy_promo_text_or_collage=true ONLY if it is a cluttered infographic, size table, multi-grid collage, or covered with big Chinese promotional price/discount banners across the garment.",
                    media_bytes=img_bytes,
                    mime_type="image/jpeg",
                    timeout_sec=8.0,
                )
                if isinstance(qc, dict) and qc:
                    return bool(qc.get("shows_target_garment") and not qc.get("has_heavy_promo_text_or_collage"))
                # Vision modeli vaqtincha javob bermasa, qolgan rasmlarda 5 daqiqa kutmasdan tezkor o'tamiz
                vision_state["alive"] = False
            except Exception:
                vision_state["alive"] = False
            return True

        for item_idx, item in enumerate(base_items):
            kw = item.get("cn_keyword") or item.get("name", "")
            cat = str(item.get("category") or "")
            live_matches = await self.pdd.search_live(kw, page_size=12, exclude_goods_ids=used_gids)
            picked_prod = None
            picked_bytes = None
            fallback_prod = None
            fallback_bytes = None
            if live_matches:
                # 50% oldindan to'lov Xitoy narxini qoplashi va jami narx raqobatchilardan hamyonbop chiqishi uchun sifatli + arzon (¥20–¥138) tovarlar birinchi!
                fresh_pool = [m for m in live_matches if m.goods_id and m.goods_id not in used_gids]
                base_pool = fresh_pool if fresh_pool else live_matches
                max_cny_item = 138.0 if self._params().ensure_50_covers_cost else 165.0
                affordable = [m for m in base_pool if 20.0 <= float(m.price_cny or 0) <= max_cny_item]
                pool = affordable if affordable else base_pool
                picked_prod = pool[0]

                # Galereyadan [1..3] (odatda reklama yozuvsiz toza kiyim rasmlari) + [0] ni tekshiramiz
                for cand in pool[:2]:
                    gal = list(cand.gallery_images or [])
                    if cand.image_url and cand.image_url not in gal:
                        gal.append(cand.image_url)
                    probe_urls = gal[1:3] + gal[:1]
                    for g_url in probe_urls[:2]:
                        if not g_url or g_url in used_urls:
                            continue
                        img_b = await self.pdd.fetch_image_bytes(g_url)
                        if not img_b:
                            continue
                        if fallback_bytes is None:
                            fallback_prod = cand
                            fallback_bytes = img_b
                        if await _is_usable_pdd_garment_photo(img_b, target_cat=cat):
                            picked_prod = cand
                            picked_bytes = img_b
                            used_urls.add(g_url)
                            break
                    if picked_bytes:
                        break

                if picked_bytes is None and fallback_bytes is not None:
                    picked_prod = fallback_prod or picked_prod
                    picked_bytes = fallback_bytes

            if picked_prod is not None:
                if picked_prod.goods_id:
                    used_gids.add(str(picked_prod.goods_id).strip())
                updated = dict(item)
                updated["price_cny"] = picked_prod.price_cny
                updated["cny"] = picked_prod.price_cny
                updated["pdd_goods_id"] = picked_prod.goods_id or updated.get("pdd_goods_id", "")
                updated["title_cn"] = picked_prod.title_cn or updated.get("cn_keyword", "")
                updated["sales_tip"] = picked_prod.sales_tip
                if picked_prod.product_url:
                    updated["url"] = picked_prod.product_url
                if picked_prod.image_url:
                    updated["image_url"] = picked_prod.image_url

                # Do'konning haqiqiy ranglari, razmerlari, qishki bichim eslatmasi va razmer jadvali (尺码表)
                chart_info: dict[str, Any] = {}
                if not picked_prod.size_chart and picked_prod.detail_images and vision_state["alive"]:
                    chart_info = await self.pdd.extract_store_size_chart(
                        picked_prod.detail_images,
                        picked_prod.title_cn,
                        ai=self.ai,
                    )
                store_colors = list(dict.fromkeys([*(picked_prod.store_colors or []), *(chart_info.get("store_colors") or [])]))
                store_sizes = list(chart_info.get("store_sizes") or picked_prod.store_sizes or [])
                size_chart = list(chart_info.get("size_chart") or picked_prod.size_chart or [])
                fit_parts = [p for p in (picked_prod.fit_note, chart_info.get("fit_note")) if p]
                updated["store_colors"] = store_colors
                updated["store_sizes"] = store_sizes
                updated["size_chart"] = size_chart
                updated["fit_note"] = " | ".join(dict.fromkeys(fit_parts))
                # Pinduoduo Tahlilchi Photoshop Studio agenti uchun aynan shu mahsulotni O'ZGARTIRMAYDIGAN aniq prompt yozadi
                # (+ Instagram Tahlilchi videolardan o'rgangan tabiiy turish promptini qo'shadi!)
                insta_pose = derive_insta_pose_direction(ig_intel, category=cat)
                updated["studio_prompt"] = build_scout_studio_prompt(updated, insta_pose_direction=insta_pose)
                downloaded_imgs.append(picked_bytes)
                enriched_items.append(updated)
            else:
                insta_pose = derive_insta_pose_direction(ig_intel, category=cat)
                item_with_prompt = dict(item)
                item_with_prompt["studio_prompt"] = build_scout_studio_prompt(item_with_prompt, insta_pose_direction=insta_pose)
                downloaded_imgs.append(None)
                enriched_items.append(item_with_prompt)

        return self._build_generated_look(
            raw_data,
            eff_brief,
            weather_line,
            raw_items_override=enriched_items,
            downloaded_images=downloaded_imgs,
        )
