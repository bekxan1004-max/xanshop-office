"""Sotuv bot: katalog, o'lcham tavsiyasi, buyurtma, chek qabul qilish, AI javoblar."""
import logging
import os
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup, default_state
from aiogram.types import (CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup,
                           KeyboardButton, Message, ReplyKeyboardMarkup)

from .accountant import AccountantAgent
from .ai import SalesAI, build_system_prompt
from .config import Settings
from .db import Database
from .notify import admin_order_kb, notify_admins
from .pricing import fmt, unique_amount
from .sizes import recommend
from .texts import (STATUS_LABELS, admin_order_card, look_50_values, look_caption, order_summary, payment_text,
                    split_list)

log = logging.getLogger(__name__)

BTN_LOOKS = "🛍 Looklar"
BTN_ORDERS = "📦 Buyurtmalarim"
BTN_OPERATOR = "👤 Operator"

MAIN_KB = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=BTN_LOOKS)], [KeyboardButton(text=BTN_ORDERS), KeyboardButton(text=BTN_OPERATOR)]],
    resize_keyboard=True)


class OrderForm(StatesGroup):
    size = State()
    height = State()
    weight = State()
    color = State()
    name = State()
    phone = State()
    address = State()
    confirm = State()


class OperatorForm(StatesGroup):
    message = State()


def ikb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t, callback_data=d) for t, d in row] for row in rows])


def look_kb(look_id: int) -> InlineKeyboardMarkup:
    return ikb([[("🛒 Buyurtma berish", f"order:{look_id}")],
                [("➡️ Keyingisi", f"next:{look_id}"), ("❓ Savol berish", f"ask:{look_id}")]])


