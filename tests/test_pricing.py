from app.pricing import (
    Item,
    PriceParams,
    Rates,
    calculate,
    cargo_charge,
    fmt,
    parse_items,
    round_look_price_uzs,
    round_up,
    unique_amount,
)
from app.sizes import recommend
from app.trends import _classify_weather, analyze_competitor_account, extract_instagram_handle

RATES = Rates(cny_uzs=1800, usd_uzs=12800)
PARAMS = PriceParams(vykup_percent=5, profit_percent=30, payment_fee_percent=0,
                     china_shipping_cny_per_item=5, cargo_usd_per_kg=9.5, cargo_client_uzs_per_kg=130000)


def test_calculate_example():
    items = [Item("Xudi", 80, 1.0), Item("Shim", 60, 0.8)]
    b = calculate(items, RATES, PARAMS)
    # (140 + 10) * 1.05 = 157.5 ¥ -> 283 500 so'm
    assert b.total_cny == 157.5
    assert b.goods_cost_uzs == 283500
    # 283 500 * 1.3 = 368 550 -> 1000 ga yaxlitlanadi
    assert b.prepay_uzs == 369000
    assert b.profit_uzs == 369000 - 283500
    # 1.8 kg * 130 000 = 234 000; tannarx 1.8 * 9.5 * 12800 = 218 880
    assert b.cargo_client_uzs == 234000
    assert b.cargo_cost_uzs == 218880
    assert b.total_client_uzs == 369000 + 234000
    assert b.total_profit_uzs == (369000 - 283500) + (234000 - 218880)


def test_payment_fee_is_covered():
    p = PriceParams(**{**PARAMS.__dict__, "payment_fee_percent": 2})
    b = calculate([Item("A", 100, 1)], RATES, p)
    assert b.prepay_uzs - b.fee_uzs - b.goods_cost_uzs >= b.goods_cost_uzs * 0.3 - 1


def test_cargo_without_client_rate_uses_cost():
    p = PriceParams(**{**PARAMS.__dict__, "cargo_client_uzs_per_kg": 0})
    client, cost = cargo_charge(2, RATES, p)
    assert cost == 243200 and client == 244000


def test_helpers():
    assert round_up(1001, 1000) == 2000
    assert unique_amount(675000, 13) == 675013
    assert unique_amount(675000, 1013) == 675013
    assert fmt(1234567) == "1 234 567"


def test_parse_items():
    items = parse_items("Xudi | 89 | 0.7 | https://x\nShim|65¥|0,5kg")
    assert [i.price_cny for i in items] == [89, 65]
    assert items[1].weight_kg == 0.5 and items[0].url == "https://x"
    for bad_fn in (lambda: parse_items("faqat nom"), lambda: calculate([], RATES, PARAMS)):
        try:
            bad_fn()
            raise AssertionError("ValueError kutilgan edi")
        except ValueError:
            pass


def test_sizes():
    assert recommend(175, 70, ["M", "L", "XL", "XXL"]) == "XL"
    assert recommend(188, 70, ["M", "L", "XL", "XXL"]) == "XXL"
    assert recommend(170, 120, ["M", "L"]) == "L"          # eng kattasi
    assert recommend(170, 45, ["L", "XL"]) == "L"           # kichigi yo'q -> eng yaqin kattasi
    assert recommend(175, 70, ["44", "46"]) is None         # raqamli o'lchamlar
    assert recommend(175, 70, []) == "XL"


def test_50_percent_covers_cost_and_transaction():
    # Misol: 42 yuan poyabzal, 1 yuan = 1880 so'm -> 42 * 1880 = 78 960 (~79 ming so'm)
    rates = Rates(cny_uzs=1880, usd_uzs=12800)
    p = PriceParams(
        vykup_percent=5,
        profit_percent=105,
        payment_fee_percent=0,
        china_shipping_cny_per_item=0,
        cargo_usd_per_kg=9.5,
        cargo_client_uzs_per_kg=130000,
        conversion_fee_percent=3,
        ensure_50_covers_cost=True,
    )
    b = calculate([Item("Krossovka", 42, 0.8)], rates, p)
    # 50% oldindan to'lov Xitoy tannarxi + UZS->CNY tranzaksiya komissiyasini to'liq qoplashi shart!
    assert b.prepay_50_uzs >= b.goods_cost_uzs
    assert b.prepay_uzs == 176000 or (170000 <= b.prepay_uzs <= 186000)
    assert b.prepay_50_uzs + b.remaining_50_uzs == b.prepay_uzs
    assert b.arrival_50_est_uzs == b.remaining_50_uzs + b.cargo_client_uzs


