"""Ixcham, sodda va tushunarli matnlar (V3.2 — Sotuv Bot, Admin Bot va Kanal uchun)."""
import json

from .config import Settings
from .pricing import fmt

def tg_escape(text: str) -> str:
    """Telegram Bot API HTML parse_mode xavfsiz ekranlash (Telegram &#x27; ni qo'llamaydi, faqat &lt;, &gt;, &amp;, &quot;)."""
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )

escape = tg_escape

STATUS_LABELS = {
    "awaiting_payment": "💳 To'lov kutilmoqda",
    "payment_review": "🔎 Chek tekshirilmoqda",
    "paid": "✅ To'lov tasdiqlandi",
    "bought": "🛍 Xitoyda xarid qilindi",
    "china_warehouse": "🏭 Xitoy omborida",
    "in_transit": "✈️ Avia yo'lda",
    "arrived": "📍 Toshkentga keldi",
    "cargo_awaiting": "💳 Qolgan to'lov kutilmoqda",
    "cargo_review": "🔎 Yakuniy chek tekshirilmoqda",
    "cargo_paid": "✅ To'liq to'landi",
    "delivered": "🎉 Yetkazildi",
    "cancelled": "❌ Bekor qilindi",
}

NEXT_STATUS = {
    "paid": "bought",
    "bought": "china_warehouse",
    "china_warehouse": "in_transit",
    "in_transit": "arrived",
    "cargo_paid": "delivered",
}

CLIENT_STATUS_MESSAGES = {
    "bought": "🛍 Buyurtma #{id} Xitoyda sotib olindi.",
    "china_warehouse": "🏭 Buyurtma #{id} Xitoy omboriga kirdi.",
    "in_transit": "✈️ Buyurtma #{id} Toshkentga yo'lga chiqdi ({delivery}).",
    "arrived": "📍 Buyurtma #{id} Toshkentga keldi! Hozir yakuniy hisobni yuboramiz.",
    "delivered": "🎉 Buyurtma #{id} topshirildi. Xaridingiz uchun rahmat!",
    "cancelled": "❌ Buyurtma #{id} bekor qilindi.",
}


def look_items(look: dict) -> list[dict]:
    return json.loads(look["items_json"])


def split_list(raw: str | None) -> list[str]:
    return [x.strip() for x in (raw or "").split(",") if x.strip()]


