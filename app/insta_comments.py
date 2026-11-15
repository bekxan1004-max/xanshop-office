"""XAN SHOP - Instagram Reels Kommentlariga Aqlli AI Javob Beruvchi Agent (v3.2).

Rasmiy Instagram Graph API (`/{media_id}/comments` va `/{comment_id}/replies`) orqali:
- Mijozlarning rang (rassvetka), razmer (bo'y/vazn), mato, '+' va narx haqidagi savollarini o'qiydi;
- Har bir savolning mazmuniga qarab (masalan: "menga mos boshqa rangi bormi?", "180 sm 75 kg ga razmer bormi?", "+")
  aniq, samimiy va sotuvga yo'naltiruvchi javob qaytaradi.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import aiohttp

from .ai import SalesAI
from .config import Settings
from .db import Database
from .pricing import fmt
from .sizes import recommend
from .texts import look_50_values, look_items, split_list

log = logging.getLogger(__name__)


def _extract_height_weight(text: str) -> tuple[float | None, float | None]:
    """Komment ichidan bo'y (150..210 sm) va vazn (40..150 kg) raqamlarini ajratib oladi."""
    nums = [int(n) for n in re.findall(r"\b(\d{2,3})\b", text or "")]
    height = next((float(n) for n in nums if 150 <= n <= 210), None)
    weight = next((float(n) for n in nums if 42 <= n <= 145 and n != height), None)
    return height, weight


