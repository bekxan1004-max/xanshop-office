"""Botlar orasidagi xabarlar va admin tugmalari."""
import logging

from aiogram import Bot
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup

from .config import Settings
from .texts import NEXT_STATUS, STATUS_LABELS

log = logging.getLogger(__name__)


def admin_order_kb(order: dict, s: Settings) -> InlineKeyboardMarkup:
    oid, st = order["id"], order["status"]
    rows: list[list[InlineKeyboardButton]] = []
    if st in ("awaiting_payment", "payment_review", "cargo_awaiting", "cargo_review"):
        what = "kargo to'lovini" if st.startswith("cargo") else "to'lovni"
        rows.append([InlineKeyboardButton(text=f"✅ Pul tushdi — {what} tasdiqlash",
                                          callback_data=f"pay_ok:{oid}")])
        if st.endswith("review"):
            rows.append([InlineKeyboardButton(text="❌ Pul tushmagan", callback_data=f"pay_no:{oid}")])
    if st in NEXT_STATUS:
        nxt = NEXT_STATUS[st]
        rows.append([InlineKeyboardButton(text=f"➡️ {STATUS_LABELS[nxt]}", callback_data=f"st:{oid}:{nxt}")])
    if st == "arrived":
        rows.append([InlineKeyboardButton(text="⚖️ Real vaznni kiritish", callback_data=f"weight:{oid}")])
        if s.cargo_collect_on_delivery and order.get("weight_kg"):
            rows.append([InlineKeyboardButton(text=f"➡️ {STATUS_LABELS['delivered']}",
                                              callback_data=f"st:{oid}:delivered")])
    if st not in ("delivered", "cancelled"):
        rows.append([InlineKeyboardButton(text="🗑 Bekor qilish", callback_data=f"cancel:{oid}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def notify_admins(admin_bot: Bot, s: Settings, text: str, reply_markup=None,
                        photo: bytes | None = None, document: tuple[bytes, str] | None = None) -> None:
    for admin_id in s.admin_ids:
        try:
            if photo:
                await admin_bot.send_photo(admin_id, BufferedInputFile(photo, "chek.jpg"),
                                           caption=text[:1024], reply_markup=reply_markup)
            elif document:
                await admin_bot.send_document(admin_id, BufferedInputFile(*document),
                                              caption=text[:1024], reply_markup=reply_markup)
            else:
                await admin_bot.send_message(admin_id, text, reply_markup=reply_markup)
        except Exception as e:
            log.warning("Adminga (%s) yuborilmadi — admin botga /start bosganmi? %s", admin_id, e)


async def send_to_agent(admin_bot: Bot, s: Settings, text: str) -> None:
    """Agent/kargoga buyurtma. AGENT_CHAT_ID bo'lmasa adminlarga yuboriladi."""
    if s.agent_chat_id:
        try:
            await admin_bot.send_message(s.agent_chat_id, text, disable_web_page_preview=True)
            return
        except Exception as e:
            log.warning("Agentga yuborilmadi: %s", e)
    await notify_admins(admin_bot, s, "📤 Agentga yuboring:\n\n" + text)


async def notify_client(
    sales_bot: Bot,
    user_id: int,
    text: str,
    userbot=None,
    source: str = "bot",
    **kwargs,
) -> bool:
    """Mijozga xabar yuboradi: shaxsiy akkauntdan (userbot) yozgan bo'lsa userbot orqali, aks holda sotuv bot orqali."""
    if source == "userbot" and userbot and getattr(userbot, "client", None):
        try:
            plain = (
                text.replace("<b>", "")
                .replace("</b>", "")
                .replace("<code>", "")
                .replace("</code>", "")
                .replace("<i>", "")
                .replace("</i>", "")
            )
            await userbot.client.send_message(user_id, plain)
            return True
        except Exception as e:
            log.warning("Userbot orqali mijozga (%s) yuborilmadi, botga o'tilmoqda: %s", user_id, e)
    try:
        await sales_bot.send_message(user_id, text, **kwargs)
        return True
    except Exception as e:
        log.warning("Mijozga (%s) yuborilmadi: %s", user_id, e)
        return False


async def notify_client_photo(
    sales_bot: Bot,
    user_id: int,
    photo_bytes: bytes,
    caption: str,
    userbot=None,
    source: str = "bot",
) -> bool:
    """Mijozga rasm (QC tekshiruv) yuboradi — bot yoki shaxsiy akkaunt orqali."""
    if source == "userbot" and userbot and getattr(userbot, "client", None):
        try:
            import io
            bio = io.BytesIO(photo_bytes)
            bio.name = "qc.jpg"
            await userbot.client.send_file(user_id, bio, caption=caption)
            return True
        except Exception as e:
            log.warning("Userbot orqali QC rasm (%s) yuborilmadi: %s", user_id, e)
    try:
        await sales_bot.send_photo(user_id, BufferedInputFile(photo_bytes, "qc.jpg"), caption=caption)
        return True
    except Exception as e:
        log.warning("Bot orqali QC rasm (%s) yuborilmadi: %s", user_id, e)
        return False
