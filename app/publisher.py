"""XAN SHOP - SMM Boshlig'i Agent v3.2 (Telegram Kanal + Rasmiy Instagram Graph API 1080p Reels).

Ixcham, sodda, tushunarli postlar hamda har bir yangi postning to'g'ridan-to'g'ri havolasini
(Telegram va Instagram permalink) qaytarish tizimi.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any

import aiohttp
from aiogram import Bot
from aiogram.types import (
    BufferedInputFile,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
)

from .pricing import fmt
from .texts import look_50_values, look_items
from .trends import select_persona_archetype

log = logging.getLogger(__name__)


def format_channel_post(
    look: dict[str, Any],
    sales_bot_username: str,
    shop_name: str = "XAN SHOP",
    manager_username: str = "",
    playbooks: dict[str, dict[str, Any]] | None = None,
) -> str:
    """Telegram kanal uchun o'rganilgan manba (@stylesh_shop / @_tima_shop) shabloniga avtomatik moslashuvchi sotuv posti."""
    items = look_items(look)
    n_items = len(items)
    items_text = "\n".join(
        f"• {i['name']}" + (f" ({i['color_uz']})" if i.get("color_uz") and i["color_uz"].lower() not in i["name"].lower() else "")
        for i in items
    )
    p50, rem50 = look_50_values(look)
    persona = select_persona_archetype(look.get("title", ""), look.get("audio_vibe", ""), idx=int(look.get("id") or 0))
    colors_line = look.get("colors") or "Och bej, To'q kulrang (grafit), To'q jigarrang"

    mgr = (manager_username or "Bekshop_style").lstrip("@")
    tg_pb = (playbooks or {}).get("tg_channel_strategy") or {}
    tpl_style = str(tg_pb.get("template_style") or "").lower()

    if tpl_style == "tima_minimal":
        lines = [
            f"- <b>Hozirgi narx (50%): {fmt(p50)} so'm</b> 🇺🇿",
            f"- To'liq narxi: {fmt(look.get('prepay_uzs', 0))} so'm",
            f"- <b>{look.get('title', 'LOOK')} ({n_items} qism)</b> ❄️",
            f"🎯 <i>{persona['target_persona']} uchun</i>",
            f"{items_text}",
            "……………………………..",
            f"- Razmer: <b>{look.get('sizes') or 'M, L, XL, 2XL'}</b> | Rang: {colors_line}",
            f"- Kargo: <b>12 000 so'm / 100 gr</b> (qolgan {fmt(rem50)} so'm + kargo Toshkentda ko'rganingizda)",
            "- Dastavka UZB bo'ylab: <b>5–12 kun (Avia)</b>",
            "………………………………",
            f"- Zakaz uchun: @{mgr} 👍",
        ]
        return "\n".join(lines)

    if tpl_style == "stylesh_dash":
        lines = [
            f"👔 <b>{look.get('title', 'Yangi Obraz')} ({n_items} qism)</b> 🇺🇿",
            f"🎯 <i>{persona['target_persona']} uchun</i>",
            f"{items_text}",
            "———————————————",
            f"-| <b>Hozirgi narx (50%): {fmt(p50)} so'm</b>",
            f"-| To'liq narxi: {fmt(look.get('prepay_uzs', 0))} so'm",
            f"-| Razmer: <b>{look.get('sizes') or 'M - 2XL'}</b> ({colors_line})",
            "———————————————",
            "-| Oldindan to'lov: 50%",
            "-| Yetkazib berish: <b>5–12 kun (Avia)</b>",
            f"-| Kargo: <b>12 000 so'm / 100 gr</b> (qolgan {fmt(rem50)} so'm + kargo Toshkentga kelganda)",
            "-| Dastafka UZB bo'ylab\n",
            f"-| Buyurtma: @{mgr}",
        ]
        return "\n".join(lines)

    mgr_line = f"👤 Stilist-menejer: @{mgr}\n" if manager_username else ""
    lines = [
        f"👔 <b>{look.get('title', 'Yangi Obraz')} ({n_items} qism)</b>",
        f"🎯 <i>{persona['target_persona']} uchun</i>\n",
        f"{items_text}\n",
        f"🎨 Rasmdagi ranglar: <b>{colors_line}</b> <i>(boshqa ranglari ham bor)</i>",
        f"📏 Razmer: <b>{look.get('sizes') or 'M, L, XL, 2XL'}</b> <i>(do'kon jadvali bo'yicha aniq tanlaymiz)</i>",
        f"✈️ Yetkazish: <b>5–12 kun (Avia)</b>\n",
        f"💳 <b>Hozirgi narx (50%): {fmt(p50)} so'm</b>",
        f"📦 <b>Kargo: 12 000 so'm / 100 gr</b> <i>(qolgan {fmt(rem50)} so'm + kargo — kiyim Toshkentga kelib, ko'rganingizda!)</i>",
        f"💰 To'liq narxi: {fmt(look.get('prepay_uzs', 0))} so'm\n",
        f"{mgr_line}👇 <b>1 daqiqada buyurtma berish:</b>",
    ]
    return "\n".join(lines)