def look_50_values(look: dict) -> tuple[int, int]:
    """(prepay_50_uzs, remaining_50_uzs) qaytaradi."""
    full = int(look.get("prepay_uzs") or 0)
    p50 = int(look.get("prepay_50_uzs") or (full // 2))
    rem50 = int(look.get("remaining_50_uzs") or (full - p50))
    return p50, rem50


def look_caption(look: dict, s: Settings) -> str:
    """Sotuv botdagi ixcham va sodda look kartochkasi."""
    from .sizes import item_size_group
    p50, rem50 = look_50_values(look)
    items = look_items(look)

    size_parts = []
    has_top = any(item_size_group(it) == "top" for it in items)
    has_bot = any(item_size_group(it) == "bottom" for it in items)
    has_sho = any(item_size_group(it) == "shoes" for it in items)
    if has_top:
        size_parts.append(f"Ust: {look.get('sizes') or 'M, L, XL, 2XL'}")
    if has_bot:
        size_parts.append("Shim: 29-36")
    if has_sho:
        size_parts.append("Oyoq: 39-44")
    size_str = " | ".join(size_parts) if size_parts else (look.get('sizes') or 'M, L, XL, 2XL')

    lines = [
        f"👔 <b>{escape(look['title'])}</b> ({len(items)} qism)",
        "",
        *[f"• {escape(i['name'])}" for i in items],
        "",
        f"🎨 Rasmdagi ranglar: <b>{escape(look.get('colors') or 'Rasmdagidek')}</b> <i>(boshqa ranglari ham bor)</i>",
        f"📏 Razmer: {escape(size_str)}",
        f"✈️ Yetkazish: {escape(s.delivery_text)}",
        "",
        f"💳 <b>Hozirgi narx (50%): {fmt(p50)} so'm</b>",
        f"📦 <b>Kargo: 12 000 so'm / 100 gr</b> <i>(qolgan {fmt(rem50)} so'm + kargo — kiyim Toshkentga kelganda!)</i>",
        f"💰 To'liq narxi: {fmt(look['prepay_uzs'])} so'm",
    ]
    if s.manager_username:
        lines.append(f"\n👤 Buyurtma uchun lichka: @{s.manager_username.lstrip('@')}")
    return "\n".join(lines)[:1024]


def order_summary(order: dict, look: dict | None) -> str:
    title = escape(look["title"]) if look else f"Look #{order['look_id']}"
    plan = order.get("payment_plan") or "50"
    rem = int(order.get("remaining_uzs") or 0)
    lines = [
        f"📦 <b>Buyurtma #{order['id']}</b> — {STATUS_LABELS.get(order['status'], order['status'])}",
        f"👔 {title} | 📏 {escape(order.get('size') or '-')} | 🎨 {escape(order.get('color') or '-')}",
        f"💳 Oldindan ({plan}%): <b>{fmt(order['prepay_due'])} so'm</b>",
    ]
    if rem > 0 and not order.get("cargo_due"):
        lines.append(f"⏳ Kelganda qolgani: {fmt(rem)} so'm + kargo")
    if order.get("cargo_due"):
        lines.append(f"✈️ Yakuniy to'lov: <b>{fmt(order['cargo_due'])} so'm</b>")
    if order.get("tracking"):
        lines.append(f"🔢 Trek: <code>{escape(order['tracking'])}</code>")
    return "\n".join(lines)


def admin_order_card(order: dict, look: dict | None) -> str:
    user = f"@{order['username']}" if order.get("username") else f"id {order['user_id']}"
    lines = [
        order_summary(order, look),
        f"👤 {escape(order.get('full_name') or '')} ({escape(user)}) | 📞 {escape(order.get('phone') or '')}",
        f"🏠 {escape(order.get('address') or '')}",
        f"💵 Foyda: <b>{fmt(order['profit_uzs'])} so'm</b>",
    ]
    if look:
        items = look_items(look)
        pdd_lines: list[str] = []
        for idx, it in enumerate(items, 1):
            gid = str(it.get("pdd_goods_id") or "").strip()
            url = str(it.get("url") or (f"https://mobile.yangkeduo.com/goods.html?goods_id={gid}" if gid else "")).strip()
            cny = it.get("price_cny", it.get("cny", 0))
            if url:
                pdd_lines.append(f"{idx}. <a href='{escape(url)}'>{escape(it.get('name', 'Tovar'))}</a> (¥{cny})")
            else:
                pdd_lines.append(f"{idx}. {escape(it.get('name', 'Tovar'))} (¥{cny})")
        if pdd_lines:
            lines.append("\n🇨🇳 <b>Pinduoduo to'g'ridan-to'g'ri havolalar:</b>\n" + "\n".join(pdd_lines))
    return "\n".join(lines)


def agent_card(order: dict, look: dict) -> str:
    lines = [f"🧾 <b>XARID #{order['id']}</b> ({escape(order.get('size') or '-')} / {escape(order.get('color') or '-')})"]
    for n, item in enumerate(look_items(look), 1):
        cny = item.get("price_cny", item.get("cny", 0))
        lines.append(f"{n}. {escape(item['name'])} — ¥{cny}")
        if item.get("url"):
            lines.append(f"   {escape(item['url'])}")
    lines.append(f"👤 {escape(order.get('full_name') or '')} | 📞 {escape(order.get('phone') or '')}")
    return "\n".join(lines)


def payment_text(amount: int, s: Settings, what: str) -> str:
    return (
        f"💳 <b>{what}</b>\n\n"
        f"Karta: <code>{escape(s.card_number)}</code>\n"
        f"Egasi: <b>{escape(s.card_owner)}</b>\n"
        f"Summa: <b><code>{amount}</code> so'm</b> ({fmt(amount)} so'm)\n\n"
        "❗️ Aynan shu summani o'tkazib, <b>chek rasmini</b> shu yerga yuboring."
    )
