"""Sozlamalar .env faylidan o'qiladi (24/7 Cloud Server, Pinduoduo, Instagram, Telegram Userbot bilan)."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _float(name: str, default: str) -> float:
    return float(os.getenv(name, default) or default)


def _ids(raw: str) -> list[int]:
    return [int(x) for x in raw.replace(" ", "").split(",") if x]


@dataclass(frozen=True)
class Settings:
    sales_bot_token: str
    admin_bot_token: str
    admin_ids: list[int]
    agent_chat_id: int | None
    gemini_api_key: str
    gemini_model: str
    shop_name: str
    delivery_text: str
    return_policy: str
    card_number: str
    card_owner: str
    auto_rates: bool
    cny_uzs: float
    usd_uzs: float
    vykup_percent: float
    profit_percent: float
    payment_fee_percent: float
    china_shipping_cny_per_item: float
    cargo_usd_per_kg: float
    cargo_client_uzs_per_kg: float
    cargo_collect_on_delivery: bool
    db_path: str
    conversion_fee_percent: float = 2.5
    ensure_50_covers_cost: bool = True
    prepay_round_to: int = 50000
    channel_id: str = ""
    office_port: int = 8080
    # Shaxsiy Telegram Akkaunt (Userbot - MTProto)
    tg_api_id: str = ""
    tg_api_hash: str = ""
    tg_phone: str = ""
    tg_session_string: str = ""
    manager_username: str = ""
    # Rasmiy Pinduoduo API, Apify Live PDD Server va Brauzer sessiyasi (Playwright)
    pdd_client_id: str = ""
    pdd_client_secret: str = ""
    pdd_rapidapi_key: str = ""
    pdd_apify_token: str = ""
    pdd_session_path: str = "data/pdd_session.json"
    # Rasmiy Instagram Graph API
    ig_user_id: str = ""
    ig_access_token: str = ""
    public_base_url: str = ""
    # 24/7 Avtonom Rejalashtiruvchi (har N soatda avto-look chiqarish, 0 = faqat tugma/buyruq bilan)
    auto_post_hours: float = 3.0
    # AI Hisobchi (Bank SMS / @HumoCardBot / @CardXabarBot webhook va bot nomlari)
    bank_webhook_secret: str = ""
    bank_bot_usernames: str = "HumoCardBot,CardXabarBot,UzcardBot,KapitalbankUzBot,IpakYoliBot"
    # OpenRouter Token Routing (Arzon & Bepul modellar: DeepSeek, Llama 3, Gemini Flash)
    openrouter_api_key: str = ""
    openrouter_model: str = "deepseek/deepseek-chat"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # OmniRoute Lokal AI Gateway (380 provayder, 150+ bepul tier, RTK+Caveman token siqish)
    omniroute_base_url: str = "http://localhost:20128/v1"
    omniroute_api_key: str = "omniroute-local"
    omniroute_model: str = "auto"
    use_omniroute: bool = True
    # ECC (everything-claude-code: 71 Agent + 314 Skill)
    ecc_root: str = "vendor/ecc"
    # Hugging Face & Fal.ai AI Image Studio (FLUX.1-Kontext-Dev / Nano Banana muqobillari)
    hf_token: str = ""
    fal_key: str = ""
    # Ovozli Sun'iy Intellekt (Reels uchun default o'chirilgan: faqat toza beat + saund-dizayn)
    ai_voice_name: str = "uz-UZ-SardorNeural"
    enable_ai_voiceover: bool = False


def load_settings() -> Settings:
    agent = os.getenv("AGENT_CHAT_ID", "").strip()
    # Cloud serverlar (Railway, Render, Fly.io) PORT o'zgaruvchisini beradi
    port_raw = os.getenv("PORT") or os.getenv("OFFICE_PORT") or "8080"
    return Settings(
        sales_bot_token=os.getenv("SALES_BOT_TOKEN", ""),
        admin_bot_token=os.getenv("ADMIN_BOT_TOKEN", ""),
        admin_ids=_ids(os.getenv("ADMIN_IDS", "")),
        agent_chat_id=int(agent) if agent else None,
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
        shop_name=os.getenv("SHOP_NAME", "XAN SHOP"),
        delivery_text=os.getenv("DELIVERY_TEXT", "5–12 kun (Avia)"),
        return_policy=os.getenv("RETURN_POLICY", ""),
        card_number=os.getenv("CARD_NUMBER", "9860 3501 4182 4135"),
        card_owner=os.getenv("CARD_OWNER", "POLVONOV BEKMUROD"),
        auto_rates=os.getenv("AUTO_RATES", "1") == "1",
        cny_uzs=_float("CNY_UZS", "1800"),
        usd_uzs=_float("USD_UZS", "12000"),
        vykup_percent=_float("VYKUP_PERCENT", "0"),
        profit_percent=_float("PROFIT_PERCENT", "0"),
        payment_fee_percent=_float("PAYMENT_FEE_PERCENT", "0"),
        china_shipping_cny_per_item=_float("CHINA_SHIPPING_CNY_PER_ITEM", "0"),
        cargo_usd_per_kg=_float("CARGO_USD_PER_KG", "9.5"),
        cargo_client_uzs_per_kg=_float("CARGO_CLIENT_UZS_PER_KG", "120000"),
        cargo_collect_on_delivery=os.getenv("CARGO_COLLECT_ON_DELIVERY", "0") == "1",
        db_path=os.getenv("DB_PATH", "data/shop.db"),
        conversion_fee_percent=_float("CONVERSION_FEE_PERCENT", "2.5"),
        ensure_50_covers_cost=os.getenv("ENSURE_50_COVERS_COST", "1") == "1",
        prepay_round_to=int(float(os.getenv("PREPAY_ROUND_TO", "50000") or "50000")),
        channel_id=os.getenv("CHANNEL_ID", "").strip(),
        office_port=int(float(port_raw)),
        tg_api_id=os.getenv("TG_API_ID", "").strip(),
        tg_api_hash=os.getenv("TG_API_HASH", "").strip(),
        tg_phone=os.getenv("TG_PHONE", "").strip(),
        tg_session_string=os.getenv("TG_SESSION_STRING", "").strip(),
        manager_username=os.getenv("MANAGER_USERNAME", "").strip(),
        pdd_client_id=os.getenv("PDD_CLIENT_ID", "").strip(),
        pdd_client_secret=os.getenv("PDD_CLIENT_SECRET", "").strip(),
        pdd_rapidapi_key=os.getenv("PDD_RAPIDAPI_KEY", "").strip(),
        pdd_apify_token=(os.getenv("APIFY_API_TOKEN", "") or os.getenv("PDD_APIFY_TOKEN", "")).strip(),
        pdd_session_path=os.getenv("PDD_SESSION_PATH", "data/pdd_session.json").strip(),
        ig_user_id=os.getenv("IG_USER_ID", "").strip(),
        ig_access_token=os.getenv("IG_ACCESS_TOKEN", "").strip(),
        public_base_url=os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/"),
        auto_post_hours=_float("AUTO_POST_HOURS", "3.0"),
        bank_webhook_secret=os.getenv("BANK_WEBHOOK_SECRET", "").strip(),
        bank_bot_usernames=os.getenv(
            "BANK_BOT_USERNAMES",
            "HumoCardBot,CardXabarBot,UzcardBot,KapitalbankUzBot,IpakYoliBot",
        ).strip(),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY", "").strip(),
        openrouter_model=os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat").strip(),
        openrouter_base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").strip().rstrip("/"),
        omniroute_base_url=os.getenv("OMNIROUTE_BASE_URL", "http://localhost:20128/v1").strip().rstrip("/"),
        omniroute_api_key=os.getenv("OMNIROUTE_API_KEY", "omniroute-local").strip(),
        omniroute_model=os.getenv("OMNIROUTE_MODEL", "auto").strip(),
        use_omniroute=os.getenv("USE_OMNIROUTE", "1") == "1",
        ecc_root=os.getenv("ECC_ROOT", "vendor/ecc").strip(),
        hf_token=os.getenv("HF_TOKEN", "").strip(),
        fal_key=os.getenv("FAL_KEY", "").strip(),
        ai_voice_name=os.getenv("AI_VOICE_NAME", "uz-UZ-SardorNeural").strip(),
        enable_ai_voiceover=os.getenv("ENABLE_AI_VOICEOVER", "0") == "1",
    )
