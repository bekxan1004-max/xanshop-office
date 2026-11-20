"""Narx kalkulyatori (sof funksiyalar, internet/DB ga bog'liq emas).

Model (XAN SHOP 50% / 100% tizimi):
  1) Xitoy xarajati (goods_cost_uzs) = (tovar CNY + Xitoy ichki yetkazish + vykup%) * kurs + UZS->CNY tranzaksiya komissiyasi
  2) Tovarning 100% sotuv narxi (prepay_uzs):
     - Oddiy rejimda: goods_cost_uzs + foyda% (+ to'lov komissiyasi)
     - 50% qoplash rejimida (ensure_50_covers_cost=True yoki profit_percent>=100):
       50% oldindan to'lov (prepay_50_uzs) Xitoydagi tovar narxi va UZS->CNY tranzaksiya komissiyasini
       100% qoplaydi (masalan: 42¥ = 79 000 so'm + tranzaksiya -> 50% to'lov = 90 000 so'm, 100% narx = 180 000 so'm).
  3) Mijoz tanlovi (ixtiyoriy):
     - 50% oldindan to'lov: hozir prepay_50_uzs to'laydi; yuk O'zbekistonga kelganda Qolgan 50% (remaining_50_uzs) + Kargo (real vazn bo'yicha) to'laydi.
     - 100% to'liq to'lov: hozir prepay_uzs (100%) to'laydi; yuk O'zbekistonga kelganda faqat Kargo to'laydi.
"""
import math
from dataclasses import dataclass


@dataclass
class Item:
    name: str
    price_cny: float
    weight_kg: float
    url: str = ""


@dataclass
class Rates:
    cny_uzs: float
    usd_uzs: float


@dataclass
class PriceParams:
    vykup_percent: float
    profit_percent: float
    payment_fee_percent: float
    china_shipping_cny_per_item: float
    cargo_usd_per_kg: float
    cargo_client_uzs_per_kg: float
    round_to: int = 1000
    prepay_round_to: int = 0            # Look sotuv narxini 50 000 / 100 000 so'm chegaraga yuqoriga yaxlitlash
    conversion_fee_percent: float = 0.0
    ensure_50_covers_cost: bool = False
    customs_duty_percent: float = 0.0   # YaTT tijoriy import boji zaxirasi (%)
    vat_percent: float = 0.0            # YaTT 12% QQS zaxirasi (%)
    tax_percent: float = 0.0            # YaTT aylanma soliq zaxirasi (%)


@dataclass
class PriceBreakdown:
    goods_cny: float
    china_shipping_cny: float
    vykup_cny: float
    total_cny: float
    goods_cost_uzs: int          # Xitoydagi jami xarajat + tranzaksiya (so'mda)
    profit_uzs: int              # tovardan sof foyda
    fee_uzs: int                 # to'lov/ekvayring komissiyasi
    prepay_uzs: int              # tovarning 100% sotuv narxi
    weight_kg: float
    cargo_cost_uzs: int          # kargoga o'zingiz to'laysiz (taxminiy)
    cargo_client_uzs: int        # mijozdan olinadigan kargo (taxminiy)
    total_client_uzs: int        # mijoz uchun jami (100% tovar + kargo)
    total_profit_uzs: int        # tovar foydasi + kargo farqi
    conversion_fee_uzs: int = 0  # UZS -> CNY konvertatsiya/tranzaksiya xarajati
    prepay_50_uzs: int = 0       # 50% oldindan to'lov summasi
    remaining_50_uzs: int = 0    # O'zbekistonga kelganda to'lanadigan qolgan 50% tovar summasi
    arrival_50_est_uzs: int = 0  # 50% tanlanganda O'zbekistonda to'lanadigan: qolgan 50% + kargo
    customs_uzs: int = 0         # YaTT rejimida import boji + QQS zaxirasi
    vat_uzs: int = 0             # YaTT QQS qismi
    tax_uzs: int = 0             # YaTT aylanma soliq zaxirasi


def round_up(value: float, step: int) -> int:
    if step <= 1:
        return int(math.ceil(value))
    return int(math.ceil(value / step) * step)


def round_look_price_uzs(x: float, step: int = 50_000) -> int:
    """Narxni 50 000 yoki 100 000 so'mlik chiroyli chegaraga YUQORIGA yaxlitlaydi (masalan 527k -> 550k, 560k -> 600k)."""
    return round_up(x, step if step > 0 else 50_000)


def cargo_charge(weight_kg: float, rates: Rates, p: PriceParams) -> tuple[int, int]:
    """(mijozdan olinadigan, kargoga to'lanadigan) so'mda."""
    cost = weight_kg * p.cargo_usd_per_kg * rates.usd_uzs
    client_rate = p.cargo_client_uzs_per_kg or p.cargo_usd_per_kg * rates.usd_uzs
    client = weight_kg * client_rate
    return round_up(client, p.round_to), int(round(cost))