def format_instagram_caption(
    look: dict[str, Any],
    sales_bot_username: str,
    shop_name: str = "XAN SHOP",
    manager_username: str = "",
    playbooks: dict[str, dict[str, Any]] | None = None,
) -> str:
    """Instagram Reels uchun o'rganilgan manba uslubiga mos opisaniya."""
    items = look_items(look)
    n_items = len(items)
    items_text = "\n".join(
        f"• {i['name']}" + (f" ({i['color_uz']})" if i.get("color_uz") and i["color_uz"].lower() not in i["name"].lower() else "")
        for i in items
    )
    p50, rem50 = look_50_values(look)
    persona = select_persona_archetype(look.get("title", ""), look.get("audio_vibe", ""), idx=int(look.get("id") or 0))
    colors_line = look.get("colors") or "Och bej, To'q kulrang (grafit), To'q jigarrang"
    mgr_clean = (manager_username or "Bekshop_style").lstrip("@")
    ig_pb = (playbooks or {}).get("ig_reels_strategy") or {}
    custom_cta = re.sub(r"@[A-Za-z0-9_]+", f"@{mgr_clean}", str(ig_pb.get("caption_cta") or "").strip())
    is_english_cta = any(w in custom_cta.lower() for w in ("save for later", "comment your", "dm to order", "link in bio"))
    cta_line = (
        custom_cta
        if (custom_cta and not is_english_cta)
        else "💬 Buyurtma, rang va razmer uchun izohda «+» yoki savolingizni yozing!"
    )

    return (
        f"{persona['hook_headline']} 🔥\n"
        f"{look.get('title', 'Tayyor Obraz')} ({n_items} qism)\n\n"
        f"To'plamda:\n{items_text}\n\n"
        f"-| Hozirgi narx (50%): {fmt(p50)} so'm\n"
        f"-| To'liq narxi: {fmt(look.get('prepay_uzs', 0))} so'm\n"
        f"-| Kargo: 12 000 so'm / 100 gr (qolgan {fmt(rem50)} so'm + kargo Toshkentga kelganda)\n"
        f"-| Razmer: {look.get('sizes') or 'M, L, XL, 2XL'} ({colors_line})\n"
        f"-| Yetkazib berish: 5–12 kun (Avia)\n\n"
        f"{cta_line}\n"
        f"📲 Telegram: @{mgr_clean} (Kod: #{look['id']})\n\n"
        f"#xanshop #lookuz #mensfashionuz #tashkentstyle #kiyimuz"
    )


def generate_premium_channel_kit(shop_name: str = "XAN SHOP", manager_username: str = "Bekshop_style") -> dict[str, str]:
    mgr = manager_username.lstrip("@") or "Bekshop_style"
    return {
        "instagram_bio": (
            f"👑 {shop_name} | Erkaklar Tayyor Obrazlari\n"
            f"• Bo'y va vazningizga mos 2/3/4 qismli setlar\n"
            f"• Hozir 50% • Kargo: 12 000 so'm / 100 gr\n"
            f"• Avia: 5–12 kun ✈️ | @{mgr}"
        ),
        "instagram_highlights": "1) ISBOTLAR  2) OTZIVLAR  3) 50% SHARTI  4) RAZMERLAR  5) KARGO",
        "telegram_channel_bio": (
            f"{shop_name} — Tayyor erkaklar obrazlari.\n"
            f"✔️ 50% oldindan | Kargo: 12 000 so'm / 100 gr\n"
            f"✈️ Avia: 5–12 kun | Zakaz: @{mgr}"
        ),
        "telegram_pinned_post": (
            f"📌 <b>{shop_name} — ISHONCHLI XARID QOIDASI</b>\n\n"
            f"1️⃣ <b>Hozir faqat 50% to'laysiz:</b>\n"
            f"Qolgan 50% + kargo (12 000 so'm / 100 gr) to'lovini kiyimingiz Toshkentga yetib kelib, sifatini ko'rganingizda to'laysiz.\n\n"
            f"2️⃣ <b>Aniq Razmer:</b>\n"
            f"Bo'y (sm), vazn (kg) va oyoq razmeringizni yozing — har bir kiyimning o'z do'kon jadvalidan aniq mos razmerni tanlab beramiz.\n\n"
            f"3️⃣ <b>Avia 5–12 kun:</b>\n"
            f"Buyurtma va savollar uchun: @{mgr}"
        ),
    }


