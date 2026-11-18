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
