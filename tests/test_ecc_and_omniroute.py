import asyncio
import json
from aiohttp.test_utils import TestClient, TestServer
from app.config import load_settings
from app.dashboard import build_dashboard_app
from app.db import Database
from app.ecc_engine import ECCRegistry, build_graphify_context_index
from app.logistics import cargo_address_specs
from app.office import AgentOffice
from app.pinduoduo import PinduoduoConnector, get_pdd_session_details, has_valid_pdd_session, import_pdd_session


def test_ecc_registry_71_agents_314_skills_and_graphify():
    reg = ECCRegistry("vendor/ecc")
    assert len(reg.agents) == 71
    assert len(reg.skills) == 314
    assert "chief-of-staff" in reg.agents
    assert "marketing-agent" in reg.agents
    assert "video-editing" in reg.skills
    assert "token-budget-advisor" in reg.skills

    graph = build_graphify_context_index("app")
    assert graph["modules"] >= 10
    assert graph["functions"] >= 20
    assert "ecc_engine.py" in graph["compact_map"]


def test_dashboard_ecc_catalog_endpoint(tmp_path):
    async def _run():
        s = load_settings()
        db = Database(str(tmp_path / "ecc_dash.db"))
        await db.connect()
        try:
            office = AgentOffice(db=db, settings=s, media_dir=str(tmp_path / "media"))
            app = build_dashboard_app(db, s, office)
            async with TestClient(TestServer(app)) as client:
                r_html = await client.get("/")
                assert r_html.status == 200
                html_txt = await r_html.text()
                assert "virtual-office-canvas" in html_txt
                assert "tab-ecc" in html_txt
                assert "office3d.js" in html_txt

                r_js = await client.get("/static/office3d.js")
                assert r_js.status == 200

                r1 = await client.get("/api/state")
                assert r1.status == 200
                st = await r1.json()
                assert st["ecc_summary"]["repo_agents_count"] == 71
                assert st["ecc_summary"]["repo_skills_count"] == 314
                assert st["ecc_summary"]["agents_count"] == 15
                assert st["ecc_summary"]["skills_count"] == 25
                assert "omniroute" in st

                r2 = await client.get("/api/ecc/catalog")
                assert r2.status == 200
                cat = await r2.json()
                assert cat["agents_count"] == 15
                assert cat["skills_count"] == 25
                assert cat["repo_agents_count"] == 71
                assert cat["repo_skills_count"] == 314
                assert len(cat["agents"]) == 15
                ids = {a["id"] for a in cat["agents"]}
                assert "marketing-agent" in ids
                assert "cpp-reviewer" not in ids
                assert "rust-reviewer" not in ids
                skill_ids = {sk["id"] for sk in cat["skills"]}
                assert "customs-trade-compliance" in skill_ids
                assert "rust-patterns" not in skill_ids

                r3 = await client.get("/api/ecc/catalog?scope=all")
                assert r3.status == 200
                cat_all = await r3.json()
                assert len(cat_all["agents"]) == 71

                # Raqobatbardosh (Optimal 65% + 50k yaxlitlash) va YaTT Bojxona kalkulyator rejimlari
                r_comp = await client.get("/api/calc?cny=45+48+42&weight=1.3&mode=competitive")
                assert r_comp.status == 200
                c_comp = await r_comp.json()
                assert 400000 <= c_comp["prepay_uzs"] <= 500000
                assert c_comp["prepay_uzs"] % 50000 == 0

                r_yatt = await client.get("/api/calc?cny=135&weight=1.3&mode=yatt_customs")
                assert r_yatt.status == 200
                c_yatt = await r_yatt.json()
                assert c_yatt["customs_uzs"] > 0 and c_yatt["tax_uzs"] > 0

                # Boshqaruvchi AI strategik tahlili va narx rejimini saqlash
                r_apply = await client.post("/api/ceo/apply_pricing", json={"mode": "competitive"})
                assert r_apply.status == 200
                ap = await r_apply.json()
                assert ap["ok"] is True
                assert ap["params"]["profit_percent"] == 65.0

                r_ceo = await client.post("/api/ceo/analyze", json={"apply_directives": True})
                assert r_ceo.status == 200
                ceo = await r_ceo.json()
                assert ceo["ok"] is True
                assert len(ceo["directives"]) >= 3

                # Ombor tozalash API
                r_clr = await client.post("/api/looks/clear")
                assert r_clr.status == 200
                assert (await r_clr.json())["ok"] is True
        finally:
            await db.close()

    asyncio.run(_run())


