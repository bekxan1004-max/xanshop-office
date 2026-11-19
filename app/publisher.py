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
    password = os.getenv("IG_PASSWORD", "1234567890beK$").strip()
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
    """Rasmiy Meta Graph API yoki to'g'ridan-to'g'ri @xans_styles sessiyasi orqali 1080p Reels joylaydi."""
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

    if local_video_path and os.path.isfile(local_video_path):
        return await asyncio.to_thread(
            _publish_via_instagrapi_sync,
            local_video_path,
            "",
            caption,
            hide_likes,
            False,
        )
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

    if (local_video_path and os.path.isfile(local_video_path)) or (local_photo_path and os.path.isfile(local_photo_path)):
        return await asyncio.to_thread(
            _publish_via_instagrapi_sync,
            local_video_path,
            local_photo_path,
            "",
            True,
            True,
        )
    return None
