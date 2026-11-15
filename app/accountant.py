"""XAN SHOP - AI Hisobchi Agent (AccountantAgent).

Vazifalari:
1) Mijoz yuborgan chek rasmini Gemini Vision (`gemini-3.8-flash`) orqali tekshiradi:
   - Summa kutilgan noyob summaga (`prepay_due` / `cargo_due`) mosmi;
   - Qabul qiluvchi karta oxirgi 4 raqami (`CARD_NUMBER`) to'g'rimi;
   - Chek avval boshqa buyurtmada ishlatilmaganmi (`image_sha256` va `tx_id` Anti-Duplicate);
   - Statusi muvaffaqiyatlimi ("Успешно" / "Muvaffaqiyatli") va tahrirlash (Photoshop) belgilari bormi.
2) Bank SMS / Telegram Bank Bot (`@HumoCardBot`, `@CardXabarBot` va h.k.) tarixidan kirim
   xabarlarini (`+90 013 UZS`) avtomatik o'qiydi va buyurtmadagi noyob summa bilan solishtiradi.
3) Chek + Bank tushumi tasdiqlanganda, inson aralashuvisiz buyurtmani `paid` holatiga o'tkazib,
   Vykup & Kargo Agentga Xitoy manzili (`ID BP-1` / `T-7621`) bilan zakaz varaqasini yuboradi!
"""
from __future__ import annotations

import hashlib
from html import escape
import logging
import re
from dataclasses import dataclass
from typing import Any

from aiogram import Bot

from .ai import SalesAI
from .config import Settings
from .db import Database
from .logistics import LogisticsAgent
from .notify import admin_order_kb, notify_admins, notify_client, send_to_agent
from .pricing import fmt
from .texts import admin_order_card

log = logging.getLogger(__name__)

# Kirim (deposit) kalit so'zlari; chiqim (spisanie/oplata) bilan adashmaslik uchun
DEPOSIT_KEYWORDS = ("popolnen", "пополнен", "kirim", "tushum", "зачислен", "perevod na", "p2p kirim", "credit")
OUTGOING_KEYWORDS = ("spisan", "списан", "chiqim", "oplata", "оплата", "pokupka", "покупка", "debit")

CARD_LAST4_RE = re.compile(r"(?:\*{1,4}|x{2,4})(\d{4})\b", re.IGNORECASE)
AMOUNT_RE = re.compile(
    r"(?:\+\s*)?(\d{1,3}(?:[\s,]\d{3})+|\d{4,9})(?:[.,](\d{2}))?\s*(?:uzs|sum|so'm|сўм|сум)\b",
    re.IGNORECASE,
)
PLUS_NUM_RE = re.compile(r"\+\s*(\d{1,3}(?:[\s,]\d{3})+|\d{4,9})(?:[.,]\d{2})?")

# Mijoz og'zaki "to'lov qildim" desa cheksiz tasdiqlashga yo'l qo'ymaydigan filtr
VERBAL_PAYMENT_CLAIM_RE = re.compile(
    r"(?:"
    r"to['`ʻʼ]?lov(?:ni|ini)?\s*qildim|tolov(?:ni|ini)?\s*qildim|to['`ʻʼ]?ladim|toladim|"
    r"(?:pul(?:ni|ini)?|summani)?\s*(?:tashladim|tashadim|o['`ʻʼ]?tkazdim|otkazdim|yubordim|tashavor)|"
    r"(?:оплатил[аи]?|перевел[аи]?|скинул[аи]?|oplatil[ai]?|perevel[ai]?|skinul[ai]?)(?:\s+(?:деньги|на\s*карту|dengi|na\s*kartu))?"
    r")\b",
    re.IGNORECASE,
)


def is_verbal_payment_claim(text: str) -> bool:
    """Mijoz rasm/chek yubormasdan og'zaki 'to'lov qildim' deb da'vo qilayotganini aniqlaydi."""
    txt = (text or "").strip()
    if not txt:
        return False
    return bool(VERBAL_PAYMENT_CLAIM_RE.search(txt))


