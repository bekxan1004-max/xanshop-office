"""Admin bot: sizning boshqaruv paneli. To'lov tasdiqlash, statuslar, looklar, narx, hisobot."""
import json
import logging
import os
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup, default_state
from aiogram.types import BotCommand, BufferedInputFile, CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message

from .accountant import AccountantAgent, parse_bank_deposit_text
from .config import Settings
from .db import Database
from .economy import get_params, get_rates, refresh_rates
from .logistics import LogisticsAgent
from .notify import admin_order_kb, notify_client, notify_client_photo, send_to_agent
from .office import AgentOffice
from .pricing import Item, PriceBreakdown, PriceParams, Rates, calculate, cargo_charge, fmt, parse_items, unique_amount
from .publisher import generate_premium_channel_kit
from .texts import (CLIENT_STATUS_MESSAGES, NEXT_STATUS, STATUS_LABELS, admin_order_card, agent_card, look_items,
                    payment_text)

log = logging.getLogger(__name__)
PHOTO_DIR = os.path.join("data", "photos")

HELP = """<b>📖 BARCHA BUYRUQLAR (Tezkor ro‘yxat)</b>

🧠 <b>Ochiq O‘rganish & Kontent:</b>
• Istalgan <b>TG/IG link</b> yoki <b>.mp4 video</b> tashlang — tizim o‘zi o‘rganadi!
/manba <i>havola</i> — TG kanal, IG profil yoki Reelsdan o‘qitish
/manbalar — O‘rganilgan kanallar va faol playbooklar
/tg_holat [yoq|toxtat] — IG yo‘q paytda bo‘sh TG postni to‘xtatish/yoqish
/ai_look — Hoziroq 1080p AI Look yaratish
/ofis — 7 ta AI agent holati · /kanal_paket — Bio paket

📦 <b>Buyurtmalar & Kargo:</b>
/buyurtmalar · /b <i>ID</i> — Buyurtmalar kartochkasi
/trek <i>ID kod</i> — Trek kiritish · /javob <i>ID matn</i> — Mijozga yozish

💰 <b>Katalog & Moliya:</b>
/looklar · /look_qosh — Katalog
/narx 80+60 1.8 · /kurs · /foyda · /hisobot · /hisobchi · /qayta_hisob"""


class AddLook(StatesGroup):
    photo = State()
    title = State()
    items = State()
    sizes = State()
    colors = State()
    confirm = State()


class AdminForm(StatesGroup):
    weight = State()
    source_link = State()


ADMIN_BOT_COMMANDS = [
    BotCommand(command="start", description="👑 Minimalist Boshqaruv Markazi"),
    BotCommand(command="ai_look", description="⚡ 1080p AI Look yaratish"),
    BotCommand(command="manba", description="🧠 TG/IG/Reel linkidan tizimni o'qitish"),
    BotCommand(command="manbalar", description="📘 O'rganilgan kanallar va strategiyalar"),
    BotCommand(command="tg_holat", description="⏸/🟢 Bo'sh TG postni boshqarish"),
    BotCommand(command="ofis", description="🏢 7 ta AI agent holati"),
    BotCommand(command="buyurtmalar", description="📦 Faol buyurtmalar"),
    BotCommand(command="looklar", description="👔 Katalog va havolalar"),
    BotCommand(command="hisobot", description="💰 Tushum va sof foyda"),
    BotCommand(command="kurs", description="💱 Valyuta kurslari"),
    BotCommand(command="help", description="📖 Barcha buyruqlar"),
]


def ikb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t, callback_data=d) for t, d in row] for row in rows])


def breakdown_text(b: PriceBreakdown, rates: Rates, p: PriceParams) -> str:
    cargo_margin = b.cargo_client_uzs - b.cargo_cost_uzs
    conv_line = (
        f" + tranzaksiya (UZS→CNY {p.conversion_fee_percent:g}%): {fmt(b.conversion_fee_uzs)} so'm"
        if b.conversion_fee_uzs
        else ""
    )
    return (
        f"Tovarlar: ¥{b.goods_cny} + ichki yetkazish ¥{b.china_shipping_cny} + vykup {p.vykup_percent:g}% "
        f"¥{b.vykup_cny} = <b>¥{b.total_cny}</b>\n"
        f"Kurs: 1¥ = {rates.cny_uzs:.0f} so'm{conv_line} → jami xarajat: <b>{fmt(b.goods_cost_uzs)} so'm</b>\n"
        f"Foyda ({p.profit_percent:g}%): {fmt(b.profit_uzs)} so'm"
        + (f" (komissiya {fmt(b.fee_uzs)})" if b.fee_uzs else "") + "\n"
        f"💯 <b>100% Sotuv narxi: {fmt(b.prepay_uzs)} so'm</b>\n"
        f"🌗 <b>50% Oldindan to'lov: {fmt(b.prepay_50_uzs)} so'm</b> (xarid + tranzaksiyani 100% qoplaydi!)\n"
        f"⏳ <b>Qolgan 50%: {fmt(b.remaining_50_uzs)} so'm</b> (O'zbekistonga kelganda kargo bilan olinadi)\n\n"
        f"Vazn {b.weight_kg} kg → kargo tannarxi {fmt(b.cargo_cost_uzs)}, mijozdan {fmt(b.cargo_client_uzs)} "
        f"(farq {fmt(cargo_margin)})\n"
        f"✈️ 50% tanlaganda Toshkentda to'lanadigan (qolgan 50% + kargo): <b>{fmt(b.arrival_50_est_uzs)} so'm</b>\n"
        f"💵 <b>Jami sof foyda: {fmt(b.total_profit_uzs)} so'm</b>"
    )