def calculate(items: list[Item], rates: Rates, p: PriceParams) -> PriceBreakdown:
    if not items:
        raise ValueError("Kamida bitta buyum kerak")
    goods_cny = sum(i.price_cny for i in items)
    shipping_cny = p.china_shipping_cny_per_item * len(items)
    vykup_cny = (goods_cny + shipping_cny) * p.vykup_percent / 100
    total_cny = goods_cny + shipping_cny + vykup_cny

    base_uzs = total_cny * rates.cny_uzs
    conversion_fee = base_uzs * (p.conversion_fee_percent / 100)
    goods_cost = base_uzs + conversion_fee

    duty_uzs = goods_cost * (max(0.0, p.customs_duty_percent) / 100)
    vat_uzs = (goods_cost + duty_uzs) * (max(0.0, p.vat_percent) / 100)
    customs_total = duty_uzs + vat_uzs
    landed_cost = goods_cost + customs_total

    profit = landed_cost * p.profit_percent / 100
    payment_share = max(0.0, p.payment_fee_percent) / 100
    tax_share = max(0.0, p.tax_percent) / 100
    total_fee_share = min(0.95, payment_share + tax_share)
    raw_full_price = (landed_cost + profit) / (1 - total_fee_share)

    eff_prepay_step = p.prepay_round_to if p.prepay_round_to > 0 else p.round_to

    if p.ensure_50_covers_cost:
        # 50% oldindan to'lov Xitoydagi tovar narxi + barcha o'tkazma/foizlarni 100% qoplaydi (0 so'm o'z cho'ntagidan!),
        # kelganda mijoz yana xuddi shuncha 50% to'laydi (sof foyda) + kargo!
        half_step = max(p.round_to, eff_prepay_step // 2) if eff_prepay_step >= p.round_to * 2 else p.round_to
        min_half = round_up(landed_cost / (1 - total_fee_share), half_step)
        min_full = min_half * 2
        prepay = max(round_up(raw_full_price, eff_prepay_step), min_full)
    else:
        prepay = round_up(raw_full_price, eff_prepay_step)

    fee = prepay * payment_share
    tax_uzs = prepay * tax_share
    net_profit = prepay - fee - tax_uzs - landed_cost
    prepay_50 = round_up(prepay / 2, p.round_to)
    remaining_50 = max(0, prepay - prepay_50)

    weight = sum(i.weight_kg for i in items)
    cargo_client, cargo_cost = cargo_charge(weight, rates, p)

    return PriceBreakdown(
        goods_cny=round(goods_cny, 2),
        china_shipping_cny=round(shipping_cny, 2),
        vykup_cny=round(vykup_cny, 2),
        total_cny=round(total_cny, 2),
        goods_cost_uzs=int(round(goods_cost)),
        profit_uzs=int(round(net_profit)),
        fee_uzs=int(round(fee)),
        prepay_uzs=prepay,
        weight_kg=round(weight, 3),
        cargo_cost_uzs=cargo_cost,
        cargo_client_uzs=cargo_client,
        total_client_uzs=prepay + cargo_client,
        total_profit_uzs=int(round(net_profit + cargo_client - cargo_cost)),
        conversion_fee_uzs=int(round(conversion_fee)),
        prepay_50_uzs=prepay_50,
        remaining_50_uzs=remaining_50,
        arrival_50_est_uzs=remaining_50 + cargo_client,
        customs_uzs=int(round(customs_total)),
        vat_uzs=int(round(vat_uzs)),
        tax_uzs=int(round(tax_uzs)),
    )


def unique_amount(base: int, order_id: int) -> int:
    """Har bir buyurtma uchun oxirgi 3 raqami boshqacha summa (bank ilovasida tanib olish uchun)."""
    return base + (order_id % 1000)


def fmt(amount: float) -> str:
    """1234567 -> '1 234 567'"""
    return f"{int(round(amount)):,}".replace(",", " ")


def parse_items(text: str) -> list[Item]:
    """Har bir qator: nomi | narx ¥ | vazn kg | link (ixtiyoriy)."""
    items: list[Item] = []
    for n, line in enumerate(text.strip().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        parts = [x.strip() for x in line.split("|")]
        if len(parts) < 3:
            raise ValueError(f"{n}-qator: 'nomi | narx | vazn' formatida yozing")
        try:
            price = float(parts[1].replace(",", ".").replace("¥", ""))
            weight = float(parts[2].replace(",", ".").lower().replace("kg", ""))
        except ValueError as e:
            raise ValueError(f"{n}-qator: narx yoki vazn raqam emas") from e
        items.append(Item(parts[0], price, weight, parts[3] if len(parts) > 3 else ""))
    if not items:
        raise ValueError("Buyumlar topilmadi")
    return items