def test_pdd_endpoints_cargo_specs_and_order_prep(tmp_path):
    async def _run():
        sess_path = tmp_path / "pdd_sess.json"
        assert has_valid_pdd_session(str(sess_path)) is False
        sess_path.write_text(
            json.dumps({
                "cookies": [],
                "origins": [{
                    "origin": "https://mobile.yangkeduo.com",
                    "localStorage": [
                        {"name": "pdd_user_id", "value": "889900"},
                        {"name": "PDDAccessToken", "value": "tok_ls_1"},
                    ],
                }],
            }),
            encoding="utf-8",
        )
        assert has_valid_pdd_session(str(sess_path)) is True
        details = get_pdd_session_details(str(sess_path))
        assert details["connected"] is True and details["user_id"] == "889900"

        specs = cargo_address_specs()
        codes = {c["code"] for c in specs}
        assert codes == {"TUJJOR-AVIA", "DOOR-AVIA"}

        from dataclasses import replace
        s = replace(load_settings(), pdd_session_path=str(sess_path))
        db = Database(str(tmp_path / "pdd_dash.db"))
        await db.connect()
        try:
            lid = await db.add_look(
                title="Test PDD Capsule",
                items=[{"name": "Xudi", "price_cny": 48, "weight_kg": 0.5, "pdd_goods_id": "598271635490"}],
                sizes="L,XL",
                colors="Qora",
                price={
                    "prepay_uzs": 360000,
                    "prepay_50_uzs": 180000,
                    "remaining_50_uzs": 180000,
                    "profit_uzs": 100000,
                    "goods_cost_uzs": 180000,
                    "weight_kg": 0.5,
                    "cargo_client_uzs": 55000,
                },
            )
            oid = await db.create_order(
                user_id=777,
                username="test_client",
                full_name="Test Mijoz",
                phone="+998901112233",
                address="Toshkent, Yunusobod",
                look_id=lid,
                size="XL",
                color="Qora",
                payment_plan="50",
                prepay_due=180001,
                remaining_uzs=180000,
                profit_uzs=100000,
                goods_cost_uzs=180000,
                status="paid",
            )
            office = AgentOffice(db=db, settings=s, media_dir=str(tmp_path / "media"))
            app = build_dashboard_app(db, s, office)
            async with TestClient(TestServer(app)) as client:
                r_st = await client.get("/api/pdd/status")
                assert r_st.status == 200
                st = await r_st.json()
                assert st["connected"] is True
                assert st["mode"] == "browser_session"
                assert len(st["cargo_addresses"]) == 2

                r_prep = await client.post(f"/api/orders/{oid}/prepare_pdd")
                assert r_prep.status == 200
                pkt = await r_prep.json()
                assert pkt["ok"] is True
                assert pkt["client_size"] == "XL"
                assert pkt["cargo"]["code"] == "TUJJOR-AVIA"
                assert pkt["items"][0]["goods_id"] == "598271635490"

                r_cred = await client.post("/api/pdd/credentials", json={"client_id": "cid_test", "client_secret": "sec_test"})
                assert r_cred.status == 200
                cr = await r_cred.json()
                assert cr["connected"] is True and cr["mode"] == "official_api"

                imp_path = tmp_path / "pdd_import.json"
                imp = import_pdd_session("PDDAccessToken=tok_cookie_123456; pdd_user_id=990011", str(imp_path))
                assert imp["ok"] is True and imp["user_id"] == "990011"
                r_imp = await client.post("/api/pdd/import_session", json={"session_data": "PDDAccessToken=tok_api_123456; pdd_user_id=778899"})
                assert r_imp.status == 200
                ij = await r_imp.json()
                assert ij["ok"] is True and ij["user_id"] == "778899"
        finally:
            import os
            os.environ.pop("PDD_CLIENT_ID", None)
            os.environ.pop("PDD_CLIENT_SECRET", None)
            await db.close()

    asyncio.run(_run())


def test_pdd_cookie_editor_metadata_and_app_only_search_error(tmp_path, monkeypatch):
    from dataclasses import replace

    sess_path = tmp_path / "pdd_cookie_editor.json"
    raw_cookies = json.dumps([
        {
            "name": "PDDAccessToken",
            "value": "tok_cookie_editor_123456",
            "domain": "mobile.yangkeduo.com",
            "path": "/",
            "expirationDate": 1799999999.5,
            "httpOnly": True,
            "secure": True,
            "sameSite": "no_restriction",
        },
        {
            "name": "pdd_user_id",
            "value": "1969996097454",
            "domain": "mobile.yangkeduo.com",
            "path": "/custom",
            "httpOnly": False,
            "secure": True,
            "sameSite": "strict",
        },
    ])
    imp = import_pdd_session(raw_cookies, str(sess_path))
    assert imp["ok"] is True and imp["user_id"] == "1969996097454"

    saved = json.loads(sess_path.read_text(encoding="utf-8"))
    by_name = {c["name"]: c for c in saved["cookies"]}
    assert by_name["PDDAccessToken"]["httpOnly"] is True
    assert by_name["PDDAccessToken"]["sameSite"] == "None"
    assert by_name["PDDAccessToken"]["expires"] == 1799999999.5
    assert by_name["pdd_user_id"]["path"] == "/custom"
    assert by_name["pdd_user_id"]["sameSite"] == "Strict"
    assert by_name["pdd_user_id"]["expires"] == -1

    err_state = {"code": "search_app_only"}

    async def _fake_search_live(self, keyword_cn: str, page_size: int = 5):
        self.last_error = err_state["code"]
        return []

    monkeypatch.setattr(PinduoduoConnector, "search_live", _fake_search_live)

    async def _run():
        s = replace(load_settings(), pdd_session_path=str(sess_path))
        db = Database(str(tmp_path / "pdd_err.db"))
        await db.connect()
        try:
            office = AgentOffice(db=db, settings=s, media_dir=str(tmp_path / "media"))
            app = build_dashboard_app(db, s, office)
            async with TestClient(TestServer(app)) as client:
                resp = await client.post("/api/pdd/test_search", json={"keyword": "卫衣男", "save_wishlist": False})
                assert resp.status == 200
                data = await resp.json()
                assert data["ok"] is False
                assert data["mode"] == "browser_session"
                assert "系统繁忙" in data["error"]
                assert "TUJJOR-AVIA" in data["error"]

                err_state["code"] = "session_expired"
                resp2 = await client.post("/api/pdd/test_search", json={"keyword": "卫衣男", "save_wishlist": False})
                assert resp2.status == 200
                data2 = await resp2.json()
                assert data2["ok"] is False
                assert "session_expired" in data2["error"]
        finally:
            await db.close()

    asyncio.run(_run())
