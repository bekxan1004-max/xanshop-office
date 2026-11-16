from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger("xanshop.source_learner")

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"


def _parse_human_count(raw: str) -> int:
    s = (raw or "").strip().upper().replace(" ", "").replace(",", "")
    if not s:
        return 0
    try:
        if s.endswith("M"):
            return int(float(s[:-1]) * 1_000_000)
        if s.endswith("K"):
            return int(float(s[:-1]) * 1_000)
        digits = re.sub(r"[^\d.]", "", s)
        return int(float(digits)) if digits else 0
    except Exception:
        return 0


def parse_source_url(raw_input: str) -> tuple[str, str, str]:
    """Normalize a user-submitted Telegram, Instagram, Reel, or YouTube link into (platform, source_key, clean_url)."""
    txt = (raw_input or "").strip()
    if not txt:
        return ("unknown", "", "")

    # Strip tracking query params for clean storage
    if txt.startswith("@"):
        handle = txt.lstrip("@").strip().lower()
        return ("telegram", f"tg:{handle}", f"https://t.me/{handle}")

    if "t.me/" in txt or "telegram.me/" in txt:
        m = re.search(r"(?:t\.me|telegram\.me)/(?:s/)?([A-Za-z0-9_]{3,64})", txt)
        if m:
            ch = m.group(1).lower()
            return ("telegram", f"tg:{ch}", f"https://t.me/{ch}")

    if "instagram.com" in txt:
        m_reel = re.search(r"instagram\.com/(?:reel|reels|p)/([A-Za-z0-9_-]+)", txt)
        if m_reel:
            code = m_reel.group(1)
            return ("ig_reel", f"reel:{code}", f"https://www.instagram.com/reel/{code}/")
        m_prof = re.search(r"instagram\.com/([A-Za-z0-9_.]{2,40})", txt)
        if m_prof:
            handle = m_prof.group(1).strip("/").lower()
            if handle not in ("p", "reel", "reels", "explore", "accounts"):
                return ("instagram", f"ig:{handle}", f"https://www.instagram.com/{handle}/")

    if "youtube.com" in txt or "youtu.be" in txt:
        parsed = urlparse(txt)
        return ("youtube", f"yt:{parsed.path.strip('/').lower() or 'channel'}", txt.split("&pp=")[0])

    clean = re.sub(r"[^a-zA-Z0-9_.-]", "", txt).lower()
    return ("web", f"web:{clean[:40]}", txt)


async def check_ig_publish_ready(ig_user_id: str, ig_token: str) -> tuple[bool, str]:
    """Check once whether Instagram Graph API publishing account is active (not checkpoint-locked)."""
    if not ig_user_id or not ig_token:
        return (False, "IG_USER_ID yoki IG_ACCESS_TOKEN ulanmagan")
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                f"{GRAPH_API_BASE}/{ig_user_id}",
                params={"fields": "id,username", "access_token": ig_token},
            )
            data = resp.json()
            if resp.status_code == 200 and data.get("id"):
                return (True, "")
            err = (data.get("error") or {}).get("message", f"HTTP {resp.status_code}")
            if "does not exist" in err.lower() or "checkpoint" in err.lower():
                return (False, f"Meta checkpoint / hisob vaqtincha bloklangan: {err[:120]}")
            return (False, err[:160])
    except Exception as exc:
        return (False, f"IG tekshiruv tarmoq xatosi: {str(exc)[:100]}")


