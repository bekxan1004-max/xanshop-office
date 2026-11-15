"""XAN SHOP - Jonli Ob-Havo (7–14 kunlik prognoz) & Instagram Raqobatchi Razvedkasi (insta_analyst).

1) Toshkentning joriy va 7–14 kun oldingi ob-havo prognozini (Open-Meteo API) oladi —
   Xitoy omborgacha (1–4 kun) + Avia kargo (3–7 kun) = jami 5–10 kunda buyurtma
   yetib borganda mijoz qanday ob-havoda kiyishini hisobga olib Look yig'adi.
2) Instagramdagi raqobatchilar (@_tima_shop, @stylesh.uz, @lookzona.uz va har qanday
   boshqa akkount)ning Bio, Opisaniya, Koment, Narx, Hook, Zvukli Reels va
   mijozlarni og'dirish tizimini chuqur tahlil qiladi.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import aiohttp

from .ai import SalesAI, extract_json_dict

if TYPE_CHECKING:
    from .config import Settings

log = logging.getLogger(__name__)

TASHKENT_WEATHER_URL = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude=41.2995&longitude=69.2401"
    "&current_weather=true&daily=temperature_2m_max,temperature_2m_min"
    "&timezone=Asia%2FTashkent&forecast_days=14"
)

_HANDLE_RE = re.compile(r"^[a-zA-Z0-9._]{1,32}$")
_RESERVED_IG_PATHS = {"reel", "reels", "p", "stories", "explore", "accounts", "direct"}


@dataclass(frozen=True)
class WeatherForecast:
    city: str
    temp_c: float
    min_c: float
    max_c: float
    season_uz: str
    clothing_advice: str
    is_live: bool = False
    future_temp_c: float = 0.0
    future_min_c: float = 0.0
    future_max_c: float = 0.0
    lead_time_days: str = "5–10 kun"
    planning_horizon_days: int = 10


def _classify_weather(temp_c: float, max_c: float, cur_temp: float | None = None) -> tuple[str, str]:
    """Kutilayotgan harorat (5–10 kun oldingi prognoz) asosida mavsum va kiyim tavsiyasini beradi."""
    prefix = ""
    if cur_temp is not None:
        prefix = (
            f"Bugun {cur_temp:.0f}°C, 5–10 kunda (Avia yetib kelganda) ~{temp_c:.0f}°C kutilmoqda — "
        )
    if temp_c <= 8.0:
        return (
            "sovuq qish / kech kuz",
            prefix + "issiq palto/bomber, 420g qalin xudi, sviter va qalin shimlar eng ko'p sotiladi.",
        )
    if max_c <= 20.0:
        return (
            "salqin kuz / bahor",
            prefix + "yengil shamolto'sar kurtka, half-zip svitshot, kargo shim va krossovkalar trendda.",
        )
    if max_c <= 27.0:
        return (
            "iliq bahor / yoz oqshomi",
            prefix + "2–3 qismli yengil kapsula (kardigan yoki heavyweight futbolka + drape shim) talabda.",
        )
    return (
        "issiq yoz",
        prefix + "280g nafas oluvchi oversize futbolka, yengil keng shim va yozgi krossovka (2–3 talik set).",
    )


async def fetch_tashkent_weather() -> WeatherForecast:
    """Toshkentning jonli ob-havosi va 5–10 kun oldingi (14 kunlik oyna) prognozini oladi."""
    try:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(TASHKENT_WEATHER_URL) as resp:
                data = await resp.json(content_type=None)
        cur = float(data["current_weather"]["temperature"])
        daily = data.get("daily", {})
        min_list = [float(x) for x in (daily.get("temperature_2m_min") or [cur])]
        max_list = [float(x) for x in (daily.get("temperature_2m_max") or [cur])]
        tmin = min_list[0]
        tmax = max_list[0]

        horizon_mins = min_list[5:10] or min_list[-4:]
        horizon_maxs = max_list[5:10] or max_list[-4:]
        f_min = round(sum(horizon_mins) / len(horizon_mins), 1)
        f_max = round(sum(horizon_maxs) / len(horizon_maxs), 1)
        f_temp = round((f_min + f_max) / 2, 1)

        season, advice = _classify_weather(f_temp, f_max, cur_temp=cur)
        return WeatherForecast(
            city="Toshkent",
            temp_c=round(cur, 1),
            min_c=round(tmin, 1),
            max_c=round(tmax, 1),
            season_uz=season,
            clothing_advice=advice,
            is_live=True,
            future_temp_c=f_temp,
            future_min_c=f_min,
            future_max_c=f_max,
            lead_time_days="5–10 kun",
            planning_horizon_days=10,
        )
    except Exception as e:
        log.info("Ob-havo API mavjud emas (%s), standart mavsum ishlatiladi", e)
        return WeatherForecast(
            city="Toshkent",
            temp_c=11.0,
            min_c=6.0,
            max_c=16.0,
            season_uz="salqin kuz / erta bahor",
            clothing_advice=(
                "Bugun ~11°C, 5–10 kunda (Avia yetib kelganda) ~10°C atrofida — "
                "qalin 420g xudi, bomber/palto va kargo/jinsi kombinatsiyasi eng xaridorgir."
            ),
            is_live=False,
            future_temp_c=10.5,
            future_min_c=5.5,
            future_max_c=15.5,
            lead_time_days="5–10 kun",
            planning_horizon_days=10,
        )


COMPETITOR_PROFILES: dict[str, dict[str, Any]] = {
    "_tima_shop": {
        "handle": "@_tima_shop",
        "title": "TIMA SHOP | Premium sifat",
        "url": "https://www.instagram.com/_tima_shop",
        "stats_snapshot": "90.5K follower • 1 120 post",
        "workforce_model": (
            "Ko'p sonli jonli stilist, videochi va DM operatorlar bilan ishlaydi; "
            "XAN SHOP esa buni 8 ta avtonom AI agent bilan nol ish haqida bajaradi."
        ),
        "bio_formula": (
            "3-yillik tajriba | O'zgacha looklar | 31 000+ mijoz ishonchi | "
            "Dostavka 7–13 kun | Buyurtma uchun: t.me/TIMA_SHOP_UZ | "
            "Highlights: ISBOTLAR, REAL HAYOTDA, POCHTALAR, MALUMOT."
        ),
        "opisaniya_formula": (
            "Reels captionida narx ataylab yozilmaydi -> 'Zakaz uchun commentga \"+\" qoldiring' -> "
            "'- Cargo alohida (100gr 13 000 so'm = 130k/kg)' -> '- Dastavka UZB bo'ylab 8–12 kun' -> "
            "'- 50% oldindan to'lov'. Karusel postlarda esa narx birinchi qatorda beriladi."
        ),
        "koment_triggers": (
            "Auditoriyani kommentga '+' yozdiradi (algoritm Reels'ni rekka chiqaradi!). "
            "Avto-DM bot darhol narx, razmer va rasmlarni lichkaga yuboradi."
        ),
        "narx_psychology": (
            "Karusel/katta setlarda 599 000, 850 000, 899 000 so'm kabi yirik yaxlit narxlar; "
            "kargo 130 000 so'm/kg (XAN SHOP esa ~115 000 so'm/kg va 50k/100k yuqoriga yaxlitlash bilan ustun)."
        ),
        "hook_patterns": [
            "170–185 SM BO'YLI BOLLAR UCHUN OBRAZ (bo'y segmenti hooki)",
            "SIZ QIDIRGAN JAPANESE LOOK (uslub hooki)",
            "QISHGA SIZ QIDIRVOTGAN PALTO (mavsumiy ehtiyoj hooki)",
        ],
        "zvuk_style": (
            "Original audio / ritmik fon beatlari (robot/diktor ovozi umuman yo'q!). "
            "XAN SHOP v3.0: toza studiya beat + whoosh/shutter/sub-bass saund-dizayn (TTS ovozsiz!)."
        ),
        "persuasion_secrets": (
            "1) Bo'yiga qarab aniq obraz berish; 2) Ko'plab ISBOTLAR/REAL HAYOTDA highlightlari; "
            "3) Kommentda '+' triggeri bilan tez Direct javob; 4) 50% oldindan to'lov ishonchi."
        ),
    },
    "shams.labs": {
        "handle": "@shams.labs",
        "title": "Shams | Viral Reels Rejissura & ManyChat Voronka (reel/DdjPwtXgBdK)",
        "url": "https://www.instagram.com/reel/DdjPwtXgBdK/",
        "stats_snapshot": "11.9K follower • 3,603 like / 2,683 komment (74% komment konversiyasi!) / 3,088 share",
        "workforce_model": "AI kontent rejissura + ManyChat/Direct avtomatik javob voronkasi.",
        "bio_formula": "Aniq pozitsiya + Kreativ AI Montaj + Telegram botga to'g'ridan-to'g'ri chaqiruv.",
        "opisaniya_formula": "Qisqa intriga savoli -> 'Kommentga maxsus so'z (+ yoki LOOK) yozing 👇 Bot Directga yuboradi'.",
        "koment_triggers": "74% komment-layk nisbati siri: tomoshabin material/narx/razmerni olish uchun izoh qoldiradi.",
        "narx_psychology": "Qiymatni oldin ko'rsatib, izoh orqali shaxsiy konsultatsiyaga olib kirish.",
        "hook_patterns": [
            "SPLIT-SCREEN (Yuqori 50% B-roll/Inspiratsiya + Quyi 50% Asosiy Obraz)",
            "QORA KAPSULA ICHIDA OQ/OLTIN QALIN KINETIK SUBTITRLAR",
            "KULMINATSIYADA FULL-SCREEN PUNCH-IN VA MAKRO TEKSTURA",
        ],
        "zvuk_style": "Ambient/Lo-Fi/Phonk fon + har kadr almashinuvida 'whoosh', 'shutter click', 'sub-bass drop' saund-dizayn.",
        "persuasion_secrets": "Yuqori vizual kontrast, qora kapsulali dinamik yozuvlar va izoh->Direct avtomatizatsiyasi.",
    },
    "stylesh.uz": {
        "handle": "@stylesh.uz",
        "title": "Stylesh.uz — Erkaklar Kapsulasi",
        "url": "https://www.instagram.com/stylesh.uz",
        "stats_snapshot": "O'zbekiston top men's capsule formati",
        "workforce_model": "Jonli jamoa asosida kunlik kapsula yig'ish va DM savdosi.",
        "bio_formula": (
            "Boshdan-oyoq tayyor kapsula • 50% oldindan to'lov • "
            "Avia yetkazish • Telegram katalog havolasi."
        ),
        "opisaniya_formula": (
            "To'liq obraz tarkibi + har bir buyum nomi + razmer jadvali (M–2XL) + "
            "'Lichkaga + yoki kod raqamini yozing' CTA."
        ),
        "koment_triggers": "Kommentga kod raqami yoki '+' yozganlarga DM va Telegram havola.",
        "narx_psychology": "Yaxlit to'plam narxlari (50k/100k chegarada) + alohida kargo shaffofligi.",
        "hook_patterns": [
            "BOSHDAN OYOQ TAYYOR OBRAZ",
            "HAR BIR BUYUM ALOHIDA ZOOMDA",
        ],
        "zvuk_style": "Dinamik phonk va street beatlar ostida tezkor kadr almashinuvi.",
        "persuasion_secrets": "Har bir qismning alohida sifatini yaqindan ko'rsatib ishonch uyg'otish.",
    },
    "lookzona.uz": {
        "handle": "@lookzona.uz",
        "title": "Lookzona.uz — Minimalistik Kolaj & Reels",
        "url": "https://www.instagram.com/lookzona.uz",
        "stats_snapshot": "2x2 minimalistik kolaj standarti",
        "workforce_model": "Dizayner + SMM menejerlar jamoasi.",
        "bio_formula": "Tayyor 2x2 looklar • Bo'y/vazn bo'yicha razmer • Telegram kanalga o'ting.",
        "opisaniya_formula": "Qisqa punktli ro'yxat + Save (Saqlab oling) chaqiruvi + Telegram bot havolasi.",
        "koment_triggers": "Narx va razmer so'rovchilar uchun komment/DM yo'naltirish.",
        "narx_psychology": "1.2 soniyada narx va 50% qulay bo'lib to'lash shaffofligi.",
        "hook_patterns": [
            "NARX VA 50% TO'LOV 1.2 SONIYADA KO'RINISHI",
            "OCH KULRANG FONDA TOZA 2x2 KOLAJ",
        ],
        "zvuk_style": "Luxury chill va estetik trend audio fon.",
        "persuasion_secrets": "Minimalizm, chiroyli palitra va tanlash qiyinligini yo'qotadigan tayyor set.",
    },
}

# Dashboard va boshqa modullar uchun tezkor benchmark ro'yxati
COMPETITOR_BENCHMARKS = [
    {
        "channel": "@_tima_shop",
        "format": "Qora fonda katta hook + qismlarga yoyilgan/model montaj + original beat",
        "hook": "170–185 sm bo'y / Japanese look / Mavsumiy ehtiyoj hooklari + kommentda '+' trigger",
        "cta": "Commentga '+' qoldiring (Avto-DM) • Avia 5–10 kun bilan undan ham tez xizmat",
    },
    {
        "channel": "@lookzona.uz",
        "format": "2x2 minimalistik och kulrang fon (#F5F5F7) kolaj + Reels tezkor kadr almashinuvi",
        "hook": "Narx va 50% oldindan to'lov birinchi 1.2 soniyada ko'rinishi",
        "cta": "Telegram kanalga o'tib razmeringizni (bo'y/vazn) yozing",
    },
    {
        "channel": "@stylesh.uz",
        "format": "To'liq boshdan-oyoq obraz + har bir buyum alohida zoom bilan",
        "hook": "Avia kargo (5–10 kun) va real vazn bo'yicha shaffof hisob",
        "cta": "Lichkaga '+' yoki kod raqamini yuboring",
    },
    {
        "channel": "@shams.labs (Viral Reel DdjPwtXgBdK)",
        "format": "Split-Screen Bento + Qora kapsulali kinetik subtitrlar + Whoosh/Shutter saund-dizayn",
        "hook": "Yuqori kontrastli vizual + 1-kadrdan Bento preview (74% komment konversiyasi)",
        "cta": "Kommentga '+' yoki 'LOOK' yozing -> Direct/Telegramda razmer va narx",
    },
]

GLOBAL_IG_NICHES: list[dict[str, str]] = [
    {
        "niche": "Diplomatiya, Yuridika va Xalqaro Universitet Talabalari (Old Money)",
        "visual_style": "Persona Spotlight Deck: Qora-oltin salobatli kadr + klassik sviter, drape shim va zamsh lofer",
        "honest_spec": "Jiddiy uchrashuv va o'qish uchun tanlangan obraz — 50% oldindan, qolgani Toshkentda ko'rib olganda",
    },
    {
        "niche": "Oversize va Erkin Streetwear Yoqtiradiganlar",
        "visual_style": "3D Orbit Turntable: Erkin bichimli xudi, bomber va keng kargo shimlar 3D aylanishda",
        "honest_spec": "Erkin o'tiradigan oversize bichim — bo'y va vazningizga qarab aniq razmer tanlab beriladi",
    },
    {
        "niche": "175–188 sm Bo'yli Klassik & Minimalist Yigitlar",
        "visual_style": "Editorial Split Showcase: Yuqorida to'liq obraz, markazda 1080p katta kiyim va narx",
        "honest_spec": "Bo'yni tik va qomatni kelishgan ko'rsatadigan Cleanfit proportsiya",
    },
    {
        "niche": "IT, Biznes, Startap va Zamonaviy Ofis Yigitlari",
        "visual_style": "Bento Zoom Reveal: 3–4 qismli jonli Bento vitrinadan har bir kiyim 1080p fokusga chiqadi",
        "honest_spec": "Kun bo'yi qulay va har joyda salobatli ko'rinadigan Smart-Casual kapsula",
    },
]

# Mijoz "aynan men uchun tanlangan ekan!" deb his qilishi uchun auditoriya-persona arxetiplari
PERSONA_ARCHETYPES: list[dict[str, str]] = [
    {
        "id": "diplomat_law",
        "target_persona": "Diplomatiya va Yuridikada o'qiydigan yigitlar",
        "hook_headline": "DIPLOMATIYA VA YURIDIKADA O'QIYDIGANLAR UCHUN",
        "sub_hook": "O'qish, ofis va jiddiy uchrashuvlar uchun Old Money obraz",
        "video_style": "persona_spotlight_deck",
        "audio_vibe": "diplomat_old_money",
    },
    {
        "id": "oversize_street",
        "target_persona": "Oversize va erkin kiyishni yoqtiradiganlar",
        "hook_headline": "OVERSIZE KIYISHNI YOQTIRADIGAN YIGITLAR UCHUN",
        "sub_hook": "Erkin bichim va ko'chada ajralib turadigan Streetwear stil",
        "video_style": "orbit_3d_turntable",
        "audio_vibe": "phonk_bass",
    },
    {
        "id": "tall_cleanfit",
        "target_persona": "175–188 sm bo'yli klassik va minimalist yigitlar",
        "hook_headline": "175–188 SM BO'YLI YIGITLAR UCHUN TAYYOR OBRAZ",
        "sub_hook": "Qomatni tik ko'rsatadigan Cleanfit uyg'unlik",
        "video_style": "editorial_split_showcase",
        "audio_vibe": "luxury_chill",
    },
    {
        "id": "it_business",
        "target_persona": "IT, Biznes va Zamonaviy Ofis yigitlari",
        "hook_headline": "IT, BIZNES VA OFISDA ISHLAYDIGANLAR UCHUN",
        "sub_hook": "Kun bo'yi qulay va har joyda jiddiy ko'rinadigan kapsula",
        "video_style": "bento_zoom_reveal",
        "audio_vibe": "lofi_editorial",
    },
    {
        "id": "uni_daily",
        "target_persona": "Universitet talabalari va faol yoshlar",
        "hook_headline": "UNIVERSITET VA HAR KUNI KIYISHGA TAYYOR SET",
        "sub_hook": "Eng ko'p so'ralgan qulay va zamonaviy kombinatsiya",
        "video_style": "orbit_3d_turntable",
        "audio_vibe": "uk_drill_beat",
    },
]


def select_persona_archetype(look_title: str = "", audio_vibe: str = "", idx: int = 0) -> dict[str, str]:
    """Look nomi yoki navbat indeksiga qarab mos auditoriya-persona, video uslubi va musiqani tanlaydi."""
    low = (look_title or "").lower()
    if any(k in low for k in ("diplomat", "yuridik", "old money", "klassik", "latte", "espresso", "lofer")):
        return PERSONA_ARCHETYPES[0]
    if any(k in low for k in ("oversize", "street", "kargo", "xudi", "grafit")):
        return PERSONA_ARCHETYPES[1]
    if any(k in low for k in ("cleanfit", "175", "170", "minimal")):
        return PERSONA_ARCHETYPES[2]
    if any(k in low for k in ("ofis", "biznes", "it", "smart", "kapsula")):
        return PERSONA_ARCHETYPES[3]
    return PERSONA_ARCHETYPES[idx % len(PERSONA_ARCHETYPES)]


def build_video_creative_directive(
    look_title: str,
    piece_count: int,
    total_price_uzs: int,
    prepay_50_uzs: int,
    palette_name: str,
    palette_hex: list[str],
    audio_vibe: str,
    weather: WeatherForecast | None = None,
    items: list[dict[str, Any]] | None = None,
    style_idx: int = 0,
    viral_hook: str = "",
) -> dict[str, Any]:
    """insta_analyst v3.0 tomonidan video_employee v3.0 ga beriladigan 1080p rejissyorlik buyrug'i."""
    lead = weather.lead_time_days if weather else "5–10 kun"
    fut_t = (weather.future_temp_c or weather.temp_c) if weather else 12.0
    season = weather.season_uz if weather else "mavsumiy"
    persona = select_persona_archetype(look_title + " " + viral_hook, audio_vibe, idx=style_idx)
    eff_vibe = audio_vibe if audio_vibe in (
        "diplomat_old_money", "phonk_bass", "luxury_chill", "lofi_editorial", "uk_drill_beat"
    ) else persona["audio_vibe"]
    hook_headline = viral_hook.strip() if (viral_hook and "UCHUN" in viral_hook.upper()) else persona["hook_headline"]

    item_specs = []
    for idx, it in enumerate(items or []):
        nm = str(it.get("name") or f"Kiyim #{idx + 1}")
        item_specs.append(f"0{idx + 1}: {nm}")

    return {
        "version": "v3.0",
        "from_agent": "insta_analyst",
        "target_agent": "video_employee",
        "resolution": "1080x1920 (Full HD 1080p, High-Bitrate H.264)",
        "target_persona": persona["target_persona"],
        "video_style": persona["video_style"],
        "audio_vibe": eff_vibe,
        "voiceover_policy": "STRICT_NO_VOICEOVER (Ovozli robot diktor taqiqlangan — faqat studiya beat + whoosh/shutter saund-dizayn)",
        "editing_architecture": f"1080p {persona['video_style']} + Persona Hook ({persona['target_persona']})",
        "hook_headline": hook_headline,
        "sub_hook": persona["sub_hook"],
        "honest_quality_pledge": (
            f"Auditoriya: {persona['target_persona']}. "
            "Mijozga murakkab texnik matn emas, aniq narx va 100% ishonch beriladi: "
            "50% hozir, qolgani kiyim Toshkentga kelib sifatini o'z ko'zi bilan ko'rganda!"
        ),
        "comment_trigger_cta": "Izohda '+' qoldiring — bo'y va vazningizga mos razmerni tanlab beramiz",
        "scene_plan": [
            f"1-Sahna (0.0s–1.4s): '{hook_headline}' auditoriya sarlavhasi + 1080p HD kirish.",
            f"2-Sahna (1.4s–5.2s): '{persona['video_style']}' uslubida kiyimlar va har birining alohida narxi ({'; '.join(item_specs[:4])}).",
            f"3-Sahna (5.2s–6.6s): 50% oldindan ({prepay_50_uzs:,} so'm), qolgani Toshkentda ko'rib olganda!".replace(",", " "),
            f"4-Sahna (6.6s–7.8s): To'liq 1080p Lookbook + Avia {lead} (~{fut_t:.0f}°C {season}).",
        ],
        "sound_design": f"{eff_vibe} + intro riser + kadr almashishida shutter-click & whoosh + 808 sub-bass",
        "palette_name": palette_name,
        "palette_hex": palette_hex,
    }


