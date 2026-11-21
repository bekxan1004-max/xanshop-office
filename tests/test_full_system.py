import asyncio
import json
import os
from aiohttp.test_utils import TestClient, TestServer

from app.accountant import AccountantAgent, is_verbal_payment_claim, parse_bank_deposit_text
from app.config import Settings
from app.dashboard import build_dashboard_app
from app.db import Database
from app.logistics import LogisticsAgent
from app.office import AgentOffice
from app.pinduoduo import PinduoduoConnector, has_valid_pdd_session, parse_pdd_search_dom_items


def _make_settings(db_file: str) -> Settings:
    return Settings(
        sales_bot_token="",
        admin_bot_token="",
        admin_ids=[1],
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
        china_shipping_cny_per_item=0.0,
        cargo_usd_per_kg=9.5,
        cargo_client_uzs_per_kg=130000.0,
        cargo_collect_on_delivery=False,
        db_path=db_file,
        conversion_fee_percent=3.0,
        ensure_50_covers_cost=True,
        manager_username="xan_manager",
        pdd_session_path=db_file + ".pdd.json",
    )


def test_pdd_sign_and_logistics(tmp_path):
    async def _run():
        pdd = PinduoduoConnector(client_id="cid", client_secret="secret123")
        sig = pdd._sign_pdd_params({"type": "pdd.ddk.goods.search", "client_id": "cid", "timestamp": "100"})
        assert len(sig) == 32 and sig.isupper()

        sess_file = tmp_path / "pdd_session.json"
        assert has_valid_pdd_session(str(sess_file)) is False
        sess_file.write_text(json.dumps({"cookies": [{"name": "PDDAccessToken", "value": "tok123"}]}), encoding="utf-8")
        assert has_valid_pdd_session(str(sess_file)) is True
        pdd_browser = PinduoduoConnector(session_path=str(sess_file))
        assert pdd_browser.is_live_api is True

        parsed = parse_pdd_search_dom_items(
            [
                {"href": "goods.html?goods_id=619842109312", "text": "Oversize Bomber Kurtka\n¥89.5\n已拼10万+件", "img": "//img.pddpic.com/a.jpg"},
                {"href": "goods.html?goods_id=619842109312", "text": "Duplicate\n¥89.5", "img": ""},
            ],
            keyword_cn="夹克",
        )
        assert len(parsed) == 1
        assert parsed[0].goods_id == "619842109312"
        assert parsed[0].price_cny == 89.5
        assert parsed[0].image_url == "https://img.pddpic.com/a.jpg"

        db = Database(str(tmp_path / "logi.db"))
        await db.connect()
        s = _make_settings(str(tmp_path / "logi.db"))
        logi = LogisticsAgent(db, s)

        assert logi.select_cargo_line("Toshkent, Yunusobod 4").code in ("DTD-AVIA", "MK-AVIA")
        assert logi.select_cargo_line("Samarqand, Registon").code == "DTD-AVIA"
        assert logi.select_cargo_line("Toshkent MK filial").code == "MK-AVIA"

        look_id = await db.add_look(
            title="Test Shoe Look",
            items=[{"name": "Retro Krossovka", "price_cny": 42, "weight_kg": 0.8, "pdd_goods_id": "551029384756"}],
            sizes="41,42,43",
            colors="Qora",
            price={
                "prepay_uzs": 180000,
                "prepay_50_uzs": 90000,
                "remaining_50_uzs": 90000,
                "profit_uzs": 95000,
                "goods_cost_uzs": 85000,
                "weight_kg": 0.8,
                "cargo_client_uzs": 104000,
            },
        )
        oid = await db.create_order(
            user_id=999,
            username="ali",
            full_name="Ali Valiyev",
            phone="+998901234567",
            address="Toshkent, Chilonzor",
            look_id=look_id,
            size="42",
            color="Qora",
            payment_plan="50",
            prepay_due=90001,
            remaining_uzs=90000,
            profit_uzs=95000,
            goods_cost_uzs=85000,
            status="arrived",
            source="userbot",
        )
        order = await db.get_order(oid)
        assert order["source"] == "userbot"

        settlement = await logi.calculate_arrival_settlement(order, weight_kg=1.0)
        assert settlement.cargo_line.code == "DTD-AVIA"
        assert settlement.remaining_50_uzs == 90000
        assert settlement.cargo_client_uzs == 130000
        assert settlement.total_due_unique_uzs == 220001  # 90000 + 130000 + (oid % 1000)

        card = logi.build_vykup_card(order, await db.get_look(look_id))
        assert "551029384756" in card
        assert "DTD-AVIA" in card
        assert "ID BP-1" in card
        assert "18124205652" in card
        await db.close()

    asyncio.run(_run())