def parse_bank_deposit_text(raw_text: str) -> tuple[int | None, str]:
    """Bank SMS yoki Telegram bank bot xabaridan (+summa UZS, karta_oxirgi_4_raqam) ni ajratib oladi.

    Chiqim (pul yechish) xabarlarida None qaytaradi.
    """
    txt = (raw_text or "").strip()
    low = txt.lower()
    if not txt:
        return None, ""

    is_outgoing = any(k in low for k in OUTGOING_KEYWORDS)
    is_deposit = any(k in low for k in DEPOSIT_KEYWORDS) or bool(PLUS_NUM_RE.search(txt))
    if is_outgoing and not any(k in low for k in DEPOSIT_KEYWORDS):
        return None, ""
    if not is_deposit:
        return None, ""

    last4_m = CARD_LAST4_RE.search(txt)
    last4 = last4_m.group(1) if last4_m else ""

    amt_m = AMOUNT_RE.search(txt)
    if amt_m:
        digits = re.sub(r"[\s,]", "", amt_m.group(1))
        return int(digits), last4

    plus_m = PLUS_NUM_RE.search(txt)
    if plus_m:
        digits = re.sub(r"[\s,]", "", plus_m.group(1))
        return int(digits), last4

    return None, last4


@dataclass(frozen=True)
class ReceiptVerdict:
    verdict: str               # "auto_approved", "ai_verified", "suspicious_fake", "duplicate"
    parsed_amount: int
    parsed_last4: str
    tx_ref: str
    reason: str
    auto_approved: bool = False