def test_competitive_capsule_and_yatt_customs_modes():
    rates = Rates(cny_uzs=1800, usd_uzs=12000)
    # 3 qismli kapsula (¥135 = 243k), 45% bozor ustamasi, 0% vykup, 0¥ pochta -> ~365k (380k benchmark!)
    comp_params = PriceParams(
        vykup_percent=0,
        profit_percent=45,
        payment_fee_percent=0,
        china_shipping_cny_per_item=0,
        cargo_usd_per_kg=8.5,
        cargo_client_uzs_per_kg=105000,
        conversion_fee_percent=2.5,
        ensure_50_covers_cost=False,
    )
    comp = calculate([Item("Xudi", 45, 0.5), Item("Shim", 48, 0.45), Item("Lofer", 42, 0.35)], rates, comp_params)
    assert 350000 <= comp.prepay_uzs <= 395000
    assert comp.customs_uzs == 0

    # YaTT rejimi ($200+ oshganda): 15% boj + 12% QQS + 4% soliq hisobga olinadi
    yatt_params = PriceParams(
        vykup_percent=0,
        profit_percent=45,
        payment_fee_percent=0,
        china_shipping_cny_per_item=0,
        cargo_usd_per_kg=4.5,
        cargo_client_uzs_per_kg=60000,
        conversion_fee_percent=2.5,
        ensure_50_covers_cost=False,
        customs_duty_percent=15.0,
        vat_percent=12.0,
        tax_percent=4.0,
    )
    yatt = calculate([Item("Optom Xudi", 34, 0.5), Item("Optom Shim", 36, 0.45)], rates, yatt_params)
    assert yatt.customs_uzs > 0
    assert yatt.vat_uzs > 0
    assert yatt.tax_uzs > 0
    assert yatt.profit_uzs > 0


def test_50k_upward_rounding_and_65_percent_margin():
    assert round_look_price_uzs(527000, 50000) == 550000
    assert round_look_price_uzs(555000, 50000) == 600000

    # Foydalanuvchi misoli: 360k tannarx + 40% foyda + komissiya (527k) -> 550k ga yuqoriga yaxlitlanadi
    rates = Rates(cny_uzs=1800, usd_uzs=12000)
    p40 = PriceParams(0, 40, 4.5, 0, 9.5, 115000, prepay_round_to=50000, conversion_fee_percent=0)
    b40 = calculate([Item("Kapsula", 200, 1.0)], rates, p40)
    assert b40.prepay_uzs == 550000
    assert b40.prepay_50_uzs + b40.remaining_50_uzs == b40.prepay_uzs

    # Yangi 65% marja: 360k * 1.65 = 594k -> 600 000 so'm
    p65 = PriceParams(0, 65, 0, 0, 9.5, 115000, prepay_round_to=50000, conversion_fee_percent=0)
    b65 = calculate([Item("Kapsula", 200, 1.0)], rates, p65)
    assert b65.prepay_uzs == 600000
    assert b65.profit_uzs == 240000


def test_insta_competitor_intelligence_and_handle_parser():
    handle = extract_instagram_handle(
        "https://www.instagram.com/_tima_shop?utm_source=ig_web_button_share_sheet&cplk=ZDNlZDc0MzIxNw=="
    )
    assert handle == "_tima_shop"
    rep = analyze_competitor_account(handle)
    assert rep["handle"] == "@_tima_shop"
    assert "+" in rep["koment_triggers"] and "komment" in rep["koment_triggers"].lower()
    assert "5–10 kun" in rep["xan_shop_counter_strategy"]
    assert len(rep["hook_patterns"]) >= 2
    season, advice = _classify_weather(6.5, 11.0, cur_temp=15.0)
    assert "sovuq" in season
    assert "5–10 kunda" in advice and "15°C" in advice and ("~6°C" in advice or "~7°C" in advice)