async def scrape_public_telegram_channel(channel_handle: str, limit: int = 25) -> dict[str, Any]:
    """Ochiq Telegram kanalning (https://t.me/s/<handle>) postlari, formati, vaqtlari va uslubini tahlil qiladi."""
    clean = channel_handle.replace("tg:", "").lstrip("@").strip().lower()
    url = f"https://t.me/s/{clean}"
    try:
        async with httpx.AsyncClient(
            timeout=12,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"},
        ) as client:
            resp = await client.get(url)
            if resp.status_code != 200 or "tgme_channel_info" not in resp.text:
                return {"ok": False, "handle": clean, "error": f"Kanal ochiq previewda topilmadi (HTTP {resp.status_code})"}

            html = resp.text
            title_m = re.search(r'<div class="tgme_channel_info_header_title"><span[^>]*>(.*?)</span>', html, flags=re.S)
            subs_m = re.search(r'<div class="tgme_channel_info_counter">\s*<span class="counter_value">([^<]+)</span>', html)
            desc_m = re.search(r'<div class="tgme_channel_info_description"[^>]*>(.*?)</div>', html, flags=re.S)

            title = re.sub(r"<[^>]+>", "", title_m.group(1)).strip() if title_m else clean
            subs = _parse_human_count(subs_m.group(1)) if subs_m else 0
            bio = re.sub(r"<[^>]+>", " ", desc_m.group(1)).strip() if desc_m else ""

            # Split message blocks cleanly
            blocks = html.split('class="tgme_widget_message_wrap')
            posts: list[dict[str, Any]] = []
            uzt = timezone(timedelta(hours=5))
            hours_uzt: list[int] = []
            photo_cnt = 0
            video_cnt = 0
            album_cnt = 0
            price_upfront_cnt = 0

            for blk in blocks[1:]:
                txt_m = re.search(r'class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', blk, flags=re.S)
                raw_txt = txt_m.group(1) if txt_m else ""
                clean_txt = re.sub(r"<br\s*/?>", "\n", raw_txt)
                clean_txt = re.sub(r"<[^>]+>", "", clean_txt).strip()
                views_m = re.search(r'class="tgme_widget_message_views">([^<]+)</span>', blk)
                dt_m = re.search(r'<time[^>]+datetime="([^"]+)"', blk)
                has_photo = "tgme_widget_message_photo_wrap" in blk
                has_video = "tgme_widget_message_video_player" in blk or "tgme_widget_message_video" in blk
                is_album = blk.count("tgme_widget_message_photo_wrap") > 1

                if has_photo:
                    photo_cnt += 1
                if has_video:
                    video_cnt += 1
                if is_album:
                    album_cnt += 1

                views_num = _parse_human_count(views_m.group(1)) if views_m else 0
                dt_str = dt_m.group(1) if dt_m else ""
                if dt_str:
                    try:
                        dt_obj = datetime.fromisoformat(dt_str.replace("Z", "+00:00")).astimezone(uzt)
                        hours_uzt.append(dt_obj.hour)
                    except Exception:
                        pass

                if re.search(r"(?:so'm|sum|сўм|uzs|\$|¥|\d{3}\s*000|\d{2,3}\s*ming)", clean_txt, flags=re.I):
                    price_upfront_cnt += 1

                posts.append({
                    "text": clean_txt[:450],
                    "views": views_num,
                    "datetime": dt_str,
                    "has_photo": has_photo,
                    "has_video": has_video,
                    "is_album": is_album,
                })

            recent = posts[-limit:]
            n = max(1, len(recent))
            avg_views = int(sum(p["views"] for p in recent) / n)
            avg_len = int(sum(len(p["text"]) for p in recent) / n)
            peak_hours = sorted(set(hours_uzt))[:5]

            dominant_format = "video_reels" if video_cnt > photo_cnt else ("photo_album" if album_cnt >= n * 0.35 else "single_photo_card")
            pricing_style = "narx_ochiq_postda" if price_upfront_cnt >= n * 0.4 else "narx_direct_yoki_botda"

            return {
                "ok": True,
                "handle": clean,
                "title": title,
                "subscribers": subs,
                "bio": bio[:280],
                "posts_scanned": len(recent),
                "avg_views": avg_views,
                "avg_text_chars": avg_len,
                "dominant_format": dominant_format,
                "pricing_style": pricing_style,
                "peak_hours_uzt": peak_hours,
                "sample_posts": recent[-6:],
            }
    except Exception as exc:
        return {"ok": False, "handle": clean, "error": str(exc)[:160]}


