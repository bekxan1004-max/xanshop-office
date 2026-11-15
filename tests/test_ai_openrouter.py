import asyncio
import json
from types import SimpleNamespace

from app.accountant import AccountantAgent
from app.ai import SalesAI, extract_json_dict
from app.config import Settings
from app.db import Database
from app.sourcing import TrendSourcingAgent
from app.trends import WeatherForecast, analyze_instagram_creative_strategy


def _base_settings(**overrides) -> Settings:
    defaults = dict(
        sales_bot_token="",
        admin_bot_token="",
        admin_ids=[],
        agent_chat_id=None,
        gemini_api_key="",
        gemini_model="gemini-3.8-flash",
        shop_name="XAN SHOP",
        delivery_text="3-7 kun",
        return_policy="",
        card_number="9860 1234 5678 4321",
        card_owner="XAN SHOP",
        auto_rates=False,
        cny_uzs=1880,
        usd_uzs=12800,
        vykup_percent=5,
        profit_percent=105,
        payment_fee_percent=0,
        china_shipping_cny_per_item=5,
        cargo_usd_per_kg=9.5,
        cargo_client_uzs_per_kg=130000,
        cargo_collect_on_delivery=False,
        db_path=":memory:",
        pdd_session_path="tests/_nonexistent_pdd.json",
    )
    defaults.update(overrides)
    return Settings(**defaults)


def test_sales_ai_openrouter_init():
    # Test setting up SalesAI with OpenRouter settings
    dummy_settings = _base_settings(
        db_path="data/test_ai.db",
        openrouter_api_key="sk-or-v1-dummy-test-key",
        openrouter_model="deepseek/deepseek-chat",
    )
    ai = SalesAI(dummy_settings)
    assert ai.enabled is True
    assert ai.openrouter_api_key == "sk-or-v1-dummy-test-key"
    assert ai.openrouter_model == "deepseek/deepseek-chat"


def test_extract_json_dict_and_gemini_model_fallback(monkeypatch):
    parsed = extract_json_dict("Mana:\n```json\n{\"ok\": true, \"count\": 3}\n```")
    assert parsed == {"ok": True, "count": 3}
    assert extract_json_dict("not json at all") is None

    s = _base_settings(gemini_api_key="fake-key", gemini_model="gemini-3.6-flash", use_omniroute=False)
    ai = SalesAI(s)
    assert ai._gemini_model_candidates() == ["gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]

    tried: list[str] = []

    class FakeInteractions:
        def create(self, **kwargs):
            m = kwargs["model"]
            tried.append(m)
            if m == "gemini-3.6-flash":
                raise RuntimeError("429 RESOURCE_EXHAUSTED")
            return SimpleNamespace(output_text="Salom! Yordam beraman.", id="int-ok-1")

    ai.client = SimpleNamespace(interactions=FakeInteractions())

    ans, iid, need_admin = asyncio.run(ai.reply("System", "Salom", "prev-1"))
    assert ans == "Salom! Yordam beraman."
    assert iid == "int-ok-1"
    assert need_admin is False
    assert ai.last_provider_used == "Gemini (gemini-3.5-flash-lite)"
    assert tried == ["gemini-3.6-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite"]


def test_sourcing_trends_and_accountant_use_omniroute(tmp_path, monkeypatch):
    async def _run():
        s = _base_settings(
            gemini_api_key="",
            use_omniroute=True,
            omniroute_base_url="http://mock-omni.local/v1",
            omniroute_model="xanshop-auto",
            db_path=str(tmp_path / "ai_acc.db"),
            pdd_session_path=str(tmp_path / "no_pdd.json"),
        )
        calls: list[str] = []

        async def fake_compat(self, base_url, api_key, model, system, text, media_bytes=None, mime_type="", timeout_sec=25.0):
            calls.append(model)
            if "REELS strategiyasi" in text:
                return json.dumps({
                    "trend_name": "OmniRoute Capsule",
                    "recommended_piece_count": 3,
                    "color_palette_name": "Obsidian",
                    "color_hex_list": ["#111111", "#FFFFFF"],
                    "viral_hook_uz": "TOP OBRAZ!",
                    "audio_vibe": "luxury_chill",
                    "conversion_reason": "Zo'r stil",
                })
            if "chekimi yo'qmi" in text:
                return json.dumps({
                    "is_receipt": False,
                    "amount_uzs": 0,
                    "receiver_card_last4": "",
                    "tx_id": "",
                    "status_ok": False,
                    "fraud_signs": "karta surati emas",
                })
            return json.dumps({
                "title": "OmniRoute Minimal Look",
                "description": "Sifatli capsule",
                "colors": "Qora",
                "sizes": "M, L, XL",
                "items": [
                    {"category": "top", "name": "Hudi", "price_cny": 45.0, "weight_kg": 0.6, "cn_keyword": "连帽卫衣"},
                    {"category": "bottom", "name": "Shim", "price_cny": 40.0, "weight_kg": 0.5, "cn_keyword": "休闲长裤"},
                ],
            })

        monkeypatch.setattr(SalesAI, "_call_openai_compat", fake_compat)

        weather = WeatherForecast(city="Toshkent", temp_c=14.0, min_c=10.0, max_c=18.0, season_uz="kuz", clothing_advice="xudi")
        strat = await analyze_instagram_creative_strategy(None, s.gemini_model, weather, settings=s)
        assert strat is not None and strat["trend_name"] == "OmniRoute Capsule"

        skaut = TrendSourcingAgent(s)
        import app.sourcing as sourcing_mod
        async def _fake_weather():
            return weather
        monkeypatch.setattr(sourcing_mod, "fetch_tashkent_weather", _fake_weather)
        look = await skaut.generate_look_async()
        assert look.title == "OmniRoute Minimal Look"
        assert look.piece_count == 2

        db = Database(str(tmp_path / "ai_acc.db"))
        await db.connect()
        look_id = await db.add_look(
            title="Test", items=look.raw_items, sizes="M,L", colors="Qora",
            price={"prepay_uzs": 200000, "prepay_50_uzs": 100000, "remaining_50_uzs": 100000, "profit_uzs": 50000, "goods_cost_uzs": 90000, "weight_kg": 1.1, "cargo_client_uzs": 140000},
        )
        oid = await db.create_order(
            user_id=77, username="ali", full_name="Ali", phone="+998901112233", address="Toshkent",
            look_id=look_id, size="L", color="Qora", payment_plan="50",
            prepay_due=100077, remaining_uzs=100000, profit_uzs=50000, goods_cost_uzs=90000, status="awaiting_payment",
        )
        acc = AccountantAgent(db, s)
        verdict = await acc.inspect_and_verify_receipt(await db.get_order(oid), b"not-a-receipt-bytes")
        assert verdict.verdict == "suspicious_fake"
        assert "cheki emas" in verdict.reason.lower()
        assert calls.count("xanshop-auto") == 4
        await db.close()

    asyncio.run(_run())
