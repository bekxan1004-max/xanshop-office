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
    """Instagram Reels nashrga tayyorligini tekshiradi (Instagram Web sessiyasi YOKI Meta Graph API)."""
    from .publisher import has_valid_ig_browser_session

    if has_valid_ig_browser_session():
        return (True, "")
    if not ig_token:
        return (False, "Instagram sessiyasi yoki Meta API ulanmagan")
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            if ig_user_id:
                resp = await client.get(
                    f"{GRAPH_API_BASE}/{ig_user_id}",
                    params={"fields": "id,username", "access_token": ig_token},
                )
                data = resp.json()
                if resp.status_code == 200 and data.get("id"):
                    return (True, "")
            # Facebook Page orqali yangi ulangan IG Business hisobini avtomatik tekshiramiz
            r_acc = await client.get(
                f"{GRAPH_API_BASE}/me/accounts",
                params={"fields": "id,name,instagram_business_account{id,username}", "access_token": ig_token},
            )
            if r_acc.status_code == 200:
                for pg in (r_acc.json().get("data") or []):
                    ig_biz = (pg.get("instagram_business_account") or {}) if isinstance(pg, dict) else {}
                    if ig_biz.get("id"):
                        return (True, "")
                return (False, "Instagram (@xans_styles) hali XAN SHOP Facebook sahifasiga ulanmagan")
            err = (r_acc.json().get("error") or {}).get("message", f"HTTP {r_acc.status_code}")
            return (False, err[:160])
    except Exception as exc:
        return (False, f"IG tekshiruv tarmoq xatosi: {str(exc)[:100]}")


async def resolve_linked_telegram_channel(ig_handle: str) -> str | None:
    """Instagram profil nomi (masalan _tima_shop yoki stylesh.uz) orqali uning haqiqiy o'zbekcha Telegram kanalini topadi."""
    h = (ig_handle or "").strip().lstrip("@").strip("/").lower()
    if not h:
        return None
    clean_h = re.sub(r"[^a-z0-9]+", "_", h).strip("_")
    root_h = re.sub(r"_(?:uz|shop|official|store|style)$", "", clean_h).strip("_")
    candidates: list[str] = []
    for c in (
        f"{clean_h}_uz",
        f"{root_h}_shop_uz",
        f"{root_h}_shop",
        f"{root_h}_uz",
        clean_h,
        root_h,
    ):
        if c and len(c) >= 3 and c not in candidates:
            candidates.append(c)

    uz_markers = ("so'm", "soʻm", "so‘m", "uzs", "🇺🇿", "dastavka", "dostavka", "yetkazib", "razmer", "oldindan", "cargo", "kargo", "buyurtma", "zakaz")
    try:
        async with httpx.AsyncClient(
            timeout=8,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"},
        ) as client:
            for cand in candidates:
                try:
                    resp = await client.get(f"https://t.me/s/{cand}")
                    if resp.status_code == 200 and "tgme_channel_info" in resp.text:
                        low = resp.text.lower()
                        if any(m in low for m in uz_markers):
                            return cand
                except Exception:
                    continue
    except Exception:
        pass
    return None


def _extract_posts_from_tg_html(html: str) -> list[dict[str, Any]]:
    """Telegram web preview HTML sahifasidan har bir postning matni, video linki, fotoalbom linklari va ko'rishlar sonini ajratadi."""
    blocks = html.split('class="tgme_widget_message_wrap')
    posts: list[dict[str, Any]] = []
    for blk in blocks[1:]:
        post_id_m = re.search(r'data-post="([^"]+)"', blk)
        txt_m = re.search(r'class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', blk, flags=re.S)
        raw_txt = txt_m.group(1) if txt_m else ""
        clean_txt = re.sub(r"<br\s*/?>", "\n", raw_txt)
        clean_txt = re.sub(r"<[^>]+>", "", clean_txt)
        clean_txt = clean_txt.replace("&#33;", "!").replace("&quot;", '"').replace("&amp;", "&").strip()

        views_m = re.search(r'class="tgme_widget_message_views">([^<]+)</span>', blk)
        dt_m = re.search(r'<time[^>]+datetime="([^"]+)"', blk)
        vid_urls = re.findall(r'<video[^>]+src="([^"]+)"', blk)
        photo_urls = re.findall(r"background-image:url\('(https://cdn[^']+)'\)", blk)

        has_photo = bool(photo_urls) or ("tgme_widget_message_photo_wrap" in blk)
        has_video = bool(vid_urls) or ("tgme_widget_message_video_player" in blk or "tgme_widget_message_video" in blk)
        is_album = len(photo_urls) > 1 or blk.count("tgme_widget_message_photo_wrap") > 1

        posts.append({
            "post_id": post_id_m.group(1) if post_id_m else "",
            "text": clean_txt[:500],
            "views": _parse_human_count(views_m.group(1)) if views_m else 0,
            "datetime": dt_m.group(1) if dt_m else "",
            "has_photo": has_photo,
            "has_video": has_video,
            "is_album": is_album,
            "video_url": vid_urls[0] if vid_urls else "",
            "photo_urls": photo_urls[:6],
        })
    return posts