async def ingest_and_learn_source(
    db: Any,
    settings: Any,
    raw_url_or_handle: str,
    user_instruction: str = "",
) -> dict[str, Any]:
    """Foydalanuvchi bergan har qanday Telegram/Instagram/Reel manbasini o'qib, tizim playbook'ini erkin yangilaydi."""
    platform, source_key, clean_url = parse_source_url(raw_url_or_handle)
    if not source_key:
        return {"ok": False, "error": "Noto'g'ri havola yoki kanal nomi"}

    scraped: dict[str, Any] = {}
    status = "active"
    style_summary = user_instruction.strip()
    posting_pattern = ""
    pricing_pattern = ""

    if platform == "telegram":
        scraped = await scrape_public_telegram_channel(source_key)
        if scraped.get("ok"):
            posting_pattern = f"Soatlar (Toshkent): {scraped.get('peak_hours_uzt')} | O'rtacha ko'rish: {scraped.get('avg_views', 0):,}"
            pricing_pattern = f"{scraped.get('pricing_style')} | Matn uzunligi: ~{scraped.get('avg_text_chars', 0)} belgi"
            style_summary = (
                f"{scraped.get('title')} ({scraped.get('subscribers', 0):,} obunachi) · "
                f"Asosiy format: {scraped.get('dominant_format')} · {user_instruction}"
            ).strip(" ·")
        else:
            status = "pending_userbot"
            style_summary = style_summary or str(scraped.get("error", "Ochiq web preview yo'q"))

    elif platform in ("instagram", "ig_reel"):
        handle = source_key.replace("ig:", "")
        if platform == "instagram" and getattr(settings, "ig_user_id", "") and getattr(settings, "ig_access_token", ""):
            from app.ig_analytics import fetch_competitor_business_discovery
            bd = await fetch_competitor_business_discovery(settings.ig_user_id, settings.ig_access_token, handles=[handle])
            if bd.get("ok"):
                scraped = bd
                info = (bd.get("competitors") or {}).get(f"@{handle}", {})
                style_summary = f"@{handle} ({info.get('followers', 0):,} obunachi) | O'rtacha {info.get('avg_likes', 0)} layk"
                posting_pattern = " | ".join(info.get("top_hooks") or [])[:180]
            else:
                status = "queued_for_ig_unlock"
                style_summary = style_summary or f"IG navbatda ({bd.get('permission_error', 'IG qulfdan chiqqach tahlil qilinadi')[:90]})"
        else:
            status = "queued_for_video_or_ig"
            style_summary = style_summary or "Reel/IG manba navbatga saqlandi (video fayl yuborilsa darhol chuqur tahlil qilinadi)"

    # AI bilan ochiq playbook sintez qilish (agar Gemini/OmniRoute yoqilgan bo'lsa)
    learned_patch: dict[str, Any] = {}
    if scraped.get("ok") or user_instruction:
        try:
            from app.ai import SalesAI
            ai = SalesAI(settings)
            if ai.enabled:
                prompt = (
                    "Sen XAN SHOP ning ochiq, o'zi rivojlanuvchi Instagram + Telegram strategisan. "
                    "Quyidagi REAL manba va foydalanuvchi ko'rsatmasidan qotib qolmagan, erkin va yuqori konversiyali strategiya chiqar.\n"
                    f"Manba: {clean_url} ({platform})\n"
                    f"Izoh: {user_instruction}\n"
                    f"Olingan ma'lumotlar: {json.dumps(scraped, ensure_ascii=False)[:2400]}\n\n"
                    "Faqat JSON qaytar:\n"
                    "{\n"
                    '  "tg_channel_strategy": {"post_tone": "...", "format": "...", "best_hours": "...", "trust_building": "..."},\n'
                    '  "ig_reels_strategy": {"hook_style": "...", "caption_cta": "...", "music_mood": "..."},\n'
                    '  "video_editing_blueprint": {"pacing": "...", "visual_mix": "...", "audio_rule": "..."},\n'
                    '  "sourcing_openness_rules": {"variety_rule": "...", "price_positioning": "..."}\n'
                    "}"
                )
                ai_res = await ai.ask_json(prompt, timeout_sec=14.0)
                if isinstance(ai_res, dict) and ai_res:
                    learned_patch = ai_res
        except Exception as exc:
            logger.debug("AI playbook synthesis fallback: %s", exc)

    if not learned_patch and scraped.get("ok") and platform == "telegram":
        learned_patch = {
            "tg_channel_strategy": {
                "format": scraped.get("dominant_format", "photo_album"),
                "pricing_style": scraped.get("pricing_style", "narx_ochiq_postda"),
                "best_hours": str(scraped.get("peak_hours_uzt") or [13, 19, 21]),
                "target_text_chars": str(scraped.get("avg_text_chars", 220)),
                "sample_hook": (scraped.get("sample_posts") or [{}])[-1].get("text", "")[:120],
            }
        }

    if db is not None:
        await db.upsert_tracked_source(
            source_key=source_key,
            platform=platform,
            url=clean_url,
            added_by="owner",
            status=status,
            style_summary=style_summary[:260],
            posting_pattern=posting_pattern[:220],
            pricing_pattern=pricing_pattern[:220],
            extracted_playbook=learned_patch or scraped,
        )
        existing_pb = await db.get_all_playbooks()
        for pb_key, pb_val in learned_patch.items():
            if isinstance(pb_val, dict):
                merged = {**(existing_pb.get(pb_key) or {}), **pb_val, "last_source": clean_url}
                await db.save_learned_playbook(pb_key, merged, source_refs=[clean_url])

    return {
        "ok": True,
        "platform": platform,
        "source_key": source_key,
        "url": clean_url,
        "status": status,
        "style_summary": style_summary,
        "posting_pattern": posting_pattern,
        "pricing_pattern": pricing_pattern,
        "scraped": scraped,
        "learned_patch": learned_patch,
    }


