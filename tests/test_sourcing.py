from app.config import Settings
from app.pricing import Rates
from app.sourcing import TrendSourcingAgent


def test_sourcing_fallback():
    settings = Settings(
        sales_bot_token="test",
        admin_bot_token="test",
        admin_ids=[123],
        agent_chat_id=None,
        gemini_api_key="",
        gemini_model="gemini-3.8-flash",
        shop_name="XAN SHOP",
        delivery_text="3-7 kun",
        return_policy="",
        card_number="",
        card_owner="",
        auto_rates=False,
        cny_uzs=1780.0,
        usd_uzs=12800.0,
        vykup_percent=5.0,
        profit_percent=30.0,
        payment_fee_percent=0.0,
        china_shipping_cny_per_item=5.0,
        cargo_usd_per_kg=9.5,
        cargo_client_uzs_per_kg=130000.0,
        cargo_collect_on_delivery=False,
        db_path=":memory:",
        pdd_session_path="tests/_nonexistent_pdd.json",
    )
    agent = TrendSourcingAgent(settings)
    look = agent.generate_look()

    assert look.title is not None
    assert look.prepay_uzs > 0
    assert look.cargo_est_uzs > 0
    assert len(look.raw_items) >= 3


def test_pinduoduo_fetch_product_details(tmp_path):
    import asyncio
    from app.pinduoduo import PinduoduoConnector

    async def _test():
        conn = PinduoduoConnector(session_path=str(tmp_path / "sess.json"))
        # 1. Catalog lookup
        res = await conn.fetch_product_details("619842109312")
        assert res["ok"] is True
        assert res["goods_id"] == "619842109312"
        assert res["total_price_uzs"] > 0
        assert res["prepay_50_uzs"] > 0
        assert res["remaining_50_uzs"] > 0
        assert res["prepay_50_uzs"] + res["remaining_50_uzs"] == res["total_price_uzs"]

        # 2. URL parsing
        url = "https://mobile.yangkeduo.com/goods.html?goods_id=598271635490&page_from=39"
        res_url = await conn.fetch_product_details(url)
        assert res_url["ok"] is True
        assert res_url["goods_id"] == "598271635490"

    asyncio.run(_test())


def test_pinduoduo_apify_poros_parser_and_mode(tmp_path):
    import json
    from app.pinduoduo import PinduoduoConnector

    conn = PinduoduoConnector(
        session_path=str(tmp_path / "no_sess.json"),
        apify_token="apify_api_test_token_123",
    )
    assert conn.is_live_api is True
    assert conn.connection_mode == "apify_pdd_live"
    assert PinduoduoConnector._compact_cn_query("老钱风双排扣羊毛呢大衣男秋冬加厚英伦外套") == "男 羊毛呢大衣 外套"

    sample_obj = {
        "goods_id": 991664725516,
        "goods_name": "男士老钱风羊毛呢大衣外套",
        "min_on_sale_group_price": 18900,
        "gallery_urls": ["//img.pddpic.com/gaudit-image/2026-10-01/sample.jpeg"],
        "side_sales_tip": "已抢120件",
    }
    encoded_chunk = json.dumps(json.dumps(sample_obj, ensure_ascii=False))
    fake_html = f'<script>self.__next_f.push([1,{encoded_chunk}])</script>'
    parsed = PinduoduoConnector.parse_poros_products(fake_html)
    assert len(parsed) == 1
    assert parsed[0]["goods_id"] == 991664725516
    assert parsed[0]["min_on_sale_group_price"] == 18900


def test_store_size_chart_winter_fit_and_admin_pdd_links():
    import json
    from app.sizes import recommend_for_look
    from app.texts import admin_order_card

    look = {
        "id": 12,
        "title": "Qishki Old Money Kapsula",
        "colors": "To'q jigarrang, Qora",
        "sizes": "M, L, XL, 2XL",
        "items_json": json.dumps([
            {
                "category": "outerwear",
                "name": "Qishki Jun Palto",
                "price_cny": 239.0,
                "pdd_goods_id": "307246992745",
                "url": "https://mobile.yangkeduo.com/goods.html?goods_id=307246992745",
                "store_sizes": ["48", "50", "52", "54"],
                "size_chart": [
                    {"size": "50", "height_cm": "175", "weight_kg": "70"},
                    {"size": "52", "height_cm": "180", "weight_kg": "75"},
                    {"size": "54", "height_cm": "185", "weight_kg": "80"},
                ],
            },
            {
                "category": "shoes",
                "name": "Qishki Chelsea Etik",
                "price_cny": 178.0,
                "pdd_goods_id": "845650894237",
                "url": "https://mobile.yangkeduo.com/goods.html?goods_id=845650894237",
                "store_sizes": ["40", "41", "42", "43", "44"],
            },
        ], ensure_ascii=False),
    }
    rec = recommend_for_look(178, 75, look, foot_cm=26.0)
    assert rec["primary_clothing_size"] == "54"  # winter +1 size up from 52
    assert rec["has_shoes"] is True
    assert rec["per_item"][1]["size"] == "43"  # winter shoe +0.5cm from 42 -> 43

    card = admin_order_card(
        {
            "id": 5, "look_id": 12, "status": "paid", "size": "Kiyim: 54 | Oyoq: 43",
            "color": "Rasmdagidek", "payment_plan": "50", "prepay_due": 500005,
            "remaining_uzs": 500000, "profit_uzs": 250000, "full_name": "Ali",
            "username": "ali_uz", "user_id": 1, "phone": "+998901112233", "address": "Toshkent",
        },
        look,
    )
    assert "https://mobile.yangkeduo.com/goods.html?goods_id=307246992745" in card
    assert "https://mobile.yangkeduo.com/goods.html?goods_id=845650894237" in card