def extract_instagram_handle(raw: str) -> str:
    """Instagram URL yoki @username matnidan toza username ajratib oladi."""
    val = (raw or "").strip()
    if not val:
        return "_tima_shop"
    if "instagram.com" in val.lower():
        if not val.lower().startswith("http"):
            val = "https://" + val
        parsed = urlparse(val)
        parts = [p for p in parsed.path.split("/") if p]
        for seg in parts:
            low = seg.lower().lstrip("@")
            if low not in _RESERVED_IG_PATHS and _HANDLE_RE.match(low):
                return low
    cleaned = val.lstrip("@").split("?")[0].split("/")[0].strip()
    return cleaned.lower() if _HANDLE_RE.match(cleaned) else "_tima_shop"


def analyze_competitor_account(raw_input: str, weather: WeatherForecast | None = None) -> dict[str, Any]:
    """Raqobatchi Instagram profili bo'yicha 7 yo'nalishli tizimli razvedka hisobotini tuzadi."""
    handle = extract_instagram_handle(raw_input)
    prof = COMPETITOR_PROFILES.get(handle)
    lead = weather.lead_time_days if weather else "5–10 kun"
    horizon_line = (
        f"Bugun {weather.temp_c}°C, {lead}dan keyin ~{weather.future_temp_c}°C ({weather.season_uz})"
        if weather
        else f"Keyingi {lead} ichidagi ob-havo oynasiga mos kapsula"
    )

    if prof:
        base = dict(prof)
        base["known_benchmark"] = True
    else:
        base = {
            "handle": f"@{handle}",
            "title": f"Instagram Fashion Monitor (@{handle})",
            "url": f"https://www.instagram.com/{handle}",
            "stats_snapshot": "Kuzatuvga olingan raqobatchi profil",
            "workforce_model": "Jonli SMM/sotuvchilar oqimi — XAN SHOP 8 ta AI agent bilan avtomatlashtiradi.",
            "bio_formula": (
                "Aniq kategoriya + tajriba/ishonch isboti + 50% oldindan to'lov + "
                f"{lead} Avia + Telegram katalog havolasi."
            ),
            "opisaniya_formula": (
                "1-qator: kuchli hook; 2-qator: tarkib/razmerlar; 3-qator: commentga '+' CTA "
                f"yoki 50k/100k yaxlitlangan narx + {lead} yetkazish."
            ),
            "koment_triggers": "Kommentga '+' yozdirib DM orqali avtomatik razmer va narx yuborish.",
            "narx_psychology": "Yaxlit 50k/100k narx (masalan 550k / 600k) + 65% marja + 50% bo'lib to'lash.",
            "hook_patterns": [
                "Bo'y va vazn segmenti (masalan 170–185 sm yigitlar uchun)",
                "Birinchi 1.5 soniyada muammo + tayyor yechim kapsulasi",
            ],
            "zvuk_style": "Toza ritmik fon beat (phonk/luxury) + whoosh/shutter saund-dizayn (sun'iy TTS ovozsiz!).",
            "persuasion_secrets": "Tayyor moslangan obraz, 100% halol mato/razmer pasporti va Xitoy ombor QC isbotlari.",
            "known_benchmark": False,
        }

    base["weather_horizon"] = horizon_line
    base["global_niches"] = GLOBAL_IG_NICHES
    base["xan_shop_counter_strategy"] = (
        f"1) Muddat halolligi: Xitoy ichki 1–4 kun + Avia 3–7 kun = {lead} (@_tima_shop 7–13 kunidan tezroq). "
        "2) Kargo afzalligi: ~115k so'm/kg ($9.5/kg) — raqobatchining 130k/kg tarifidan arzon. "
        "3) Narx va foyda: 65% marja va 50k/100k yuqoriga yaxlitlash (masalan 527k -> 550k/600k). "
        "4) Halol Premium Video (v3.0): TTS robot ovozsiz, Bento Split-Screen, qora kapsula subtitrlar va 100% real mato/razmer kafolati."
    )
    return base