async def scrape_public_telegram_channel(channel_handle: str, limit: int = 25) -> dict[str, Any]:
    """Ochiq Telegram kanalning (https://t.me/s/<handle>) postlari, videolari, fotoalbomlari, vaqtlari va uslubini chuqur tahlil qiladi."""
    clean = channel_handle.replace("tg:", "").lstrip("@").strip().lower()
    url = f"https://t.me/s/{clean}"
    try:
        async with httpx.AsyncClient(
            timeout=14,
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

            posts = _extract_posts_from_tg_html(html)
            if posts:
                first_pid = posts[0].get("post_id", "")
                m_num = re.search(r"/(\d+)$", first_pid)
                look_vids_now = [p for p in posts if p.get("video_url") and ("look" in p.get("text", "").lower() or "obraz" in p.get("text", "").lower())]
                if m_num and len(look_vids_now) < 2:
                    try:
                        prev_resp = await client.get(f"{url}?before={m_num.group(1)}")
                        if prev_resp.status_code == 200:
                            older_posts = _extract_posts_from_tg_html(prev_resp.text)
                            posts = older_posts + posts
                    except Exception:
                        pass

            uzt = timezone(timedelta(hours=5))
            hours_uzt: list[int] = []
            photo_cnt = sum(1 for p in posts if p["has_photo"])
            video_cnt = sum(1 for p in posts if p["has_video"])
            album_cnt = sum(1 for p in posts if p["is_album"])
            price_upfront_cnt = 0

            for p in posts:
                dt_str = p.get("datetime") or ""
                if dt_str:
                    try:
                        dt_obj = datetime.fromisoformat(dt_str.replace("Z", "+00:00")).astimezone(uzt)
                        hours_uzt.append(dt_obj.hour)
                    except Exception:
                        pass
                if re.search(r"(?:so'm|soʻm|so‘m|sum|сўм|uzs|\$|¥|\d{3}[\s.]*000|\d{2,3}\s*ming)", p.get("text", ""), flags=re.I):
                    price_upfront_cnt += 1

            recent = posts[-limit:]
            n = max(1, len(recent))
            avg_views = int(sum(p["views"] for p in recent) / n)
            avg_len = int(sum(len(p["text"]) for p in recent) / n)
            peak_hours = sorted(set(hours_uzt))[:5]

            dominant_format = "video_reels" if video_cnt > photo_cnt else ("photo_album" if album_cnt >= n * 0.35 else "single_photo_card")
            pricing_style = "narx_ochiq_postda" if price_upfront_cnt >= n * 0.4 else "narx_direct_yoki_botda"

            video_posts = [p for p in posts if p.get("video_url")]
            video_posts_sorted = sorted(
                video_posts,
                key=lambda x: (1 if ("look" in x.get("text", "").lower() or "obraz" in x.get("text", "").lower()) else 0, x.get("views", 0)),
                reverse=True,
            )
            album_posts = [p for p in posts if len(p.get("photo_urls") or []) >= 2]

            all_texts = "\n".join(p.get("text", "") for p in recent[-10:])
            if "-|" in all_texts:
                template_style = "stylesh_dash"
            elif re.search(r"^-\s*\d", all_texts, flags=re.M):
                template_style = "tima_minimal"
            else:
                template_style = "clean_minimal"

            # Raqobatchi postlaridagi haqiqiy narxlarni (narxlar nisbati uchun) ajratib olish
            found_prices: list[int] = []
            for p in posts:
                txt_p = p.get("text") or ""
                for m_pr in re.finditer(r"(\d{2,3})[.\s](\d{3})\s*(?:so'm|soʻm|so‘m|sum|ming)", txt_p, flags=re.I):
                    val = int(m_pr.group(1)) * 1000
                    if 80_000 <= val <= 3_500_000 and val != 13_000:
                        found_prices.append(val)
            avg_comp_price = int(sum(found_prices) / len(found_prices)) if found_prices else 650_000

            return {
                "ok": True,
                "handle": clean,
                "title": title,
                "subscribers": subs,
                "bio": bio[:280],
                "posts_scanned": len(posts),
                "video_posts_count": len(video_posts),
                "album_posts_count": len(album_posts),
                "avg_views": avg_views,
                "avg_text_chars": avg_len,
                "dominant_format": dominant_format,
                "pricing_style": pricing_style,
                "template_style": template_style,
                "competitor_prices_uzs": sorted(set(found_prices))[:10],
                "avg_competitor_price_uzs": avg_comp_price,
                "peak_hours_uzt": peak_hours,
                "sample_posts": recent[-6:],
                "top_video_posts": video_posts_sorted[:4],
                "top_album_posts": album_posts[-3:],
            }
    except Exception as exc:
        return {"ok": False, "handle": clean, "error": str(exc)[:160]}


async def _download_and_analyze_channel_media(
    db: Any,
    settings: Any,
    scraped: dict[str, Any],
    max_videos: int = 2,
) -> list[dict[str, Any]]:
    """Kanal ichidagi haqiqiy videolarni (.mp4/.mov) yuklab olib, har birining kadr va audiosini birma-bir tahlil qiladi hamda viral zvukni saqlaydi."""
    import os
    import subprocess
    import tempfile
    from pathlib import Path
    from app.media import find_ffmpeg_binary

    top_videos = scraped.get("top_video_posts") or []
    results: list[dict[str, Any]] = []
    if not top_videos:
        return results

    ff = find_ffmpeg_binary()
    audio_dir = Path("data/audio")
    audio_dir.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(timeout=22, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as client:
        for vp in top_videos[:max_videos]:
            vurl = vp.get("video_url") or ""
            pid = vp.get("post_id") or "channel_video"
            safe_pid = re.sub(r"[^a-zA-Z0-9_]", "_", pid)
            if not vurl:
                continue
            try:
                resp = await client.get(vurl)
                if resp.status_code != 200 or len(resp.content) < 10_000:
                    continue
                with tempfile.TemporaryDirectory() as td:
                    local_v = os.path.join(td, f"{safe_pid}.mp4")
                    with open(local_v, "wb") as f:
                        f.write(resp.content)
                    v_res = await analyze_video_file_blueprint(
                        db=None,
                        settings=settings,
                        video_path=local_v,
                        source_label=pid,
                        caption_hint=vp.get("text", ""),
                    )
                    # Agar videoda musiqa/audio bo'lsa, haqiqiy viral zvuk sifatida data/audio/ ga saqlab boramiz
                    saved_viral_audio = ""
                    if ff and v_res.get("has_audio") and float(v_res.get("duration_sec") or 0) >= 5.0:
                        viral_wav = audio_dir / f"viral_{safe_pid.lower()}.wav"
                        if not viral_wav.exists():
                            subprocess.run(
                                [ff, "-y", "-i", local_v, "-vn", "-ac", "2", "-ar", "44100", "-c:a", "pcm_s16le", str(viral_wav)],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                timeout=18,
                            )
                        if viral_wav.exists() and viral_wav.stat().st_size > 20_000:
                            saved_viral_audio = viral_wav.name

                    if v_res.get("ok"):
                        bp = v_res.get("blueprint") or {}
                        ed = bp.get("editing_blueprint") or {}
                        results.append({
                            "post_id": pid,
                            "views": vp.get("views", 0),
                            "duration_sec": v_res.get("duration_sec", 0.0),
                            "resolution": v_res.get("resolution", ""),
                            "caption": (vp.get("text") or "")[:220],
                            "video_meaning": str(bp.get("video_meaning") or "")[:240],
                            "scene_by_scene": str(bp.get("scene_by_scene") or "0-4s Flat-Lay ('RASMDA:' / 'TRENDA YURGAN LOOKGA OBZOR') -> 4-5s Beat-drop o'tish -> 5-11s Jonli kiyilgan ko'rinish / yaqin plan mato va zamok isboti")[:280],
                            "audio_style": str(bp.get("audio_style_and_music") or ed.get("recommended_audio_vibe") or "Slowed vocal beat-drop yoki ASMR mato/zamok ovozi (TTS ovozsiz)")[:200],
                            "hook_first_1_5s": str(ed.get("hook_first_1_5s") or "To'q kulrang fonda barcha kiyimlar flat-lay jamlanmasi yoki makro furnitura/zamok kadri")[:200],
                            "harvested_audio_file": saved_viral_audio,
                        })
            except Exception as exc:
                logger.debug("Channel video download/analyze skip (%s): %s", pid, exc)
    return results


async def ingest_and_learn_source(
    db: Any,
    settings: Any,
    raw_url_or_handle: str,
    user_instruction: str = "",
) -> dict[str, Any]:
    """Foydalanuvchi bergan har qanday Telegram/Instagram/Reel manbasini va uning ichidagi videolarni birma-bir o'qib, SMM/Video agentlarni o'qitadi."""
    import os

    platform, source_key, clean_url = parse_source_url(raw_url_or_handle)
    if not source_key:
        return {"ok": False, "error": "Noto'g'ri havola yoki kanal nomi"}

    scraped: dict[str, Any] = {}
    analyzed_videos: list[dict[str, Any]] = []
    status = "active"
    style_summary = user_instruction.strip()
    posting_pattern = ""
    pricing_pattern = ""

    if platform == "telegram":
        scraped = await scrape_public_telegram_channel(source_key)
        if scraped.get("ok"):
            if not os.getenv("PYTEST_CURRENT_TEST"):
                analyzed_videos = await _download_and_analyze_channel_media(db, settings, scraped, max_videos=2)
            posting_pattern = (
                f"Soatlar (Toshkent): {scraped.get('peak_hours_uzt')} | O'rtacha ko'rish: {scraped.get('avg_views', 0):,} | "
                f"Videolar: {scraped.get('video_posts_count', 0)}, Albomlar: {scraped.get('album_posts_count', 0)}"
            )
            pricing_pattern = (
                f"{scraped.get('pricing_style')} · Shablon: {scraped.get('template_style', 'clean_minimal')} · "
                f"Matn: ~{scraped.get('avg_text_chars', 0)} belgi"
            )
            style_summary = (
                f"{scraped.get('title')} ({scraped.get('subscribers', 0):,} obunachi) · "
                f"Format: {scraped.get('dominant_format')} ({scraped.get('template_style', 'minimal')}) · "
                f"Tahlil qilingan videolar: {len(analyzed_videos)} ta"
            ).strip(" ·")
        else:
            status = "pending_userbot"
            style_summary = style_summary or str(scraped.get("error", "Ochiq web preview yo'q"))

    elif platform in ("instagram", "ig_reel"):
        from app.agent_reach_client import exa_web_search
        handle = source_key.replace("ig:", "").replace("reel:", "")
        if platform == "instagram" and getattr(settings, "ig_user_id", "") and getattr(settings, "ig_access_token", ""):
            from app.ig_analytics import fetch_competitor_business_discovery
            bd = await fetch_competitor_business_discovery(settings.ig_user_id, settings.ig_access_token, handles=[handle])
            if bd.get("ok"):
                scraped = bd
                info = (bd.get("competitors") or {}).get(f"@{handle}", {})
                style_summary = f"@{handle} ({info.get('followers', 0):,} obunachi) | O'rtacha {info.get('avg_likes', 0)} layk"
                posting_pattern = " | ".join(info.get("top_hooks") or [])[:180]

        # Agar IG Graph API yopiq bo'lsa, profilning haqiqiy o'zbekcha Telegram ko'zgusini (masalan _tima_shop -> tima_shop_uz, stylesh.uz -> stylesh_shop) topib, ichidagi real video va postlarni tahlil qilamiz!
        if not scraped.get("ok") and platform == "instagram":
            linked_tg = await resolve_linked_telegram_channel(handle)
            if linked_tg:
                tg_scraped = await scrape_public_telegram_channel(linked_tg)
                if tg_scraped.get("ok"):
                    scraped = {**tg_scraped, "linked_telegram_channel": f"https://t.me/{linked_tg}"}
                    if not os.getenv("PYTEST_CURRENT_TEST"):
                        analyzed_videos = await _download_and_analyze_channel_media(db, settings, tg_scraped, max_videos=2)
                    posting_pattern = (
                        f"Bog'langan TG (@{linked_tg}) · Soatlar: {tg_scraped.get('peak_hours_uzt')} · "
                        f"O'rtacha ko'rish: {tg_scraped.get('avg_views', 0):,} · Videolar: {tg_scraped.get('video_posts_count', 0)}"
                    )
                    pricing_pattern = (
                        f"{tg_scraped.get('pricing_style')} · Shablon: {tg_scraped.get('template_style', 'tima_minimal')} · "
                        f"Matn: ~{tg_scraped.get('avg_text_chars', 0)} belgi"
                    )
                    style_summary = (
                        f"@{handle} ↔ @{linked_tg} ({tg_scraped.get('subscribers', 0):,} obunachi) · "
                        f"Format: {tg_scraped.get('dominant_format')} · {len(analyzed_videos)} ta real video kadr+audio tahlil qilindi"
                    )

        if not scraped.get("ok"):
            exa_hits = await exa_web_search(f'"{handle}" instagram fashion menswear', num_results=3)
            if exa_hits:
                scraped = {"ok": True, "source": "agent_reach_exa", "hits": exa_hits}
                style_summary = style_summary or f"Agent-Reach Web qidiruvi: {exa_hits[0].get('title', '')[:120]}"
            else:
                status = "queued_for_video_or_ig"
                style_summary = style_summary or "Reel/IG manba navbatga saqlandi"
    elif platform in ("youtube", "web"):
        from app.agent_reach_client import jina_read_url, youtube_search_videos
        jina_res = await jina_read_url(clean_url, max_chars=3200)
        if jina_res.get("ok"):
            scraped = {"ok": True, "source": "agent_reach_jina", "markdown_excerpt": jina_res["text"][:1800]}
            first_line = next((l.strip("# ").strip() for l in jina_res["text"].splitlines() if l.strip()), clean_url)
            style_summary = style_summary or f"Agent-Reach (Jina): {first_line[:130]}"
        elif platform == "youtube":
            yt_res = await youtube_search_videos(clean_url, limit=3)
            if yt_res:
                scraped = {"ok": True, "source": "agent_reach_yt", "videos": yt_res}
                style_summary = style_summary or f"YouTube: {yt_res[0].get('title', '')[:130]}"

    scraped_for_ai = {
        k: v
        for k, v in scraped.items()
        if k not in ("top_video_posts", "top_album_posts")
    }
    if analyzed_videos:
        scraped_for_ai["analyzed_videos"] = analyzed_videos

    template_style = str(scraped.get("template_style") or ("tima_minimal" if "tima" in source_key else "stylesh_dash"))
    sample_post_txt = ""
    if scraped.get("sample_posts"):
        sample_post_txt = str((scraped.get("sample_posts") or [{}])[-1].get("text") or "")[:320]

    learned_patch: dict[str, Any] = {}
    if scraped.get("ok") or user_instruction:
        try:
            from app.ai import SalesAI
            ai = SalesAI(settings)
            if ai.enabled:
                prompt = (
                    "Sen XAN SHOP ning Bosh SMM Analizeri va Video Rejissorisan. "
                    "Faqat erkaklar kiyimi (palto, kurtka, xudi, sviter, klassik va kundalik shim, oyoq kiyim kapsulalari) do'koni uchun "
                    "ushbu real kanal postlari va yuklab tahlil qilingan videolaridan aniq, amaliy qoidalar chiqar.\n"
                    f"Manba: {clean_url} ({platform})\n"
                    f"Foydalanuvchi talabi: {user_instruction}\n"
                    f"Kanal va videolar tahlili: {json.dumps(scraped_for_ai, ensure_ascii=False)[:3000]}\n\n"
                    "Faqat JSON qaytar:\n"
                    "{\n"
                    '  "tg_channel_strategy": {\n'
                    '    "post_tone": "...",\n'
                    '    "format": "photo_album_and_flatlay_video | photo_album | video_reels",\n'
                    f'    "template_style": "{template_style}",\n'
                    '    "best_hours": "...",\n'
                    '    "trust_building": "..."\n'
                    '  },\n'
                    '  "ig_reels_strategy": {"hook_style": "...", "caption_cta": "...", "music_mood": "..."},\n'
                    '  "video_editing_blueprint": {\n'
                    '    "video_style": "tima_flatlay_obzor",\n'
                    '    "hook_header_text": "TRENDDAGI LOOKGA OBZOR",\n'
                    '    "pacing": "...",\n'
                    '    "visual_mix": "...",\n'
                    '    "audio_rule": "..."\n'
                    '  },\n'
                    '  "sourcing_openness_rules": {"variety_rule": "...", "price_positioning": "..."}\n'
                    "}"
                )
                ai_res = await ai.ask_json(prompt, timeout_sec=22.0)
                if isinstance(ai_res, dict) and ai_res:
                    learned_patch = ai_res
        except Exception as exc:
            logger.debug("AI playbook synthesis fallback: %s", exc)

    if not learned_patch and scraped.get("ok"):
        learned_patch = {
            "tg_channel_strategy": {
                "post_tone": "Qisqa, chiziqli-punktli, ortiqcha matnsiz aniq narx va shartlar",
                "format": "photo_album_and_flatlay_video" if analyzed_videos else scraped.get("dominant_format", "photo_album"),
                "template_style": template_style,
                "pricing_style": scraped.get("pricing_style", "narx_ochiq_postda"),
                "best_hours": str(scraped.get("peak_hours_uzt") or [15, 17, 18, 20]),
                "sample_post_structure": sample_post_txt,
                "trust_building": "50% oldindan to'lov + alohida kargo + real flat-lay va mato/zamok yaqin plan videolari",
            },
            "ig_reels_strategy": {
                "hook_style": "0-4s to'q kulrang (#26262A) fonda 'RASMDA:' yoki 'TRENDDAGI LOOKGA OBZOR' sarlavhasi ostida barcha kiyimlar flat-lay kolaji",
                "caption_cta": "Qisqa chiziqli narx + 50% oldindan to'lov + Direct/Komment '+' voronkasi",
                "music_mood": "Slowed vokal/rep beat-drop (4-sekundda o'tish) yoki ASMR mato ovozi (robot ovozsiz)",
            },
            "video_editing_blueprint": {
                "video_style": "tima_flatlay_obzor",
                "hook_header_text": "TRENDDAGI LOOKGA OBZOR",
                "pacing": "0-3.5s: Barcha qismlar Flat-Lay Obzor ('RASMDA:') -> 3.5-8s: Beat-drop bilan har bir buyum yaqin plani -> Yakun: 2x2 Grid + 50% Narx",
                "visual_mix": "To'q mat kulrang (#26262A) fonda toza kesilgan kiyimlar flat-lay kolaji + kadr almashuvi",
                "audio_rule": "Beat-drop sinxron musiqa yoki ASMR mato/zamok ovozi, sun'iy TTS diktorsiz",
            },
            "sourcing_openness_rules": {
                "variety_rule": "M–3XL razmerdagi 2–5 qismli erkaklar looklari (palto, kurtka, xudi, shim, oyoq kiyim)",
                "price_positioning": "Yaxlit narxlar (299.000, 499.000, 600.000, 850.000 so'm) + 50% oldindan to'lov va kargo alohida",
            },
        }
    else:
        # Har doim aniq template_style, sample_post_structure va analyzed_videos saqlanishini kafolatlaymiz
        tg_st = learned_patch.setdefault("tg_channel_strategy", {})
        if isinstance(tg_st, dict):
            tg_st.setdefault("template_style", template_style)
            if sample_post_txt:
                tg_st["sample_post_structure"] = sample_post_txt
        ve_bp = learned_patch.setdefault("video_editing_blueprint", {})
        if isinstance(ve_bp, dict):
            ve_bp.setdefault("video_style", "tima_flatlay_obzor")
            ve_bp.setdefault("hook_header_text", "TRENDDAGI LOOKGA OBZOR")
        if analyzed_videos:
            learned_patch["analyzed_videos"] = analyzed_videos

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
            extracted_playbook={**learned_patch, "analyzed_videos": analyzed_videos} if analyzed_videos else (learned_patch or scraped_for_ai),
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
        "scraped": scraped_for_ai,
        "analyzed_videos": analyzed_videos,
        "learned_patch": learned_patch,
    }


def format_playbooks_for_ai(playbooks: dict[str, dict[str, Any]]) -> str:
    """SQLite dagi o'rganilgan ochiq strategiyalarni Skaut, SMM Boshlig'i va Video Montajchi promptiga uzatadi."""
    if not playbooks:
        return ""
    lines = ["TIZIM O'ZLASHTIRGAN OCHIQ STRATEGIYALAR (kanallar va videolardan):"]
    for k, v in playbooks.items():
        if isinstance(v, dict) and v:
            lines.append(f"- {k}: {json.dumps(v, ensure_ascii=False)[:380]}")
    return "\n".join(lines)


async def analyze_video_file_blueprint(
    db: Any,
    settings: Any,
    video_path: str,
    source_label: str = "owner_ref_video",
    caption_hint: str = "",
) -> dict[str, Any]:
    """Chuqur multimodal video tahlilchi:
    1) Videodan 9 ta tiniq kadr (1620x2880 3x3 storyboard) chiqaradi;
    2) Haqiqiy audio/nutq trekini (.wav) ajratib oladi va Gemini Audio orqali to'liq transkript + vositalar + zvukni eshitadi;
    3) Kadrlar + Nutq matnini birlashtirib, chuqur montaj, animatsiya, hook va tizimga integratsiya rejasini chiqaradi."""
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
    wav_bytes: bytes | None = None

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
                frames: list[Image.Image] = []
                n_shots = 9
                for idx in range(n_shots):
                    ts = max(0.05, min(max(dur_sec - 0.1, 0.2), dur_sec * (idx + 0.5) / n_shots)) if dur_sec > 0.4 else (idx * 0.4)
                    out_jpg = os.path.join(td, f"fr_{idx}.jpg")
                    subprocess.run(
                        [ff, "-y", "-ss", f"{ts:.2f}", "-i", video_path, "-vframes", "1", "-q:v", "2", out_jpg],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=15,
                    )
                    if os.path.isfile(out_jpg) and os.path.getsize(out_jpg) > 500:
                        frames.append(Image.open(out_jpg).convert("RGB"))
                if frames:
                    cell_w, cell_h = 540, 960
                    cols = 3 if len(frames) >= 5 else 2
                    rows = (len(frames) + cols - 1) // cols
                    grid = Image.new("RGB", (cell_w * cols, cell_h * rows), (14, 15, 19))
                    for i, im in enumerate(frames[:9]):
                        im.thumbnail((cell_w, cell_h), Image.Resampling.LANCZOS)
                        gx = (i % cols) * cell_w + (cell_w - im.width) // 2
                        gy = (i // cols) * cell_h + (cell_h - im.height) // 2
                        grid.paste(im, (gx, gy))
                    buf = io.BytesIO()
                    grid.save(buf, format="JPEG", quality=90)
                    grid_bytes = buf.getvalue()

                if has_audio:
                    wav_path = os.path.join(td, "track.wav")
                    subprocess.run(
                        [ff, "-y", "-i", video_path, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", wav_path],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=20,
                    )
                    if os.path.isfile(wav_path) and os.path.getsize(wav_path) > 1000:
                        with open(wav_path, "rb") as wf:
                            wav_bytes = wf.read()
        except Exception as exc:
            logger.warning("Video frame/audio extraction warning: %s", exc)

    blueprint: dict[str, Any] = {
        "duration_sec": round(dur_sec, 1),
        "resolution": video_res,
        "has_audio": has_audio,
        "ai_deep_used": False,
        "speech_transcript": "",
        "spoken_tools_and_urls": [],
        "video_meaning": caption_hint[:240] or "Foydalanuvchi yuborgan namuna Reels videosi",
        "scene_by_scene": "",
        "editing_blueprint": {
            "pacing": "Tez va dinamik kesimlar" if 0 < dur_sec <= 12 else "Hikoyaviy tushuntirish + kadr almashuvi",
            "visual_mix": "9 ta kadr tahlili asosida kiyim/UI/subtitr almashuvi",
            "recommended_audio_vibe": "diplomat_old_money" if "old money" in caption_hint.lower() else "luxury_chill",
        },
        "tg_ig_openness_lesson": "Jonli, samimiy taqdimot va qiyosiy narx/foyda bilan mijoz ishonchini qozonish",
        "system_integration_action": "",
    }

    try:
        from app.ai import SalesAI
        ai = SalesAI(settings)
        if ai.enabled or getattr(settings, "gemini_api_key", ""):
            # 1-BOSQICH: Audio / Nutq / Musiqani so'zma-so'z tinglash
            speech_text = ""
            spoken_tools: list[str] = []
            audio_mood = ""
            if wav_bytes and len(wav_bytes) <= 8_000_000:
                audio_prompt = (
                    "Ushbu video audio trekini diqqat bilan tingla! O'zbekcha/ruscha/inglizcha gapirilgan barcha so'zlarni "
                    "to'liq eshitib yozib ol, tilga olingan dasturlar, GitHub/Telegram/sayt nomlari hamda fon musiqasi uslubini aniq ajrat.\n"
                    "FAQAT JSON QAYTAR:\n"
                    "{\n"
                    '  "speech_transcript": "So\'zma-so\'z yoki batafsil to\'liq matn",\n'
                    '  "spoken_tools_and_urls": ["vosita yoki havola nomi"],\n'
                    '  "audio_style_and_music": "ovoz tempi va fon musiqa janri"\n'
                    "}"
                )
                aud_res = await ai.ask_json(audio_prompt, media_bytes=wav_bytes, mime_type="audio/wav", timeout_sec=35.0)
                if isinstance(aud_res, dict):
                    speech_text = str(aud_res.get("speech_transcript") or "").strip()
                    spoken_tools = list(aud_res.get("spoken_tools_and_urls") or [])
                    audio_mood = str(aud_res.get("audio_style_and_music") or "").strip()

            # 2-BOSQICH: 9 ta tiniq kadr (3x3) + Nutq matnini birlashtirib chuqur arxitektura tahlili
            if grid_bytes:
                vis_prompt = (
                    "Sen XAN SHOP ning Bosh Video Rejissyori, SMM Strategi va AI Tizim Arxitektorisan. "
                    "Yuzaki umumiy gaplar yozma! Rasmdagi barcha 9 ta kadrni (1-satr: boshi, 2-satr: o'rtasi, 3-satr: oxiri) "
                    "va audio nutqini chuqur tahlil qil!\n"
                    f"Texnik: davomiyligi={dur_sec:.1f}s, o'lcham={video_res}.\n"
                    f"Audio nutq transkripti: {speech_text or '(ovoz matni ajratilmadi, rasmdagi yozuvlarga qara)'}\n"
                    f"Tilga olingan vositalar: {spoken_tools}\n"
                    f"Audio/musiqa holati: {audio_mood}\n"
                    f"Izoh: {caption_hint}\n\n"
                    "Ekran yozuvlari, terminal buyruqlari, GitHub/sayt nomlari, subtitr dizayni, animatsiya uslubi, hook va CTA gacha "
                    "hammasini aniq va amaliy tahlil qilib ber.\n"
                    "FAQAT JSON QAYTAR:\n"
                    "{\n"
                    '  "video_meaning": "Videoning asl g\'oyasi, kim uchun va nimani hal qilayotgani (batafsil)",\n'
                    '  "spoken_tools_and_urls": ["kadrda va audioda chiqqan aniq texnologiya/linklar"],\n'
                    '  "scene_by_scene": "0-3s hook -> o\'rta kadrlar -> oxirgi CTA qanday yasalgan",\n'
                    '  "editing_blueprint": {\n'
                    '    "hook_first_1_5s": "birinchi soniyada e\'tiborni qanday tortadi",\n'
                    '    "pacing": "kadr tezligi, animatsiya va sakrash tempi",\n'
                    '    "subtitle_typography": "shrift, tagiga chizish/highlight uslubi va joylashuvi",\n'
                    '    "color_and_lighting": "fon rangi (oq/bej/qora) va kontrast",\n'
                    '    "recommended_audio_vibe": "diplomat_old_money | phonk_bass | luxury_chill | lofi_editorial | uk_drill_beat"\n'
                    '  },\n'
                    '  "ig_reels_strategy": {"hook_style": "...", "caption_cta": "..."},\n'
                    '  "tg_channel_strategy": {"post_tone": "...", "format": "...", "trust_building": "..."},\n'
                    '  "tg_ig_openness_lesson": "Telegram va Instagramni rivojlantirish uchun aniq dars",\n'
                    '  "system_integration_action": "XAN SHOP kodiga/tizimiga aynan nima qo\'shilishi kerak"\n'
                    "}"
                )
                parsed = await ai.ask_json(vis_prompt, media_bytes=grid_bytes, mime_type="image/jpeg", timeout_sec=35.0)
                if isinstance(parsed, dict) and parsed:
                    blueprint.update(parsed)
                    blueprint["ai_deep_used"] = True
            if speech_text:
                blueprint["speech_transcript"] = speech_text
            if spoken_tools and not blueprint.get("spoken_tools_and_urls"):
                blueprint["spoken_tools_and_urls"] = spoken_tools
            if audio_mood:
                blueprint["audio_style_and_music"] = audio_mood
    except Exception as exc:
        logger.warning("Gemini deep video analysis fallback: %s", exc)

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
