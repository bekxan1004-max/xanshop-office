"""Ishga tushirish: python main.py
24/7 Birlashgan Tizim:
- Sotuv Bot (@aiogram)
- Admin Bot (@aiogram)
- Shaxsiy Telegram Akkaunt Userbot (@telethon — mijozlar bilan jonli odam profilidan gaplashadi)
- 24/7 AI Agent Office Web-Paneli (http://localhost:8080 yoki Cloud Server domeni)
- 24/7 Avtonom Look/Reels Scheduler va CBU valyuta kursi yangilovchisi
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.admin_bot import ADMIN_BOT_COMMANDS, build_admin_router
from app.ai import SalesAI
from app.config import load_settings
from app.dashboard import start_dashboard_server
from app.db import Database
from app.economy import rates_loop
from app.notify import notify_admins
from app.office import AgentOffice, office_scheduler_loop
from app.omniroute_server import start_omniroute_server
from app.sales_bot import build_sales_router
from app.userbot import PersonalStylistUserbot


async def main() -> None:
    s = load_settings()
    db = Database(s.db_path)
    await db.connect()
    omni_runner = await start_omniroute_server(s, port=20128)
    ai = SalesAI(s)

    has_tokens = (
        ":" in s.sales_bot_token
        and ":" in s.admin_bot_token
        and not s.sales_bot_token.startswith("123456:")
        and bool(s.admin_ids)
    )

    if not has_tokens:
        office = AgentOffice(db=db, settings=s)
        if s.auto_post_hours > 0 and not await db.list_looks(only_active=False):
            await office.run_look_pipeline()
        userbot = PersonalStylistUserbot(db=db, settings=s, ai=ai)
        await userbot.start()
        runner = await start_dashboard_server(db, s, office)

        async def _log_alert(text: str) -> None:
            logging.info("[Alert] %s", text)

        rates_task = asyncio.create_task(rates_loop(db, s, _log_alert))
        sched_task = asyncio.create_task(office_scheduler_loop(office, _log_alert))
        logging.warning(
            "🏢 AI Agent Office 24/7 Web-Paneli ochildi: http://localhost:%d "
            "(Telegram bot tokenlar .env ga kiritilgach botlar ham avtomatik ulanadi)",
            s.office_port,
        )
        try:
            while True:
                await asyncio.sleep(3600)
        finally:
            rates_task.cancel()
            sched_task.cancel()
            await userbot.stop()
            await runner.cleanup()
            await db.close()
        return

    props = DefaultBotProperties(parse_mode=ParseMode.HTML)
    sales_bot = Bot(s.sales_bot_token, default=props)
    admin_bot = Bot(s.admin_bot_token, default=props)
    sales_username = "XanShopUzBot"
    for attempt in range(3):
        try:
            sales_username = (await sales_bot.get_me(request_timeout=20)).username or sales_username
            break
        except Exception as e:
            logging.warning("Telegram get_me urinish #%d muvaffaqiyatsiz: %s", attempt + 1, e)
            await asyncio.sleep(2)

    office = AgentOffice(
        db=db,
        settings=s,
        sales_bot=sales_bot,
        admin_bot=admin_bot,
        sales_username=sales_username,
    )
    runner = await start_dashboard_server(db, s, office)
    if s.auto_post_hours > 0 and not await db.list_looks(only_active=False):
        await office.run_look_pipeline()

    userbot = PersonalStylistUserbot(db=db, settings=s, ai=ai, admin_bot=admin_bot, sales_bot=sales_bot)
    await userbot.start()
    office.userbot = userbot

    shared = dict(
        db=db,
        settings=s,
        ai=ai,
        sales_bot=sales_bot,
        admin_bot=admin_bot,
        sales_username=sales_username,
        userbot=userbot,
    )
    sales_dp = Dispatcher(storage=MemoryStorage(), **shared)
    sales_dp.include_router(build_sales_router())
    admin_dp = Dispatcher(storage=MemoryStorage(), **shared)
    admin_dp.include_router(build_admin_router(s))
    try:
        await admin_bot.set_my_commands(ADMIN_BOT_COMMANDS)
    except Exception:
        pass

    async def alert(text: str) -> None:
        await notify_admins(admin_bot, s, text)

    rates_task = asyncio.create_task(rates_loop(db, s, alert))
    sched_task = asyncio.create_task(office_scheduler_loop(office, alert))
    logging.info(
        "Ishga tushdi: @%s (sotuv bot) | AI Agent Office: http://localhost:%d | AI: %s",
        sales_username,
        s.office_port,
        "yoqilgan" if ai.enabled else "o'chiq (GEMINI_API_KEY yo'q)",
    )
    ofis_url = s.public_base_url if (s.public_base_url and "localhost" not in s.public_base_url) else f"http://localhost:{s.office_port}"
    try:
        await notify_admins(
            admin_bot,
            s,
            f"🟢 <b>{s.shop_name} — 24/7 AI AGENT OFFICE (v3.3)</b> ishga tushdi!\n"
            f"🛍 Sotuv bot: @{sales_username}\n"
            f"🌐 Virtual Ofis: {ofis_url}\n"
            f"🧠 Ochiq o‘rganish: <code>.mp4</code> video yoki <code>t.me / instagram.com / pinduoduo</code> link tashlang!\n"
            f"Menyu: /start · /help · /ofis · /pdd",
        )
    except Exception as e:
        logging.warning("Boshlanish xabarini adminlarga yuborishda vaqtinchalik xato: %s", e)
    try:
        while True:
            try:
                await asyncio.gather(
                    sales_dp.start_polling(sales_bot, handle_signals=False),
                    admin_dp.start_polling(admin_bot, handle_signals=False),
                )
                break
            except asyncio.CancelledError:
                raise
            except Exception as poll_err:
                logging.warning("Telegram polling vaqtincha uzildi (%s) — 10 soniyadan keyin qayta ulanadi...", poll_err)
                await asyncio.sleep(10)
    finally:
        rates_task.cancel()
        sched_task.cancel()
        await userbot.stop()
        await runner.cleanup()
        await db.close()
        await sales_bot.session.close()
        await admin_bot.session.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("To'xtatildi.")