def build_reels_strategy_summary(weather: WeatherForecast) -> dict[str, Any]:
    """API /api/state va Skaut agent uchun tezkor (LLM kutmaydigan) strategiya xulosasi."""
    return {
        "lead_time_days": weather.lead_time_days,
        "planning_horizon_days": weather.planning_horizon_days,
        "today_temp_c": weather.temp_c,
        "future_temp_c": weather.future_temp_c or weather.temp_c,
        "future_range_c": f"{weather.future_min_c or weather.min_c}..{weather.future_max_c or weather.max_c}°C",
        "target_season_uz": weather.season_uz,
        "clothing_advice": weather.clothing_advice,
        "pricing_rounding_rule": "50 000 / 100 000 so'm yuqoriga yaxlitlash (65% sof marja)",
        "top_hooks": [
            f"170–185 SM BO'YLI YIGITLAR UCHUN ({weather.season_uz.upper()})",
            "COMMENTGA '+' QOLDIRING • 50% OLDINDAN TO'LOV",
            f"AVIA {weather.lead_time_days.upper()} • BOSHDAN OYOQ KAPSULA",
        ],
        "competitor_insights": COMPETITOR_BENCHMARKS,
    }


async def analyze_instagram_creative_strategy(
    genai_client: Any = None,
    model_name: str = "gemini-3.8-flash",
    weather: WeatherForecast | None = None,
    settings: "Settings | None" = None,
) -> dict[str, Any] | None:
    """Instagram trendlari, raqobatchilar (@_tima_shop, @stylesh.uz, @lookzona.uz) va
    5–10 kun oldingi ob-havo asosida kreativ Reels strategiyasi yaratadi."""
    if not settings and not genai_client:
        return None
    w = weather or await fetch_tashkent_weather()
    prompt = f"""Sen Instagram Fashion Reels bo'yicha top-razvedkachi va kreativ direktorsan (O'zbekiston bozori: @_tima_shop, @lookzona.uz, @stylesh.uz).
Bugungi Toshkent ob-havosi: {w.temp_c}°C.
JUDA MUHIM LOGISTIKA OMILI: Pinduoduo Xitoy omborgacha 1–4 kun + Avia kargo 3–7 kun = jami {w.lead_time_days} yetib boradi.
Reels rekka chiqib mijoz buyurtma berganda 5–10 kundan keyingi kutilayotgan ob-havo: {w.future_temp_c or w.temp_c}°C ({w.season_uz}) — {w.clothing_advice}.
Raqobatchi @_tima_shop usuli: bo'y/uslubga qaratilgan hook ("170-185 sm bollar uchun"), kommentga "+" triggeri, 50% oldindan to'lov, yaxlit 50k/100k narxlar.

Vazifang: Keyingi {w.lead_time_days} ob-havosiga mos tushadigan, odamlarni komment yozishga va buyurtma berishga undaydigan REELS strategiyasi tuz.
FAQAT JSON QAYTAR:
{{
  "trend_name": "Kreativ trend nomi (masalan: 170-185 sm Cleanfit Old Money Capsule)",
  "recommended_piece_count": 3,
  "color_palette_name": "Dizayner palitra nomi",
  "color_hex_list": ["#16171B", "#3C3732", "#C7B8A5", "#F3F3F5"],
  "viral_hook_uz": "Video 1-soniyasi uchun kuchli psixologik hook (maks 36 belgi)",
  "cta_uz": "Video oxiri/opisaniya CTA (masalan: IZOHDA '+' YOZING • 50% TO'LOV)",
  "audio_vibe": "phonk_bass",
  "conversion_reason": "Nega @_tima_shop/@stylesh auditoriyasi shu formatni saqlaydi va zakaz beradi (1 gap)"
}}
Eslatma: recommended_piece_count 2, 3, 4 yoki 5 bo'lsin; audio_vibe faqat 'phonk_bass', 'luxury_chill' yoki 'uk_drill_beat' bo'lsin."""

    if settings is not None:
        ai = SalesAI(settings)
        if genai_client and ai.client is None:
            ai.client = genai_client
        parsed = await ai.ask_json(prompt, timeout_sec=15.0)
        if isinstance(parsed, dict) and "trend_name" in parsed:
            return parsed

    if not genai_client:
        return None

    def _call():
        return genai_client.interactions.create(model=model_name, input=prompt)

    try:
        res = await asyncio.wait_for(asyncio.to_thread(_call), timeout=15.0)
        parsed = extract_json_dict(getattr(res, "output_text", None) or "")
        if isinstance(parsed, dict) and "trend_name" in parsed:
            return parsed
    except Exception as e:
        log.info("Instagram kreativ tahlil zaxiraga o'tdi (%s)", e)
    return None


