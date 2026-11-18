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
            f"- 50% oldindan to'lov (+ kargo va qolgan {fmt(rem50)} so'm Toshkentda ko'rganingizda)",
            "- Dastavka UZB bo'ylab: <b>5–10 kun (Avia)</b>",
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
            "-| Yetkazib berish: <b>5–10 kun (Avia)</b>",
            f"-| + kargo (qolgan {fmt(rem50)} so'm + kargo Toshkentga kelganda)",
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
        f"📏 Razmer: <b>{look.get('sizes') or 'M, L, XL, 2XL'}</b> <i>(bo'y/vaznga qarab tanlaymiz)</i>",
        f"✈️ Yetkazish: <b>5–10 kun (Avia)</b>\n",
        f"💳 <b>Hozirgi narx (50%): {fmt(p50)} so'm</b>",
        f"📦 <b>+ kargo</b> <i>(qolgan {fmt(rem50)} so'm + kargo — kiyim Toshkentga kelib, ko'rganingizda!)</i>",
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
    cta_line = custom_cta if custom_cta else "💬 Buyurtma, rang va razmer uchun izohda «+» yoki savolingizni yozing!"

    return (
        f"{persona['hook_headline']} 🔥\n"
        f"{look.get('title', 'Tayyor Obraz')} ({n_items} qism)\n\n"
        f"To'plamda:\n{items_text}\n\n"
        f"-| Hozirgi narx (50%): {fmt(p50)} so'm\n"
        f"-| + kargo (qolgan {fmt(rem50)} so'm + kargo — kiyim Toshkentga kelib, ko'rganingizda!)\n"
        f"-| To'liq narxi: {fmt(look.get('prepay_uzs', 0))} so'm\n"
        f"-| Razmer: M, L, XL, 2XL ({colors_line})\n"
        f"-| Yetkazib berish: 5–10 kun (Avia)\n\n"
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
            f"• Hozir 50% • Qolgani Toshkentga kelganda!\n"
            f"• Avia: 5–10 kun ✈️ | @{mgr}"
        ),
        "instagram_highlights": "1) ISBOTLAR  2) OTZIVLAR  3) 50% SHARTI  4) RAZMERLAR  5) KARGO",
        "telegram_channel_bio": (
            f"{shop_name} — Tayyor erkaklar obrazlari.\n"
            f"✔️ 50% oldindan | Qolgani Toshkentda ko'rib olganda\n"
            f"✈️ Avia: 5–10 kun | Zakaz: @{mgr}"
        ),
        "telegram_pinned_post": (
            f"📌 <b>{shop_name} — ISHONCHLI XARID QOIDASI</b>\n\n"
            f"1️⃣ <b>Hozir faqat 50% to'laysiz:</b>\n"
            f"Qolgan 50% + kargo to'lovini kiyimingiz Toshkentga yetib kelib, sifatini ko'rganingizda to'laysiz.\n\n"
            f"2️⃣ <b>Aniq Razmer:</b>\n"
            f"Bo'y (sm) va vazningizni (kg) yozing — sizga aniq mos razmerni (M–2XL) tanlab beramiz.\n\n"
            f"3️⃣ <b>Avia 5–10 kun:</b>\n"
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
    if not (ig_media_id and ig_access_token):
        return "https://www.instagram.com/xan_styles/reels/"
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
    return "https://www.instagram.com/xan_styles/reels/"


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


async def publish_reels_to_instagram(
    ig_user_id: str,
    ig_access_token: str,
    video_public_url: str,
    caption: str,
    hide_likes: bool = True,
) -> str | None:
    """Rasmiy Meta / Instagram Graph API orqali 1080p Reels videoni (likes yashirilgan holda) Instagram sahifaga joylaydi."""
    if not (ig_user_id and ig_access_token and video_public_url.startswith("http")):
        return None

    base = f"https://graph.facebook.com/v21.0/{ig_user_id}"
    try:
        timeout = aiohttp.ClientTimeout(total=40)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            create_payload: dict[str, str] = {
                "media_type": "REELS",
                "video_url": video_public_url,
                "caption": caption,
                "share_to_feed": "true",
                "access_token": ig_access_token,
            }
            if hide_likes:
                create_payload["hide_like_and_view_counts"] = "true"
                create_payload["like_and_view_counts_disabled"] = "true"
            async with session.post(f"{base}/media", data=create_payload) as r1:
                res1 = await r1.json(content_type=None)
            creation_id = res1.get("id")
            if not creation_id:
                log.warning("Instagram Reels container xatosi: %s", res1)
                return None

            for _ in range(14):
                await asyncio.sleep(3)
                async with session.get(
                    f"https://graph.facebook.com/v21.0/{creation_id}",
                    params={"fields": "status_code", "access_token": ig_access_token},
                ) as st_resp:
                    st_data = await st_resp.json(content_type=None)
                if st_data.get("status_code") == "FINISHED":
                    break

            async with session.post(
                f"{base}/media_publish",
                data={"creation_id": creation_id, "access_token": ig_access_token},
            ) as r2:
                res2 = await r2.json(content_type=None)
            return str(res2.get("id") or "") or None
    except Exception as e:
        log.warning("Instagram Graph API xatosi: %s", e)
        return None


async def publish_story_to_instagram(
    ig_user_id: str,
    ig_access_token: str,
    video_public_url: str = "",
    image_public_url: str = "",
) -> str | None:
    """Yangi chiqqan Look videoni yoki flat-lay rasmni avtomatik ravishda Instagram Istoriyaga (STORIES) ham joylaydi."""
    if not (ig_user_id and ig_access_token and (video_public_url.startswith("http") or image_public_url.startswith("http"))):
        return None

    base = f"https://graph.facebook.com/v21.0/{ig_user_id}"
    try:
        timeout = aiohttp.ClientTimeout(total=40)
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
            if not creation_id:
                log.debug("Instagram Story container skip: %s", res1)
                return None

            for _ in range(12):
                await asyncio.sleep(3)
                async with session.get(
                    f"https://graph.facebook.com/v21.0/{creation_id}",
                    params={"fields": "status_code", "access_token": ig_access_token},
                ) as st_resp:
                    st_data = await st_resp.json(content_type=None)
                if st_data.get("status_code") == "FINISHED":
                    break

            async with session.post(
                f"{base}/media_publish",
                data={"creation_id": creation_id, "access_token": ig_access_token},
            ) as r2:
                res2 = await r2.json(content_type=None)
            return str(res2.get("id") or "") or None
    except Exception as e:
        log.debug("Instagram Story API skip: %s", e)
        return None