def channel_order_kb(
    sales_bot_username: str,
    look_id: int,
    manager_username: str = "",
) -> InlineKeyboardMarkup:
    bot_clean = (sales_bot_username or "XanShopUzBot").lstrip("@")
    bot_url = f"https://t.me/{bot_clean}?start=look_{look_id}"
    rows = [
        [InlineKeyboardButton(text="🛒 Buyurtma berish (1 daqiqa)", url=bot_url)],
    ]
    if manager_username:
        mgr_clean = manager_username.lstrip("@")
        rows.append([InlineKeyboardButton(text=f"👤 Menejer (@{mgr_clean})", url=f"https://t.me/{mgr_clean}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_telegram_post_link(channel_id: str | int, msg_id: int | None) -> str:
    """Telegram kanal postining to'g'ridan-to'g'ri havolasini tuzadi."""
    if not msg_id:
        return ""
    ch = str(channel_id or "").strip()
    if ch.startswith("@"):
        return f"https://t.me/{ch.lstrip('@')}/{msg_id}"
    if ch.startswith("-100"):
        return f"https://t.me/c/{ch[4:]}/{msg_id}"
    return f"https://t.me/Xan_style/{msg_id}"


async def get_instagram_permalink(ig_media_id: str, ig_access_token: str) -> str:
    """Yuklangan Instagram Reels videoning aniq havolasini (permalink) oladi."""
    if ig_media_id and ig_media_id.startswith("web_reel_"):
        code = ig_media_id[len("web_reel_"):]
        if code and not code.isdigit():
            return f"https://www.instagram.com/reel/{code}/"
        return "https://www.instagram.com/xans_styles/reels/"
    if not (ig_media_id and ig_access_token):
        return "https://www.instagram.com/xans_styles/reels/"
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                f"https://graph.facebook.com/v21.0/{ig_media_id}",
                params={"fields": "permalink,shortcode", "access_token": ig_access_token},
            ) as resp:
                data = await resp.json(content_type=None)
                if data.get("permalink"):
                    return str(data["permalink"])
    except Exception:
        pass
    return "https://www.instagram.com/xans_styles/reels/"


async def publish_look_to_telegram(
    bot: Bot,
    channel_id: int | str,
    look: dict[str, Any],
    sales_bot_username: str,
    shop_name: str = "XAN SHOP",
    photo_bytes: bytes | None = None,
    video_path: str | None = None,
    manager_username: str = "",
    playbooks: dict[str, dict[str, Any]] | None = None,
    item_photo_paths: list[str] | None = None,
) -> int | None:
    caption = format_channel_post(
        look,
        sales_bot_username,
        shop_name,
        manager_username=manager_username,
        playbooks=playbooks,
    )
    kb = channel_order_kb(sales_bot_username, look["id"], manager_username=manager_username)

    try:
        # Agar o'rganilgan kanal (@stylesh_shop / @_tima_shop) fotoalbom formatini qo'llasa va alohida buyum rasmlari bo'lsa,
        # asosiy kolaj + har bir buyum rasmini karusel albom sifatida ham chiqaradi
        tg_pb = (playbooks or {}).get("tg_channel_strategy") or {}
        fmt_mode = str(tg_pb.get("format") or "").lower()
        valid_album_paths = [p for p in (item_photo_paths or []) if p and os.path.exists(p)]
        if "album" in fmt_mode and len(valid_album_paths) >= 2 and hasattr(bot, "send_media_group"):
            try:
                media_group = [
                    InputMediaPhoto(
                        media=FSInputFile(p),
                        caption=f"📸 <b>{look.get('title', 'Tayyor Look')}</b> — barcha qismlar yaqin planda" if idx == 0 else None,
                        parse_mode="HTML" if idx == 0 else None,
                    )
                    for idx, p in enumerate(valid_album_paths[:5])
                ]
                await bot.send_media_group(chat_id=channel_id, media=media_group)
            except Exception as alb_exc:
                log.debug("Telegram album yuborish skip: %s", alb_exc)

        mp4_candidate = ""
        if video_path:
            if video_path.endswith(".mp4") and os.path.exists(video_path):
                mp4_candidate = video_path
            elif video_path.endswith(".gif") and os.path.exists(video_path[:-4] + ".mp4"):
                mp4_candidate = video_path[:-4] + ".mp4"

        if mp4_candidate:
            vid = FSInputFile(mp4_candidate)
            msg = await bot.send_video(
                chat_id=channel_id,
                video=vid,
                caption=caption,
                parse_mode="HTML",
                reply_markup=kb,
                supports_streaming=True,
                width=1080,
                height=1920,
            )
            return msg.message_id

        if video_path and os.path.exists(video_path):
            anim = FSInputFile(video_path)
            msg = await bot.send_animation(
                chat_id=channel_id,
                animation=anim,
                caption=caption,
                parse_mode="HTML",
                reply_markup=kb,
            )
            return msg.message_id

        if photo_bytes:
            photo = BufferedInputFile(photo_bytes, filename=f"look_{look['id']}.jpg")
            msg = await bot.send_photo(
                chat_id=channel_id,
                photo=photo,
                caption=caption,
                parse_mode="HTML",
                reply_markup=kb,
            )
            return msg.message_id

        if look.get("photo_path") and os.path.exists(look["photo_path"]):
            photo = FSInputFile(look["photo_path"])
            msg = await bot.send_photo(
                chat_id=channel_id,
                photo=photo,
                caption=caption,
                parse_mode="HTML",
                reply_markup=kb,
            )
            return msg.message_id

        msg = await bot.send_message(
            chat_id=channel_id,
            text=caption,
            parse_mode="HTML",
            reply_markup=kb,
            disable_web_page_preview=True,
        )
        return msg.message_id
    except Exception as e:
        log.exception("Kanalga post chiqarishda xatolik: %s", e)
        return None


def _publish_via_instagrapi_sync(
    local_video_path: str = "",
    local_photo_path: str = "",
    caption: str = "",
    hide_likes: bool = True,
    is_story: bool = False,
) -> str | None:
    """Facebook sahifasiz, to'g'ridan-to'g'ri Instagram (@xans_styles) sessiyasi orqali Reels (likes yashirilgan) va Istoriya joylaydi."""
    if os.getenv("PYTEST_CURRENT_TEST"):
        return None
    username = os.getenv("IG_USERNAME", "xans_styles").strip()
    password = os.getenv("IG_PASSWORD", "").strip()
    if not username or not password:
        return None
    try:
        from pathlib import Path
        from instagrapi import Client

        cl = Client()
        cl.delay_range = [1, 2]
        sess_file = Path("data/ig_session.json")
        sess_file.parent.mkdir(parents=True, exist_ok=True)
        if sess_file.is_file():
            try:
                cl.load_settings(sess_file)
            except Exception:
                pass
        cl.login(username, password)
        try:
            cl.dump_settings(sess_file)
        except Exception:
            pass

        if is_story:
            if local_video_path and os.path.isfile(local_video_path):
                media = cl.video_upload_to_story(Path(local_video_path))
                return str(getattr(media, "pk", "") or getattr(media, "id", "") or "") or None
            if local_photo_path and os.path.isfile(local_photo_path):
                media = cl.photo_upload_to_story(Path(local_photo_path))
                return str(getattr(media, "pk", "") or getattr(media, "id", "") or "") or None
            return None

        if local_video_path and os.path.isfile(local_video_path):
            extra = {"like_and_view_counts_disabled": 1} if hide_likes else {}
            media = cl.clip_upload(Path(local_video_path), caption=caption, extra_data=extra)
            return str(getattr(media, "code", "") or getattr(media, "pk", "") or "") or None
    except Exception as exc:
        log.debug("Direct instagrapi publish fallback skip: %s", exc)
    return None


DEFAULT_IG_BROWSER_SESSION = "data/ig_browser_session.json"


def has_valid_ig_browser_session(session_path: str = DEFAULT_IG_BROWSER_SESSION) -> bool:
    """Saqlangan Instagram brauzer sessiyasida (`sessionid` cookie) faol kirish borligini tekshiradi."""
    if not session_path or not os.path.isfile(session_path):
        return False
    try:
        import json

        data = json.loads(open(session_path, encoding="utf-8").read())
        for c in (data.get("cookies") or []):
            if str(c.get("name") or "") == "sessionid" and str(c.get("value") or "").strip():
                return True
    except Exception:
        pass
    return False


async def publish_reels_via_web_browser(
    local_video_path: str,
    caption: str,
    hide_likes: bool = True,
    session_path: str = DEFAULT_IG_BROWSER_SESSION,
) -> str | None:
    """Facebook'siz to'g'ridan-to'g'ri Instagram veb-sessiyasi orqali 1080p Reels yuklaydi va har bir videoda 'Hide like and view counts' ni yoqadi."""
    if os.getenv("PYTEST_CURRENT_TEST") or not local_video_path or not os.path.isfile(local_video_path):
        return None
    if not has_valid_ig_browser_session(session_path):
        return None
    try:
        from playwright.async_api import async_playwright
    except Exception:
        return None

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                ctx = await browser.new_context(
                    storage_state=session_path,
                    viewport={"width": 1280, "height": 900},
                )
                page = await ctx.new_page()
                await page.goto("https://www.instagram.com/", timeout=30000, wait_until="domcontentloaded")
                await page.wait_for_timeout(3000)

                # 0) Agar "Continue as xans_styles" profili taklif etilsa, uni bosib lentaga kiramiz
                for sel in (
                    '[aria-label*="Continue"]',
                    '[role="button"]:has-text("Continue")',
                    'div[role="button"]:has-text("Continue")',
                    'button:has-text("Continue")',
                    '[role="button"]:has-text("Войти как")',
                ):
                    loc = page.locator(sel).first
                    if await loc.count() > 0:
                        try:
                            await loc.click(timeout=3000)
                            await page.wait_for_timeout(2500)
                            break
                        except Exception:
                            pass

                # Agar parol yoki login formasi chiqsa - avto-login
                ig_user = os.getenv("IG_USERNAME", "xans_styles").strip()
                ig_pwd = os.getenv("IG_PASSWORD", "").strip()
                pwd_input = page.locator('input[type="password"]').first
                user_input = page.locator('input[name="username"]').first

                if await pwd_input.count() > 0 and ig_pwd:
                    try:
                        if await user_input.count() > 0 and ig_user:
                            await user_input.fill(ig_user)
                        log.info("Instagram brauzerida paroli kiritilmoqda...")
                        await pwd_input.fill(ig_pwd)
                        await pwd_input.press("Enter")
                        await page.wait_for_timeout(5000)
                        await ctx.storage_state(path=session_path)
                    except Exception as e_pwd:
                        log.warning("Instagram avto-login xatosi: %s", e_pwd)

                if "/accounts/login" in page.url or "challenge" in page.url:
                    log.warning("Instagram brauzer sessiyasi eskirgan yoki tekshiruv so'radi: %s", page.url)
                    return None

                # "Not Now" / "Save info" bildirishnoma oynalarini yopish
                for sel in (
                    'button:has-text("Not Now")',
                    'button:has-text("Не сейчас")',
                    'button:has-text("Save info")',
                    'button:has-text("Сохранить данные")',
                    'div[role="button"]:has-text("Not Now")',
                ):
                    loc = page.locator(sel).first
                    if await loc.count() > 0:
                        try:
                            await loc.click(timeout=2000)
                            await page.wait_for_timeout(600)
                        except Exception:
                            pass

                # 1) Create / Post tugmasini bosish (Instagram 2026 Business sidebar: svg[aria-label="Post"])
                clicked_create = False
                for sel in (
                    'svg[aria-label="Post"]',
                    'svg[aria-label="New post"]',
                    'svg[aria-label="Создать"]',
                    'svg[aria-label="Публикация"]',
                ):
                    loc = page.locator(sel).first
                    if await loc.count() > 0:
                        try:
                            await loc.click(timeout=5000)
                            await page.wait_for_timeout(1400)
                            clicked_create = True
                            break
                        except Exception:
                            continue

                if not clicked_create:
                    log.warning("Instagram Create/Post tugmasi topilmadi")
                    return None

                # Agar Create menyusi ochilsa "Post" ni tanlaymiz
                post_opt = page.locator('div[role="dialog"] span:has-text("Post"), a[role="link"]:has-text("Post")').first
                if await post_opt.count() > 0 and await page.locator('input[type="file"]').count() == 0:
                    try:
                        await post_opt.click(timeout=3000)
                        await page.wait_for_timeout(800)
                    except Exception:
                        pass

                # 2) Video faylni yuklash
                file_inp = page.locator('input[type="file"]').first
                await file_inp.set_input_files(os.path.abspath(local_video_path))
                await page.wait_for_timeout(4500)

                # "Video posts are now shared as reels" oynasi chiqsa OK bosamiz
                ok_btn = page.locator('button:has-text("OK"), button:has-text("ОК")').first
                if await ok_btn.count() > 0:
                    try:
                        await ok_btn.click(timeout=3000)
                        await page.wait_for_timeout(900)
                    except Exception:
                        pass

                # 9:16 Original Reels nisbatini tanlash
                crop_svg = page.locator('div[role="dialog"] svg[aria-label="Select crop"]').first
                if await crop_svg.count() > 0:
                    try:
                        await crop_svg.click(timeout=3000)
                        await page.wait_for_timeout(600)
                        orig_opt = page.locator('div[role="dialog"] span:has-text("Original"), div[role="dialog"] span:has-text("9:16"), div[role="dialog"] span:has-text("Оригинал")').first
                        if await orig_opt.count() > 0:
                            await orig_opt.click(timeout=3000)
                            await page.wait_for_timeout(600)
                    except Exception:
                        pass

                # 3) 2 marta Next (Crop -> Trim/Cover -> Caption ekrani)
                for _ in range(2):
                    nxt = page.locator('div[role="dialog"] div[role="button"]:has-text("Next"), div[role="dialog"] button:has-text("Next"), div[role="dialog"] div[role="button"]:has-text("Далее")').first
                    if await nxt.count() > 0:
                        await nxt.click(timeout=8000)
                        await page.wait_for_timeout(2200)

                # 4) Opisaniya yozish
                cap_box = page.locator('div[role="dialog"] div[role="textbox"][aria-label*="caption"], div[role="dialog"] div[role="textbox"], div[role="dialog"] textarea').first
                if await cap_box.count() > 0:
                    await cap_box.click(timeout=5000)
                    await cap_box.fill(caption[:2100])
                    await page.wait_for_timeout(700)

                # 5) HAR BIR VIDEODA ALOHIDA "Hide like and view counts on this post" ni yoqish ("Add AI label" ga tegmasdan!)
                if hide_likes:
                    adv = page.locator(
                        'div[role="dialog"] span:has-text("Advanced settings"), div[role="dialog"] div[role="button"]:has-text("Advanced settings"), div[role="dialog"] :text("Расширенные настройки")'
                    ).first
                    if await adv.count() > 0:
                        await adv.scroll_into_view_if_needed()
                        await adv.click(timeout=5000)
                        await page.wait_for_timeout(1000)
                        hide_sw = page.locator(
                            'xpath=//div[@role="dialog"]//*[contains(normalize-space(.), "Hide like and view counts") or contains(normalize-space(.), "Скрыть число отметок")]/ancestor::div[.//input[@type="checkbox" or @role="switch"]][1]//input[@type="checkbox" or @role="switch"]'
                        ).first
                        if await hide_sw.count() == 0:
                            # Fallback: agar "Add AI label" 1-switch bo'lsa, "Hide like" 2-switch (nth(1)) bo'ladi
                            all_sw = page.locator('div[role="dialog"] input[type="checkbox"], div[role="dialog"] input[role="switch"]')
                            hide_sw = all_sw.nth(1) if await all_sw.count() >= 2 else all_sw.first
                        if await hide_sw.count() > 0:
                            try:
                                await hide_sw.scroll_into_view_if_needed()
                                if not await hide_sw.is_checked():
                                    await hide_sw.click(force=True, timeout=4000)
                                    await page.wait_for_timeout(500)
                            except Exception:
                                pass

                # 6) Share tugmasi
                share_btn = page.locator(
                    'div[role="dialog"] div[role="button"]:has-text("Share"), div[role="dialog"] button:has-text("Share"), div[role="dialog"] div[role="button"]:has-text("Поделиться")'
                ).first
                if await share_btn.count() > 0:
                    await share_btn.click(timeout=8000)
                    for _ in range(30):
                        await page.wait_for_timeout(2000)
                        body_txt = (await page.locator('div[role="dialog"]').inner_text() if await page.locator('div[role="dialog"]').count() > 0 else "")
                        if any(k in body_txt.lower() for k in ("reel has been shared", "post has been shared", "публикация размещена", "shared reel")):
                            try:
                                await page.goto("https://www.instagram.com/xans_styles/", timeout=20000, wait_until="domcontentloaded")
                                await page.wait_for_timeout(2500)
                                reel_loc = page.locator('a[href*="/reel/"]').first
                                if await reel_loc.count() > 0:
                                    href = await reel_loc.get_attribute("href")
                                    m_code = re.search(r"/reel/([A-Za-z0-9_-]+)", href or "")
                                    if m_code:
                                        return f"web_reel_{m_code.group(1)}"
                            except Exception:
                                pass
                            return f"web_reel_{int(asyncio.get_running_loop().time())}"
            finally:
                await browser.close()
    except Exception as exc:
        log.warning("Instagram Web Browser Reels yuklash xatosi: %s", exc)
    return None


async def interactive_ig_browser_login(
    session_path: str = DEFAULT_IG_BROWSER_SESSION,
    timeout_sec: int = 240,
) -> bool:
    """Bir martalik Chrome oynasi orqali @xans_styles sessiyasini saqlaydi (Facebook shart emas!)."""
    try:
        from playwright.async_api import async_playwright
    except Exception:
        return False
    os.makedirs(os.path.dirname(session_path) or "data", exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        try:
            ctx = await browser.new_context(viewport={"width": 1100, "height": 820})
            page = await ctx.new_page()
            await page.goto("https://www.instagram.com/accounts/login/", timeout=30000)
            elapsed = 0
            while elapsed < timeout_sec:
                cookies = await ctx.cookies("https://www.instagram.com")
                if any(c.get("name") == "sessionid" and str(c.get("value") or "").strip() for c in cookies):
                    await ctx.storage_state(path=session_path)
                    return True
                await asyncio.sleep(2)
                elapsed += 2
        finally:
            await browser.close()
    return False


async def resolve_active_ig_user_id(ig_user_id: str, ig_access_token: str) -> str:
    """Facebook Page'ga ulangan faol Instagram Business ID ni avtomatik aniqlaydi."""
    if not ig_access_token:
        return ig_user_id
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            if ig_user_id:
                async with session.get(
                    f"https://graph.facebook.com/v22.0/{ig_user_id}",
                    params={"fields": "id,username", "access_token": ig_access_token},
                ) as r0:
                    d0 = await r0.json(content_type=None)
                    if r0.status == 200 and d0.get("id"):
                        return str(d0["id"])
            async with session.get(
                "https://graph.facebook.com/v22.0/me/accounts",
                params={"fields": "id,name,instagram_business_account{id,username}", "access_token": ig_access_token},
            ) as r1:
                if r1.status == 200:
                    d1 = await r1.json(content_type=None)
                    for pg in (d1.get("data") or []):
                        ig_biz = (pg.get("instagram_business_account") or {}) if isinstance(pg, dict) else {}
                        if ig_biz.get("id"):
                            return str(ig_biz["id"])
    except Exception:
        pass
    return ig_user_id


async def publish_reels_to_instagram(
    ig_user_id: str,
    ig_access_token: str,
    video_public_url: str,
    caption: str,
    hide_likes: bool = True,
    local_video_path: str = "",
) -> str | None:
    """1080p Reels joylaydi: avval har bir videoda 'Hide Likes' ni yoqa oladigan Instagram Web sessiyasi (Facebook'siz), so'ng Meta Graph API."""
    # 1) Agar Facebook'siz Instagram brauzer sessiyasi saqlangan bo'lsa va hide_likes=True bo'lsa — har bir videoda alohida laykni yashirib yuklaydi!
    if local_video_path and os.path.isfile(local_video_path) and has_valid_ig_browser_session():
        web_id = await publish_reels_via_web_browser(
            local_video_path,
            caption,
            hide_likes=hide_likes,
        )
        if web_id:
            return web_id

    # 2) Rasmiy Meta Graph API (agar Facebook sahifaga ulangan IG Business hisob bo'lsa)
    eff_ig_id = await resolve_active_ig_user_id(ig_user_id, ig_access_token) if ig_access_token else ig_user_id
    if eff_ig_id and ig_access_token and video_public_url.startswith("http"):
        base = f"https://graph.facebook.com/v22.0/{eff_ig_id}"
        try:
            timeout = aiohttp.ClientTimeout(total=45)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # Meta rasmiy Graph API faqat hujjatlashtirilgan parametrlarni qabul qiladi
                # (like sonini yashirish Instagram profil sozlamasidan 1 marta yoqiladi, aks holda API Error 100 beradi)
                create_payload: dict[str, str] = {
                    "media_type": "REELS",
                    "video_url": video_public_url,
                    "caption": caption,
                    "share_to_feed": "true",
                    "access_token": ig_access_token,
                }
                async with session.post(f"{base}/media", data=create_payload) as r1:
                    res1 = await r1.json(content_type=None)
                creation_id = res1.get("id")
                if creation_id:
                    for _ in range(16):
                        await asyncio.sleep(3)
                        async with session.get(
                            f"https://graph.facebook.com/v22.0/{creation_id}",
                            params={"fields": "status_code", "access_token": ig_access_token},
                        ) as st_resp:
                            st_data = await st_resp.json(content_type=None)
                        if st_data.get("status_code") in ("FINISHED", "ERROR"):
                            break

                    async with session.post(
                        f"{base}/media_publish",
                        data={"creation_id": creation_id, "access_token": ig_access_token},
                    ) as r2:
                        res2 = await r2.json(content_type=None)
                    pub_id = str(res2.get("id") or "") or None
                    if pub_id:
                        return pub_id
                else:
                    log.warning("Instagram Graph API Reels container xatosi: %s", str(res1)[:220])
        except Exception as e:
            log.warning("Instagram Graph API xatosi: %s", e)

    # 3) instagrapi zaxirasi: FAQAT lokal kompyuterda (rezidensial IP) ruxsat etiladi.
    # Bulutli serverlarda (GitHub Actions / Azure / AWS) bu bloklanadi va foydalanuvchi telefoniga "Pixel 8 Pro bloklandi" xabarini chiqaradi.
    is_cloud_runner = bool(os.getenv("GITHUB_ACTIONS") or os.getenv("CI"))
    if not is_cloud_runner and local_video_path and os.path.isfile(local_video_path):
        return await asyncio.to_thread(
            _publish_via_instagrapi_sync,
            local_video_path,
            "",
            caption,
            hide_likes,
            False,
        )
    return None


async def publish_story_via_web_browser(
    local_photo_path: str = "",
    local_video_path: str = "",
    session_path: str = DEFAULT_IG_BROWSER_SESSION,
) -> str | None:
    """Facebook'siz Instagram mobil veb-sessiyasi orqali Istoriya (Story) joylaydi."""
    target_path = local_photo_path if (local_photo_path and os.path.isfile(local_photo_path)) else local_video_path
    if os.getenv("PYTEST_CURRENT_TEST") or not target_path or not os.path.isfile(target_path):
        return None
    if not has_valid_ig_browser_session(session_path):
        return None
    try:
        from playwright.async_api import async_playwright
    except Exception:
        return None

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                ctx = await browser.new_context(
                    storage_state=session_path,
                    viewport={"width": 390, "height": 844},
                    user_agent=(
                        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
                    ),
                    is_mobile=True,
                    has_touch=True,
                )
                page = await ctx.new_page()
                await page.goto("https://www.instagram.com/", timeout=30000, wait_until="domcontentloaded")
                await page.wait_for_timeout(3000)
                for sel in ('[aria-label*="Continue"]', '[role="button"]:has-text("Continue")', 'button:has-text("Continue")'):
                    if await page.locator(sel).count() > 0:
                        try:
                            await page.locator(sel).first.click(timeout=3000)
                            await page.wait_for_timeout(3000)
                            break
                        except Exception:
                            pass
                if "/accounts/login" in page.url or "challenge" in page.url:
                    return None
                for sel in ('button:has-text("Your story")', 'span:has-text("Your story")', 'svg[aria-label="New story"]'):
                    loc = page.locator(sel).first
                    if await loc.count() > 0:
                        async with page.expect_file_chooser(timeout=8000) as fc_info:
                            await loc.click(timeout=5000)
                        fc = await fc_info.value
                        await fc.set_files(os.path.abspath(target_path))
                        await page.wait_for_timeout(3500)
                        add_btn = page.locator('button:has-text("Add to your story"), span:has-text("Add to your story")').first
                        if await add_btn.count() > 0:
                            await add_btn.click(timeout=8000)
                            await page.wait_for_timeout(4000)
                            return f"web_story_{int(asyncio.get_running_loop().time())}"
                        break
            finally:
                await browser.close()
    except Exception as exc:
        log.debug("Instagram Web Story skip: %s", exc)
    return None


async def publish_story_to_instagram(
    ig_user_id: str,
    ig_access_token: str,
    video_public_url: str = "",
    image_public_url: str = "",
    local_video_path: str = "",
    local_photo_path: str = "",
) -> str | None:
    """Yangi chiqqan Look videoni yoki flat-lay rasmni avtomatik ravishda Instagram Istoriyaga (STORIES) ham joylaydi."""
    if has_valid_ig_browser_session() and (local_photo_path or local_video_path):
        st_web = await publish_story_via_web_browser(
            local_photo_path=local_photo_path,
            local_video_path=local_video_path,
        )
        if st_web:
            return st_web

    eff_ig_id = await resolve_active_ig_user_id(ig_user_id, ig_access_token) if ig_access_token else ig_user_id
    if eff_ig_id and ig_access_token and (video_public_url.startswith("http") or image_public_url.startswith("http")):
        base = f"https://graph.facebook.com/v22.0/{eff_ig_id}"
        try:
            timeout = aiohttp.ClientTimeout(total=45)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                story_payload: dict[str, str] = {
                    "media_type": "STORIES",
                    "access_token": ig_access_token,
                }
                if video_public_url.startswith("http"):
                    story_payload["video_url"] = video_public_url
                else:
                    story_payload["image_url"] = image_public_url

                async with session.post(f"{base}/media", data=story_payload) as r1:
                    res1 = await r1.json(content_type=None)
                creation_id = res1.get("id")
                if creation_id:
                    for _ in range(14):
                        await asyncio.sleep(3)
                        async with session.get(
                            f"https://graph.facebook.com/v22.0/{creation_id}",
                            params={"fields": "status_code", "access_token": ig_access_token},
                        ) as st_resp:
                            st_data = await st_resp.json(content_type=None)
                        if st_data.get("status_code") in ("FINISHED", "ERROR"):
                            break

                    async with session.post(
                        f"{base}/media_publish",
                        data={"creation_id": creation_id, "access_token": ig_access_token},
                    ) as r2:
                        res2 = await r2.json(content_type=None)
                    st_id = str(res2.get("id") or "") or None
                    if st_id:
                        return st_id
        except Exception as e:
            log.debug("Instagram Story API skip: %s", e)

    is_cloud_runner = bool(os.getenv("GITHUB_ACTIONS") or os.getenv("CI"))
    if not is_cloud_runner and ((local_video_path and os.path.isfile(local_video_path)) or (local_photo_path and os.path.isfile(local_photo_path))):
        return await asyncio.to_thread(
            _publish_via_instagrapi_sync,
            local_video_path,
            local_photo_path,
            "",
            True,
            True,
        )
    return None