async def analyze_competitor_with_ai(
    raw_input: str,
    settings: "Settings",
    db: Any = None,
    weather: WeatherForecast | None = None,
) -> dict[str, Any]:
    """insta_analyst agenti orqali istalgan raqobatchi profilini AI + benchmark bilan chuqur tahlil qiladi."""
    w = weather or await fetch_tashkent_weather()
    report = analyze_competitor_account(raw_input, weather=w)
    if db is not None:
        await db.set_agent_status("insta_analyst", "working", f"{report['handle']} profili tahlil qilinmoqda...")

    ai_provider = "Tizimli Razvedka Bazasi"
    ai = SalesAI(settings)
    if ai.enabled:
        prompt = (
            f"Sen XAN SHOP 'Instagram Tahlilchisi' (insta_analyst) agentisan.\n"
            f"Maqsadli raqobatchi: {report['handle']} ({report['url']})\n"
            f"Mavjud tahlil: {report['bio_formula']} | Hooklar: {', '.join(report['hook_patterns'])} | "
            f"Koment: {report['koment_triggers']} | Zvuk: {report['zvuk_style']}\n"
            f"Toshkent ob-havosi 5–10 kundan keyin: {w.future_temp_c or w.temp_c}°C ({w.season_uz}).\n"
            f"XAN SHOP ustunligi: Avia 5–10 kun, kargo ~$9.5/kg (115k/kg), 50k/100k yaxlitlangan narx (65% marja), "
            f"va 8 ta avtonom AI agent.\n\n"
            "FAQAT JSON QAYTAR (o'zbek tilida):\n"
            "{\n"
            '  "winning_hook": "Raqobatchidan kuchliroq 3 soniyalik hook",\n'
            '  "bio_improvement": "Bio uchun 1 ta aniq kuchaytiruvchi g\'oya",\n'
            '  "caption_cta": "Opisaniya va komment (\'+\') trigger shabloni",\n'
            '  "zvuk_and_pacing": "Zvuk turi va video montaj tezligi tavsiyasi",\n'
            '  "persuasion_angle": "Odamlarni 50% oldindan to\'lovga og\'dirish psixologik usuli"\n'
            "}"
        )
        ai_json = await ai.ask_json(prompt, timeout_sec=12.0)
        if isinstance(ai_json, dict) and ai_json:
            report["ai_recommendations"] = ai_json
            ai_provider = ai.last_provider_used or "AI Tahlil"

    report["provider"] = ai_provider
    if db is not None:
        await db.set_agent_status(
            "insta_analyst",
            "idle",
            f"{report['handle']} tahlil qilindi ({w.lead_time_days} ob-havo bilan)",
            increment_done=True,
        )
        await db.log_agent_action(
            "insta_analyst",
            f"Instagram raqobatchi tahlili: {report['handle']} [{ai_provider}]",
            f"Hook: {report['hook_patterns'][0]} | Ob-havo ({w.lead_time_days}): ~{w.future_temp_c or w.temp_c}°C ({w.season_uz})",
            target_id="skaut",
        )
    return report