def test_dashboard_routes(tmp_path):
    async def _run():
        db_file = str(tmp_path / "dash.db")
        db = Database(db_file)
        await db.connect()
        s = _make_settings(db_file)
        office = AgentOffice(db=db, settings=s, media_dir=str(tmp_path / "media"))
        app = build_dashboard_app(db, s, office)

        async with TestClient(TestServer(app)) as client:
            r_health = await client.get("/health")
            assert r_health.status == 200
            h_json = await r_health.json()
            assert h_json["status"] == "ok"

            r_home = await client.get("/")
            assert r_home.status == 200
            html = await r_home.text()
            assert "XAN SHOP" in html

            r_calc = await client.get("/api/calc?cny=42&weight=0.8")
            assert r_calc.status == 200
            calc = await r_calc.json()
            assert calc["prepay_50_uzs"] >= calc["goods_cost_uzs"]

            r_state = await client.get("/api/state")
            assert r_state.status == 200
            st = await r_state.json()
            assert len(st["agents"]) == 9
            assert any(a["agent_id"] == "photo_studio" for a in st["agents"])
            assert "weather" in st
            assert "channel_kit" in st
            assert "bank_transactions" in st
        await db.close()

    asyncio.run(_run())


def test_accountant_parser_duplicate_and_webhook(tmp_path):
    async def _run():
        assert parse_bank_deposit_text("HUMO *4321 Popolnenie +90 013.00 UZS")[0] == 90013
        assert parse_bank_deposit_text("HUMO *4321 Popolnenie +90 013.00 UZS")[1] == "4321"
        assert parse_bank_deposit_text("UZCARD **8899 Kirim: +220 001 so'm") == (220001, "8899")
        assert parse_bank_deposit_text("Spisanie s karty *4321 -90 000 UZS")[0] is None
        assert parse_bank_deposit_text("Oplata pokupki 150 000 UZS")[0] is None
        assert is_verbal_payment_claim("ha men to'lov qildim") is True
        assert is_verbal_payment_claim("pulni tashladim aka") is True
        assert is_verbal_payment_claim("Oplatil na kartu") is True
        assert is_verbal_payment_claim("qanday to'lov qilaman?") is False
        assert is_verbal_payment_claim("50% qancha bo'ladi?") is False

        db_file = str(tmp_path / "acc.db")
        db = Database(db_file)
        await db.connect()
        s = _make_settings(db_file)
        s = Settings(**{**s.__dict__, "card_number": "9860 1234 5678 4321", "bank_webhook_secret": "sec123"})

        look_id = await db.add_look(
            title="Accountant Look",
            items=[{"name": "Kurtka", "price_cny": 42, "weight_kg": 0.8}],
            sizes="L,XL",
            colors="Qora",
            price={
                "prepay_uzs": 180000,
                "prepay_50_uzs": 90000,
                "remaining_50_uzs": 90000,
                "profit_uzs": 95000,
                "goods_cost_uzs": 85000,
                "weight_kg": 0.8,
                "cargo_client_uzs": 104000,
            },
        )
        o1_id = await db.create_order(
            user_id=101,
            username="u1",
            full_name="Ali",
            phone="+998901112233",
            address="Toshkent",
            look_id=look_id,
            size="L",
            color="Qora",
            payment_plan="50",
            prepay_due=90013,
            remaining_uzs=90000,
            profit_uzs=95000,
            goods_cost_uzs=85000,
            status="awaiting_payment",
        )
        o2_id = await db.create_order(
            user_id=102,
            username="u2",
            full_name="Vali",
            phone="+998904445566",
            address="Samarqand",
            look_id=look_id,
            size="XL",
            color="Qora",
            payment_plan="50",
            prepay_due=90014,
            remaining_uzs=90000,
            profit_uzs=95000,
            goods_cost_uzs=85000,
            status="awaiting_payment",
        )

        acc = AccountantAgent(db, s)
        warn_o1 = await AccountantAgent.check_verbal_payment_text(db, 101, "To'lov qildim")
        assert warn_o1 is not None and "og'zaki" in warn_o1.lower()
        assert (await db.get_order(o1_id))["status"] == "awaiting_payment"
        assert await AccountantAgent.check_verbal_payment_text(db, 101, "Salom, razmeri bormi?") is None

        fake_img = b"real_click_receipt_bytes_001"
        v1, msg1 = await acc.handle_uploaded_receipt(await db.get_order(o1_id), fake_img)
        assert v1.verdict == "ai_verified"
        assert msg1 is not None
        assert (await db.get_order(o1_id))["status"] == "payment_review"

        # Bir xil chekni 2-buyurtmaga qayta yuborish -> Anti-Duplicate bloklashi kerak
        v_dup, msg_dup = await acc.handle_uploaded_receipt(await db.get_order(o2_id), fake_img)
        assert v_dup.verdict == "duplicate"
        assert "avval" in msg_dup.lower()
        assert (await db.get_order(o2_id))["status"] == "awaiting_payment"

        # Webhook orqali bank kirim xabari -> o1 avtomatik 'paid' bolishi kerak
        office = AgentOffice(db=db, settings=s, media_dir=str(tmp_path / "media"))
        app = build_dashboard_app(db, s, office)
        async with TestClient(TestServer(app)) as client:
            r_unauth = await client.post("/api/bank_webhook", json={"text": "Popolnenie *4321 +90 013 UZS"})
            assert r_unauth.status == 403

            r_ok = await client.post(
                "/api/bank_webhook",
                headers={"X-Webhook-Secret": "sec123"},
                json={"text": "HUMO *4321 Popolnenie +90 013.00 UZS", "source": "macrodroid"},
            )
            assert r_ok.status == 200
            body = await r_ok.json()
            assert body["matched"] is True
            assert body["order_id"] == o1_id
            assert (await db.get_order(o1_id))["status"] == "paid"

            # Teskari tartib: avval bank SMS (+90 014 UZS), keyin mijoz cheki
            r_early = await client.post(
                "/api/bank_webhook",
                json={"secret": "sec123", "text": "Kirim *4321 +90 014 UZS", "source": "humo"},
            )
            # Avval buyurtma awaiting_payment da bor edi -> birdan tasdiqlaydi!
            assert (await r_early.json())["matched"] is True
            assert (await db.get_order(o2_id))["status"] == "paid"

            # Bank tushumi buyurtma yaratilishidan OLDIN kelgan holat (unmatched tx -> keyin chek yuborilganda auto_approved)
            r_pre = await client.post(
                "/api/bank_webhook",
                json={"secret": "sec123", "text": "Kirim *4321 +90 015 UZS", "source": "humo"},
            )
            assert (await r_pre.json())["matched"] is False
            o3_id = await db.create_order(
                user_id=103, username="u3", full_name="Hasan", phone="+998907778899", address="Farg'ona",
                look_id=look_id, size="L", color="Qora", payment_plan="50", prepay_due=90015,
                remaining_uzs=90000, profit_uzs=95000, goods_cost_uzs=85000, status="awaiting_payment",
            )
            v3, msg3 = await acc.handle_uploaded_receipt(await db.get_order(o3_id), b"receipt_for_o3_unique_90015")
            assert v3.verdict == "auto_approved" and v3.auto_approved is True
            assert msg3 is None
            assert (await db.get_order(o3_id))["status"] == "paid"

        await db.close()

    asyncio.run(_run())


