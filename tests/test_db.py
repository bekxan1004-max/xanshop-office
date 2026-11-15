import asyncio

from app.db import Database


def test_db_flow(tmp_path):
    async def run():
        db = Database(str(tmp_path / "test.db"))
        await db.connect()
        try:
            await db.set_setting("cny_uzs", 1800)
            assert await db.get_setting("cny_uzs") == "1800"

            lid = await db.add_look(
                "Qishki look",
                [{"name": "Xudi", "price_cny": 80, "weight_kg": 0.8, "url": "https://x"}],
                "M,L,XL",
                "Qora,Oq",
                {"prepay_uzs": 369000, "profit_uzs": 85500, "goods_cost_uzs": 283500,
                 "weight_kg": 0.8, "cargo_client_uzs": 104000},
            )
            assert len(await db.list_looks()) == 1

            oid = await db.create_order(
                user_id=111, username="ali", full_name="Ali Valiyev", phone="+998901234567",
                address="Toshkent", look_id=lid, size="XL", color="Qora",
                prepay_due=369001, profit_uzs=85500, goods_cost_uzs=283500, status="awaiting_payment",
            )
            assert (await db.payable_order(111))["id"] == oid
            await db.update_order(oid, status="paid", tracking="YT123")
            assert await db.payable_order(111) is None
            assert (await db.get_order(oid))["tracking"] == "YT123"
            assert len(await db.active_orders()) == 1

            await db.set_interaction(111, "inter_1")
            assert await db.get_interaction(111) == "inter_1"
        finally:
            await db.close()

    asyncio.run(run())
