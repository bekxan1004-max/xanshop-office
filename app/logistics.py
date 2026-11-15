"""XAN SHOP - Vykup & Kargo Agent (LogisticsAgent).

2 ta Avia Kargo liniyasini (Door-to-Door $9.5/kg va Tujjor Avia $9.5/kg — jami 5–10 kun)
aqlli boshqaradi, Pinduoduo vykup varaqasini shakllantiradi, kechikayotgan yuklarni
nazorat qiladi va Toshkentga kelganda Qolgan 50% + Real Kargo hisobini chiqaradi.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from html import escape
from typing import Any

from .config import Settings
from .db import Database
from .economy import get_params, get_rates
from .pricing import cargo_charge, fmt, unique_amount
from .texts import look_items


@dataclass(frozen=True)
class CargoLine:
    code: str
    name: str
    rate_usd_kg: float
    eta_days: str
    mode: str
    client_id: str
    cn_recipient: str
    cn_phone: str
    cn_address: str


CARGO_LINES: dict[str, CargoLine] = {
    "door_to_door": CargoLine(
        code="DOOR-AVIA",
        name="Avia Door-to-Door (Shenzhen)",
        rate_usd_kg=9.5,
        eta_days="5–10 kun",
        mode="Kuryer mijoz eshigigacha eltib beradi",
        client_id="ID BP-1",
        cn_recipient="徐安吉 ID BP-1",
        cn_phone="18124205652",
        cn_address="广东省深圳市宝安区福永街道怀德南路199号锦城大厦5008 ID BP-1",
    ),
    "tujjor_avia": CargoLine(
        code="TUJJOR-AVIA",
        name="Tujjor Avia Express (Yiwu)",
        rate_usd_kg=9.5,
        eta_days="5–10 kun",
        mode="Tezkor avia reys (Toshkent ombori / kuryer)",
        client_id="T-7621",
        cn_recipient="T-7621",
        cn_phone="15757912326",
        cn_address="浙江省金华市义乌市苏溪镇东洪新村11栋3单元1号门 (T-7621)",
    ),
}


def cargo_address_specs() -> list[dict[str, str]]:
    """Pinduoduo manzil kitobi uchun 2 ta tasdiqlangan Xitoy kargo omborining tuzilgan maydonlari."""
    return [
        {
            "key": "tujjor_avia",
            "code": CARGO_LINES["tujjor_avia"].code,
            "name": CARGO_LINES["tujjor_avia"].name,
            "client_id": CARGO_LINES["tujjor_avia"].client_id,
            "cn_recipient": CARGO_LINES["tujjor_avia"].cn_recipient,
            "cn_phone": CARGO_LINES["tujjor_avia"].cn_phone,
            "province": "浙江省",
            "city": "金华市",
            "district": "义乌市",
            "street": "苏溪镇东洪新村11栋3单元1号门 (T-7621)",
            "cn_address": CARGO_LINES["tujjor_avia"].cn_address,
            "route_rule": "Toshkent shahar buyurtmalari uchun (5–10 kun)",
        },
        {
            "key": "door_to_door",
            "code": CARGO_LINES["door_to_door"].code,
            "name": CARGO_LINES["door_to_door"].name,
            "client_id": CARGO_LINES["door_to_door"].client_id,
            "cn_recipient": CARGO_LINES["door_to_door"].cn_recipient,
            "cn_phone": CARGO_LINES["door_to_door"].cn_phone,
            "province": "广东省",
            "city": "深圳市",
            "district": "宝安区",
            "street": "福永街道怀德南路199号锦城大厦5008 ID BP-1",
            "cn_address": CARGO_LINES["door_to_door"].cn_address,
            "route_rule": "Viloyatlar va eshikgacha yetkazish uchun (5–10 kun)",
        },
    ]


@dataclass(frozen=True)
class ArrivalSettlement:
    order_id: int
    weight_kg: float
    cargo_line: CargoLine
    remaining_50_uzs: int
    cargo_client_uzs: int
    cargo_cost_uzs: int
    total_due_unique_uzs: int
    net_order_profit_uzs: int


class LogisticsAgent:
    """Vykup, Xitoy ombori, 2 ta Avia Kargo liniyasi va Toshkent yakuniy hisob-kitob agenti."""

    def __init__(self, db: Database, settings: Settings):
        self.db = db
        self.s = settings

    def select_cargo_line(self, address: str) -> CargoLine:
        """Mijoz manziliga qarab optimal kargo liniyasini tanlaydi."""
        addr_low = (address or "").lower()
        if any(k in addr_low for k in ("toshkent", "tashkent", "yunusobod", "chilonzor", "mirzo", "sergeli", "shayxontohur")):
            return CARGO_LINES["tujjor_avia"]
        return CARGO_LINES["door_to_door"]

    def build_vykup_card(self, order: dict[str, Any], look: dict[str, Any]) -> str:
        """Siz Pinduoduo'da to'lashingiz uchun tayyor xarid kartasi (Door-to-Door / Tujjor kargo ombori manzili bilan)."""
        line = self.select_cargo_line(order.get("address", ""))
        items = look_items(look)
        plan = order.get("payment_plan") or "50"

        rows = [
            f"🧾 <b>PINDUODUO XARID KARTASI (SIZ UCHUN TAYYOR) — BUYURTMA #{order['id']}</b>",
            f"✈️ <b>Kargo liniyasi:</b> {line.name} (<code>{line.code}</code> · ${line.rate_usd_kg}/kg · {line.eta_days})",
            f"🏷 <b>Kargo ombor kodi:</b> <code>{escape(line.client_id)}</code> (Buyurtma: <code>XAN-{order['id']}</code>)",
            "",
            "🇨🇳 <b>PINDUODUO / TAOBAO YETKAZISH MANZILI (Nusxa oling):</b>",
            f"• 收件人 (Oluvchi): <code>{escape(line.cn_recipient)}</code>",
            f"• 手机号码 (Tel): <code>{escape(line.cn_phone)}</code>",
            f"• 详细地址 (Manzil): <code>{escape(line.cn_address)}</code>",
            "",
            "<b>Xarid qilinadigan buyumlar (Pinduoduo / Taobao):</b>",
        ]
        for idx, it in enumerate(items, 1):
            cny = it.get("price_cny", it.get("cny", 0))
            pdd_id = it.get("pdd_goods_id", "")
            rows.append(f"{idx}) <b>{escape(it['name'])}</b> — <b>¥{cny:g}</b>")
            if it.get("cn_keyword"):
                rows.append(f"   🇨🇳 Qidiruv: <code>{escape(it['cn_keyword'])}</code>")
            if pdd_id:
                rows.append(f"   🆔 PDD ID: <code>{pdd_id}</code>")
            if it.get("url"):
                rows.append(f"   🔗 {escape(it['url'])}")

        rows += [
            "",
            f"📏 <b>Razmer:</b> <code>{escape(order.get('size') or 'XL')}</code>",
            f"🎨 <b>Rang:</b> <code>{escape(order.get('color') or 'Standart')}</code>",
            f"💳 <b>Mijoz to'lovi:</b> {plan}% to'langan ({fmt(order.get('prepay_due', 0))} so'm)",
            "",
            f"👤 <b>Qabul qiluvchi:</b> {escape(order.get('full_name') or '')}",
            f"📞 <b>Tel:</b> <code>{escape(order.get('phone') or '')}</code>",
            f"🏠 <b>Manzil:</b> {escape(order.get('address') or '')}",
            "",
            f"📸 <i>Xitoy omboriga kelganda QC rasmni izohga <code>#{order['id']}</code> yozib yuboring!</i>",
        ]
        return "\n".join(rows)

    async def calculate_arrival_settlement(self, order: dict[str, Any], weight_kg: float) -> ArrivalSettlement:
        """Yuk O'zbekistonga kelganda Qolgan 50% + Real Kargo hisobini va sof foydani chiqaradi."""
        rates = await get_rates(self.db, self.s)
        params = await get_params(self.db, self.s)
        client_cargo, cost_cargo = cargo_charge(weight_kg, rates, params)
        rem_50 = int(order.get("remaining_uzs") or 0)
        base_due = rem_50 + client_cargo
        due_unique = unique_amount(base_due, int(order["id"]))

        line = self.select_cargo_line(order.get("address", ""))
        net_profit = int(order.get("profit_uzs") or 0) + (client_cargo - cost_cargo)

        return ArrivalSettlement(
            order_id=int(order["id"]),
            weight_kg=weight_kg,
            cargo_line=line,
            remaining_50_uzs=rem_50,
            cargo_client_uzs=client_cargo,
            cargo_cost_uzs=cost_cargo,
            total_due_unique_uzs=due_unique,
            net_order_profit_uzs=net_profit,
        )

    async def check_sla_alerts(self) -> list[str]:
        """Uzoq vaqt bir joyda turib qolgan buyurtmalarni aniqlaydi."""
        now = int(time.time())
        alerts: list[str] = []
        for o in await self.db.active_orders(limit=50):
            age_hours = (now - int(o.get("updated_at") or now)) / 3600.0
            if o["status"] == "paid" and age_hours > 12:
                alerts.append(f"⚠️ Buyurtma #{o['id']} to'langaniga {age_hours:.0f} soat bo'ldi — Pinduoduo'dan vykup qiling!")
            elif o["status"] == "bought" and age_hours > 48 and not o.get("tracking"):
                alerts.append(f"⚠️ Buyurtma #{o['id']} uchun hali Xitoy trek-kodi (/trek {o['id']} KOD) kiritilmagan!")
        return alerts