async def generate_smart_comment_reply(
    comment_text: str,
    commenter_username: str,
    look: dict[str, Any] | None,
    settings: Settings,
    ai: SalesAI | None = None,
) -> str:
    """Komment mazmuniga qarab (rang/rassvetka, razmer/bo'y-vazn, '+', narx) aqlli javob tayyorlaydi."""
    raw = (comment_text or "").strip()
    low = raw.lower()
    mgr = (settings.manager_username or "Bekshop_style").lstrip("@")
    user_prefix = f"@{commenter_username} " if commenter_username else ""

    if look:
        p50, rem50 = look_50_values(look)
        full_price = int(look.get("prepay_uzs") or (p50 * 2))
        colors = str(look.get("colors") or "Och bej, To'q kulrang (grafit), Qora")
        sizes_str = str(look.get("sizes") or "M, L, XL, 2XL")
        items = look_items(look)
        items_names = ", ".join(i["name"] for i in items)
        look_code = f"#{look['id']}"
    else:
        p50, rem50, full_price = 250_000, 250_000, 500_000
        colors = "Och bej, To'q kulrang (grafit), Qora"
        sizes_str = "M, L, XL, 2XL"
        items_names = "To'liq kapsula to'plam"
        look_code = "#1"

    # 1. Bo'y va vazn yozilgan bo'lsa — darhol aniq razmer tavsiya qilamiz
    h_cm, w_kg = _extract_height_weight(raw)
    if h_cm and w_kg:
        rec = recommend(h_cm, w_kg, split_list(sizes_str)) or "XL"
        return (
            f"{user_prefix}Sizga ({int(h_cm)} sm / {int(w_kg)} kg) aynan {rec} razmer ideal tushadi ✅ "
            f"Rasmdagi ({colors}) va boshqa ranglari ham bor. "
            f"Hozirgi narx (50%): {fmt(p50)} so'm + kargo (kelganda). "
            f"Zakaz uchun Direct yoki Telegram @{mgr} ga yozing ({look_code}) 🙌"
        )

    # 2. Rang / Rassvetka haqida savol ("rangi bormi", "rassvetka", "qorasi bormi", "menga mosidan")
    color_keywords = ("rang", "rassvet", "rasvet", "qora", "oq", "kulrang", "bej", "ko'k", "kok", "jigarrang", "boshqa", "mosidan")
    if any(k in low for k in color_keywords):
        return (
            f"{user_prefix}Albatta! Videodagi ({colors}) ranglardan tashqari qora, oq, to'q kulrang, bej va to'q ko'k "
            f"rassvetkalari ham bor 🎨 Razmerlar: {sizes_str}. "
            f"Hozirgi narx (50%): {fmt(p50)} so'm + kargo (kelganda). "
            f"O'zingizga yoqqan rangni Direct yoki TG @{mgr} ga yozing, rasmlarini tashlab beramiz!"
        )

    # 3. Razmer haqida savol ("razmer", "o'lcham", "xl bormi", "katta razmer")
    size_keywords = ("razmer", "o'lcham", "olcham", "xl", "2xl", "3xl", "xxl", "bo'y", "boy", "vazn")
    if any(k in low for k in size_keywords):
        return (
            f"{user_prefix}Ha, {sizes_str} (va buyurtma asosida 3XL gacha) barcha razmerlar mavjud 📏 "
            f"Bo'yingiz (sm) va vazningizni (kg) yozvoringsangiz, sizga aniq mos razmer va rangni tanlab beramiz! "
            f"Hozirgi narx (50%): {fmt(p50)} so'm + kargo. TG: @{mgr} ({look_code})"
        )

    # 4. "+" yoki qisqa trigger / narx so'rovi
    if raw in ("+", "++", "+++", "look", "narx", "narxi", "qancha") or len(raw) <= 4 or any(
        k in low for k in ("narx", "qancha", "nechpul", "necha", "zakaz", "olmoqchi", "kerak")
    ):
        return (
            f"{user_prefix}To'plam ({items_names}) — Hozirgi narx (50%): {fmt(p50)} so'm + kargo "
            f"(qolgan {fmt(rem50)} so'm + kargo kiyim Toshkentga kelib, ko'rganingizda! To'liq: {fmt(full_price)} so'm) 🔥 "
            f"Rasmdagi ({colors}) va boshqa ranglari bor, razmer {sizes_str}. "
            f"Buyurtma uchun Direct yoki TG @{mgr} ga yozing ({look_code})!"
        )

    # 5. Murakkabroq yoki erkin savol bo'lsa — AI orqali aqlli javob
    if ai and (ai.enabled or ai.client):
        prompt = (
            f"Sen '{settings.shop_name}' erkaklar kiyim do'konining Instagram menejerisan.\n"
            f"Obraz: {look.get('title') if look else 'Tayyor Obraz'} ({items_names}).\n"
            f"Videodagi ranglar: {colors} (lekin omborda qora, oq, kulrang, bej, to'q ko'k rassvetkalari ham bor).\n"
            f"Razmerlar: {sizes_str} (bo'y va vaznga qarab aniq tanlab beriladi).\n"
            f"Shart: Hozirgi narx (50%): {fmt(p50)} so'm + kargo (qolgan {fmt(rem50)} so'm + kargo kiyim 5–10 kunda Toshkentga kelganda to'lanadi, to'liq narxi {fmt(full_price)} so'm).\n"
            f"Mijoz (@{commenter_username}) Instagram Reels izohida shunday yozdi: \"{raw}\"\n\n"
            f"Vazifang: Mijozning savoliga aynan mos, samimiy, qisqa (2–3 gap, maksimum 260 belgi) o'zbek tilida javob yoz va Direct yoki Telegram @{mgr} ({look_code}) ga yozishga chorla."
        )
        ai_ans = await ai.ask(prompt, timeout_sec=10.0)
        if ai_ans and len(ai_ans.strip()) > 15:
            cleaned = ai_ans.strip().replace('"', "")
            if commenter_username and not cleaned.startswith("@"):
                cleaned = f"@{commenter_username} {cleaned}"
            return cleaned[:290]

    return (
        f"{user_prefix}Assalomu alaykum! Bu to'plamda ({colors}) va boshqa ranglar hamda {sizes_str} razmerlar bor ✅ "
        f"Hozirgi narx (50%): {fmt(p50)} so'm + kargo (qolgani Toshkentga kelganda). "
        f"Bo'y/vazningizni Direct yoki TG @{mgr} ga yozing, moslab beramiz!"
    )


