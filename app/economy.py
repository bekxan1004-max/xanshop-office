"""Kurslar (CBU) va narx parametrlari: DB dagi qo'lda o'rnatilgan qiymatlar .env dan ustun."""
import asyncio
import logging

import aiohttp

from .config import Settings
from .db import Database
from .pricing import PriceParams, Rates

log = logging.getLogger(__name__)
CBU_URL = "https://cbu.uz/uz/arkhiv-kursov-valyut/json/"


async def get_rates(db: Database, s: Settings) -> Rates:
    cny = await db.get_setting("cny_uzs")
    usd = await db.get_setting("usd_uzs")
    return Rates(float(cny) if cny else s.cny_uzs, float(usd) if usd else s.usd_uzs)


async def get_params(db: Database, s: Settings) -> PriceParams:
    profit = await db.get_setting("profit_percent")
    vykup = await db.get_setting("vykup_percent")
    cn_ship = await db.get_setting("china_shipping_cny_per_item")
    conv_fee = await db.get_setting("conversion_fee_percent")
    ensure_50 = await db.get_setting("ensure_50_covers_cost")
    cargo_client = await db.get_setting("cargo_client_uzs_per_kg")
    prepay_round = await db.get_setting("prepay_round_to")
    return PriceParams(
        vykup_percent=float(vykup) if vykup is not None else s.vykup_percent,
        profit_percent=float(profit) if profit is not None else s.profit_percent,
        payment_fee_percent=s.payment_fee_percent,
        china_shipping_cny_per_item=float(cn_ship) if cn_ship is not None else s.china_shipping_cny_per_item,
        cargo_usd_per_kg=s.cargo_usd_per_kg,
        cargo_client_uzs_per_kg=float(cargo_client) if cargo_client is not None else s.cargo_client_uzs_per_kg,
        prepay_round_to=int(float(prepay_round)) if prepay_round is not None else getattr(s, "prepay_round_to", 50000),
        conversion_fee_percent=float(conv_fee) if conv_fee is not None else s.conversion_fee_percent,
        ensure_50_covers_cost=(ensure_50 == "1") if ensure_50 is not None else s.ensure_50_covers_cost,
    )


async def fetch_cbu() -> Rates | None:
    """O'zbekiston Markaziy banki rasmiy kursi."""
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(CBU_URL) as resp:
                data = await resp.json(content_type=None)
        by_ccy = {row["Ccy"]: float(row["Rate"]) for row in data}
        return Rates(cny_uzs=by_ccy["CNY"], usd_uzs=by_ccy["USD"])
    except Exception as e:  # internet yo'q, format o'zgargan va h.k.
        log.warning("CBU kursini olib bo'lmadi: %s", e)
        return None


async def refresh_rates(db: Database, s: Settings) -> tuple[Rates, Rates] | None:
    """Kursni yangilaydi. (eski, yangi) qaytaradi yoki None."""
    new = await fetch_cbu()
    if not new:
        return None
    old = await get_rates(db, s)
    await db.set_setting("cny_uzs", round(new.cny_uzs, 2))
    await db.set_setting("usd_uzs", round(new.usd_uzs, 2))
    return old, new


async def rates_loop(db: Database, s: Settings, alert, every_hours: float = 6) -> None:
    """Har N soatda kursni yangilaydi; 3% dan ko'p o'zgarsa adminga xabar beradi."""
    while True:
        if s.auto_rates:
            result = await refresh_rates(db, s)
            if result:
                old, new = result
                change = abs(new.cny_uzs - old.cny_uzs) / old.cny_uzs * 100
                if change >= 3:
                    await alert(
                        f"⚠️ Yuan kursi {change:.1f}% o'zgardi: {old.cny_uzs:.0f} → {new.cny_uzs:.0f}.\n"
                        "Look narxlarini yangilash uchun: /qayta_hisob")
        await asyncio.sleep(every_hours * 3600)