def test_photo_studio_kontext_and_custom_look_creator(tmp_path):
    async def _run():
        import base64
        import io
        from PIL import Image, ImageDraw
        from app.photo_studio import (
            PhotoStudioAgent,
            _build_kontext_edit_instruction,
            _isolate_from_clean_white_studio_bg,
            _verify_regenerated_rgba,
        )
        from app.sourcing import TrendSourcingAgent

        s = _make_settings(str(tmp_path / "custom.db"))
        # 1) Studio isolatori oq fondan qora shimni ham, ustki kurtkani ham oq qirrasiz va kesmasdan ajratadi
        studio_sheet = Image.new("RGB", (300, 300), (255, 255, 255))
        drw = ImageDraw.Draw(studio_sheet)
        drw.rectangle([60, 40, 240, 260], fill=(18, 20, 24))
        rgba = _isolate_from_clean_white_studio_bg(studio_sheet, category="bottom")
        assert rgba.mode == "RGBA"
        assert _verify_regenerated_rgba(rgba) is True
        assert rgba.info.get("xan_studio_regenerated") == "1"

        # 2) Kontext buyrug'i kategoriyaga mos yoziladi
        p_bot = _build_kontext_edit_instruction({"name": "Qora Klassik Drape Shim", "category": "bottom"})
        assert "shoes" in p_bot.lower() and "ankle hems" in p_bot.lower()

        # 3) PhotoStudioAgent kontekst regeneratsiyasi mock orqali 100% ishlaydi
        agent = PhotoStudioAgent(s)
        buf = io.BytesIO()
        studio_sheet.save(buf, format="PNG")
        agent._call_hf_kontext_img2img_sync = lambda *_a, **_kw: buf.getvalue()
        monkey_orig = os.environ.get("PYTEST_CURRENT_TEST")
        os.environ["XAN_PHOTO_STUDIO_IN_TESTS"] = "1"
        try:
            st_res = await agent.render_product_studio_async(
                studio_sheet,
                {"name": "Qora Oversize Svitshot", "category": "top"},
                use_cache=False,
            )
            assert st_res.used_nano_banana is True
            assert st_res.model_used == "hf_flux_kontext_img2img"
        finally:
            os.environ.pop("XAN_PHOTO_STUDIO_IN_TESTS", None)
            if monkey_orig is not None:
                os.environ["PYTEST_CURRENT_TEST"] = monkey_orig

        # 4) Custom Look Blueprint Parser (matn + rasm + kargo shim taqiqi)
        skaut = TrendSourcingAgent(s)
        bp = await skaut.build_custom_look_blueprint_async(
            prompt_text="Jigarrang zamsh kurtka, qora svitshot, qora kargo shim va chelsea etik yig'",
            piece_count=4,
        )
        assert len(bp["items"]) == 4
        assert all("kargo" not in str(it["name"]).lower() for it in bp["items"])

        # 5) Dashboard /api/looks/custom_create endpointi rasm + buyruq bilan Look yaratadi
        db_file = str(tmp_path / "dash_custom.db")
        db = Database(db_file)
        await db.connect()
        s_dash = _make_settings(db_file)
        office = AgentOffice(db=db, settings=s_dash, media_dir=str(tmp_path / "media"))
        app = build_dashboard_app(db, s_dash, office)
        img_b64 = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
        async with TestClient(TestServer(app)) as client:
            r_bad = await client.post("/api/looks/custom_create", json={})
            assert r_bad.status == 400

            r_ok = await client.post(
                "/api/looks/custom_create",
                json={
                    "prompt": "Jigarrang zamsh kurtka va qora klassik shimdan iborat 3 qismli look yig'",
                    "media_b64": img_b64,
                    "media_mime": "image/png",
                    "piece_count": 3,
                    "max_prepay_50_uzs": 350000,
                },
            )
            assert r_ok.status == 200
            payload = await r_ok.json()
            assert payload["ok"] is True
            assert payload["piece_count"] >= 2
            assert payload["prepay_50_uzs"] % 50000 == 0
        await db.close()

    asyncio.run(_run())