def format_playbooks_for_ai(playbooks: dict[str, dict[str, Any]]) -> str:
    """SQLite dagi o'rganilgan ochiq strategiyalarni Skaut va Video Montajchi promptiga uzatadi."""
    if not playbooks:
        return ""
    lines = ["TIZIM O'ZLASHTIRGAN OCHIQ STRATEGIYALAR (kanallar va videolardan):"]
    for k, v in playbooks.items():
        if isinstance(v, dict) and v:
            lines.append(f"- {k}: {json.dumps(v, ensure_ascii=False)[:320]}")
    return "\n".join(lines)


async def analyze_video_file_blueprint(
    db: Any,
    settings: Any,
    video_path: str,
    source_label: str = "owner_ref_video",
    caption_hint: str = "",
) -> dict[str, Any]:
    """Yuborilgan/yuklangan .mp4 videodan 4 ta asosiy kadr (storyboard) va audio/texnik ko'rsatkichlarni olib,
    Gemini Vision orqali to'liq montaj, hook, zvuk va stil strategiyasini tizimga integratsiya qiladi."""
    import io
    import os
    import subprocess
    import tempfile
    from PIL import Image
    from app.media import find_ffmpeg_binary

    if not video_path or not os.path.isfile(video_path):
        return {"ok": False, "error": "Video fayl topilmadi"}

    ff = find_ffmpeg_binary()
    dur_sec = 0.0
    video_res = "noma'lum"
    has_audio = False
    grid_bytes: bytes | None = None

    if ff:
        try:
            probe = subprocess.run([ff, "-i", video_path], capture_output=True, text=True, timeout=15)
            info = probe.stderr or ""
            m_dur = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", info)
            if m_dur:
                dur_sec = int(m_dur.group(1)) * 3600 + int(m_dur.group(2)) * 60 + float(m_dur.group(3))
            m_res = re.search(r"Video:.*?(\d{3,4}x\d{3,4})", info)
            if m_res:
                video_res = m_res.group(1)
            has_audio = "Audio:" in info

            with tempfile.TemporaryDirectory() as td:
                pcts = [0.08, 0.35, 0.65, 0.90]
                frames: list[Image.Image] = []
                for idx, p in enumerate(pcts):
                    ts = max(0.05, round(dur_sec * p, 2)) if dur_sec > 0.4 else (idx * 0.5)
                    out_jpg = os.path.join(td, f"fr_{idx}.jpg")
                    subprocess.run(
                        [ff, "-y", "-ss", str(ts), "-i", video_path, "-vframes", "1", "-q:v", "3", out_jpg],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=15,
                    )
                    if os.path.isfile(out_jpg) and os.path.getsize(out_jpg) > 500:
                        frames.append(Image.open(out_jpg).convert("RGB"))
                if frames:
                    cell_w, cell_h = 360, 640
                    grid = Image.new("RGB", (cell_w * 2, cell_h * 2), (18, 18, 22))
                    for i, im in enumerate(frames[:4]):
                        im.thumbnail((cell_w, cell_h), Image.Resampling.LANCZOS)
                        gx = (i % 2) * cell_w + (cell_w - im.width) // 2
                        gy = (i // 2) * cell_h + (cell_h - im.height) // 2
                        grid.paste(im, (gx, gy))
                    buf = io.BytesIO()
                    grid.save(buf, format="JPEG", quality=88)
                    grid_bytes = buf.getvalue()
        except Exception as exc:
            logger.warning("Video frame extraction warning: %s", exc)

    blueprint: dict[str, Any] = {
        "duration_sec": round(dur_sec, 1),
        "resolution": video_res,
        "has_audio": has_audio,
        "video_meaning": caption_hint[:180] or "Foydalanuvchi yuborgan namuna Reels videosi",
        "editing_blueprint": {
            "pacing": "Tez va dinamik kesimlar" if 0 < dur_sec <= 9 else "Hikoyaviy editorial ritm",
            "visual_mix": "Storyboard 4 kadr tahlili asosida kiyim fakturasi va to'liq obraz almashuvi",
            "recommended_audio_vibe": "diplomat_old_money" if "old money" in caption_hint.lower() else "luxury_chill",
        },
        "tg_ig_openness_lesson": "Jonli, samimiy taqdimot va qiyosiy narx/foyda bilan mijoz ishonchini qozonish",
    }

    try:
        from app.ai import SalesAI
        ai = SalesAI(settings)
        if (ai.enabled or getattr(settings, "gemini_api_key", "")) and grid_bytes:
            prompt = (
                "Sen XAN SHOP video montaj direktori va Telegram/Instagram strategisan. "
                "Ushbu 4 ta ketma-ket video kadrini (chap-tepa -> o'ng-tepa -> chap-past -> o'ng-past) diqqat bilan tahlil qil!\n"
                f"Texnik ko'rsatkichlar: davomiyligi={dur_sec:.1f}s, o'lchami={video_res}, audio={'bor' if has_audio else 'yoq'}.\n"
                f"Foydalanuvchi izohi: {caption_hint}\n\n"
                "Vazifang: bu video nega odamlarni ushlab qolyapti, kadrlar/matn/rang/temp qanday tuzilgan, "
                "bizning `video_employee` va Telegram/Instagram kanalimiz aynan shunday ochiq/samarali uslubga o'tishi uchun nima qilishi kerak?\n"
                "FAQAT JSON QAYTAR:\n"
                "{\n"
                '  "video_meaning": "...",\n'
                '  "editing_blueprint": {\n'
                '    "hook_first_1_5s": "...",\n'
                '    "pacing": "...",\n'
                '    "text_overlay_style": "...",\n'
                '    "color_and_lighting": "...",\n'
                '    "recommended_audio_vibe": "diplomat_old_money | phonk_bass | luxury_chill | lofi_editorial | uk_drill_beat"\n'
                '  },\n'
                '  "ig_reels_strategy": {"hook_style": "...", "caption_cta": "..."},\n'
                '  "tg_channel_strategy": {"post_tone": "...", "format": "...", "trust_building": "..."},\n'
                '  "tg_ig_openness_lesson": "..."\n'
                "}"
            )
            parsed = await ai.ask_json(prompt, media_bytes=grid_bytes, mime_type="image/jpeg", timeout_sec=22.0)
            if isinstance(parsed, dict) and parsed:
                blueprint.update(parsed)
    except Exception as exc:
        logger.warning("Gemini video vision fallback: %s", exc)

    if db is not None:
        key = f"video:{re.sub(r'[^a-zA-Z0-9_-]', '', source_label)[:36]}_{int(time.time())}"
        await db.upsert_tracked_source(
            source_key=key,
            platform="video_ref",
            url=source_label,
            added_by="owner",
            status="analyzed",
            style_summary=str(blueprint.get("video_meaning", ""))[:240],
            posting_pattern=f"{dur_sec:.1f}s · {video_res}",
            extracted_playbook=blueprint,
        )
        existing_pb = await db.get_all_playbooks()
        for pb_key in ("editing_blueprint", "ig_reels_strategy", "tg_channel_strategy"):
            val = blueprint.get(pb_key)
            if isinstance(val, dict) and val:
                target_key = "video_editing_blueprint" if pb_key == "editing_blueprint" else pb_key
                merged = {**(existing_pb.get(target_key) or {}), **val, "last_video_ref": source_label}
                await db.save_learned_playbook(target_key, merged, source_refs=[source_label])

    return {
        "ok": True,
        "frames_extracted": bool(grid_bytes),
        "duration_sec": round(dur_sec, 1),
        "resolution": video_res,
        "has_audio": has_audio,
        "blueprint": blueprint,
    }