def build_admin_router(s: Settings) -> Router:
    root = Router(name="admin_root")
    admin = Router(name="admin")
    admin.message.filter(F.from_user.id.in_(s.admin_ids))
    admin.callback_query.filter(F.from_user.id.in_(s.admin_ids))
    staff_ids = set(s.admin_ids) | ({s.agent_chat_id} if s.agent_chat_id else set())
    staff = Router(name="staff")
    staff.message.filter(F.from_user.id.in_(staff_ids))
    root.include_routers(admin, staff)

    # ---------------- minimalist boshqaruv markazi ----------------
    async def _build_home_hub(db: Database) -> tuple[str, InlineKeyboardMarkup]:
        orders = await db.active_orders(limit=50)
        looks = await db.list_looks(only_active=True)
        sources = await db.list_tracked_sources(limit=50)
        pbs = await db.get_all_playbooks()
        rates, params = await get_rates(db, s), await get_params(db, s)
        allow_tg = (await db.get_setting("allow_tg_without_ig")) == "1"
        ig_paused = (await db.get_setting("ig_pause_alerted")) == "1"

        if allow_tg:
            tg_badge = "🟢 TG Erkin Yoqilgan"
            tg_btn = "⏸ TG Avto: Yoqiq"
        elif ig_paused:
            tg_badge = "⏸ Pauzada (IG checkpoint — token tejalmoqda)"
            tg_btn = "🟢 TG Avto: Pauzada"
        else:
            tg_badge = "🟢 IG + TG Avto Tayyor"
            tg_btn = "⏸ TG Avto: Auto"

        text = (
            f"👑 <b>{escape(s.shop_name)} · Boshqaruv Markazi</b>\n\n"
            f"📦 Buyurtma: <b>{len(orders)}</b> · 👔 Look: <b>{len(looks)}</b>\n"
            f"🧠 Bilim: <b>{len(sources)}</b> manba · <b>{len(pbs)}</b> playbook\n"
            f"📡 Avto-nashr: {tg_badge}\n"
            f"💱 1¥ = <b>{rates.cny_uzs:.0f}</b> so'm · Foyda: <b>{params.profit_percent:g}%</b>\n\n"
            "💡 <i>Istalgan <b>t.me / instagram.com</b> link yoki <b>.mp4 video</b> tashlasangiz — "
            "tizim o‘zi o‘rganib rivojlanadi.</i>"
        )
        kb = ikb([
            [("⚡ AI Look", "adm:ai_look"), ("🏢 AI Ofis", "adm:office")],
            [("🧠 Manbalar", "adm:sources"), ("➕ Link O‘rgatish", "adm:add_src")],
            [("📦 Buyurtmalar", "adm:orders"), ("👔 Katalog", "adm:looks")],
            [("💰 Moliya & Kurs", "adm:finance"), (tg_btn, "adm:tg_toggle")],
            [("🎬 Video Tahlil", "adm:video_help"), ("📖 Buyruqlar", "adm:cmds")],
        ])
        return text, kb

    async def _edit_or_send(cb: CallbackQuery, text: str, kb: InlineKeyboardMarkup | None = None):
        try:
            await cb.message.edit_text(text, reply_markup=kb)
        except Exception:
            await cb.message.answer(text, reply_markup=kb)

    @admin.message(CommandStart())
    @admin.message(Command("help"))
    async def start(message: Message, state: FSMContext, db: Database):
        await state.clear()
        txt, kb = await _build_home_hub(db)
        await message.answer(txt, reply_markup=kb)

    @admin.message(Command("bekor"))
    async def cancel_any(message: Message, state: FSMContext, db: Database):
        await state.clear()
        txt, kb = await _build_home_hub(db)
        await message.answer("❌ Amal bekor qilindi.\n\n" + txt, reply_markup=kb)

    @admin.callback_query(F.data == "adm:home")
    async def cb_home(cb: CallbackQuery, state: FSMContext, db: Database):
        await state.clear()
        await cb.answer()
        txt, kb = await _build_home_hub(db)
        await _edit_or_send(cb, txt, kb)

    @admin.callback_query(F.data == "adm:cmds")
    async def cb_cmds(cb: CallbackQuery):
        await cb.answer()
        await _edit_or_send(cb, HELP, ikb([[("◀️ Bosh menyu", "adm:home")]]))

    @admin.callback_query(F.data == "adm:video_help")
    async def cb_video_help(cb: CallbackQuery):
        await cb.answer()
        await _edit_or_send(
            cb,
            "🎬 <b>Namuna Video Orqali Tizimni O‘qitish</b>\n\n"
            "• Istalgan Reels <code>.mp4</code> videoni shu yerga tashlang (yoki forward qiling).\n"
            "• Tizim kadrlarni, montaj tempini, matn uslubini va zvuk turini tahlil qilib, "
            "<b>Video Montajchi</b> hamda <b>IG/TG Strategiya</b> bazasiga yozadi.",
            ikb([[("◀️ Bosh menyu", "adm:home")]]),
        )

    @admin.callback_query(F.data == "adm:office")
    async def cb_office(cb: CallbackQuery, db: Database):
        await cb.answer()
        agents = await db.list_agents()
        lines = [f"🏢 <b>{escape(s.shop_name)} · 7 ta AI Agent</b>\n"]
        for a in agents:
            icon = "🟢" if a["status"] == "idle" else ("⚡" if a["status"] == "working" else "🔴")
            lines.append(f"{icon} <b>{escape(a['name'])}</b> ({a['tasks_done']} ta)\n   └ <i>{escape(a['current_task'][:90])}</i>")
        await _edit_or_send(cb, "\n".join(lines), ikb([[("🔄 Yangilash", "adm:office"), ("◀️ Bosh menyu", "adm:home")]]))

    @admin.callback_query(F.data == "adm:sources")
    async def cb_sources(cb: CallbackQuery, db: Database):
        await cb.answer()
        sources = await db.list_tracked_sources(limit=12)
        pbs = await db.get_all_playbooks()
        lines = ["🧠 <b>O‘rganilgan Kanallar & Playbooklar</b>\n"]
        if not sources:
            lines.append("Hali tashqi manba qo‘shilmagan. <b>➕ Link O‘rgatish</b> ni bosing.")
        for src in sources[:8]:
            lines.append(
                f"• <b>[{escape(src['platform'])}]</b> <code>{escape((src['url'] or src['source_key'])[:55])}</code>\n"
                f"  └ <i>{escape((src.get('style_summary') or '')[:95])}</i>"
            )
        if pbs:
            lines.append(f"\n📘 Faol playbooklar: <code>{', '.join(pbs.keys())}</code>")
        await _edit_or_send(
            cb,
            "\n".join(lines),
            ikb([[("➕ Link O‘rgatish", "adm:add_src"), ("🔄 Yangilash", "adm:sources")], [("◀️ Bosh menyu", "adm:home")]]),
        )

    @admin.callback_query(F.data == "adm:add_src")
    async def cb_add_src(cb: CallbackQuery, state: FSMContext):
        await state.set_state(AdminForm.source_link)
        await cb.answer()
        await cb.message.answer(
            "🔗 <b>Telegram kanal, Instagram sahifa yoki Reel havolasini yuboring:</b>\n"
            "Masalan: <code>https://t.me/kanal_nomi</code> yoki link + izoh.\n\n"
            "Bekor qilish: /bekor"
        )

    @admin.message(AdminForm.source_link, F.text)
    async def fsm_source_link_got(message: Message, state: FSMContext, db: Database):
        raw = (message.text or "").strip()
        if raw.startswith("/"):
            await state.clear()
            await message.answer("Bekor qilindi. /help")
            return
        await state.clear()
        parts = raw.split(maxsplit=1)
        url_arg = parts[0]
        note_arg = parts[1] if len(parts) > 1 else ""
        wait_m = await message.answer("🕵️‍♂️ <b>Halol O‘g‘ri manbani o‘rganmoqda...</b>")
        from .source_learner import ingest_and_learn_source
        res = await ingest_and_learn_source(db, s, url_arg, user_instruction=note_arg)
        if not res.get("ok"):
            await wait_m.edit_text(f"❌ Xato: {escape(str(res.get('error', '')))}", reply_markup=ikb([[("◀️ Bosh menyu", "adm:home")]]))
            return
        await wait_m.edit_text(
            f"✅ <b>Manba o‘zlashtirildi ({escape(res['platform'].upper())})</b>\n"
            f"🔗 <code>{escape(res['url'])}</code>\n"
            f"🎨 <i>{escape(res.get('style_summary') or '')[:220]}</i>\n"
            f"{'⏱ ' + escape(res['posting_pattern']) if res.get('posting_pattern') else ''}",
            reply_markup=ikb([[("🧠 Manbalar", "adm:sources"), ("◀️ Bosh menyu", "adm:home")]]),
        )

    @admin.callback_query(F.data == "adm:tg_toggle")
    async def cb_tg_toggle(cb: CallbackQuery, db: Database):
        cur = await db.get_setting("allow_tg_without_ig")
        new_val = "0" if cur == "1" else "1"
        await db.set_setting("allow_tg_without_ig", new_val)
        await cb.answer("🟢 TG avto yoqildi" if new_val == "1" else "⏸ IG blokda bo'lsa TG pauzada")
        txt, kb = await _build_home_hub(db)
        await _edit_or_send(cb, txt, kb)

    @admin.callback_query(F.data == "adm:orders")
    async def cb_orders(cb: CallbackQuery, db: Database):
        await cb.answer()
        orders = await db.active_orders(limit=10)
        if not orders:
            await _edit_or_send(cb, "📦 Hozircha faol buyurtmalar yo‘q.", ikb([[("◀️ Bosh menyu", "adm:home")]]))
            return
        await cb.message.answer(f"📦 <b>So‘nggi {len(orders)} ta faol buyurtma:</b>")
        for o in reversed(orders[:5]):
            await send_card(cb.message, db, o)

    @admin.callback_query(F.data == "adm:looks")
    async def cb_looks(cb: CallbackQuery, db: Database, sales_username: str):
        await cb.answer()
        looks = await db.list_looks(only_active=False)
        if not looks:
            await _edit_or_send(cb, "👔 Katalog bo‘sh. /ai_look yoki /look_qosh bosing.", ikb([[("◀️ Bosh menyu", "adm:home")]]))
            return
        lines = [f"👔 <b>Katalog ({len(looks)} ta look):</b>\n"]
        for lk in looks[:10]:
            st = "✅" if lk["active"] else "⏸"
            lines.append(f"{st} <b>#{lk['id']}</b> {escape(lk['title'][:40])} — {fmt(lk['prepay_uzs'])} so'm (50%: {fmt(lk.get('prepay_50_uzs') or 0)})")
        lines.append("\nBatafsil /toggle uchun: /looklar")
        await _edit_or_send(cb, "\n".join(lines), ikb([[("⚡ Yangi AI Look", "adm:ai_look"), ("◀️ Bosh menyu", "adm:home")]]))

    @admin.callback_query(F.data == "adm:finance")
    async def cb_finance(cb: CallbackQuery, db: Database):
        await cb.answer()
        orders = await db.all_orders()
        paid = [o for o in orders if o["status"] not in ("awaiting_payment", "payment_review", "cancelled")]
        cargo_paid = [o for o in paid if o["status"] in ("cargo_paid", "delivered") and o["cargo_due"]]
        revenue = sum(o["prepay_due"] for o in paid) + sum(o["cargo_due"] for o in cargo_paid)
        profit = sum(o["profit_uzs"] for o in paid) + sum(o["cargo_due"] - o["cargo_cost_uzs"] for o in cargo_paid)
        rates, params = await get_rates(db, s), await get_params(db, s)
        txs = await db.list_bank_transactions(limit=4)
        tx_lines = [f"• +{fmt(t['amount_uzs'])} so'm (*{escape(t.get('card_last4') or '????')})" for t in txs] or ["Hozircha tushum yo‘q"]
        txt = (
            "💰 <b>Moliya & Kurslar</b>\n\n"
            f"📦 Jami buyurtma: <b>{len(orders)}</b> (to‘langan: <b>{len(paid)}</b>)\n"
            f"💵 Tushum: <b>{fmt(revenue)} so'm</b>\n"
            f"💎 Taxminiy sof foyda: <b>{fmt(profit)} so'm</b>\n"
            f"💱 Kurs: 1¥ = <b>{rates.cny_uzs:.1f}</b> so'm · 1$ = <b>{rates.usd_uzs:.0f}</b> so'm · Foyda: <b>{params.profit_percent:g}%</b>\n\n"
            "🏦 <b>So‘nggi karta tushumlari:</b>\n" + "\n".join(tx_lines)
        )
        await _edit_or_send(cb, txt, ikb([[("🔄 CBU Kurs Yangilash", "adm:refresh_rates"), ("◀️ Bosh menyu", "adm:home")]]))

    @admin.callback_query(F.data == "adm:refresh_rates")
    async def cb_refresh_rates(cb: CallbackQuery, db: Database):
        res = await refresh_rates(db, s)
        await cb.answer("✅ CBU dan yangilandi" if res else "❌ CBU xatosi", show_alert=not bool(res))
        await cb_finance(cb, db)

    @admin.callback_query(F.data == "adm:ai_look")
    async def cb_ai_look(cb: CallbackQuery, db: Database, sales_bot: Bot, admin_bot: Bot, sales_username: str):
        await cb.answer("⚡ Ishga tushirildi...")
        wait_msg = await cb.message.answer("⚡ <b>1080p AI Look tayyorlanmoqda...</b>")
        office = AgentOffice(db=db, settings=s, sales_bot=sales_bot, admin_bot=admin_bot, sales_username=sales_username)
        res = await office.run_look_pipeline(season="avtomatik ob-havo", delete_previous=False, notify_admin_on_publish=False)
        try:
            await wait_msg.delete()
        except Exception:
            pass
        caption = (
            f"✅ <b>Look #{res.look_id} ({res.piece_count} qism, 1080p)</b>\n"
            f"👔 <b>{escape(res.title)}</b>\n"
            f"💳 <b>50%: {fmt(res.prepay_50_uzs)} so'm</b> + kargo (100%: {fmt(res.prepay_uzs)} so'm)\n"
            f"🎬 <code>{escape(res.video_style)}</code> · 🎵 <code>{escape(res.audio_vibe)}</code>"
        )
        if res.mp4_path and res.mp4_path.endswith(".mp4") and os.path.exists(res.mp4_path):
            await cb.message.answer_video(FSInputFile(res.mp4_path), caption=caption, supports_streaming=True, reply_markup=ikb([[("◀️ Bosh menyu", "adm:home")]]))
        elif os.path.exists(res.photo_path):
            await cb.message.answer_photo(FSInputFile(res.photo_path), caption=caption, reply_markup=ikb([[("◀️ Bosh menyu", "adm:home")]]))
        else:
            await cb.message.answer(caption, reply_markup=ikb([[("◀️ Bosh menyu", "adm:home")]]))

    async def send_card(message: Message, db: Database, order: dict, note: str = ""):
        look = await db.get_look(order["look_id"])
        await message.answer((note + "\n\n" if note else "") + admin_order_card(order, look),
                             reply_markup=admin_order_kb(order, s))

    async def drop_kb(cb: CallbackQuery):
        try:
            await cb.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass

    @admin.message(Command("buyurtmalar"))
    async def orders_cmd(message: Message, db: Database):
        orders = await db.active_orders()
        if not orders:
            await message.answer("Faol buyurtmalar yo'q.")
            return
        for o in reversed(orders):
            await send_card(message, db, o)

    @admin.message(Command("b"))
    async def order_cmd(message: Message, command: CommandObject, db: Database):
        if not command.args or not command.args.strip().isdigit():
            await message.answer("Masalan: /b 15")
            return
        order = await db.get_order(int(command.args))
        if not order:
            await message.answer("Topilmadi.")
            return
        await send_card(message, db, order)

    # ---------------- AI Agent Office (/ofis va /ai_look) ----------------
    @admin.message(Command("ofis"))
    async def office_cmd(message: Message, db: Database):
        agents = await db.list_agents()
        lines = [f"🏢 <b>{escape(s.shop_name)} — AI AGENT OFFICE</b>\n"]
        for a in agents:
            icon = "🟢" if a["status"] == "idle" else ("⚡" if a["status"] == "working" else "🔴")
            boss = f" (Boshlig'i: {a['boss_id']})" if a.get("boss_id") else ""
            lines.append(
                f"{icon} <b>{escape(a['name'])}</b>{boss}\n"
                f"   └ Vazifa: <i>{escape(a['current_task'])}</i> · Bajarildi: <b>{a['tasks_done']}</b> ta"
            )
        lines.append(f"\n🌐 <b>Ochiq Web-Ofis Boshqaruv Paneli:</b>\n<code>http://localhost:{s.office_port}</code>")
        lines.append("\n🚀 Yangi avtonom Look + Kolaj + Reels video yaratish: /ai_look")
        await message.answer("\n".join(lines))

    @admin.message(Command("kanal_paket"))
    async def channel_kit_cmd(message: Message):
        kit = generate_premium_channel_kit(s.shop_name, s.manager_username)
        await message.answer(
            "🏆 <b>INSTAGRAM VA TELEGRAM KANAL UCHUN PREMIUM OFORMLENIYA PAKETI</b>\n\n"
            f"📸 <b>Instagram Bio:</b>\n<code>{escape(kit['instagram_bio'])}</code>\n\n"
            f"⭕ <b>Instagram Aktualnoe (Highlights):</b>\n<code>{escape(kit['instagram_highlights'])}</code>\n\n"
            f"📢 <b>Telegram Kanal Bio:</b>\n<code>{escape(kit['telegram_channel_bio'])}</code>\n\n"
            f"📌 <b>Telegram Kanal Zakrep (Pinned Post):</b>\n{kit['telegram_pinned_post']}"
        )

    @admin.message(Command("manba"))
    @admin.message(Command("addsource"))
    async def add_source_cmd(message: Message, command: CommandObject, db: Database):
        args_str = (command.args or "").strip()
        if not args_str:
            await message.answer(
                "🔗 Menga o'rganish uchun Telegram kanal, Instagram akkaunt yoki Reels linkini yuboring:\n"
                "Masalan: <code>/manba https://t.me/kanal_nomi</code>\n"
                "yoki <code>/manba https://www.instagram.com/accaunt/ montaj zo'r</code>"
            )
            return
        parts = args_str.split(maxsplit=1)
        url_arg = parts[0]
        note_arg = parts[1] if len(parts) > 1 else ""
        wait_m = await message.answer("🕵️‍♂️ <b>Halol O'g'ri manbani o'rganmoqda...</b>")
        from .source_learner import ingest_and_learn_source
        res = await ingest_and_learn_source(db, s, url_arg, user_instruction=note_arg)
        if not res.get("ok"):
            await wait_m.edit_text(f"❌ Xato: {escape(str(res.get('error', 'noma`lum')))}")
            return
        msg_lines = [
            f"✅ <b>Manba tizimga qo'shildi ({escape(res['platform'].upper())})</b>",
            f"🔗 <code>{escape(res['url'])}</code>",
            f"📌 Holat: <b>{escape(res['status'])}</b>",
        ]
        if res.get("style_summary"):
            msg_lines.append(f"🎨 Xulosa: <i>{escape(res['style_summary'])}</i>")
        if res.get("posting_pattern"):
            msg_lines.append(f"⏱ Ritm: {escape(res['posting_pattern'])}")
        if res.get("pricing_pattern"):
            msg_lines.append(f"💰 Narx uslubi: {escape(res['pricing_pattern'])}")
        if res.get("learned_patch"):
            msg_lines.append("🧠 <b>Playbook yangilandi!</b> Keyingi look va videolar endi shu uslubdan foydalanadi.")
        await wait_m.edit_text("\n".join(msg_lines))

    @admin.message(Command("manbalar"))
    @admin.message(Command("sources"))
    async def list_sources_cmd(message: Message, db: Database):
        sources = await db.list_tracked_sources(limit=20)
        pbs = await db.get_all_playbooks()
        if not sources and not pbs:
            await message.answer("Hali o'rganilgan tashqi manbalar yo'q. Qo'shish: <code>/manba https://t.me/...</code>")
            return
        lines = ["🧠 <b>O'ZLASHTIRILGAN KANALLAR VA STRATEGIYALAR</b>\n"]
        for src in sources[:12]:
            lines.append(
                f"• <b>[{escape(src['platform'])}]</b> <code>{escape(src['url'] or src['source_key'])}</code> ({escape(src['status'])})\n"
                f"  └ <i>{escape((src.get('style_summary') or '')[:120])}</i>"
            )
        if pbs:
            lines.append("\n📘 <b>Faol Playbook lar:</b>")
            for k, v in pbs.items():
                lines.append(f"• <code>{escape(k)}</code>: {escape(json.dumps(v, ensure_ascii=False)[:180])}")
        await message.answer("\n".join(lines))

    @admin.message(Command("tg_holat"))
    async def tg_holat_cmd(message: Message, command: CommandObject, db: Database):
        arg = (command.args or "").strip().lower()
        if arg in ("yoq", "on", "1", "ruxsat"):
            await db.set_setting("allow_tg_without_ig", "1")
            await message.answer("🟢 <b>TG avto-posti yoqildi</b> (Instagram blokda bo'lsa ham Telegram kanalga post qo'yaveradi).")
            return
        if arg in ("toxtat", "off", "0", "pauza"):
            await db.set_setting("allow_tg_without_ig", "0")
            await message.answer("⏸ <b>TG bo'sh postlari to'xtatildi</b> (Instagram qulfdan chiqmaguncha bekorga token sarflanmaydi).")
            return
        cur = await db.get_setting("allow_tg_without_ig")
        st_txt = "YOQILGAN (IG siz ham ishlaydi)" if cur == "1" else "PAUZADA (IG blokda bo'lsa token tejaydi)"
        await message.answer(
            f"📢 <b>Telegram Avto-Nashr Holati:</b> {st_txt}\n\n"
            "O'zgartirish: <code>/tg_holat yoq</code> yoki <code>/tg_holat toxtat</code>"
        )

    @admin.message(StateFilter(default_state), F.video)
    async def learn_from_uploaded_video(message: Message, db: Database, admin_bot: Bot):
        wait_m = await message.answer("🎬 <b>Videoni kadrlar va audio bo'yicha chuqur tahlil qilyapman...</b>")
        import tempfile
        from .source_learner import analyze_video_file_blueprint
        with tempfile.TemporaryDirectory() as td:
            vpath = os.path.join(td, "ref_reel.mp4")
            try:
                tg_file = await admin_bot.get_file(message.video.file_id)
                await admin_bot.download_file(tg_file.file_path, vpath)
            except Exception as exc:
                await wait_m.edit_text(f"❌ Videoni yuklab bo'lmadi: {escape(str(exc)[:120])}")
                return
            hint = (message.caption or "").strip()
            res = await analyze_video_file_blueprint(
                db, s, vpath,
                source_label=f"tg_video_{message.message_id}",
                caption_hint=hint,
            )
        if not res.get("ok"):
            await wait_m.edit_text(f"❌ Video tahlil xatosi: {escape(str(res.get('error', '')))}")
            return
        bp = res.get("blueprint") or {}
        ed = bp.get("editing_blueprint") or {}
        await wait_m.edit_text(
            "✅ <b>Video to'liq tahlil qilindi va tizimga integratsiya qilindi!</b>\n\n"
            f"⏱ Davomiyligi: <b>{res['duration_sec']}s</b> | 📐 Sifat: <b>{escape(str(res['resolution']))}</b>\n"
            f"🎯 Ma'nosi: <i>{escape(str(bp.get('video_meaning', ''))[:160])}</i>\n"
            f"🎬 Montaj/Ritm: <i>{escape(str(ed.get('pacing', ''))[:140])}</i>\n"
            f"🎵 Mos Zvuk: <code>{escape(str(ed.get('recommended_audio_vibe', 'luxury_chill')))}</code>\n"
            f"🔓 Ochiqlik darsi: <i>{escape(str(bp.get('tg_ig_openness_lesson', ''))[:160])}</i>\n\n"
            "🧠 Keyingi video va kanallar shu blueprint asosida rivojlanadi!",
            reply_markup=ikb([[("🧠 Manbalar", "adm:sources"), ("◀️ Bosh menyu", "adm:home")]]),
        )

    @admin.message(
        StateFilter(default_state),
        F.text,
        ~F.text.startswith("/"),
        F.text.regexp(r"https?://(?:t\.me|telegram\.me|(?:www\.)?instagram\.com|youtube\.com|youtu\.be)/"),
    )
    async def auto_learn_dropped_url(message: Message, db: Database):
        parts = (message.text or "").strip().split(maxsplit=1)
        url_arg = parts[0]
        note_arg = parts[1] if len(parts) > 1 else ""
        wait_m = await message.answer("🕵️‍♂️ <b>Havoladan o‘rganilmoqda...</b>")
        from .source_learner import ingest_and_learn_source
        res = await ingest_and_learn_source(db, s, url_arg, user_instruction=note_arg)
        if not res.get("ok"):
            await wait_m.edit_text(f"❌ Xato: {escape(str(res.get('error', '')))}")
            return
        await wait_m.edit_text(
            f"✅ <b>Havola tizimga o‘rgatildi ({escape(res['platform'].upper())})</b>\n"
            f"🔗 <code>{escape(res['url'])}</code>\n"
            f"🎨 <i>{escape((res.get('style_summary') or '')[:220])}</i>",
            reply_markup=ikb([[("🧠 Manbalar", "adm:sources"), ("◀️ Bosh menyu", "adm:home")]]),
        )

    @admin.message(Command("ai_look"))
    async def ai_look_cmd(message: Message, command: CommandObject, db: Database, sales_bot: Bot, admin_bot: Bot, sales_username: str):
        args_str = (command.args or "").strip()
        season = args_str if args_str else "avtomatik ob-havo"
        wait_msg = await message.answer(
            "⚡ <b>1080p Full HD Look tayyorlanmoqda...</b>\n"
            "• Instagram Tahlilchi auditoriya va video uslubini tanlamoqda\n"
            "• Video Montajchi 1080x1920 .mp4 Reels render qilmoqda\n"
            "• Yangi Look IG + TG kanalga joylanmoqda..."
        )
        office = AgentOffice(db=db, settings=s, sales_bot=sales_bot, admin_bot=admin_bot, sales_username=sales_username)
        res = await office.run_look_pipeline(season=season, delete_previous=False, notify_admin_on_publish=False)
        try:
            await wait_msg.delete()
        except Exception:
            pass
        caption = (
            f"✅ <b>Yangi Look #{res.look_id} ({res.piece_count} qism, 1080p) joylandi!</b>\n\n"
            f"👔 <b>{escape(res.title)}</b>\n"
            f"🎯 Auditoriya: <i>{escape(res.target_persona)}</i>\n"
            f"🎬 Uslub: <code>{escape(res.video_style)}</code> · 🎵 Zvuk: <code>{escape(res.audio_vibe)}</code>\n"
            f"💳 <b>Hozirgi narx (50%): {fmt(res.prepay_50_uzs)} so'm</b>\n"
            f"📦 <b>+ kargo</b> (100%: {fmt(res.prepay_uzs)} so'm)\n"
            f"💵 Sof foyda: <b>{fmt(res.profit_uzs)} so'm</b>\n\n"
            f"📢 <b>Telegram Kanal:</b> {res.tg_link}\n"
            f"📸 <b>Instagram Reels:</b> {res.ig_link}"
        )
        if res.mp4_path and res.mp4_path.endswith(".mp4") and os.path.exists(res.mp4_path):
            await message.answer_video(FSInputFile(res.mp4_path), caption=caption, supports_streaming=True)
        elif os.path.exists(res.video_path):
            await message.answer_animation(FSInputFile(res.video_path), caption=caption)
        elif os.path.exists(res.photo_path):
            await message.answer_photo(FSInputFile(res.photo_path), caption=caption)
        else:
            await message.answer(caption)

    # ---------------- to'lov ----------------
    @admin.callback_query(F.data.startswith("pay_ok:"))
    async def pay_ok(cb: CallbackQuery, db: Database, sales_bot: Bot, admin_bot: Bot, userbot=None):
        order = await db.get_order(int(cb.data.split(":")[1]))
        st = order["status"] if order else None
        look = await db.get_look(order["look_id"]) if order else None
        src = (order.get("source") or "bot") if order else "bot"
        if st in ("awaiting_payment", "payment_review"):
            await db.update_order(order["id"], status="paid")
            plan = order.get("payment_plan") or "50"
            await notify_client(sales_bot, order["user_id"],
                                f"✅ {plan}% oldindan to'lov qabul qilindi! Buyurtma #{order['id']} Xitoydan xarid qilish navbatiga qo'yildi.\n"
                                "Har bir bosqichda shu yerda xabar beramiz.",
                                userbot=userbot, source=src)
            order = await db.get_order(order["id"])
            logistics = LogisticsAgent(db, s)
            vykup_card = logistics.build_vykup_card(order, look)
            await send_to_agent(admin_bot, s, vykup_card)
            await db.set_agent_status("cargo_logistics", "idle", f"Buyurtma #{order['id']} Pinduoduo xarid kartasi tayyorlandi", increment_done=True)
            await db.log_agent_action("cargo_logistics", f"Buyurtma #{order['id']} ({plan}% to'lov) Pinduoduo xarid kartasi tayyorlandi",
                                      f"Summa: {fmt(order['prepay_due'])} so'm | Qolgan: {fmt(order.get('remaining_uzs') or 0)} so'm")
        elif st in ("cargo_awaiting", "cargo_review"):
            await db.update_order(order["id"], status="cargo_paid")
            await notify_client(sales_bot, order["user_id"],
                                f"✅ Yakuniy to'lov qabul qilindi! Buyurtma #{order['id']} manzilingizga jo'natiladi.",
                                userbot=userbot, source=src)
            order = await db.get_order(order["id"])
            await db.set_agent_status("cargo_logistics", "idle", f"Buyurtma #{order['id']} yakuniy to'lovi tasdiqlandi", increment_done=True)
            await db.log_agent_action("cargo_logistics", f"Buyurtma #{order['id']} yakuniy (qolgan 50% + kargo) to'lovi tasdiqlandi",
                                      f"Summa: {fmt(order['cargo_due'])} so'm")
        else:
            await cb.answer("Holat allaqachon o'zgargan", show_alert=True)
            return
        await cb.answer("Tasdiqlandi")
        await drop_kb(cb)
        await send_card(cb.message, db, order, "✅ To'lov tasdiqlandi")

    @admin.callback_query(F.data.startswith("pay_no:"))
    async def pay_no(cb: CallbackQuery, db: Database, sales_bot: Bot, userbot=None):
        order = await db.get_order(int(cb.data.split(":")[1]))
        back = {"payment_review": "awaiting_payment", "cargo_review": "cargo_awaiting"}
        if not order or order["status"] not in back:
            await cb.answer("Holat allaqachon o'zgargan", show_alert=True)
            return
        await db.update_order(order["id"], status=back[order["status"]])
        await notify_client(sales_bot, order["user_id"],
                            f"❌ Buyurtma #{order['id']} bo'yicha to'lov topilmadi. Summani tekshirib, chekni qayta "
                            "yuboring yoki 👤 Operator tugmasini bosing.",
                            userbot=userbot, source=order.get("source") or "bot")
        await cb.answer("Mijozga xabar berildi")
        await drop_kb(cb)

    # ---------------- statuslar ----------------
    @admin.callback_query(F.data.startswith("st:"))
    async def set_status(cb: CallbackQuery, db: Database, sales_bot: Bot, userbot=None):
        _, oid, new = cb.data.split(":")
        order = await db.get_order(int(oid))
        allowed = NEXT_STATUS.get(order["status"]) == new if order else False
        if order and order["status"] == "arrived" and new == "delivered" and s.cargo_collect_on_delivery:
            allowed = True
        if not allowed:
            await cb.answer("Holat allaqachon o'zgargan", show_alert=True)
            return
        await db.update_order(order["id"], status=new)
        await db.set_agent_status("cargo_logistics", "idle", f"Buyurtma #{order['id']} -> {STATUS_LABELS[new]}", increment_done=True)
        await db.log_agent_action("cargo_logistics", f"Buyurtma #{order['id']} holati yangilandi: {STATUS_LABELS[new]}")
        if new in CLIENT_STATUS_MESSAGES:
            await notify_client(sales_bot, order["user_id"],
                                CLIENT_STATUS_MESSAGES[new].format(id=order["id"], delivery=s.delivery_text),
                                userbot=userbot, source=order.get("source") or "bot")
        await cb.answer(STATUS_LABELS[new])
        await drop_kb(cb)
        await send_card(cb.message, db, await db.get_order(order["id"]), f"Holat: {STATUS_LABELS[new]}")

    @admin.callback_query(F.data.startswith("cancel:"))
    async def cancel_ask(cb: CallbackQuery):
        oid = cb.data.split(":")[1]
        await cb.answer()
        await cb.message.answer(f"#{oid} buyurtmani bekor qilasizmi? To'lov qilingan bo'lsa pulni o'zingiz qaytarasiz.",
                                reply_markup=ikb([[("Ha, bekor qilish", f"cancel_yes:{oid}"), ("Yo'q", "noop")]]))

    @admin.callback_query(F.data == "noop")
    async def noop(cb: CallbackQuery):
        await cb.answer()
        await drop_kb(cb)

    @admin.callback_query(F.data.startswith("cancel_yes:"))
    async def cancel_yes(cb: CallbackQuery, db: Database, sales_bot: Bot, userbot=None):
        order = await db.get_order(int(cb.data.split(":")[1]))
        if not order or order["status"] in ("delivered", "cancelled"):
            await cb.answer("Mumkin emas", show_alert=True)
            return
        await db.update_order(order["id"], status="cancelled")
        await notify_client(sales_bot, order["user_id"], CLIENT_STATUS_MESSAGES["cancelled"].format(id=order["id"]),
                            userbot=userbot, source=order.get("source") or "bot")
        await cb.answer("Bekor qilindi")
        await drop_kb(cb)

    # ---------------- vazn va kargo (+ qolgan 50%) to'lovi ----------------
    @admin.callback_query(F.data.startswith("weight:"))
    async def weight_ask(cb: CallbackQuery, state: FSMContext):
        oid = int(cb.data.split(":")[1])
        await state.set_state(AdminForm.weight)
        await state.update_data(order_id=oid)
        await cb.answer()
        await cb.message.answer(f"#{oid} buyurtmaning real vaznini kg da yozing (masalan: 2.4). Bekor: /bekor")

    @admin.message(AdminForm.weight, F.text)
    async def weight_got(message: Message, state: FSMContext, db: Database, sales_bot: Bot, userbot=None):
        try:
            w = float(message.text.replace(",", ".").lower().replace("kg", "").strip())
            assert 0 < w < 100
        except (ValueError, AssertionError):
            await message.answer("Raqam yozing, masalan: 2.4")
            return
        oid = (await state.get_data())["order_id"]
        await state.clear()
        order = await db.get_order(oid)
        if not order or order["status"] != "arrived":
            await message.answer("Bu buyurtma 'yetib keldi' holatida emas.")
            return
        src = order.get("source") or "bot"
        client_cargo, cost_cargo = cargo_charge(w, await get_rates(db, s), await get_params(db, s))
        rem_uzs = int(order.get("remaining_uzs") or 0)
        total_arrival_base = rem_uzs + client_cargo

        if s.cargo_collect_on_delivery and rem_uzs == 0:
            await db.update_order(oid, weight_kg=w, cargo_due=client_cargo, cargo_cost_uzs=cost_cargo)
            await notify_client(sales_bot, order["user_id"],
                                f"⚖️ Buyurtma #{oid} vazni: {w} kg.\nKargo summasi: <b>{fmt(client_cargo)} so'm</b> — "
                                "kuryerga yetkazib berganda to'laysiz.",
                                userbot=userbot, source=src)
        else:
            due = unique_amount(total_arrival_base, oid)
            await db.update_order(oid, weight_kg=w, cargo_due=due, cargo_cost_uzs=cost_cargo, status="cargo_awaiting")
            if rem_uzs > 0:
                breakdown_msg = (
                    f"⚖️ Buyurtma #{oid} O'zbekistonga yetib keldi! Vazni: <b>{w} kg</b>.\n\n"
                    f"• Tovarning qolgan 50% qismi: <b>{fmt(rem_uzs)} so'm</b>\n"
                    f"• Kargo to'lovi ({w} kg): <b>{fmt(client_cargo)} so'm</b>\n\n"
                    + payment_text(due, s, "Qolgan 50% + Kargo to'lovi")
                    + "\n\nTo'lovdan so'ng buyurtmangizni manzilingizga jo'natamiz."
                )
            else:
                breakdown_msg = (
                    f"⚖️ Buyurtma #{oid} O'zbekistonga yetib keldi! Vazni: <b>{w} kg</b>.\n\n"
                    + payment_text(due, s, "Kargo to'lovi")
                    + "\n\nTo'lovdan so'ng buyurtmangizni manzilingizga jo'natamiz."
                )
            await notify_client(sales_bot, order["user_id"], breakdown_msg, userbot=userbot, source=src)

        await db.set_agent_status("cargo_logistics", "idle", f"Buyurtma #{oid} Toshkent hisobi ({w} kg): {fmt(total_arrival_base)} so'm", increment_done=True)
        await db.log_agent_action("cargo_logistics", f"Buyurtma #{oid} O'zbekistonga keldi ({w} kg)",
                                  f"Qolgan 50%: {fmt(rem_uzs)} so'm + Kargo: {fmt(client_cargo)} so'm = Jami: {fmt(total_arrival_base)} so'm")
        await send_card(message, db, await db.get_order(oid),
                        f"⚖️ Vazn {w} kg · Qolgan 50%: {fmt(rem_uzs)} + Kargo: {fmt(client_cargo)} = {fmt(total_arrival_base)} so'm")

    # ---------------- trek, javob ----------------
    @admin.message(Command("trek"))
    async def trek(message: Message, command: CommandObject, db: Database, sales_bot: Bot, userbot=None):
        parts = (command.args or "").split(maxsplit=1)
        if len(parts) != 2 or not parts[0].isdigit():
            await message.answer("Masalan: /trek 15 YT123456789")
            return
        order = await db.get_order(int(parts[0]))
        if not order:
            await message.answer("Topilmadi.")
            return
        await db.update_order(order["id"], tracking=parts[1])
        await notify_client(sales_bot, order["user_id"],
                            f"🔢 Buyurtma #{order['id']} trek raqami: <code>{escape(parts[1])}</code>",
                            userbot=userbot, source=order.get("source") or "bot")
        await message.answer("✅ Saqlandi va mijozga yuborildi.")

    @admin.message(Command("javob"))
    async def reply_client(message: Message, command: CommandObject, sales_bot: Bot, db: Database, userbot=None):
        parts = (command.args or "").split(maxsplit=1)
        if len(parts) != 2 or not parts[0].isdigit():
            await message.answer("Masalan: /javob 123456789 Assalomu alaykum...")
            return
        uid = int(parts[0])
        orders = await db.user_orders(uid, limit=1)
        src = orders[0].get("source") or "bot" if orders else "bot"
        ok = await notify_client(sales_bot, uid, f"👤 <b>Operator:</b> {escape(parts[1])}", userbot=userbot, source=src)
        await message.answer("✅ Yuborildi." if ok else "❌ Yuborilmadi (mijoz botni bloklagan bo'lishi mumkin).")

    # ---------------- narx, kurs, foyda ----------------
    @admin.message(Command("narx"))
    async def price_cmd(message: Message, command: CommandObject, db: Database):
        try:
            prices_raw, weight_raw = (command.args or "").split()
            prices = [float(x) for x in prices_raw.replace(",", ".").split("+")]
            weight = float(weight_raw.replace(",", "."))
        except ValueError:
            await message.answer("Masalan: /narx 80+60+45 2.1  (yuanlar + bilan, jami vazn kg)")
            return
        items = [Item(f"#{i}", p, 0) for i, p in enumerate(prices, 1)]
        items[0].weight_kg = weight
        rates, params = await get_rates(db, s), await get_params(db, s)
        await message.answer(breakdown_text(calculate(items, rates, params), rates, params))

    @admin.message(Command("kurs"))
    async def rates_cmd(message: Message, command: CommandObject, db: Database):
        args = (command.args or "").lower().split()
        if args == ["yangila"]:
            result = await refresh_rates(db, s)
            if not result:
                await message.answer("❌ CBU dan olib bo'lmadi. Qo'lda: /kurs cny 1780")
                return
        elif len(args) == 2 and args[0] in ("cny", "usd"):
            try:
                await db.set_setting(f"{args[0]}_uzs", float(args[1].replace(",", ".")))
            except ValueError:
                await message.answer("Masalan: /kurs cny 1780")
                return
        rates = await get_rates(db, s)
        await message.answer(f"1 ¥ = {rates.cny_uzs:.2f} so'm\n1 $ = {rates.usd_uzs:.2f} so'm\n\n"
                             "Look narxlarini yangilash: /qayta_hisob")

    @admin.message(Command("foyda"))
    async def profit_cmd(message: Message, command: CommandObject, db: Database):
        try:
            value = float((command.args or "").replace("%", "").replace(",", "."))
            assert 0 <= value <= 300
        except (ValueError, AssertionError):
            p = await get_params(db, s)
            await message.answer(f"Hozirgi foyda: {p.profit_percent:g}%. O'zgartirish: /foyda 30")
            return
        await db.set_setting("profit_percent", value)
        await message.answer(f"✅ Foyda {value:g}%. Eski looklar uchun: /qayta_hisob")

    async def price_look(db: Database, items: list[Item]) -> PriceBreakdown:
        return calculate(items, await get_rates(db, s), await get_params(db, s))

    @admin.message(Command("qayta_hisob"))
    async def recalc(message: Message, db: Database):
        lines = []
        for lk in await db.list_looks(only_active=False):
            items = [
                Item(i["name"], float(i.get("price_cny", i.get("cny", 0))), float(i["weight_kg"]), i.get("url", ""))
                for i in look_items(lk)
            ]
            b = await price_look(db, items)
            await db.update_look(
                lk["id"],
                prepay_uzs=b.prepay_uzs,
                prepay_50_uzs=b.prepay_50_uzs,
                remaining_50_uzs=b.remaining_50_uzs,
                profit_uzs=b.profit_uzs,
                goods_cost_uzs=b.goods_cost_uzs,
                cargo_est_uzs=b.cargo_client_uzs,
            )
            if b.prepay_uzs != lk["prepay_uzs"]:
                lines.append(f"#{lk['id']}: {fmt(lk['prepay_uzs'])} → {fmt(b.prepay_uzs)} (50%: {fmt(b.prepay_50_uzs)})")
        await message.answer("✅ Qayta hisoblandi.\n" + ("\n".join(lines) or "Narxlar o'zgarmadi."))

    @admin.message(Command("hisobot"))
    async def report(message: Message, db: Database):
        orders = await db.all_orders()
        counts: dict[str, int] = {}
        for o in orders:
            counts[o["status"]] = counts.get(o["status"], 0) + 1
        paid = [o for o in orders if o["status"] not in ("awaiting_payment", "payment_review", "cancelled")]
        cargo_paid = [o for o in paid if o["status"] in ("cargo_paid", "delivered") and o["cargo_due"]]
        revenue = sum(o["prepay_due"] for o in paid) + sum(o["cargo_due"] for o in cargo_paid)
        profit = sum(o["profit_uzs"] for o in paid) + sum(o["cargo_due"] - o["cargo_cost_uzs"] for o in cargo_paid)
        lines = ["📊 <b>Hisobot</b>", f"Jami buyurtma: {len(orders)}, to'langan: {len(paid)}", ""]
        lines += [f"{STATUS_LABELS.get(k, k)}: {v}" for k, v in counts.items()]
        lines += ["", f"💰 Tushum: {fmt(revenue)} so'm", f"💵 Taxminiy foyda: {fmt(profit)} so'm"]
        await message.answer("\n".join(lines))

    @admin.message(Command("hisobchi"))
    async def accountant_cmd(
        message: Message,
        command: CommandObject,
        db: Database,
        sales_bot: Bot,
        admin_bot: Bot,
        userbot=None,
    ):
        raw_arg = (command.args or "").strip()
        if raw_arg:
            normalized = raw_arg if ("+" in raw_arg or "uzs" in raw_arg.lower()) else f"Popolnenie +{raw_arg} UZS"
            res = await AccountantAgent(db, s).process_bank_notification(
                normalized,
                source="admin_cmd",
                sales_bot=sales_bot,
                admin_bot=admin_bot,
                userbot=userbot,
            )
            if res.get("matched"):
                await message.answer(
                    f"✅ Tushum (<b>+{fmt(res['amount'])} so'm</b>) Buyurtma <b>#{res['order_id']}</b> bilan bog'landi "
                    "va Vykup bo'limiga yuborildi!"
                )
            else:
                await message.answer(
                    f"📥 Tushum qayd etildi (+{fmt(res.get('amount') or 0)} so'm) · Holat: <code>{res.get('reason', 'kutilmoqda')}</code>"
                )
            return

        txs = await db.list_bank_transactions(limit=10)
        lines = [
            "🧮 <b>AI HISOBCHI — BANK TUSHUMLARI</b>\n"
            f"Kuzatilayotgan botlar: <code>{escape(s.bank_bot_usernames)}</code>\n"
            "💡 <i>@HumoCardBot / @CardXabarBot xabarini shu botga forward qiling "
            "yoki Android SMS Forwarder'ni <code>/api/bank_webhook</code> ga ulang.</i>\n"
        ]
        if not txs:
            lines.append("Hozircha bank tushumlari qayd etilmagan.")
        for t in txs:
            st_txt = f"✅ Buyurtma #{t['matched_order_id']}" if t.get("matched_order_id") else "⏳ Chek kutilmoqda"
            lines.append(
                f"• <b>+{fmt(t['amount_uzs'])} so'm</b> (*{escape(t.get('card_last4') or '????')}) · "
                f"<i>{escape(t['source'])}</i> · {st_txt}"
            )
        await message.answer("\n".join(lines))

    # ---------------- looklar ----------------
    @admin.message(Command("looklar"))
    async def looks_cmd(message: Message, db: Database, sales_username: str):
        looks = await db.list_looks(only_active=False)
        if not looks:
            await message.answer("Looklar yo'q. Qo'shish: /look_qosh")
            return
        for lk in looks:
            state = "✅ faol" if lk["active"] else "⏸ o'chiq"
            link = f"https://t.me/{sales_username}?start=look_{lk['id']}"
            await message.answer(
                f"#{lk['id']} <b>{escape(lk['title'])}</b> — {fmt(lk['prepay_uzs'])} so'm, {state}\n"
                f"Foyda: {fmt(lk['profit_uzs'])} so'm · {lk['weight_kg']} kg\n"
                f"Instagram uchun havola:\n<code>{link}</code>",
                reply_markup=ikb([[("⏸ O'chirish" if lk["active"] else "▶️ Yoqish", f"toggle:{lk['id']}")]]))

    @admin.callback_query(F.data.startswith("toggle:"))
    async def toggle(cb: CallbackQuery, db: Database):
        lk = await db.get_look(int(cb.data.split(":")[1]))
        await db.update_look(lk["id"], active=0 if lk["active"] else 1)
        await cb.answer("O'chirildi" if lk["active"] else "Yoqildi")
        await drop_kb(cb)

    @admin.message(Command("look_qosh"))
    async def add_start(message: Message, state: FSMContext):
        await state.clear()
        await state.set_state(AddLook.photo)
        await message.answer("1/5 📸 Look rasmini yuboring (kolaj). Bekor: /bekor")

    @admin.message(AddLook.photo, F.photo)
    async def add_photo(message: Message, state: FSMContext):
        await state.update_data(photo_id=message.photo[-1].file_id)
        await state.set_state(AddLook.title)
        await message.answer("2/5 ✏️ Look nomi (masalan: Qishki casual — xudi + shim + kurtka):")

    @admin.message(AddLook.title, F.text)
    async def add_title(message: Message, state: FSMContext):
        await state.update_data(title=message.text.strip()[:120])
        await state.set_state(AddLook.items)
        await message.answer(
            "3/5 🧾 Buyumlar, har biri yangi qatorda:\n"
            "<code>nomi | narx ¥ | vazn kg | link</code>\n\nMasalan:\n"
            "<code>Oversize xudi | 89 | 0.7 | https://item.taobao.com/...\n"
            "Keng shim | 65 | 0.5 | https://...\n"
            "Puxovik | 159 | 1.2 | https://...</code>")

    @admin.message(AddLook.items, F.text)
    async def add_items(message: Message, state: FSMContext):
        try:
            items = parse_items(message.text)
        except ValueError as e:
            await message.answer(f"❌ {e}")
            return
        await state.update_data(items=[i.__dict__ for i in items])
        await state.set_state(AddLook.sizes)
        await message.answer("4/5 📏 O'lchamlar vergul bilan (masalan: M,L,XL,2XL) yoki <code>-</code>:")

    @admin.message(AddLook.sizes, F.text)
    async def add_sizes(message: Message, state: FSMContext):
        await state.update_data(sizes="" if message.text.strip() == "-" else message.text.strip())
        await state.set_state(AddLook.colors)
        await message.answer("5/5 🎨 Ranglar vergul bilan (masalan: Qora,Kulrang) yoki <code>-</code>:")

    @admin.message(AddLook.colors, F.text)
    async def add_colors(message: Message, state: FSMContext, db: Database):
        await state.update_data(colors="" if message.text.strip() == "-" else message.text.strip())
        data = await state.get_data()
        items = [Item(**i) for i in data["items"]]
        rates, params = await get_rates(db, s), await get_params(db, s)
        b = calculate(items, rates, params)
        await state.update_data(price=b.__dict__)
        await state.set_state(AddLook.confirm)
        await message.answer(f"<b>{escape(data['title'])}</b>\n\n" + breakdown_text(b, rates, params),
                             reply_markup=ikb([[("✅ Saqlash", "look_save"), ("❌ Bekor", "look_cancel")]]))

    @admin.callback_query(AddLook.confirm, F.data == "look_cancel")
    async def add_cancel(cb: CallbackQuery, state: FSMContext):
        await state.clear()
        await cb.answer("Bekor qilindi")
        await drop_kb(cb)

    @admin.callback_query(AddLook.confirm, F.data == "look_save")
    async def add_save(cb: CallbackQuery, state: FSMContext, db: Database, bot: Bot, sales_username: str):
        data = await state.get_data()
        await state.clear()
        look_id = await db.add_look(data["title"], data["items"], data["sizes"], data["colors"], data["price"])
        os.makedirs(PHOTO_DIR, exist_ok=True)
        path = os.path.join(PHOTO_DIR, f"look_{look_id}.jpg")
        await bot.download(data["photo_id"], destination=path)
        await db.update_look(look_id, photo_path=path)
        await cb.answer("Saqlandi")
        await drop_kb(cb)
        await cb.message.answer(
            f"✅ Look #{look_id} saqlandi va botda ko'rinadi.\n\nInstagram post/bio uchun havola:\n"
            f"<code>https://t.me/{sales_username}?start=look_{look_id}</code>")

    # ---------------- QC rasm (admin yoki agent) ----------------
    @staff.message(StateFilter(default_state), F.photo, F.caption.regexp(r"^#(\d+)"))
    async def qc_photo(message: Message, bot: Bot, db: Database, sales_bot: Bot, userbot=None):
        oid = int(message.caption.split()[0][1:])
        order = await db.get_order(oid)
        if not order:
            await message.answer("Bunday buyurtma yo'q.")
            return
        data = await bot.download(message.photo[-1])
        ok = await notify_client_photo(
            sales_bot,
            order["user_id"],
            data.read(),
            caption=f"📸 Buyurtma #{oid}: tovaringiz rasmi (jo'natishdan oldin tekshiruv).",
            userbot=userbot,
            source=order.get("source") or "bot",
        )
        await message.answer(f"✅ QC rasm #{oid} mijozga yuborildi." if ok else "❌ Mijozga yuborib bo'lmadi.")

    @staff.message(CommandStart())
    async def staff_start(message: Message):
        await message.answer("Siz agent sifatida ulandingiz. Buyurtmalar shu yerga keladi.\n"
                             "QC rasmni izohda #raqam bilan yuboring (masalan: #15).")

    # ---------------- forward qilingan bank SMS tushumi ----------------
    @admin.message(
        StateFilter(default_state),
        F.text,
        ~F.text.startswith("/"),
        F.text.func(lambda t: parse_bank_deposit_text(t)[0] is not None),
    )
    async def forwarded_bank_sms(
        message: Message,
        db: Database,
        sales_bot: Bot,
        admin_bot: Bot,
        userbot=None,
    ):
        res = await AccountantAgent(db, s).process_bank_notification(
            message.text,
            source="admin_forward",
            sales_bot=sales_bot,
            admin_bot=admin_bot,
            userbot=userbot,
        )
        if res.get("matched"):
            await message.answer(
                f"✅ <b>Bank tushumi tasdiqlandi!</b>\n"
                f"Summa: <b>+{fmt(res['amount'])} so'm</b> → Buyurtma <b>#{res['order_id']}</b> "
                "avtomatik <code>paid</code> qilindi va Xitoy vykupga yuborildi!"
            )
        elif res.get("reason") == "karta_boshqa":
            await message.answer(
                f"ℹ️ Boshqa karta raqami uchun tushum qayd etildi (+{fmt(res.get('amount') or 0)} so'm)."
            )
        else:
            await message.answer(
                f"📥 Bank tushumi saqlandi: <b>+{fmt(res.get('amount') or 0)} so'm</b>.\n"
                "Mos kutilayotgan buyurtma cheki yuborilgan zahoti avtomatik tasdiqlanadi."
            )

    # ---------------- tushunilmagan xabarlar / begonalar ----------------
    # Ota router handlerlari ichki routerlardan oldin tekshiriladi, shuning uchun alohida router oxirida.
    fallback = Router(name="fallback")
    root.include_router(fallback)

    @fallback.message()
    async def stranger(message: Message):
        if message.from_user.id in s.admin_ids:
            await message.answer("Buyruq tushunilmadi. Ro'yxat: /help")
            return
        await message.answer(f"Bu bot faqat do'kon egasi uchun.\nSizning Telegram ID: <code>{message.from_user.id}</code>")

    return root