class AccountantAgent:
    """AI Hisobchi & Anti-Fake Chek Tekshiruvchi."""

    def __init__(self, db: Database, settings: Settings):
        self.db = db
        self.s = settings
        self.ai = SalesAI(settings)
        self.client = self.ai.client

    def _my_card_last4(self) -> str:
        digits = "".join(ch for ch in (self.s.card_number or "") if ch.isdigit())
        return digits[-4:] if len(digits) >= 4 else ""

    async def confirm_order_payment(
        self,
        order: dict[str, Any],
        sales_bot: Bot | None,
        admin_bot: Bot | None,
        userbot=None,
        reason: str = "AI Hisobchi avtomatik tasdiqladi",
    ) -> None:
        """Buyurtma to'lovini tasdiqlaydi va Xitoy vykup kartasini yuboradi."""
        st = order["status"]
        look = await self.db.get_look(order["look_id"])
        src = order.get("source") or "bot"

        if st in ("awaiting_payment", "payment_review"):
            await self.db.update_order(order["id"], status="paid")
            plan = order.get("payment_plan") or "50"
            if sales_bot:
                await notify_client(
                    sales_bot,
                    order["user_id"],
                    f"✅ {plan}% oldindan to'lov tasdiqlandi! Buyurtma #{order['id']} Xitoydan xarid qilish navbatiga qo'yildi.\n"
                    "Har bir bosqichda shu yerda xabar beramiz.",
                    userbot=userbot,
                    source=src,
                )
            updated = await self.db.get_order(order["id"])
            logistics = LogisticsAgent(self.db, self.s)
            vykup_card = logistics.build_vykup_card(updated, look)
            if admin_bot:
                await send_to_agent(admin_bot, self.s, vykup_card)
                await notify_admins(
                    admin_bot,
                    self.s,
                    f"🧮 <b>AI HISOBCHI: To'lov Avtomatik Tasdiqlandi!</b>\n"
                    f"Buyurtma <b>#{order['id']}</b> · Sabab: {reason}\n\n"
                    + admin_order_card(updated, look),
                    reply_markup=admin_order_kb(updated, self.s),
                )
            await self.db.set_agent_status(
                "cargo_logistics",
                "idle",
                f"Buyurtma #{order['id']} Pinduoduo xarid kartasi tayyorlandi",
                increment_done=True,
            )
            await self.db.log_agent_action(
                "accountant",
                f"Buyurtma #{order['id']} ({plan}%) to'lovi tasdiqlandi va Kargo/Xarid kartasi tayyorlandi",
                reason,
                target_id="cargo_logistics",
            )
        elif st in ("cargo_awaiting", "cargo_review"):
            await self.db.update_order(order["id"], status="cargo_paid")
            if sales_bot:
                await notify_client(
                    sales_bot,
                    order["user_id"],
                    f"✅ Yakuniy to'lov tasdiqlandi! Buyurtma #{order['id']} manzilingizga jo'natiladi.",
                    userbot=userbot,
                    source=src,
                )
            updated = await self.db.get_order(order["id"])
            if admin_bot:
                await notify_admins(
                    admin_bot,
                    self.s,
                    f"🧮 <b>AI HISOBCHI: Yakuniy To'lov Avtomatik Tasdiqlandi!</b>\n"
                    f"Buyurtma <b>#{order['id']}</b> · Sabab: {reason}\n\n"
                    + admin_order_card(updated, look),
                    reply_markup=admin_order_kb(updated, self.s),
                )
            await self.db.log_agent_action(
                "accountant",
                f"Buyurtma #{order['id']} yakuniy (qolgan 50% + kargo) to'lovi avtomatik tasdiqlandi",
                reason,
                target_id="cargo_logistics",
            )

    async def process_bank_notification(
        self,
        raw_text: str,
        source: str = "bank_bot",
        sales_bot: Bot | None = None,
        admin_bot: Bot | None = None,
        userbot=None,
    ) -> dict[str, Any]:
        """Bank SMS yoki Telegram bot kirim xabarini qayta ishlaydi va noyob summa orqali zakazni tasdiqlaydi."""
        amount, last4 = parse_bank_deposit_text(raw_text)
        if not amount:
            return {"matched": False, "reason": "kirim_emas"}

        my_last4 = self._my_card_last4()
        if my_last4 and my_last4 != "0000" and last4 and last4 != my_last4:
            # Boshqa karta raqamiga tushgan xabar
            tx_id = await self.db.add_bank_tx(source, amount, last4, raw_text[:400], None)
            return {"matched": False, "tx_id": tx_id, "amount": amount, "reason": "karta_boshqa"}

        order = await self.db.find_pending_order_by_amount(amount)
        tx_id = await self.db.add_bank_tx(
            source, amount, last4, raw_text[:400], order["id"] if order else None
        )
        await self.db.set_agent_status(
            "accountant",
            "idle",
            f"Bank tushumi qayd etildi: +{fmt(amount)} so'm" + (f" (Buyurtma #{order['id']})" if order else ""),
            increment_done=True,
        )

        if order:
            await self.confirm_order_payment(
                order,
                sales_bot=sales_bot,
                admin_bot=admin_bot,
                userbot=userbot,
                reason=f"Bank tarixida aniq tushum topildi: +{fmt(amount)} so'm ({source})",
            )
            return {"matched": True, "tx_id": tx_id, "order_id": order["id"], "amount": amount}

        await self.db.log_agent_action(
            "accountant",
            f"Bank tushumi saqlandi (+{fmt(amount)} so'm), kutilayotgan buyurtma cheki kutilmoqda",
            f"Manba: {source} | Karta: *{last4 or '????'}",
        )
        return {"matched": False, "tx_id": tx_id, "amount": amount, "reason": "buyurtma_topilmadi"}

    async def inspect_and_verify_receipt(
        self,
        order: dict[str, Any],
        file_bytes: bytes,
        mime_type: str = "image/jpeg",
        sales_bot: Bot | None = None,
        admin_bot: Bot | None = None,
        userbot=None,
    ) -> ReceiptVerdict:
        """Chek rasmini Anti-Fake + OCR + Bank tarixi bo'yicha tekshiradi."""
        await self.db.set_agent_status(
            "accountant",
            "working",
            f"Buyurtma #{order['id']} cheki Gemini Vision va Bank tarixi bo'yicha tekshirilmoqda...",
        )
        stage_cargo = order["status"].startswith("cargo")
        expected_amount = int(order["cargo_due"] if stage_cargo else order["prepay_due"])
        sha256 = hashlib.sha256(file_bytes).hexdigest()

        # 1) Dublikat rasm tekshiruvi
        dup = await self.db.is_duplicate_receipt(sha256, "", exclude_order_id=order["id"])
        if dup:
            verdict = ReceiptVerdict(
                verdict="duplicate",
                parsed_amount=0,
                parsed_last4="",
                tx_ref="",
                reason=f"Bu chek rasmi avval Buyurtma #{dup['order_id']} da ishlatilgan!",
            )
            await self.db.add_receipt_check(order["id"], "", sha256, 0, "", verdict.verdict, verdict.reason)
            await self.db.set_agent_status("accountant", "idle", f"🚨 Dublikat chek aniqlandi (#{order['id']})", increment_done=True)
            await self.db.log_agent_action("accountant", f"🚨 Buyurtma #{order['id']}: DUBLIKAT CHEK bloklandi!", verdict.reason)
            return verdict

        # 2) Gemini Vision bilan chekni o'qish
        parsed_amount = 0
        parsed_last4 = ""
        tx_ref = ""
        is_receipt = True
        ocr_failed = False
        ai_ocr_attempted = False
        status_ok = True
        fraud_signs = "yo'q"

        if mime_type.startswith("image/") and (self.ai.enabled or self.client is not None):
            ai_ocr_attempted = True
            if self.client is not self.ai.client:
                self.ai.client = self.client
            my_last4 = self._my_card_last4()
            prompt = (
                "Bu rasm O'zbekiston to'lov ilovasi (Click, Payme, Uzum, Humo, Kapitalbank) chekimi yo'qmi, tekshir.\n"
                "Agar rasm umuman to'lov cheki bo'lmasa (oddiy surat, chat skrinshoti, kiyim rasmi), is_receipt=false qo'y.\n"
                "Uni sinchiklab o'qi va FAQAT JSON qaytar:\n"
                "{\n"
                '  "is_receipt": true,\n'
                '  "amount_uzs": 90013,\n'
                '  "receiver_card_last4": "1234",\n'
                '  "tx_id": "chek raqami yoki trans_id",\n'
                '  "status_ok": true,\n'
                '  "fraud_signs": "yoq"\n'
                "}\n"
                f"Kutilgan summa: {expected_amount} so'm. Bizning karta oxiri: {my_last4 or 'noma_lum'}.\n"
                "Agar summa aniq ko'rinmasa amount_uzs=0 yoz. Agar summa o'zgartirilgan (Photoshop/shrift har xil) "
                "yoki status muvaffaqiyatsiz bo'lsa, status_ok=false yoz va fraud_signs ga sababini yoz."
            )
            try:
                data = await self.ai.ask_json(
                    prompt,
                    media_bytes=file_bytes,
                    mime_type=mime_type,
                    timeout_sec=20.0,
                )
                if data:
                    is_receipt = bool(data.get("is_receipt", True))
                    parsed_amount = int(float(str(data.get("amount_uzs") or 0).replace(" ", "").replace(",", "")))
                    parsed_last4 = str(data.get("receiver_card_last4") or "").strip()[-4:]
                    tx_ref = str(data.get("tx_id") or "").strip()
                    status_ok = bool(data.get("status_ok", True))
                    fraud_signs = str(data.get("fraud_signs") or "yo'q").strip()
                else:
                    ocr_failed = True
            except Exception as e:
                ocr_failed = True
                log.info("AI chek OCR xatosi (%s)", e)

        # 3) Dublikat tx_id tekshiruvi
        if tx_ref:
            dup_tx = await self.db.is_duplicate_receipt("no_hash_match", tx_ref, exclude_order_id=order["id"])
            if dup_tx:
                verdict = ReceiptVerdict(
                    verdict="duplicate",
                    parsed_amount=parsed_amount,
                    parsed_last4=parsed_last4,
                    tx_ref=tx_ref,
                    reason=f"Chek ID ({tx_ref}) avval Buyurtma #{dup_tx['order_id']} da ishlatilgan!",
                )
                await self.db.add_receipt_check(order["id"], tx_ref, sha256, parsed_amount, parsed_last4, verdict.verdict, verdict.reason)
                await self.db.set_agent_status("accountant", "idle", f"🚨 Takroriy Chek ID (#{order['id']})", increment_done=True)
                await self.db.log_agent_action("accountant", f"🚨 Buyurtma #{order['id']}: Takroriy Chek ID aniqlandi!", verdict.reason)
                return verdict

        # 4) Anti-Fake tekshiruvi
        my_last4 = self._my_card_last4()
        problems: list[str] = []
        if not is_receipt:
            problems.append("Yuborilgan rasm to'lov cheki emas")
        elif ai_ocr_attempted and not ocr_failed and parsed_amount <= 0:
            problems.append("Chekdagi summa o'qilmadi — aniq ko'rinadigan to'lov cheki rasmini yuboring")
        if not status_ok:
            problems.append("Chek statusi muvaffaqiyatli emas")
        if fraud_signs and fraud_signs.lower() not in ("yoq", "yo'q", "none", "no", ""):
            problems.append(f"Tahrir/shubha: {fraud_signs}")
        if parsed_amount > 0 and abs(parsed_amount - expected_amount) > 500:
            problems.append(f"Summa mos emas (Chekda: {fmt(parsed_amount)}, Kutilgan: {fmt(expected_amount)})")
        if my_last4 and my_last4 != "0000" and parsed_last4 and parsed_last4 != my_last4:
            problems.append(f"Karta oxiri mos emas (*{parsed_last4} != *{my_last4})")

        if problems:
            reason = " · ".join(problems)
            verdict = ReceiptVerdict(
                verdict="suspicious_fake",
                parsed_amount=parsed_amount,
                parsed_last4=parsed_last4,
                tx_ref=tx_ref,
                reason=reason,
            )
            await self.db.add_receipt_check(order["id"], tx_ref, sha256, parsed_amount, parsed_last4, verdict.verdict, reason)
            await self.db.set_agent_status("accountant", "idle", f"🚨 Shubhali chek (#{order['id']}): {reason[:45]}", increment_done=True)
            await self.db.log_agent_action("accountant", f"🚨 Buyurtma #{order['id']}: SHUBHALI CHEK!", reason)
            return verdict

        # 5) Bank tarixidan (unmatched deposit) tekshirish!
        bank_tx = await self.db.find_unmatched_bank_tx(expected_amount)
        if bank_tx:
            await self.db.match_bank_tx(bank_tx["id"], order["id"])
            reason = f"Chek OCR to'g'ri + Bank tarixida +{fmt(expected_amount)} so'm tasdiqlandi!"
            verdict = ReceiptVerdict(
                verdict="auto_approved",
                parsed_amount=parsed_amount or expected_amount,
                parsed_last4=parsed_last4,
                tx_ref=tx_ref,
                reason=reason,
                auto_approved=True,
            )
            await self.db.add_receipt_check(order["id"], tx_ref, sha256, verdict.parsed_amount, parsed_last4, verdict.verdict, reason)
            await self.confirm_order_payment(
                order,
                sales_bot=sales_bot,
                admin_bot=admin_bot,
                userbot=userbot,
                reason=reason,
            )
            return verdict

        # 6) Chek toza ko'rindi, bank SMS/bot xabari yoki admin tasdig'ini kutmoqda
        reason = (
            f"Chek OCR toza (Summa: {fmt(parsed_amount or expected_amount)} so'm)"
            if parsed_amount
            else (
                "Chek adminga yuborildi (AI Vision vaqtincha band — qo'lda/bank SMS orqali tasdiqlanadi)"
                if ocr_failed
                else "Chek qabul qilindi, bank SMS tushumi yoki admin tasdig'i kutilmoqda"
            )
        )
        verdict = ReceiptVerdict(
            verdict="ai_verified",
            parsed_amount=parsed_amount,
            parsed_last4=parsed_last4,
            tx_ref=tx_ref,
            reason=reason,
        )
        await self.db.add_receipt_check(order["id"], tx_ref, sha256, parsed_amount, parsed_last4, verdict.verdict, reason)
        await self.db.set_agent_status("accountant", "idle", f"Buyurtma #{order['id']} cheki tekshirildi — bank/admin kutilmoqda", increment_done=True)
        await self.db.log_agent_action("accountant", f"Buyurtma #{order['id']} cheki tekshirildi", reason)
        return verdict

    async def handle_uploaded_receipt(
        self,
        order: dict[str, Any],
        file_bytes: bytes,
        mime_type: str = "image/jpeg",
        doc_name: str = "chek",
        is_photo: bool = True,
        sales_bot: Bot | None = None,
        admin_bot: Bot | None = None,
        userbot=None,
        source_prefix: str = "",
        actor_label: str = "",
    ) -> tuple[ReceiptVerdict, str | None]:
        """Chekni tekshiradi, adminlarni ogohlantiradi va mijozga javob matnini qaytaradi (avto-tasdiqda None)."""
        verdict = await self.inspect_and_verify_receipt(
            order,
            file_bytes=file_bytes,
            mime_type=mime_type,
            sales_bot=sales_bot,
            admin_bot=admin_bot,
            userbot=userbot,
        )
        photo_arg = file_bytes if is_photo else None
        doc_arg = None if is_photo else (file_bytes, doc_name)

        if verdict.auto_approved:
            if admin_bot:
                await notify_admins(
                    admin_bot,
                    self.s,
                    f"🧾 {source_prefix}Avto-tasdiqlangan chek (Buyurtma #{order['id']})",
                    photo=photo_arg,
                    document=doc_arg,
                )
            return verdict, None

        stage_cargo = order["status"].startswith("cargo")
        look = await self.db.get_look(order["look_id"])
        amount = order["cargo_due"] if stage_cargo else order["prepay_due"]

        if verdict.verdict in ("duplicate", "suspicious_fake"):
            if admin_bot:
                caption = (
                    f"🚨 <b>{source_prefix}AI HISOBCHI OGOHLANTIRISHI ({verdict.verdict.upper()})</b>\n"
                    f"Sabab: <i>{escape(verdict.reason)}</i>\n"
                    f"Kutilgan summa: <code>{amount}</code> so'm\n\n"
                    + admin_order_card(order, look)
                )
                await notify_admins(
                    admin_bot,
                    self.s,
                    caption,
                    admin_order_kb(order, self.s),
                    photo=photo_arg,
                    document=doc_arg,
                )
            return (
                verdict,
                f"⚠️ Chek AI Hisobchi tekshiruvidan o'tmadi: {verdict.reason}\n\n"
                "Iltimos, to'lovni amalga oshirgan haqiqiy chek rasmini yuboring.",
            )

        new_status = "cargo_review" if stage_cargo else "payment_review"
        await self.db.update_order(order["id"], status=new_status)
        order["status"] = new_status
        if admin_bot:
            caption = (
                f"🧾 <b>{source_prefix}Chek: {'KARGO + QOLGAN 50%' if stage_cargo else 'OLDINDAN'} to'lov</b>\n"
                f"🤖 AI Hisobchi: <i>{escape(verdict.reason)}</i>\n"
                f"Kutilgan summa: <code>{amount}</code> so'm\n\n"
                + admin_order_card(order, look)
            )
            await notify_admins(
                admin_bot,
                self.s,
                caption,
                admin_order_kb(order, self.s),
                photo=photo_arg,
                document=doc_arg,
            )
        if actor_label:
            await self.db.log_agent_action(
                "sales_stylist",
                f"Buyurtma #{order['id']} bo'yicha to'lov cheki qabul qilindi",
                f"{actor_label} | Summa: {fmt(amount)} so'm | {verdict.reason}",
                target_id="accountant",
            )
        return (
            verdict,
            f"🔎 Chek AI Hisobchi tomonidan tekshirildi ({verdict.reason}).\n"
            f"Bank tushumi tasdiqlangach buyurtma #{order['id']} darhol Xitoy omboriga yuboriladi.",
        )

    @staticmethod
    async def check_verbal_payment_text(db: Database, user_id: int, text: str) -> str | None:
        """Og'zaki 'to'lov qildim' matniga AI tasdiqlab qo'ymasligi uchun qat'iy javob qaytaradi."""
        if not is_verbal_payment_claim(text):
            return None
        order = await db.payable_order(user_id)
        if not order:
            orders = await db.user_orders(user_id, limit=1)
            if orders and orders[0]["status"] in ("paid", "bought", "china_warehouse", "in_transit", "arrived", "cargo_paid", "delivered"):
                return None  # Buyurtmasi allaqachon tasdiqlangan bo'lsa, oddiy dialog davom etadi
            return (
                "⚠️ Og'zaki xabar bilan to'lov tasdiqlanmaydi.\n"
                "Avval buyurtmani rasmiylashtiring va to'lov chekini (rasm/skrinshot) shu yerga yuboring — "
                "shundan keyingina AI Hisobchi uni tekshirib tasdiqlaydi."
            )
        stage_cargo = order["status"].startswith("cargo")
        amount = int(order["cargo_due"] if stage_cargo else order["prepay_due"])
        return (
            f"⚠️ Buyurtma #{order['id']} hali to'langan deb tasdiqlanmadi (og'zaki xabar yetarli emas).\n\n"
            f"Iltimos, {fmt(amount)} so'm o'tkazganingizni tasdiqlovchi chek rasmini (skrinshot yoki PDF) "
            "shu yerga yuboring — AI Hisobchi chek va bank tushumini tekshirgach buyurtma tasdiqlanadi!"
        )
