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
        "title": "Diplomatiya va Yuridika Old Money Kapsulasi",
        "description": "Och bej zamokli sviter + to'q kulrang (grafit) klassik shim + to'q jigarrang zamsh lofer.",
        "piece_count": 3,
        "palette_name": "Old Money Espresso & Latte",
        "palette_hex": ["#2B211B", "#7A6352", "#C8B8A6", "#F5F0EB"],
        "audio_vibe": "diplomat_old_money",
        "viral_hook": "DIPLOMATIYA VA YURIDIKADA O'QIYDIGANLAR UCHUN",
        "colors": "Och bej, To'q kulrang (grafit), To'q jigarrang",
        "sizes": "M, L, XL, 2XL",
        "items": [
            {"category": "top", "name": "Bej Zamokli Sviter", "price_cny": 48.0, "weight_kg": 0.45, "cn_keyword": "美式复古半拉链立领卫衣男宽松华夫格上衣"},
            {"category": "bottom", "name": "Grafit Klassik Shim", "price_cny": 52.0, "weight_kg": 0.45, "cn_keyword": "垂感西装裤男直筒宽松老钱风休闲长裤"},
            {"category": "shoes", "name": "Jigarrang Zamsh Lofer", "price_cny": 54.0, "weight_kg": 0.68, "cn_keyword": "老钱风翻毛皮乐福鞋男一脚蹬英伦休闲皮鞋"},
        ],
    },
    {
        "title": "Oversize Streetwear To'liq Seti (4-in-1)",
        "description": "Qora bomber kurtka + grafit oversize xudi + zaytun-xaki kargo shim + oq-kulrang retro krossovka.",
        "piece_count": 4,
        "palette_name": "Monochrome Graphite & Ice",
        "palette_hex": ["#18191C", "#34373E", "#8E929B", "#ECEEEF"],
        "audio_vibe": "phonk_bass",
        "viral_hook": "OVERSIZE KIYISHNI YOQTIRADIGAN YIGITLAR UCHUN",
        "colors": "Qora, To'q kulrang (grafit), To'q zaytun, Oq-kulrang",
        "sizes": "M, L, XL, 2XL",
        "items": [
            {"category": "outerwear", "name": "Qora Bomber Kurtka", "price_cny": 58.0, "weight_kg": 0.65, "cn_keyword": "美式复古重磅飞行员夹克男春秋宽松外套"},
            {"category": "top", "name": "Grafit Oversize Xudi", "price_cny": 42.0, "weight_kg": 0.50, "cn_keyword": "420g重磅纯棉连帽卫衣男宽松美式帽衫"},
            {"category": "bottom", "name": "Zaytun Kargo Shim", "price_cny": 40.0, "weight_kg": 0.45, "cn_keyword": "美式工装裤男直筒宽松多口袋伞兵休闲裤"},
            {"category": "shoes", "name": "Oq-Kulrang Krossovka", "price_cny": 38.0, "weight_kg": 0.70, "cn_keyword": "复古百搭板鞋男休闲运动鞋防滑厚底潮鞋"},
        ],
    },
    {
        "title": "175–188 sm Cleanfit Klassik Obraz",
        "description": "Qora bomber kurtka + och bej zamokli sviter + grafit klassik shim + oq-kulrang retro krossovka.",
        "piece_count": 4,
        "palette_name": "Cleanfit Obsidian & Sand",
        "palette_hex": ["#15181E", "#3A3D45", "#C7B8A5", "#F4F3EF"],
        "audio_vibe": "luxury_chill",
        "viral_hook": "175–188 SM BO'YLI YIGITLAR UCHUN TAYYOR OBRAZ",
        "colors": "Qora, Och bej, To'q kulrang (grafit), Oq-kulrang",
        "sizes": "M, L, XL, 2XL",
        "items": [
            {"category": "outerwear", "name": "Qora Bomber Kurtka", "price_cny": 56.0, "weight_kg": 0.62, "cn_keyword": "Cleanfit双拉链针织开衫男立领夹克外套"},
            {"category": "top", "name": "Bej Zamokli Sviter", "price_cny": 44.0, "weight_kg": 0.44, "cn_keyword": "美式复古半拉链立领卫衣男宽松华夫格上衣"},
            {"category": "bottom", "name": "Grafit Klassik Shim", "price_cny": 46.0, "weight_kg": 0.45, "cn_keyword": "垂感西装裤男直筒宽松老钱风休闲长裤"},
            {"category": "shoes", "name": "Oq-Kulrang Krossovka", "price_cny": 38.0, "weight_kg": 0.70, "cn_keyword": "复古百搭板鞋男休闲运动鞋防滑厚底潮鞋"},
        ],
    },
    {
        "title": "IT va Biznes Smart-Casual Kapsula",
        "description": "Qora bomber kurtka + grafit klassik shim + to'q jigarrang zamsh lofer + qora minimalist kepka.",
        "piece_count": 4,
        "palette_name": "Smart Slate & Espresso",
        "palette_hex": ["#1C1E24", "#4A4E58", "#D6CBBF"],
        "audio_vibe": "lofi_editorial",
        "viral_hook": "IT, BIZNES VA OFISDA ISHLAYDIGANLAR UCHUN",
        "colors": "Qora, To'q kulrang (grafit), To'q jigarrang",
        "sizes": "M, L, XL, 2XL",
        "items": [
            {"category": "outerwear", "name": "Qora Bomber Kurtka", "price_cny": 58.0, "weight_kg": 0.62, "cn_keyword": "美式复古重磅飞行员夹克男春秋宽松外套"},
            {"category": "bottom", "name": "Grafit Klassik Shim", "price_cny": 48.0, "weight_kg": 0.45, "cn_keyword": "垂感西装裤男直筒宽松老钱风休闲长裤"},
            {"category": "shoes", "name": "Jigarrang Zamsh Lofer", "price_cny": 49.0, "weight_kg": 0.68, "cn_keyword": "老钱风翻毛皮乐福鞋男一脚蹬英伦休闲皮鞋"},
            {"category": "accessory", "name": "Qora Minimalist Kepka", "price_cny": 18.0, "weight_kg": 0.12, "cn_keyword": "韩版百搭软顶棒球帽男女显脸小遮阳鸭舌帽"},
        ],
    },
    {
        "title": "Universitet va Kundalik Oversize Set (3-in-1)",
        "description": "Grafit oversize xudi + zaytun-xaki kargo shim + oq-kulrang retro krossovka.",
        "piece_count": 3,
        "palette_name": "Obsidian & Steel Grey",
        "palette_hex": ["#141518", "#383B42", "#D2D4D9"],
        "audio_vibe": "uk_drill_beat",
        "viral_hook": "UNIVERSITET VA HAR KUNI KIYISHGA TAYYOR SET",
        "colors": "To'q kulrang (grafit), To'q zaytun, Oq-kulrang",
        "sizes": "S, M, L, XL, 2XL",
        "items": [
            {"category": "top", "name": "Grafit Oversize Xudi", "price_cny": 46.0, "weight_kg": 0.50, "cn_keyword": "420g重磅纯棉连帽卫衣男宽松美式帽衫"},
            {"category": "bottom", "name": "Zaytun Kargo Shim", "price_cny": 48.0, "weight_kg": 0.50, "cn_keyword": "美式工装裤男直筒宽松多口袋伞兵休闲裤"},
            {"category": "shoes", "name": "Oq-Kulrang Krossovka", "price_cny": 42.0, "weight_kg": 0.70, "cn_keyword": "复古百搭板鞋男休闲运动鞋防滑厚底潮鞋"},
        ],
    },
]