async def poll_and_reply_instagram_comments(
    db: Database,
    settings: Settings,
    ai: SalesAI | None = None,
    notify_fn=None,
) -> int:
    """Instagram Reels izohlarini tekshirib, yangi izohlarga AI orqali avtomatik javob qaytaradi."""
    if not (settings.ig_user_id and settings.ig_access_token):
        return 0

    replied_raw = await db.get_setting("replied_ig_comments_json") or "[]"
    try:
        replied_ids: set[str] = set(json.loads(replied_raw))
    except Exception:
        replied_ids = set()

    looks = await db.list_looks(only_active=False)
    look_by_ig_id = {str(lk.get("ig_media_id")): lk for lk in looks if lk.get("ig_media_id")}
    latest_look = looks[0] if looks else None

    replied_count = 0
    base = "https://graph.facebook.com/v21.0"
    timeout = aiohttp.ClientTimeout(total=20)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                f"{base}/{settings.ig_user_id}/media",
                params={
                    "fields": "id,caption,comments_count,permalink",
                    "limit": 8,
                    "access_token": settings.ig_access_token,
                },
            ) as m_resp:
                m_data = await m_resp.json(content_type=None)

            media_list = m_data.get("data") or []
            for media in media_list:
                media_id = str(media.get("id") or "")
                if not media_id or int(media.get("comments_count") or 0) <= 0:
                    continue

                async with session.get(
                    f"{base}/{media_id}/comments",
                    params={
                        "fields": "id,text,username,timestamp,replies{id,text,username}",
                        "limit": 25,
                        "access_token": settings.ig_access_token,
                    },
                ) as c_resp:
                    c_data = await c_resp.json(content_type=None)

                for cmt in c_data.get("data") or []:
                    cid = str(cmt.get("id") or "")
                    c_user = str(cmt.get("username") or "").strip()
                    c_text = str(cmt.get("text") or "").strip()
                    if not cid or not c_text or cid in replied_ids:
                        continue
                    if c_user.lower() in ("xan_styles", "xan_shop"):
                        replied_ids.add(cid)
                        continue

                    existing_replies = (cmt.get("replies") or {}).get("data") or []
                    if any(str(r.get("username") or "").lower() in ("xan_styles", "xan_shop") for r in existing_replies):
                        replied_ids.add(cid)
                        continue

                    matched_look = look_by_ig_id.get(media_id) or latest_look
                    reply_msg = await generate_smart_comment_reply(
                        comment_text=c_text,
                        commenter_username=c_user,
                        look=matched_look,
                        settings=settings,
                        ai=ai,
                    )

                    async with session.post(
                        f"{base}/{cid}/replies",
                        data={"message": reply_msg, "access_token": settings.ig_access_token},
                    ) as rep_resp:
                        rep_data = await rep_resp.json(content_type=None)

                    if rep_data.get("id"):
                        replied_ids.add(cid)
                        replied_count += 1
                        await db.log_agent_action(
                            "sales_stylist",
                            f"💬 Instagram Reels izohiga AI javob berildi (@{c_user})",
                            f"Savol: '{c_text}' -> Javob: '{reply_msg}'",
                        )
                        if notify_fn:
                            permalink = media.get("permalink") or "https://www.instagram.com/xan_styles/reels/"
                            await notify_fn(
                                f"💬 <b>Instagram izohiga AI javob berdi!</b>\n"
                                f"👤 Mijoz: <b>@{c_user}</b>\n"
                                f"❓ Izoh: <i>{c_text}</i>\n"
                                f"🤖 Javob: <code>{reply_msg}</code>\n"
                                f"🔗 <a href='{permalink}'>Reels'ni ochish</a>"
                            )
    except Exception as e:
        log.warning("Instagram kommentlarni tekshirishda xato: %s", e)

    if replied_count > 0:
        kept = list(replied_ids)[-500:]
        await db.set_setting("replied_ig_comments_json", json.dumps(kept))

    return replied_count