def options_kb(prefix: str, options: list[str], extra: list[tuple[str, str]] | None = None,
               mark: str | None = None) -> InlineKeyboardMarkup:
    rows, row = [], []
    for i, opt in enumerate(options):
        row.append((f"⭐️ {opt}" if opt == mark else opt, f"{prefix}:{i}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    if extra:
        rows.append(extra)
    rows.append([("❌ Bekor qilish", "cancel_order")])
    return ikb(rows)


async def send_look(message: Message, look: dict, db: Database, s: Settings) -> None:
    caption = look_caption(look, s)
    photo = look.get("sales_file_id")
    if not photo and look.get("photo_path") and os.path.exists(look["photo_path"]):
        photo = FSInputFile(look["photo_path"])
    if photo:
        msg = await message.answer_photo(photo, caption=caption, reply_markup=look_kb(look["id"]))
        if not look.get("sales_file_id"):
            await db.update_look(look["id"], sales_file_id=msg.photo[-1].file_id)
    else:
        await message.answer(caption, reply_markup=look_kb(look["id"]))


def build_sales_router() -> Router:
    r = Router(name="sales")

    # ---------------- start / menyu ----------------
    @r.message(CommandStart())
    async def start(message: Message, command: CommandObject, state: FSMContext, db: Database, settings: Settings):
        await state.clear()
        await message.answer(
            f"Assalomu alaykum! <b>{escape(settings.shop_name)}</b> ga xush kelibsiz 👋\n"
            "Tayyor looklarni ko'ring, o'lcham bo'yicha yordam beraman, buyurtma 1 daqiqada.\n"
            "Istalgan savolni shu yerga yozing.", reply_markup=MAIN_KB)
        args = command.args or ""
        if args.startswith("look_") and args[5:].isdigit():  # Instagram havolasi: ?start=look_5
            look = await db.get_look(int(args[5:]))
            if look and look["active"]:
                await send_look(message, look, db, settings)
                return
        await show_first_look(message, db, settings)

    async def show_first_look(message: Message, db: Database, s: Settings):
        looks = await db.list_looks()
        if not looks:
            await message.answer("Hozircha yangi looklar tayyorlanmoqda. Tez orada qo'shiladi!")
            return
        await message.answer(f"Hozir {len(looks)} ta look bor. Birinchisi:")
        await send_look(message, looks[0], db, s)

    @r.message(F.text == BTN_LOOKS)
    @r.message(Command("looklar"))
    async def looks_cmd(message: Message, state: FSMContext, db: Database, settings: Settings):
        await state.clear()
        await show_first_look(message, db, settings)

    @r.callback_query(F.data.startswith("next:"))
    async def next_look(cb: CallbackQuery, db: Database, settings: Settings):
        current = int(cb.data.split(":")[1])
        looks = await db.list_looks()
        if not looks:
            await cb.answer("Looklar yo'q")
            return
        nxt = next((lk for lk in looks if lk["id"] > current), looks[0])
        await cb.answer()
        await send_look(cb.message, nxt, db, settings)

    @r.message(F.text == BTN_ORDERS)
    @r.message(Command("buyurtmalarim"))
    async def my_orders(message: Message, state: FSMContext, db: Database):
        await state.clear()
        orders = await db.user_orders(message.from_user.id)
        if not orders:
            await message.answer("Sizda hali buyurtma yo'q. 🛍 Looklar bo'limidan tanlang!")
            return
        for o in orders[:5]:
            await message.answer(order_summary(o, await db.get_look(o["look_id"])))

    # ---------------- operator ----------------
    @r.message(F.text == BTN_OPERATOR)
    async def operator(message: Message, state: FSMContext):
        await state.set_state(OperatorForm.message)
        await message.answer("Savolingizni yozing, operator tez orada javob beradi ✍️")

    @r.callback_query(F.data.startswith("ask:"))
    async def ask(cb: CallbackQuery):
        await cb.answer()
        await cb.message.answer("Savolingizni yozing — o'lcham, rang, mato, yetkazish... Darhol javob beraman 🙂")

    @r.message(OperatorForm.message)
    async def operator_msg(message: Message, state: FSMContext, admin_bot: Bot, settings: Settings):
        await state.clear()
        await forward_to_operator(message, admin_bot, settings, message.text or "(matnsiz xabar)")
        await message.answer("✅ Yuborildi. Operator shu yerda javob beradi.", reply_markup=MAIN_KB)

    async def forward_to_operator(message: Message, admin_bot: Bot, s: Settings, text: str):
        u = message.from_user
        who = f"@{u.username}" if u.username else escape(u.full_name)
        await notify_admins(admin_bot, s,
                            f"👤 <b>Operator kerak</b> — {who} (id <code>{u.id}</code>)\n\n{escape(text)}\n\n"
                            f"Javob: <code>/javob {u.id} </code>matn")

    # ---------------- buyurtma oqimi ----------------
    @r.callback_query(F.data.startswith("order:"))
    async def order_start(cb: CallbackQuery, state: FSMContext, db: Database):
        look = await db.get_look(int(cb.data.split(":")[1]))
        if not look or not look["active"]:
            await cb.answer("Bu look hozir mavjud emas", show_alert=True)
            return
        await cb.answer()
        await state.clear()
        await state.update_data(look_id=look["id"], sizes=split_list(look["sizes"]),
                                colors=split_list(look["colors"]))
        await ask_size(cb.message, state)

    async def ask_size(message: Message, state: FSMContext, mark: str | None = None):
        data = await state.get_data()
        if not data["sizes"]:
            await state.update_data(size="")
            await ask_color(message, state)
            return
        await state.set_state(OrderForm.size)
        text = "📏 O'lchamni tanlang:" if not mark else f"⭐️ Sizga <b>{escape(mark)}</b> mos keladi. Tanlang:"
        await message.answer(text, reply_markup=options_kb(
            "size", data["sizes"], [("📏 O'lchamimni bilmayman", "size_help")], mark))

    @r.callback_query(OrderForm.size, F.data == "size_help")
    async def size_help(cb: CallbackQuery, state: FSMContext):
        await cb.answer()
        await state.set_state(OrderForm.height)
        await cb.message.answer("Bo'yingiz necha sm? (masalan: 175)")

    @r.message(OrderForm.height)
    async def got_height(message: Message, state: FSMContext):
        try:
            h = float((message.text or "").replace(",", "."))
            assert 120 <= h <= 220
        except (ValueError, AssertionError):
            await message.answer("Bo'yni sm da raqam bilan yozing, masalan: 175")
            return
        await state.update_data(height=h)
        await state.set_state(OrderForm.weight)
        await message.answer("Vazningiz necha kg? (masalan: 70)")

    @r.message(OrderForm.weight)
    async def got_weight(message: Message, state: FSMContext):
        try:
            w = float((message.text or "").replace(",", "."))
            assert 30 <= w <= 200
        except (ValueError, AssertionError):
            await message.answer("Vaznni kg da raqam bilan yozing, masalan: 70")
            return
        data = await state.get_data()
        rec = recommend(data["height"], w, data["sizes"])
        if rec is None:
            await message.answer("Bu lookda o'lchamlar maxsus jadval bo'yicha. Operator aniqlab beradi, "
                                 "hozircha taxminiy o'lchamni tanlang.")
        await ask_size(message, state, rec)

    @r.callback_query(OrderForm.size, F.data.startswith("size:"))
    async def got_size(cb: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        await state.update_data(size=data["sizes"][int(cb.data.split(":")[1])])
        await cb.answer()
        await ask_color(cb.message, state)

    async def ask_color(message: Message, state: FSMContext):
        data = await state.get_data()
        if not data["colors"]:
            await state.update_data(color="")
            await ask_name(message, state)
            return
        await state.set_state(OrderForm.color)
        await message.answer("🎨 Rangni tanlang:", reply_markup=options_kb("color", data["colors"]))

    @r.callback_query(OrderForm.color, F.data.startswith("color:"))
    async def got_color(cb: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        await state.update_data(color=data["colors"][int(cb.data.split(":")[1])])
        await cb.answer()
        await ask_name(cb.message, state)

    async def ask_name(message: Message, state: FSMContext):
        await state.set_state(OrderForm.name)
        await message.answer("👤 Qabul qiluvchining ism-familiyasi:")

    @r.message(OrderForm.name, F.text)
    async def got_name(message: Message, state: FSMContext):
        await state.update_data(full_name=message.text.strip()[:100])
        await state.set_state(OrderForm.phone)
        kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📞 Raqamni yuborish", request_contact=True)]],
                                 resize_keyboard=True, one_time_keyboard=True)
        await message.answer("📞 Telefon raqamingiz (tugmani bosing yoki yozing):", reply_markup=kb)

    @r.message(OrderForm.phone)
    async def got_phone(message: Message, state: FSMContext):
        phone = message.contact.phone_number if message.contact else (message.text or "").strip()
        digits = "".join(ch for ch in phone if ch.isdigit())
        if len(digits) < 9:
            await message.answer("Telefon raqamni to'liq yozing, masalan: +998 90 123 45 67")
            return
        await state.update_data(phone=phone)
        await state.set_state(OrderForm.address)
        await message.answer("🏠 Yetkazish manzili (viloyat, tuman, ko'cha, uy):", reply_markup=MAIN_KB)

    @r.message(OrderForm.address, F.text)
    async def got_address(message: Message, state: FSMContext, db: Database):
        await state.update_data(address=message.text.strip()[:300])
        data = await state.get_data()
        look = await db.get_look(data["look_id"])
        p50, rem50 = look_50_values(look)
        await state.set_state(OrderForm.confirm)
        await message.answer(
            "<b>Buyurtmani tekshiring va to'lov usulini tanlang:</b>\n\n"
            f"👗 {escape(look['title'])}\n"
            + (f"📏 O'lcham: {escape(data['size'])}\n" if data.get("size") else "")
            + (f"🎨 Rang: {escape(data['color'])}\n" if data.get("color") else "")
            + f"👤 {escape(data['full_name'])}\n📞 {escape(data['phone'])}\n🏠 {escape(data['address'])}\n\n"
            f"🌗 <b>1-variant (50% oldindan): ~{fmt(p50)} so'm</b>\n"
            f"   <i>Qolgan 50% ({fmt(rem50)} so'm) + kargo (~{fmt(look['cargo_est_uzs'])} so'm) yuk O'zbekistonga kelganda to'lanadi!</i>\n\n"
            f"💯 <b>2-variant (100% to'liq): ~{fmt(look['prepay_uzs'])} so'm</b>\n"
            f"   <i>Yuk O'zbekistonga kelganda faqat kargo (~{fmt(look['cargo_est_uzs'])} so'm) to'lanadi!</i>",
            reply_markup=ikb([
                [(f"🌗 50% oldindan ({fmt(p50)} so'm)", "confirm_order:50")],
                [(f"💯 100% to'liq ({fmt(look['prepay_uzs'])} so'm)", "confirm_order:100")],
                [("❌ Bekor qilish", "cancel_order")],
            ]),
        )

    @r.callback_query(F.data == "cancel_order")
    async def cancel_order(cb: CallbackQuery, state: FSMContext):
        await state.clear()
        await cb.answer("Bekor qilindi")
        await cb.message.answer("Buyurtma bekor qilindi. Boshqa looklarni ko'rishingiz mumkin.", reply_markup=MAIN_KB)

    @r.callback_query(OrderForm.confirm, F.data.startswith("confirm_order"))
    async def confirm_order(cb: CallbackQuery, state: FSMContext, db: Database, settings: Settings, admin_bot: Bot):
        data = await state.get_data()
        await state.clear()
        look = await db.get_look(data["look_id"])
        p50, rem50 = look_50_values(look)
        plan = "100" if cb.data.endswith(":100") else "50"
        base_prepay = int(look["prepay_uzs"]) if plan == "100" else p50
        rem_uzs = 0 if plan == "100" else rem50

        u = cb.from_user
        oid = await db.create_order(
            user_id=u.id, username=u.username, full_name=data["full_name"], phone=data["phone"],
            address=data["address"], look_id=look["id"], size=data.get("size", ""), color=data.get("color", ""),
            payment_plan=plan, prepay_due=0, remaining_uzs=rem_uzs,
            profit_uzs=look["profit_uzs"], goods_cost_uzs=look["goods_cost_uzs"],
            status="awaiting_payment")
        amount = unique_amount(base_prepay, oid)
        await db.update_order(oid, prepay_due=amount)
        await db.set_agent_status("sales_stylist", "idle", f"Buyurtma #{oid} ({plan}%) rasmiylashtirildi", increment_done=True)
        await db.log_agent_action("sales_stylist", f"Yangi buyurtma #{oid} qabul qilindi ({plan}% to'lov rejasi)",
                                  f"Mijoz: {data['full_name']}, Oldindan: {fmt(amount)} so'm, Qolgan: {fmt(rem_uzs)} so'm")
        await cb.answer("Buyurtma qabul qilindi")
        label = f"Oldindan to'lov ({plan}%)"
        await cb.message.answer(f"✅ Buyurtma <b>#{oid}</b> ({plan}% reja) qabul qilindi!\n\n"
                                + payment_text(amount, settings, label))
        order = await db.get_order(oid)
        await notify_admins(admin_bot, settings, f"🆕 Yangi buyurtma ({plan}% to'lov kutilmoqda)\n\n"
                            + admin_order_card(order, look), reply_markup=admin_order_kb(order, settings))

    # ---------------- chek ----------------
    @r.message(StateFilter(default_state), F.photo | F.document)
    async def receipt(message: Message, bot: Bot, db: Database, settings: Settings, admin_bot: Bot):
        order = await db.payable_order(message.from_user.id)
        if not order:
            await message.answer("Rasm uchun rahmat! Agar bu to'lov cheki bo'lsa, avval buyurtma bering. "
                                 "Savol bo'lsa yozing 🙂")
            return
        if message.photo:
            data = await bot.download(message.photo[-1])
            file_bytes, mime_type, is_photo, doc_name = data.read(), "image/jpeg", True, "chek.jpg"
        else:
            data = await bot.download(message.document)
            file_bytes = data.read()
            mime_type = message.document.mime_type or "application/octet-stream"
            is_photo, doc_name = False, message.document.file_name or "chek"

        verdict, client_reply = await AccountantAgent(db, settings).handle_uploaded_receipt(
            order,
            file_bytes=file_bytes,
            mime_type=mime_type,
            doc_name=doc_name,
            is_photo=is_photo,
            sales_bot=bot,
            admin_bot=admin_bot,
        )
        if client_reply:
            status_line = (
                f"\nBuyurtma #{order['id']}: {STATUS_LABELS[order['status']]}"
                if verdict.verdict == "ai_verified"
                else ""
            )
            await message.answer(escape(client_reply) + status_line)

    # ---------------- erkin savollar -> AI ----------------
    @r.message(StateFilter(default_state), F.text)
    async def free_text(message: Message, bot: Bot, db: Database, settings: Settings, ai: SalesAI, admin_bot: Bot):
        uid = message.from_user.id
        verbal_warn = await AccountantAgent.check_verbal_payment_text(db, uid, message.text)
        if verbal_warn:
            await message.answer(escape(verbal_warn))
            return
        if not ai.enabled:
            await forward_to_operator(message, admin_bot, settings, message.text)
            await message.answer("Savolingiz operatorga yuborildi, tez orada javob beramiz 🙏", reply_markup=MAIN_KB)
            return
        await bot.send_chat_action(uid, "typing")
        system = build_system_prompt(settings, await db.list_looks(), await db.user_orders(uid))
        answer, inter_id, need_admin = await ai.reply(system, message.text, await db.get_interaction(uid))
        if inter_id:
            await db.set_interaction(uid, inter_id)
        await message.answer(answer or "Savolingiz operatorga yuborildi, tez orada javob beramiz 🙏")
        if need_admin or not answer:
            await forward_to_operator(message, admin_bot, settings, message.text)

    @r.callback_query()
    async def stale_button(cb: CallbackQuery):
        await cb.answer("Bu tugma eskirgan. 🛍 Looklar tugmasidan qaytadan boshlang.", show_alert=True)

    return r
