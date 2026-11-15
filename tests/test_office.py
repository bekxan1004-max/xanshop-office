import asyncio
import json
import os
from app.config import Settings
from app.db import Database
from app.office import AgentOffice


def test_agent_office_full_pipeline(tmp_path):
    async def _run():
        db_file = str(tmp_path / "office_test.db")
        media_dir = str(tmp_path / "photos")
        db = Database(db_file)
        await db.connect()

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
            card_number="8600 0000 0000 0000",
            card_owner="XAN SHOP",
            auto_rates=False,
            cny_uzs=1880.0,
            usd_uzs=12800.0,
            vykup_percent=5.0,
            profit_percent=105.0,
            payment_fee_percent=0.0,
            china_shipping_cny_per_item=5.0,
            cargo_usd_per_kg=9.5,
            cargo_client_uzs_per_kg=130000.0,
            cargo_collect_on_delivery=False,
            db_path=db_file,
            conversion_fee_percent=3.0,
            ensure_50_covers_cost=True,
            pdd_session_path=str(tmp_path / "no_pdd_sess.json"),
        )

        office = AgentOffice(db=db, settings=settings, media_dir=media_dir)
        # 1-sikl (4 qismli), 2-sikl (3 qismli), 3-sikl (2 qismli), 4-sikl (5 qismli)
        counts = []
        for _ in range(4):
            res = await office.run_look_pipeline()
            counts.append(res.piece_count)
            assert res.prepay_50_uzs >= res.goods_cost_uzs
            assert res.prepay_50_uzs + res.remaining_50_uzs == res.prepay_uzs
            assert os.path.exists(res.photo_path)
            assert os.path.exists(res.video_path)
            assert os.path.exists(res.insta_caption_path)
            if os.path.exists(res.mp4_path):
                assert os.path.getsize(res.mp4_path) > 1000

            saved = await db.get_look(res.look_id)
            assert saved["palette_name"] == res.palette_name
            assert json.loads(saved["palette_hex"]) == res.palette_hex

        assert set(counts) == {2, 3, 4, 5}

        agents = {a["agent_id"]: a for a in await db.list_agents()}
        assert agents["video_employee"]["boss_id"] == "smm_manager"
        assert agents["insta_analyst"]["tasks_done"] == 4
        assert agents["skaut"]["tasks_done"] == 4
        assert agents["video_employee"]["tasks_done"] == 4
        assert agents["smm_manager"]["tasks_done"] == 4

        logs = await db.list_agent_logs(limit=30)
        assert len(logs) >= 12
        await db.close()

    asyncio.run(_run())