def test_v3_self_learning_and_video_directive():
    import asyncio
    from app.config import load_settings
    from app.db import Database
    from app.trends import build_video_creative_directive

    s = load_settings()
    assert "4135" in s.card_number
    assert "POLVONOV BEKMUROD" in s.card_owner.upper()
    assert s.enable_ai_voiceover is False

    directive = build_video_creative_directive(
        look_title="170-185 sm Cleanfit Capsule",
        piece_count=3,
        total_price_uzs=600000,
        prepay_50_uzs=300000,
        palette_name="Obsidian Gold",
        palette_hex=["#16171B", "#D8A848"],
        audio_vibe="phonk_bass",
    )
    assert directive["version"] == "v3.0"
    assert directive["target_agent"] == "video_employee"
    assert "STRICT_NO_VOICEOVER" in directive["voiceover_policy"]
    assert len(directive["scene_plan"]) == 4

    async def _check_db():
        db = Database(":memory:")
        await db.connect()
        try:
            learnings = await db.record_agent_learning(
                "video_employee",
                "Test V3 lesson: Split-screen + qora kapsula subtitr konversiyani oshirdi.",
                xp_gain=120,
            )
            assert any("Test V3 lesson" in x for x in learnings)
            agents = await db.list_agents()
            ve = next(a for a in agents if a["agent_id"] == "video_employee")
            assert ve["version"] == "v3.0"
            assert ve["xp"] >= 1120
            assert ve["level"] >= 11
        finally:
            await db.close()

    asyncio.run(_check_db())


def test_pinduoduo_only_and_winter_old_money_rules():
    from dataclasses import replace
    from app.config import load_settings
    from app.ig_analytics import evaluate_seasonal_styling_rules
    from app.pinduoduo import PinduoduoConnector
    from app.sourcing import TrendSourcingAgent

    rules = evaluate_seasonal_styling_rules({"cur_temp": 8.0, "forecast_5_10d_min": 3.0, "forecast_5_10d_max": 10.0})
    assert rules["is_cold_season"] is True
    assert rules["forbid_tshirts"] is True

    pdd = PinduoduoConnector()
    matched = pdd.match_verified_item("outerwear", "Qishki Jun Palto", "羊毛大衣男", 138.0, 1.15)
    assert matched["url"].startswith("https://mobile.yangkeduo.com/search_result.html?search_key=")
    assert "1688.com" not in matched["url"]

    s = replace(load_settings(), gemini_api_key="", pdd_rapidapi_key="")
    agent = TrendSourcingAgent(s)
    agent._fallback_idx = 0
    look = agent.generate_look()
    assert look.piece_count >= 3
    names_low = " ".join(i.get("name", "").lower() for i in look.raw_items)
    assert "futbolka" not in names_low
    assert "kargo" not in names_low
    for item in look.raw_items:
        assert "1688.com" not in (item.get("url") or "")
        assert "yangkeduo.com" in (item.get("url") or "")


def test_halol_ogri_db_and_real_audio_tracks(tmp_path):
    import asyncio
    from dataclasses import replace
    from app.config import load_settings
    from app.db import Database
    from app.ig_analytics import run_live_instagram_analyst_async
    from app.media import synthesize_reels_beat_wav

    out_wav = tmp_path / "out_beat.wav"
    audio_res = synthesize_reels_beat_wav(out_wav, duration_sec=3.0, vibe="diplomat_old_money")
    assert audio_res
    assert ("diplomat_old_money" in audio_res) or str(out_wav) == audio_res

    async def _check():
        db = Database(":memory:")
        await db.connect()
        try:
            s = replace(load_settings(), ig_access_token="", gemini_api_key="")
            intel = await run_live_instagram_analyst_async(db, s, cycle_idx=0)
            ho = intel["halol_ogri"]
            assert ho["accounts_tracked"] >= 5
            assert ho["videos_analyzed"] >= 4
            assert "Pinduoduo Skaut" in ho["scout_brief"]
            assert "Video Montajchi" in ho["video_brief"]
            accs = await db.list_competitor_accounts()
            vids = await db.list_competitor_videos()
            assert len(accs) >= 5 and len(vids) >= 4
            assert all(v["competitor_sell_price_uzs"] > 0 and v["estimated_profit_uzs"] > 0 for v in vids)
        finally:
            await db.close()

    asyncio.run(_check())