def _sync_item_with_studio_photo_color(name: str, category: str = "", idx: int = 0) -> tuple[str, str]:
    """Lokal studiya rasmidagi HAQIQIY rang bilan buyum nomini 100% bir xil qiladi (rasmda boshqa, yozuvda boshqa bo'lmasligi uchun)."""
    low = (name or "").lower()
    cat = (category or "").lower()
    if any(k in low for k in ("bomber", "kurtka", "vetrovka", "jaket", "palt")) or cat == "outerwear":
        return "Qora Bomber Kurtka", "Qora"
    if any(k in low for k in ("sviter", "kardigan", "polo", "zip", "rubashka", "ko'ylak", "futbolka")):
        return "Bej Zamokli Sviter", "Och bej"
    if any(k in low for k in ("xudi", "hud", "hood", "tolstovka", "svitshot")) or cat == "top":
        return "Grafit Oversize Xudi", "To'q kulrang (grafit)"
    if any(k in low for k in ("kargo", "parashyut", "jinsi", "jeans")):
        return "Zaytun Kargo Shim", "To'q zaytun (xaki)"
    if any(k in low for k in ("shim", "bryuk", "drape", "triko", "shalvar")) or cat == "bottom":
        return "Grafit Klassik Shim", "To'q kulrang (grafit)"
    if any(k in low for k in ("lofer", "tufli", "zamsh", "klassik oyoq")):
        return "Jigarrang Zamsh Lofer", "To'q jigarrang"
    if any(k in low for k in ("krossovka", "oyoq", "keda", "sneaker")) or cat == "shoes":
        return "Oq-Kulrang Krossovka", "Oq-kulrang"
    if any(k in low for k in ("kepka", "shapka", "sumka", "soat", "kamar", "ochki")) or cat == "accessory":
        return "Qora Minimalist Kepka", "Qora"
    fallbacks = [
        ("Bej Zamokli Sviter", "Och bej"),
        ("Grafit Klassik Shim", "To'q kulrang (grafit)"),
        ("Jigarrang Zamsh Lofer", "To'q jigarrang"),
        ("Qora Bomber Kurtka", "Qora"),
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
            if i.get("url") and "yangkeduo.com" in str(i.get("url")):
                pdd_enriched["url"] = i["url"]
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
    ) -> str:
        return f"""Sen "XAN SHOP" moda brendining Bosh Bozor Tahlilchisi, Dizayner-Stilisti va Pinduoduo Skaut Agentisan.
Instagram Reels tahlilchisi quyidagi trend hisobotini yubordi:
- Trend yo'nalishi: {brief.trend_name}
- Tavsiya etilgan buyumlar soni: {brief.recommended_piece_count} ta buyum (faqat 4 talik emas, aynan {brief.recommended_piece_count} ta buyum bo'lsin!)
- Dizayner ranglar palitrasi: {brief.color_palette_name} ({', '.join(brief.color_hex_list)})
- Toshkent ob-havosi va mavsumi: {weather_line}
- Auditoriya: {gender}

Vazifang: Pinduoduo (拼多多) da eng ko'p sotilayotgan (10万+ sotuvli), O'zbekiston bozorida raqobatbardosh narxga tushadigan (har buyum ~22–65 CNY, to'plam jami ~95–170 CNY atrofida) aynan {brief.recommended_piece_count} qismli uyg'un Look yig'.
MUHIM QOIDA: "title" va har bir buyumning "name" maydoni FAQAT O'ZBEK TILIDA, qisqa va tushunarli (2–3 so'z, masalan: "Qora Bomber Kurtka", "Bej Zamokli Sviter", "Keng Kargo Shim", "Oq Retro Krossovka", "Qora Zamsh Lofer") bo'lsin! Inglizcha so'zlar yozma!
Har bir buyum uchun real Pinduoduo narxi (yuan - CNY), vazni (kg), kategoriyasi (outerwear, top, bottom, shoes, accessory) va xitoycha qidiruv so'zini ber.

FAQAT JSON QAYTAR:
{{
  "title": "O'zbekcha qisqa Look nomi",
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

    def _pick_template_if_invalid(self, data: dict[str, Any] | None) -> dict[str, Any]:
        if isinstance(data, dict) and isinstance(data.get("items"), list) and len(data["items"]) >= 2:
            return data
        tpl = DYNAMIC_LOOK_TEMPLATES[self._fallback_idx % len(DYNAMIC_LOOK_TEMPLATES)]
        self._fallback_idx += 1
        return tpl

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

        # Agar jonli Pinduoduo rasmi emas, lokal studiya rasmlari ishlatilayotgan bo'lsa,
        # rasmdagi kiyim rangi bilan yozuvdagi rangni 100% bir xil qilamiz!
        has_live_imgs = bool(downloaded_images and any(downloaded_images))
        exact_colors: list[str] = []
        if not has_live_imgs:
            for idx, it in enumerate(norm_items):
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

        return self._build_generated_look(self._pick_template_if_invalid(data), brief, weather_line)

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
    ) -> GeneratedLook:
        """Jonli Toshkent ob-havosi + OmniRoute/Gemini AI + Pinduoduo bilan asinxron Look yaratadi."""
        weather = weather or await fetch_tashkent_weather()
        eff_brief = trend_brief or await self.analyze_instagram_trends_async(weather)
        eff_season = weather.season_uz if season in ("", "avtomatik ob-havo") else season
        weather_line = (
            f"{weather.city}: bugun {weather.temp_c}°C, {weather.lead_time_days}dan keyin "
            f"~{weather.future_temp_c or weather.temp_c}°C ({eff_season}) — {weather.clothing_advice}"
        )

        if self.client is not self.ai.client:
            self.ai.client = self.client
        prompt = self._build_look_prompt(eff_brief, weather_line, gender)
        ai_data = await self.ai.ask_json(prompt, timeout_sec=16.0) if (self.ai.enabled or self.client) else None
        raw_data = self._pick_template_if_invalid(ai_data)
        gen = self._build_generated_look(raw_data, eff_brief, weather_line)

        # Agar Rasmiy Pinduoduo yoki RapidAPI ulangan bo'lsa, jonli narx va rasmlarni olamiz
        # (browser_session cookie'larni search_result.html anti-bot cheklovida kuydirmaslik uchun qidiruvga ishlatilmaydi)
        if self.pdd.connection_mode not in ("official_api", "rapidapi"):
            return gen

        enriched_items: list[dict[str, Any]] = []
        downloaded_imgs: list[bytes | None] = []
        for item in gen.raw_items:
            kw = item.get("cn_keyword") or item.get("name", "")
            live_matches = await self.pdd.search_live(kw, page_size=1)
            if live_matches:
                best = live_matches[0]
                updated = dict(item)
                updated["price_cny"] = best.price_cny
                updated["cny"] = best.price_cny
                updated["pdd_goods_id"] = best.goods_id or updated.get("pdd_goods_id", "")
                updated["sales_tip"] = best.sales_tip
                if best.product_url:
                    updated["url"] = best.product_url
                if best.image_url:
                    updated["image_url"] = best.image_url
                img_bytes = await self.pdd.fetch_image_bytes(best.image_url)
                downloaded_imgs.append(img_bytes)
                enriched_items.append(updated)
            else:
                downloaded_imgs.append(None)
                enriched_items.append(item)

        return self._build_generated_look(
            raw_data,
            eff_brief,
            weather_line,
            raw_items_override=enriched_items,
            downloaded_images=downloaded_imgs,
        )
