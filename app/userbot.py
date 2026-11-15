"""XAN SHOP - Haqiqiy Shaxsiy Telegram Akkaunt Agent (Telethon MTProto Userbot).

Mijozlar botdan emas, balki jonli odam profilidan (@xan_manager)
yozishni afzal ko'rishadi. Ushbu modul siz ochib bergan haqiqiy Telegram akkauntni
24/7 rejimida AI Stilist & Sotuvchi sifatida boshqaradi:
- Xabarni o'qilgan qiladi ("read") va haqiqiy odamdek "yozmoqda..." (typing) ko'rsatadi;
- Matn, ovozli xabar (golosovoy) va Instagram skrinshotlarini tushunadi;
- Mijoz Look so'rasa, `.mp4` Reels video va kolaj rasmini lichkaga tashlaydi;
- Bo'y va vaznni so'rab, Xitoy razmerini (M, L, XL, 2XL) aniq tanlab beradi;
- Suhbat davomida buyurtmani (50% yoki 100% to'lov rejasi bilan, source='userbot')
  bazaga yozadi va karta raqamni beradi;
- Mijoz lichkaga to'lov cheki rasmini tashlasa, uni avtomatik Admin botga tasdiqlash tugmasi bilan uzatadi!
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from collections import defaultdict
from html import escape

from aiogram import Bot
from telethon import TelegramClient, events
from telethon.sessions import StringSession

from .accountant import AccountantAgent
from .ai import SalesAI, build_system_prompt
from .config import Settings, load_settings
from .db import Database
from .notify import admin_order_kb, notify_admins
from .pricing import fmt, unique_amount
from .texts import admin_order_card, look_50_values, look_caption

log = logging.getLogger(__name__)

# AI javobidan avtomatik buyurtma yaratish tegi:
# [ORDER:look_id=1|size=XL|color=Qora|plan=50|name=Ali|phone=+998901234567|address=Toshkent Yunusobod]
ORDER_TAG_RE = re.compile(r"\[ORDER:([^\]]+)\]", re.IGNORECASE)
LOOK_SHOW_RE = re.compile(r"\[SHOW_LOOK:(\d+)\]", re.IGNORECASE)


def _strip_html(text: str) -> str:
    return (
        text.replace("&quot;", '"')
        .replace("&#x27;", "'")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("<b>", "")
        .replace("</b>", "")
        .replace("<i>", "")
        .replace("</i>", "")
        .replace("<code>", "")
        .replace("</code>", "")
    )


class PersonalStylistUserbot:
    """Haqiqiy Telegram profil (Userbot) orqali 24/7 sotuv va mijozlar bilan muloqot."""

    def __init__(
        self,
        db: Database,
        settings: Settings,
        ai: SalesAI,
        admin_bot: Bot | None = None,
        sales_bot: Bot | None = None,
    ):
        self.db = db
        self.s = settings
        self.ai = ai
        self.admin_bot = admin_bot
        self.sales_bot = sales_bot
        self.client: TelegramClient | None = None
        self._user_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

    def _bank_bot_set(self) -> set[str]:
        return {
            u.strip().lstrip("@").lower()
            for u in (self.s.bank_bot_usernames or "").split(",")
            if u.strip()
        }

    @property
    def configured(self) -> bool:
        return bool(self.s.tg_api_id and self.s.tg_api_hash and (self.s.tg_session_string or self.s.tg_phone))

    async def start(self) -> bool:
        """Shaxsiy Telegram akkauntga ulanadi va xabarlarni tinglashni boshlaydi."""
        if not self.configured:
            log.info("ℹ️ Shaxsiy Telegram Userbot sozlanmagan (TG_API_ID / TG_API_HASH bo'sh). Faqat Bot rejimida.")
            return False

        os.makedirs("data", exist_ok=True)
        session = (
            StringSession(self.s.tg_session_string)
            if self.s.tg_session_string
            else os.path.join("data", "xan_userbot")
        )
        self.client = TelegramClient(session, int(self.s.tg_api_id), self.s.tg_api_hash)

        try:
            await self.client.connect()
            if not await self.client.is_user_authorized():
                log.warning(
                    "⚠️ Shaxsiy Telegram Userbot hali avtorizatsiya qilinmagan. "
                    "Avtorizatsiya qilish uchun: python -m app.userbot"
                )
                return False

            me = await self.client.get_me()
            uname = f"@{me.username}" if me.username else me.first_name
            log.info("👤 Shaxsiy Telegram Akkaunt (Userbot) ulandi: %s", uname)
            await self.db.set_agent_status(
                "sales_stylist",
                "idle",
                f"Shaxsiy profil ({uname}) + Bot 24/7 aloqada",
            )
            await self.db.log_agent_action(
                "sales_stylist",
                f"Haqiqiy Telegram akkaunt ({uname}) AI boshqaruviga ulandi",
            )
            self._register_handlers()
            return True
        except Exception as e:
            log.warning("Userbot ulanishida xato: %s", e)
            return False

    def _register_handlers(self) -> None:
        assert self.client is not None

        @self.client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
        async def _on_private_message(event: events.NewMessage.Event) -> None:
            sender = await event.get_sender()
            if not sender:
                return
            uname_low = (getattr(sender, "username", "") or "").lstrip("@").lower()
            if getattr(sender, "bot", False):
                if uname_low and uname_low in self._bank_bot_set():
                    await event.mark_read()
                    await AccountantAgent(self.db, self.s).process_bank_notification(
                        event.raw_text or "",
                        source=f"@{uname_low}",
                        sales_bot=self.sales_bot,
                        admin_bot=self.admin_bot,
                        userbot=self,
                    )
                return
            uid = sender.id
            if uid in self.s.admin_ids:
                # Adminning o'zi sinab ko'rishi mumkin, lekin oddiy eslatmalar bilan adashmasligi uchun davom etamiz
                pass

            async with self._user_locks[uid]:
                await self._process_private_message(event, sender)

    async def _process_private_message(self, event: events.NewMessage.Event, sender) -> None:
        uid = sender.id
        username = getattr(sender, "username", "") or ""
        full_name = f"{getattr(sender, 'first_name', '') or ''} {getattr(sender, 'last_name', '') or ''}".strip()

        await event.mark_read()

        # 1) Agar mijoz to'lovi kutilayotgan buyurtma bo'yicha chek (rasm/PDF) yuborgan bo'lsa
        if event.photo or event.document:
            order = await self.db.payable_order(uid)
            if order:
                img_bytes = await event.download_media(bytes)
                mime_type = "image/jpeg" if event.photo else (getattr(event.document, "mime_type", None) or "application/octet-stream")
                attrs = getattr(event.document, "attributes", None) or []
                doc_name = (
                    "chek.jpg"
                    if event.photo
                    else (next((getattr(a, "file_name", None) for a in attrs if getattr(a, "file_name", None)), None) or "chek.pdf")
                )
                _, client_reply = await AccountantAgent(self.db, self.s).handle_uploaded_receipt(
                    order,
                    file_bytes=img_bytes,
                    mime_type=mime_type,
                    doc_name=doc_name,
                    is_photo=bool(event.photo),
                    sales_bot=self.sales_bot,
                    admin_bot=self.admin_bot,
                    userbot=self,
                    source_prefix="[SHAXSIY AKKAUNT] ",
                    actor_label=f"Mijoz: {full_name} (@{username})",
                )
                if client_reply:
                    await event.respond(client_reply)
                return

        # 2) Matn, rasm (Instagram skrinshot) yoki ovozli xabar (golosovoy)
        media_bytes: bytes | None = None
        mime_type = ""
        text = (event.raw_text or "").strip()

        if event.voice or event.audio:
            media_bytes = await event.download_media(bytes)
            mime_type = "audio/ogg"
            if not text:
                text = "Mijoz ovozli xabar yubordi. Ovozni eshitib, savoliga o'zbek/rus tilida javob ber."
        elif event.photo:
            media_bytes = await event.download_media(bytes)
            mime_type = "image/jpeg"
            if not text:
                text = "Mijoz kiyim yoki look rasmini yubordi. Katalogimizdagi qaysi Lookka mosligini aytib, narxi (50%/100%) va razmer tanlashda yordam ber."

        if not text and not media_bytes:
            return

        if not media_bytes:
            verbal_warn = await AccountantAgent.check_verbal_payment_text(self.db, uid, text)
            if verbal_warn:
                await event.respond(verbal_warn)
                return

        # Haqiqiy insondek "typing..." holatini ko'rsatish
        async with self.client.action(uid, "typing"):
            await asyncio.sleep(1.4)
            looks = await self.db.list_looks()
            orders = await self.db.user_orders(uid)
            system = build_system_prompt(self.s, looks, orders, is_personal_account=True)
            answer, inter_id, need_admin = await self.ai.reply(
                system,
                text,
                await self.db.get_interaction(uid),
                media_bytes=media_bytes,
                mime_type=mime_type,
            )
            if inter_id:
                await self.db.set_interaction(uid, inter_id)

        if not answer:
            answer = "Hozir bazadan aniq ma'lumotni tekshirib, sizga 2 daqiqada yozaman 🙏"
            need_admin = True

        show_match = LOOK_SHOW_RE.search(answer)
        clean_answer = LOOK_SHOW_RE.sub("", answer)
        order_match = ORDER_TAG_RE.search(clean_answer)
        clean_answer = ORDER_TAG_RE.sub("", clean_answer).strip()

        if show_match:
            lk_id = int(show_match.group(1))
            lk = await self.db.get_look(lk_id)
            if lk:
                cap = _strip_html(look_caption(lk, self.s))
                vid = lk.get("video_path") or ""
                if vid and os.path.exists(vid) and vid.endswith(".mp4"):
                    await self.client.send_file(uid, vid, caption=cap, supports_streaming=True)
                elif lk.get("photo_path") and os.path.exists(lk["photo_path"]):
                    await self.client.send_file(uid, lk["photo_path"], caption=cap)

        if clean_answer:
            await event.respond(_strip_html(clean_answer))

        if order_match:
            await self._handle_structured_order(uid, username, full_name, order_match.group(1), event)

        await self.db.set_agent_status(
            "sales_stylist",
            "idle",
            f"Shaxsiy lichkada mijoz ({full_name or username}) bilan suhbatlashdi",
            increment_done=True,
        )

        if need_admin and self.admin_bot:
            who = f"@{username}" if username else escape(full_name)
            await notify_admins(
                self.admin_bot,
                self.s,
                f"👤 <b>[Shaxsiy Akkaunt] Operator yordami kerak</b> — {who} (id <code>{uid}</code>)\n\n"
                f"Mijoz yozdi: {escape(text)}",
            )

    async def _handle_structured_order(
        self,
        uid: int,
        username: str,
        full_name: str,
        kv_raw: str,
        event: events.NewMessage.Event,
    ) -> None:
        fields: dict[str, str] = {}
        for part in kv_raw.split("|"):
            if "=" in part:
                k, v = part.split("=", 1)
                fields[k.strip().lower()] = v.strip()

        try:
            look_id = int(fields.get("look_id", "1") or "1")
        except ValueError:
            look_id = 1
        look = await self.db.get_look(look_id)
        if not look:
            looks = await self.db.list_looks()
            if not looks:
                return
            look = looks[0]

        p50, rem50 = look_50_values(look)
        plan = "100" if fields.get("plan") == "100" else "50"
        base_prepay = int(look["prepay_uzs"]) if plan == "100" else p50
        rem_uzs = 0 if plan == "100" else rem50

        oid = await self.db.create_order(
            user_id=uid,
            username=username,
            full_name=fields.get("name") or full_name,
            phone=fields.get("phone", ""),
            address=fields.get("address", ""),
            look_id=look["id"],
            size=fields.get("size", "XL"),
            color=fields.get("color", ""),
            payment_plan=plan,
            prepay_due=0,
            remaining_uzs=rem_uzs,
            profit_uzs=look["profit_uzs"],
            goods_cost_uzs=look["goods_cost_uzs"],
            status="awaiting_payment",
            source="userbot",
        )
        amount = unique_amount(base_prepay, oid)
        await self.db.update_order(oid, prepay_due=amount)

        pay_msg = (
            f"✅ Buyurtmangiz #{oid} ({plan}% to'lov rejasi) rasmiylashtirildi!\n\n"
            f"💳 Karta: {self.s.card_number}\n"
            f"👤 Egasi: {self.s.card_owner}\n"
            f"💰 O'tkaziladigan aniq summa: {fmt(amount)} so'm ({amount})\n"
            + (
                f"⏳ Qolgan 50% ({fmt(rem_uzs)} so'm) + Kargo (~{fmt(look['cargo_est_uzs'])} so'm) — yuk Toshkentga kelganda!\n\n"
                if rem_uzs > 0
                else "✈️ Yuk Toshkentga kelganda faqat kargo vazni bo'yicha to'lanadi!\n\n"
            )
            + "To'lov qilgach, chek rasmini (skrinshotni) shu lichkaga tashlang 🙏"
        )
        await event.respond(pay_msg)

        if self.admin_bot:
            order = await self.db.get_order(oid)
            await notify_admins(
                self.admin_bot,
                self.s,
                f"🆕 <b>[Shaxsiy Akkauntdan Buyurtma] #{oid} ({plan}% reja)</b>\n\n"
                + admin_order_card(order, look),
                reply_markup=admin_order_kb(order, self.s),
            )

    async def stop(self) -> None:
        if self.client:
            await self.client.disconnect()


async def _interactive_login() -> None:
    """Bir marta terminalda telefon/SMS kod kiritib, shaxsiy akkaunt StringSession olish yordamchisi."""
    s = load_settings()
    if not (s.tg_api_id and s.tg_api_hash):
        print("❌ Avval .env fayliga TG_API_ID va TG_API_HASH kiriting (https://my.telegram.org dan olinadi).")
        return
    os.makedirs("data", exist_ok=True)
    client = TelegramClient(StringSession(), int(s.tg_api_id), s.tg_api_hash)
    await client.start(phone=s.tg_phone or (lambda: input("Telegram raqamingiz (+998...): ")))
    me = await client.get_me()
    session_str = client.session.save()
    await client.disconnect()
    print(f"\n✅ Muvaffaqiyatli ulandi: {me.first_name} (@{me.username})")
    print("\nQuyidagi qatorni .env faylingizga (va 24/7 server Environment Variables ga) qo'shing:\n")
    print(f"TG_SESSION_STRING={session_str}\n")


if __name__ == "__main__":
    asyncio.run(_interactive_login())