def test_open_source_learner_and_nonrigid_flexibility(tmp_path):
    import asyncio
    from dataclasses import replace
    from app.config import load_settings
    from app.db import Database
    from app.source_learner import format_playbooks_for_ai, parse_source_url
    from app.sourcing import InstagramTrendBrief, TrendSourcingAgent

    assert parse_source_url("https://t.me/uz_menswear_test")[:2] == ("telegram", "tg:uz_menswear_test")
    assert parse_source_url("https://www.instagram.com/reel/DfwuRH0TXX5/?vrfl=123")[:2] == ("ig_reel", "reel:DfwuRH0TXX5")
    assert parse_source_url("https://www.instagram.com/stylesh.uz/")[:2] == ("instagram", "ig:stylesh.uz")

    # Ochiq/erkin tizim: AI tanlagan noodatiy/yangi buyumni qattiq qolipga majburlab o'zgartirib yubormasligi kerak!
    s = replace(load_settings(), gemini_api_key="", pdd_rapidapi_key="")
    agent = TrendSourcingAgent(s)
    brief = InstagramTrendBrief(
        trend_name="Diplomat Old Money",
        recommended_piece_count=2,
        color_palette_name="Cream",
        color_hex_list=["#111111"],
        viral_hook_uz="Test",
        audio_vibe="diplomat_old_money",
        conversion_reason="Test",
    )
    ai_raw = {
        "title": "Erkin Klassik Kardigan Seti",
        "items": [
            {"category": "outerwear", "name": "Merino Yengil Kardigan", "price_cny": 79.0, "weight_kg": 0.45, "cn_keyword": "羊毛开衫男"},
            {"category": "bottom", "name": "Bej Chinos Shim", "price_cny": 65.0, "weight_kg": 0.45, "cn_keyword": "休闲卡其裤男"},
        ],
    }
    res = agent._enforce_seasonal_and_persona_rules(ai_raw, brief)
    assert res["items"][0]["name"] == "Merino Yengil Kardigan"
    assert res["items"][1]["name"] == "Bej Chinos Shim"
    assert all("yangkeduo.com/search_result.html" in it["url"] for it in res["items"])

    async def _check_db():
        db = Database(":memory:")
        await db.connect()
        try:
            await db.upsert_tracked_source(
                source_key="tg:sample_shop",
                platform="telegram",
                url="https://t.me/sample_shop",
                style_summary="Ochiq foto-albom va narx",
            )
            await db.save_learned_playbook(
                "tg_channel_strategy",
                {"format": "photo_album", "trust_building": "real_video_review"},
                source_refs=["https://t.me/sample_shop"],
            )
            srcs = await db.list_tracked_sources()
            pbs = await db.get_all_playbooks()
            assert len(srcs) == 1
            assert "photo_album" in format_playbooks_for_ai(pbs)
        finally:
            await db.close()

    asyncio.run(_check_db())

    from app.admin_bot import ADMIN_BOT_COMMANDS, HELP, build_admin_router
    assert any(c.command == "manba" for c in ADMIN_BOT_COMMANDS)
    assert any(c.command == "tg_holat" for c in ADMIN_BOT_COMMANDS)
    assert "/manba" in HELP and ".mp4" in HELP
    router = build_admin_router(s)
    assert router is not None


def test_agent_reach_deep_video_and_remotion():
    import json
    from pathlib import Path
    from app.agent_reach_client import (
        exa_web_search,
        jina_read_url,
        youtube_search_videos,
        fetch_video_metadata_ytdlp,
    )
    from app.source_learner import analyze_video_file_blueprint
    from app.media import render_reels_with_remotion

    assert all(
        callable(fn)
        for fn in (
            exa_web_search,
            jina_read_url,
            youtube_search_videos,
            fetch_video_metadata_ytdlp,
            analyze_video_file_blueprint,
            render_reels_with_remotion,
        )
    )
    assert render_reels_with_remotion("unused_remotion_test.mp4", {}) is None

    studio = Path("remotion_studio")
    pkg = json.loads((studio / "package.json").read_text(encoding="utf-8"))
    assert "remotion" in (pkg.get("dependencies") or {})
    assert (studio / "render_reel.mjs").is_file()
    assert (studio / "src" / "Root.tsx").is_file()
    look_tsx = (studio / "src" / "LookReel.tsx").read_text(encoding="utf-8")
    assert "minHeight: 0" in look_tsx
    assert "minmax(0, 1fr)" in look_tsx


if __name__ == "__main__":
    test_calculate_example()
    test_payment_fee_is_covered()
    test_cargo_without_client_rate_uses_cost()
    test_helpers()
    test_parse_items()
    test_sizes()
    test_agent_reach_deep_video_and_remotion()
    print("OK")
