from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from typing import Any
from urllib.parse import unquote

import httpx

logger = logging.getLogger("xanshop.ig_analytics")

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"

REQUIRED_ANALYST_PERMS = [
    "instagram_basic",
    "instagram_content_publish",
    "instagram_manage_insights",
    "instagram_manage_comments",
    "instagram_manage_messages",
]

SEED_COMPETITOR_ACCOUNTS = [
    {
        "handle": "_tima_shop",
        "region": "uzbekistan",
        "style_focus": "Streetwear & Old Money Kapsula (Toshkent)",
        "followers_est": 85000,
        "avg_likes": 420.0,
        "avg_views": 18500,
        "notes": {"trigger": "+ kommentda", "delivery": "10-15 kun", "markup": "yuqori"},
    },
    {
        "handle": "stylesh.uz",
        "region": "uzbekistan",
        "style_focus": "Editorial Split-Screen Cleanfit & Old Money",
        "followers_est": 64000,
        "avg_likes": 350.0,
        "avg_views": 14200,
        "notes": {"trigger": "narx / razmer kommentda", "hook": "bo'y va vazn bo'yicha"},
    },
    {
        "handle": "lookzona.uz",
        "region": "uzbekistan",
        "style_focus": "4-in-1 Tayyor Obraz & Qiyosiy Narx Reels",
        "followers_est": 52000,
        "avg_likes": 290.0,
        "avg_views": 12800,
        "notes": {"trigger": "+ kommentda", "hook": "butik vs Xitoy narxi"},
    },
    {
        "handle": "menstyle.uz",
        "region": "uzbekistan",
        "style_focus": "Qishki Klassik Palto, Vodolazka & Lofer",
        "followers_est": 41000,
        "avg_likes": 240.0,
        "avg_views": 9600,
        "notes": {"trigger": "Direct / Telegram"},
    },
    {
        "handle": "oldmoney.menswear",
        "region": "global",
        "style_focus": "Quiet Luxury, Double-Breasted Palto & Piano Reels",
        "followers_est": 420000,
        "avg_likes": 6200.0,
        "avg_views": 145000,
        "notes": {"music": "klassik piano/strings", "pacing": "sekin editorial zoom"},
    },
]

CURATED_MARKET_VIDEO_PATTERNS = [
    {
        "video_key": "seed_oldmoney_palto_uz",
        "account_handle": "stylesh.uz",
        "video_url": "https://www.instagram.com/stylesh.uz/reels/",
        "posted_at_info": "Kechqurun 19:30 (Kuz-Qish mavsum)",
        "garment_type": "Qishki ikki qatorli jun palto + kashmir vodolazka + drape shim",
        "video_meaning": "Diplomatiya/yuridika talabalari va ofis yigitlari uchun qimmat butik ko'rinishini arzonroq narxda berish",
        "editing_style": "persona_spotlight_deck",
        "video_quality": "1080p Studio, silliq kamera zoom va aniq narx kapsulasi",
        "music_genre": "Klassik Piano & Strings (Old Money Cinema)",
        "audio_vibe": "diplomat_old_money",
        "views_est": 24800,
        "likes_count": 690,
        "comments_count": 84,
        "competitor_sell_price_uzs": 1150000,
        "estimated_pdd_cost_uzs": 540000,
        "estimated_profit_uzs": 430000,
        "xan_target_price_uzs": 950000,
        "insight_summary": "Qishki palto + vodolazka + drape shim obrazlarida klassik piano musiqasi bilan qiziqish 2.4x yuqori; raqobatchi 1.15M so'mga sotmoqda.",
    },
    {
        "video_key": "seed_tima_kapsula_uz",
        "account_handle": "_tima_shop",
        "video_url": "https://www.instagram.com/_tima_shop/reels/",
        "posted_at_info": "Kechqurun 20:15 (Payshanba-Yakshanba)",
        "garment_type": "Qalin 420g oversize xudi + bomber kurtka + kargo shim + retro krossovka",
        "video_meaning": "Universitet yigitlari uchun tayyor ko'cha stili (kommentda '+' orqali tezkor zakaz)",
        "editing_style": "orbit_3d_turntable",
        "video_quality": "1080p Tez almashuvchi kadrlar, yorqin sarlavha",
        "music_genre": "Dark Drift Phonk Bass (Haqiqiy ritmik trek)",
        "audio_vibe": "phonk_bass",
        "views_est": 31200,
        "likes_count": 820,
        "comments_count": 142,
        "competitor_sell_price_uzs": 890000,
        "estimated_pdd_cost_uzs": 420000,
        "estimated_profit_uzs": 310000,
        "xan_target_price_uzs": 750000,
        "insight_summary": "Tez kadr almashuvi + drift phonk treki yosh auditoriyada koment '+' faolligini oshiradi; biz 50% oldindan va 5-10 kun avia bilan ustunmiz.",
    },
    {
        "video_key": "seed_lookzona_blazer_uz",
        "account_handle": "lookzona.uz",
        "video_url": "https://www.instagram.com/lookzona.uz/reels/",
        "posted_at_info": "Tushlik 13:00 va Kechqurun 19:00",
        "garment_type": "To'q ko'k klassik jun blazer + och bej zamokli sviter + klassik shim",
        "video_meaning": "IT va biznes yigitlari uchun ofis-smart kiyim (butik narxidan 40% arzon solishtirish)",
        "editing_style": "editorial_split_showcase",
        "video_quality": "1080p Split-Screen qiyoslash, toza bej/qora fon",
        "music_genre": "Luxury Deep House Lounge (Minimalist elektronika)",
        "audio_vibe": "luxury_chill",
        "views_est": 19400,
        "likes_count": 510,
        "comments_count": 63,
        "competitor_sell_price_uzs": 980000,
        "estimated_pdd_cost_uzs": 465000,
        "estimated_profit_uzs": 355000,
        "xan_target_price_uzs": 850000,
        "insight_summary": "Blazer + sviter qatlamli kuz-qish to'plamlari Deep House lounge fonida jiddiy mijozlarni tortadi; konversiya narx solishtirish hookida.",
    },
    {
        "video_key": "seed_menstyle_chelsea_uz",
        "account_handle": "menstyle.uz",
        "video_url": "https://www.instagram.com/menstyle.uz/reels/",
        "posted_at_info": "Kechqurun 20:45",
        "garment_type": "Qora charm Chelsea etik + taupe-jigarrang jun shim + kashmir vodolazka",
        "video_meaning": "Sovuq kunlar uchun issiq va qimmatbaho ko'rinadigan klassik obraz",
        "editing_style": "bento_zoom_reveal",
        "video_quality": "1080p Yaqin faktura va mato zoom kadrlari",
        "music_genre": "Warm Lofi Editorial Beat",
        "audio_vibe": "lofi_editorial",
        "views_est": 15900,
        "likes_count": 430,
        "comments_count": 49,
        "competitor_sell_price_uzs": 920000,
        "estimated_pdd_cost_uzs": 440000,
        "estimated_profit_uzs": 320000,
        "xan_target_price_uzs": 800000,
        "insight_summary": "Sovuq havoda futbolka o'rniga vodolazka + charm etik ko'rsatish mijozda 'pulingga arziydi' ishonchini beradi.",
    },
]

_IG_NON_ACCOUNTS = {
    "p", "reel", "reels", "explore", "accounts", "stories", "tv", "direct", "about", "legal", "developer",
}


async def audit_ig_token_permissions(token: str) -> dict[str, Any]:
    """Check which Meta Graph API permissions the active IG_ACCESS_TOKEN actually holds."""
    if not token:
        return {
            "ok": False,
            "granted": [],
            "missing": list(REQUIRED_ANALYST_PERMS),
            "has_insights": False,
            "has_comments_reply": False,
            "error": "IG_ACCESS_TOKEN kiritilmagan",
        }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{GRAPH_API_BASE}/me/permissions",
                params={"access_token": token},
            )
            data = resp.json()
            if resp.status_code != 200 or "error" in data:
                err_msg = (data.get("error") or {}).get("message", f"HTTP {resp.status_code}")
                return {
                    "ok": False,
                    "granted": [],
                    "missing": list(REQUIRED_ANALYST_PERMS),
                    "has_insights": False,
                    "has_comments_reply": False,
                    "error": err_msg,
                }
            granted = [
                row["permission"]
                for row in (data.get("data") or [])
                if row.get("status") == "granted"
            ]
            missing = [p for p in REQUIRED_ANALYST_PERMS if p not in granted]
            return {
                "ok": True,
                "granted": granted,
                "missing": missing,
                "has_insights": "instagram_manage_insights" in granted,
                "has_comments_reply": "instagram_manage_comments" in granted,
                "error": "",
            }
    except Exception as exc:
        return {
            "ok": False,
            "granted": [],
            "missing": list(REQUIRED_ANALYST_PERMS),
            "has_insights": False,
            "has_comments_reply": False,
            "error": str(exc)[:180],
        }


async def fetch_own_instagram_performance(
    ig_user_id: str,
    token: str,
    has_insights: bool = False,
    limit: int = 10,
) -> dict[str, Any]:
    """Fetch @xan_styles real IG media likes/comments (+ insights if permitted)."""
    if not ig_user_id or not token:
        return {"ok": False, "error": "IG_USER_ID yoki IG_ACCESS_TOKEN yo'q", "posts": []}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            prof_resp = await client.get(
                f"{GRAPH_API_BASE}/{ig_user_id}",
                params={
                    "fields": "username,followers_count,media_count",
                    "access_token": token,
                },
            )
            prof = prof_resp.json() if prof_resp.status_code == 200 else {}

            media_resp = await client.get(
                f"{GRAPH_API_BASE}/{ig_user_id}/media",
                params={
                    "fields": "id,caption,like_count,comments_count,media_product_type,permalink,timestamp",
                    "limit": limit,
                    "access_token": token,
                },
            )
            media_data = media_resp.json()
            if media_resp.status_code != 200 or "error" in media_data:
                err_msg = (media_data.get("error") or {}).get("message", f"HTTP {media_resp.status_code}")
                return {"ok": False, "error": err_msg, "posts": []}

            raw_posts = media_data.get("data") or []
            posts: list[dict[str, Any]] = []
            recent_comments: list[dict[str, Any]] = []
            insights_error = ""

            for idx, m in enumerate(raw_posts):
                mid = str(m.get("id") or "")
                likes = int(m.get("like_count") or 0)
                cmts = int(m.get("comments_count") or 0)
                caption = str(m.get("caption") or "")
                post_entry: dict[str, Any] = {
                    "id": mid,
                    "likes": likes,
                    "comments": cmts,
                    "score": likes + cmts * 3,
                    "type": m.get("media_product_type") or "",
                    "timestamp": m.get("timestamp") or "",
                    "permalink": m.get("permalink") or "",
                    "title_line": (caption.splitlines()[0] if caption else "")[:90],
                    "caption_snippet": caption[:240],
                    "reach": None,
                    "views": None,
                    "saved": None,
                }

                if mid and (cmts > 0 or idx < 3):
                    try:
                        c_resp = await client.get(
                            f"{GRAPH_API_BASE}/{mid}/comments",
                            params={
                                "fields": "id,text,timestamp,username",
                                "limit": 8,
                                "access_token": token,
                            },
                        )
                        if c_resp.status_code == 200:
                            for c in (c_resp.json().get("data") or []):
                                recent_comments.append({
                                    "media_id": mid,
                                    "comment_id": c.get("id"),
                                    "text": c.get("text", ""),
                                    "username": c.get("username", ""),
                                    "timestamp": c.get("timestamp", ""),
                                })
                    except Exception:
                        pass

                if mid and (has_insights or idx == 0):
                    try:
                        ins_resp = await client.get(
                            f"{GRAPH_API_BASE}/{mid}/insights",
                            params={
                                "metric": "reach,saved,shares,views",
                                "access_token": token,
                            },
                        )
                        ins_json = ins_resp.json()
                        if ins_resp.status_code == 200 and "data" in ins_json:
                            for metric in ins_json["data"]:
                                mname = metric.get("name")
                                vals = metric.get("values") or [{}]
                                val = vals[0].get("value")
                                if mname in ("reach", "views", "saved"):
                                    post_entry[mname] = val
                        elif "error" in ins_json and not insights_error:
                            insights_error = (ins_json["error"] or {}).get("message", "")
                    except Exception:
                        pass

                posts.append(post_entry)

            posts_sorted = sorted(posts, key=lambda x: x["score"], reverse=True)
            top_post = posts_sorted[0] if posts_sorted else None
            total_likes = sum(p["likes"] for p in posts)
            total_comments = sum(p["comments"] for p in posts)

            return {
                "ok": True,
                "username": prof.get("username", "xan_styles"),
                "followers_count": int(prof.get("followers_count") or 0),
                "media_count": int(prof.get("media_count") or len(posts)),
                "analyzed_posts": len(posts),
                "total_likes": total_likes,
                "total_comments": total_comments,
                "top_post": top_post,
                "posts": posts_sorted,
                "recent_comments": recent_comments,
                "insights_available": bool(has_insights and not insights_error),
                "insights_error": insights_error,
            }
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:180], "posts": []}


async def fetch_competitor_business_discovery(
    ig_user_id: str,
    token: str,
    handles: list[str] | None = None,
) -> dict[str, Any]:
    """Query Instagram Graph API business_discovery for Uzbek menswear competitors."""
    if not ig_user_id or not token:
        return {"ok": False, "error": "Token yo'q", "competitors": {}, "raw_media": []}

    targets = [h.lstrip("@").strip() for h in (handles or ["_tima_shop", "stylesh.uz", "lookzona.uz"]) if h.strip()]
    results: dict[str, Any] = {}
    raw_media: list[dict[str, Any]] = []
    perm_error = ""

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            for handle in targets:
                fields = (
                    f"business_discovery.username({handle})"
                    "{username,followers_count,media_count,"
                    "media.limit(5){id,permalink,caption,like_count,comments_count,media_product_type,timestamp}}"
                )
                resp = await client.get(
                    f"{GRAPH_API_BASE}/{ig_user_id}",
                    params={"fields": fields, "access_token": token},
                )
                payload = resp.json()
                bd = payload.get("business_discovery")
                if resp.status_code == 200 and isinstance(bd, dict):
                    media_list = (bd.get("media") or {}).get("data") or []
                    avg_likes = round(sum(int(m.get("like_count") or 0) for m in media_list) / max(1, len(media_list)), 1)
                    avg_cmts = round(sum(int(m.get("comments_count") or 0) for m in media_list) / max(1, len(media_list)), 1)
                    top_captions = [
                        (m.get("caption") or "").splitlines()[0][:100]
                        for m in sorted(media_list, key=lambda x: int(x.get("like_count") or 0), reverse=True)[:3]
                    ]
                    results[f"@{handle}"] = {
                        "followers": int(bd.get("followers_count") or 0),
                        "media_count": int(bd.get("media_count") or 0),
                        "avg_likes": avg_likes,
                        "avg_comments": avg_cmts,
                        "top_hooks": top_captions,
                    }
                    for m in media_list:
                        raw_media.append({"handle": handle, **m})
                else:
                    err = (payload.get("error") or {}).get("message", f"HTTP {resp.status_code}")
                    if "permission" in err.lower() or "does not exist" in err.lower() or (payload.get("error") or {}).get("code") in (10, 100):
                        perm_error = err
                        break
    except Exception as exc:
        perm_error = str(exc)[:160]

    return {
        "ok": bool(results),
        "permission_error": perm_error,
        "competitors": results,
        "raw_media": raw_media,
    }


async def discover_fashion_accounts_from_web(
    db: Any,
    cycle_idx: int = 0,
    allow_network: bool = True,
) -> dict[str, Any]:
    """Halol O'g'ri: internet qidiruv orqali O'zbekiston va global erkaklar kiyimi Instagram akkountlarini yig'ib boradi (IG logini xavfsiz qoladi)."""
    if db is not None:
        for seed in SEED_COMPETITOR_ACCOUNTS:
            await db.upsert_competitor_account(
                handle=seed["handle"],
                region=seed["region"],
                style_focus=seed["style_focus"],
                followers_est=seed["followers_est"],
                avg_likes=seed["avg_likes"],
                avg_views=seed["avg_views"],
                discovered_via="benchmark_seed",
                notes=seed["notes"],
            )

    discovered_handles: list[str] = []
    web_snippets: list[dict[str, Any]] = []

    if allow_network:
        queries = [
            "old money men winter outfit 2026",
            "erkaklar kiyimi toshkent kiyim narxlari",
            "menswear winter capsule lookbook 2026",
            "streetwear oversize mens outfit 2026",
            "diplomat classic wool coat men outfit",
        ]
        q = queries[cycle_idx % len(queries)]
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            }
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                resp = await client.get(
                    "https://www.youtube.com/results",
                    params={"search_query": q},
                    headers=headers,
                )
                if resp.status_code == 200:
                    html = resp.text
                    # Extract real YouTube menswear channels & videos from ytInitialData
                    m_yt = re.search(r"var ytInitialData = (\{.*?\});</script>", html)
                    yt_txt = m_yt.group(1) if m_yt else html
                    vids = re.findall(
                        r'"videoRenderer":\{"videoId":"([^"]+)".*?"title":\{"runs":\[\{"text":"([^"]+)"\}\].*?"ownerText":\{"runs":\[\{"text":"([^"]+)"',
                        yt_txt,
                    )
                    views_raw = re.findall(r'"viewCountText":\{"simpleText":"([^"]+)"\}', yt_txt)
                    pub_raw = re.findall(r'"publishedTimeText":\{"simpleText":"([^"]+)"\}', yt_txt)

                    for i, (vid, raw_title, raw_channel) in enumerate(vids[:6]):
                        title_clean = raw_title.encode("utf-8").decode("unicode_escape", errors="ignore") if "\\u" in raw_title else raw_title
                        ch_handle = re.sub(r"[^a-zA-Z0-9_.]", "_", raw_channel.strip()).strip("_").lower()[:28] or f"yt_fashion_{i+1}"
                        v_str = views_raw[i] if i < len(views_raw) else "12,000 views"
                        v_digits = re.sub(r"\D", "", v_str)
                        views_num = int(v_digits) if v_digits else 12000
                        pub_str = pub_raw[i] if i < len(pub_raw) else "Yaqinda"
                        if ch_handle not in discovered_handles:
                            discovered_handles.append(ch_handle)
                            if db is not None:
                                await db.upsert_competitor_account(
                                    handle=ch_handle,
                                    platform="youtube_shorts",
                                    region="uzbekistan" if any(u in q for u in ("toshkent", "kiyim")) else "global",
                                    style_focus=title_clean[:90],
                                    avg_views=views_num,
                                    avg_likes=round(views_num * 0.035, 1),
                                    discovered_via="youtube_live_crawler",
                                    notes={"query": q, "sample_video": f"https://www.youtube.com/watch?v={vid}"},
                                )
                        web_snippets.append({
                            "handle": ch_handle,
                            "video_id": vid,
                            "video_url": f"https://www.youtube.com/watch?v={vid}",
                            "title": title_clean[:160],
                            "snippet": f"Kanal: {raw_channel} | Ko'rishlar: {v_str} | Vaqt: {pub_str}",
                            "views_est": views_num,
                            "posted_at_info": pub_str,
                        })

                    # Also capture any Instagram handles present
                    for m in re.finditer(r"instagram\.com(?:/|%2F)([A-Za-z0-9_.]{3,30})(?:/|%2F|\b)", html):
                        cand = m.group(1).strip(".").lower()
                        if cand and cand not in _IG_NON_ACCOUNTS and cand not in discovered_handles:
                            discovered_handles.append(cand)
                            if db is not None:
                                await db.upsert_competitor_account(
                                    handle=cand,
                                    platform="instagram",
                                    region="global",
                                    style_focus="Cross-linked Instagram Menswear",
                                    discovered_via="youtube_bio_crawler",
                                    notes={"query": q, "discovered_ts": int(time.time())},
                                )
        except Exception as exc:
            logger.debug("Web discovery skipped: %s", exc)

        # Agent-Reach (Exa MCP) ochiq internet qidiruvi (API kalitsiz)
        try:
            from app.agent_reach_client import exa_web_search
            exa_hits = await exa_web_search(q, num_results=3, timeout_sec=8.0)
            for hit in exa_hits:
                h_url = hit.get("url") or ""
                m_ig = re.search(r"instagram\.com/([A-Za-z0-9_.]{3,30})", h_url)
                if m_ig:
                    cand = m_ig.group(1).strip(".").lower()
                    if cand not in _IG_NON_ACCOUNTS and cand not in discovered_handles:
                        discovered_handles.append(cand)
                        if db is not None:
                            await db.upsert_competitor_account(
                                handle=cand,
                                platform="instagram",
                                region="global",
                                style_focus=hit.get("title", "")[:90],
                                discovered_via="agent_reach_exa",
                                notes={"url": h_url},
                            )
                if hit.get("title"):
                    web_snippets.append({
                        "handle": m_ig.group(1).lower() if m_ig else "web_fashion",
                        "video_id": str(abs(hash(h_url)) % 10_000_000),
                        "video_url": h_url,
                        "title": hit.get("title", "")[:160],
                        "snippet": hit.get("snippet", "")[:260],
                        "views_est": 22000,
                        "posted_at_info": hit.get("published") or "Exa Internet Trend",
                    })
        except Exception as exc:
            logger.debug("Agent-Reach Exa skipped: %s", exc)

    return {
        "discovered_handles": discovered_handles,
        "web_snippets": web_snippets,
    }


def _estimate_pdd_economics_from_caption(caption: str, garment_hint: str = "") -> dict[str, int]:
    """Raqobatchi postidagi narx, Xitoy Pinduoduo tannarxi va foyda tahlilini hisoblaydi."""
    low = f"{caption} {garment_hint}".lower()
    # Extract UZS price if mentioned in caption (e.g. "750 000", "850.000", "900 ming")
    sell_uzs = 890000
    m_k = re.search(r"(\d{3})\s*(?:000|ming)", low)
    m_m = re.search(r"(\d(?:[\.,]\d{1,2})?)\s*mln", low)
    if m_m:
        sell_uzs = int(float(m_m.group(1).replace(",", ".")) * 1_000_000)
    elif m_k:
        val = int(m_k.group(1)) * 1000
        if 250000 <= val <= 3500000:
            sell_uzs = val

    if any(w in low for w in ("palto", "overcoat", "trench", "blazer")):
        pdd_cny, kg = 255.0, 2.1
        sell_uzs = max(sell_uzs, 1050000)
    elif any(w in low for w in ("sviter", "vodolazka", "kashmir", "chelsea", "lofer", "shim")):
        pdd_cny, kg = 195.0, 1.55
        sell_uzs = max(sell_uzs, 890000)
    else:
        pdd_cny, kg = 175.0, 1.45

    goods_uzs = int(pdd_cny * 1880 * 1.08)  # CNY + tranzaksiya/konvertatsiya
    cargo_uzs = int(kg * 130000)
    est_profit = max(120000, sell_uzs - goods_uzs - cargo_uzs)
    # XAN SHOP raqobatchidan arzonroq (50% oldindan) lekin 60%+ sof marjani ushlab turadigan narx
    xan_target = max(int(goods_uzs * 1.65), min(sell_uzs - 100000, int(goods_uzs * 1.85)))
    xan_target = ((xan_target + 49999) // 50000) * 50000
    return {
        "competitor_sell_price_uzs": sell_uzs,
        "estimated_pdd_cost_uzs": goods_uzs + cargo_uzs,
        "estimated_profit_uzs": est_profit,
        "xan_target_price_uzs": xan_target,
    }


def _classify_video_pattern(caption: str, account_handle: str, is_cold: bool = True) -> dict[str, str]:
    low = f"{caption} {account_handle}".lower()
    if any(w in low for w in ("diplomat", "old money", "palto", "vodolazka", "blazer", "lofer", "klassik", "stylesh")):
        return {
            "garment_type": "Qishki Palto/Blazer + Kashmir Vodolazka + Klassik Shim",
            "video_meaning": "Jiddiy/talaba/biznes auditoriyaga butik darajasidagi Old Money obrazni hamyonbop taklifda sotish",
            "editing_style": "persona_spotlight_deck" if "diplomat" in low or "old money" in low else "editorial_split_showcase",
            "video_quality": "1080p Studio, silliq kamera zoom va kontrastli kapsula subtitr",
            "music_genre": "Klassik Piano & Strings / Old Money Cinema",
            "audio_vibe": "diplomat_old_money",
        }
    if any(w in low for w in ("xudi", "kargo", "street", "oversize", "tima", "hoodie")):
        return {
            "garment_type": "420g Oversize Xudi + Bomber + Kargo + Krossovka",
            "video_meaning": "Yoshlar/universitet uchun trenddagi keng ko'cha to'plami (+ komment triggeri)",
            "editing_style": "orbit_3d_turntable",
            "video_quality": "1080p Tez o'tuvchi ritmik kadrlar va qora kapsula narx kartasi",
            "music_genre": "Dark Drift Phonk Bass",
            "audio_vibe": "phonk_bass",
        }
    return {
        "garment_type": "Kuz-Qish Smart-Casual Kapsula (Sviter/Blazer + Klassik Shim)" if is_cold else "Smart Casual Obraz",
        "video_meaning": "Kundalik va ofis kiyinish uchun tayyor rang-mos obraz",
        "editing_style": "bento_zoom_reveal",
        "video_quality": "1080p Matoga yaqin zoom + solishtirish narx bloki",
        "music_genre": "Luxury Deep House Lounge" if is_cold else "Warm Lofi Editorial Beat",
        "audio_vibe": "luxury_chill",
    }


async def analyze_competitor_videos_batch(
    db: Any,
    settings: Any,
    comp_discovery: dict[str, Any],
    web_intel: dict[str, Any],
    rules: dict[str, Any],
) -> list[dict[str, Any]]:
    """Halol O'g'ri: har bir video/postni ma'no, montaj, musiqa, qiziqish va narx-foyda bo'yicha tahlil qilib DB ga yozadi."""
    analyzed: list[dict[str, Any]] = []
    is_cold = bool(rules.get("is_cold_season", True))

    # 1) Seed curated benchmark videos so DB immediately holds deep market baselines
    for item in CURATED_MARKET_VIDEO_PATTERNS:
        row = dict(item)
        if db is not None:
            await db.add_competitor_video(row)
        analyzed.append(row)

    # 2) Live Meta business_discovery media items (if token unlocked & scope active)
    for m in (comp_discovery.get("raw_media") or [])[:8]:
        caption = str(m.get("caption") or "")
        handle = str(m.get("handle") or "_tima_shop")
        mid = str(m.get("id") or f"{handle}_{abs(hash(caption)) % 100000}")
        cls = _classify_video_pattern(caption, handle, is_cold=is_cold)
        econ = _estimate_pdd_economics_from_caption(caption, cls["garment_type"])
        likes = int(m.get("like_count") or 0)
        cmts = int(m.get("comments_count") or 0)
        row = {
            "video_key": f"ig_{mid}",
            "account_handle": handle,
            "video_url": str(m.get("permalink") or f"https://www.instagram.com/{handle}/reels/"),
            "posted_at_info": str(m.get("timestamp") or "So'nggi IG Reels"),
            "garment_type": cls["garment_type"],
            "video_meaning": cls["video_meaning"],
            "editing_style": cls["editing_style"],
            "video_quality": cls["video_quality"],
            "music_genre": cls["music_genre"],
            "audio_vibe": cls["audio_vibe"],
            "views_est": max(likes * 25, 1200),
            "likes_count": likes,
            "comments_count": cmts,
            "competitor_sell_price_uzs": econ["competitor_sell_price_uzs"],
            "estimated_pdd_cost_uzs": econ["estimated_pdd_cost_uzs"],
            "estimated_profit_uzs": econ["estimated_profit_uzs"],
            "xan_target_price_uzs": econ["xan_target_price_uzs"],
            "insight_summary": f"@{handle} jonli Reels: {likes} layk, {cmts} izoh | Narx ~{econ['competitor_sell_price_uzs']:,} so'm",
            "raw_json": {"caption": caption[:400], "source": "graph_business_discovery"},
        }
        if db is not None:
            await db.add_competitor_video(row)
        analyzed.append(row)

    # 3) Jonli Internet / YouTube / Web videolari (IG akkauntini xavfga qo'ymasdan tahlil)
    for idx, snip in enumerate((web_intel.get("web_snippets") or [])[:6]):
        text = f"{snip.get('title', '')} {snip.get('snippet', '')}"
        handles = web_intel.get("discovered_handles") or []
        handle = str(snip.get("handle") or (handles[idx] if idx < len(handles) else f"web_trend_{idx+1}"))
        cls = _classify_video_pattern(text, handle, is_cold=is_cold)
        econ = _estimate_pdd_economics_from_caption(text, cls["garment_type"])
        v_id = str(snip.get("video_id") or abs(hash(snip.get("title", ""))) % 1000000)
        vkey = f"web_{handle}_{v_id}"
        views_n = int(snip.get("views_est") or 14000)
        likes_n = max(45, int(views_n * 0.032))
        cmts_n = max(6, int(views_n * 0.0025))
        row = {
            "video_key": vkey,
            "account_handle": handle,
            "video_url": str(snip.get("video_url") or f"https://www.instagram.com/{handle}/reels/"),
            "posted_at_info": str(snip.get("posted_at_info") or "Internet Trend Razvedkasi (So'nggi)"),
            "garment_type": cls["garment_type"],
            "video_meaning": snip.get("title", "")[:150] or cls["video_meaning"],
            "editing_style": cls["editing_style"],
            "video_quality": cls["video_quality"],
            "music_genre": cls["music_genre"],
            "audio_vibe": cls["audio_vibe"],
            "views_est": views_n,
            "likes_count": likes_n,
            "comments_count": cmts_n,
            "competitor_sell_price_uzs": econ["competitor_sell_price_uzs"],
            "estimated_pdd_cost_uzs": econ["estimated_pdd_cost_uzs"],
            "estimated_profit_uzs": econ["estimated_profit_uzs"],
            "xan_target_price_uzs": econ["xan_target_price_uzs"],
            "insight_summary": f"@{handle} ({views_n:,} ko'rish, {snip.get('posted_at_info', '')}): {cls['garment_type']} | Zvuk: {cls['audio_vibe']}",
            "raw_json": snip,
        }
        if db is not None:
            await db.add_competitor_video(row)
        analyzed.append(row)

    return analyzed


def evaluate_seasonal_styling_rules(weather: Any = None) -> dict[str, Any]:
    """Return strict seasonal & persona garment rules for Uzbekistan weather (5-10d arrival)."""
    now_month = datetime.now().month
    if isinstance(weather, dict):
        cur_temp = float(weather.get("cur_temp") or 12.0)
        arr_min = float(weather.get("forecast_5_10d_min") or weather.get("min_temp") or 4.0)
        arr_max = float(weather.get("forecast_5_10d_max") or weather.get("max_temp") or 12.0)
    elif weather is not None:
        cur_temp = float(getattr(weather, "temp_c", 12.0) or 12.0)
        arr_min = float(getattr(weather, "future_min_c", None) or getattr(weather, "future_temp_c", None) or getattr(weather, "min_c", 4.0) or 4.0)
        arr_max = float(getattr(weather, "future_max_c", None) or getattr(weather, "max_c", 12.0) or 12.0)
    else:
        cur_temp, arr_min, arr_max = 12.0, 4.0, 12.0

    is_cold_season = (now_month in (11, 12, 1, 2, 3)) or arr_min <= 11.0 or cur_temp <= 15.0
    if arr_min <= 5.0 or now_month in (12, 1, 2):
        weather_tier = "qish_sovuq"
        season_label = "Qish (Sovuq havo)"
        mandatory_layers = (
            "Qalin qishki/kuz-qish palto, kashmir/jun sviter, qalin flis xudi yoki kurtka, "
            "qalin jun/klassik shim va yopiq etik/lofer bo'lishi SHART."
        )
    elif is_cold_season:
        weather_tier = "kech_kuz_qish_boshi"
        season_label = "Kuz-Qish"
        mandatory_layers = (
            "Qalin zamokli sviter, jemper, kashmir vodolazka, bomber/kurtka yoki palto, "
            "drape klassik shim va zamsh lofer/botinka."
        )
    else:
        weather_tier = "bahor_iliq"
        season_label = "Bahor-Kuz"
        mandatory_layers = "Yengil kardigan/ko'ylak, klassik shim, lofer."

    return {
        "weather_tier": weather_tier,
        "season_label": season_label,
        "cur_temp": cur_temp,
        "arr_min": arr_min,
        "arr_max": arr_max,
        "is_cold_season": is_cold_season,
        "forbid_tshirts": is_cold_season,
        "forbidden_cold_words": [
            "futbolka", "t-shirt", "tee", "mayka", "shorti", "shorts", "polo yozgi", "slipper", "tapochka"
        ] if is_cold_season else [],
        "forbidden_diplomat_words": [
            "kargo", "cargo", "xudi", "hoodie", "kepka", "cap", "sportiv", "trening", "jinsiy shorti", "krossovka", "jordan"
        ],
        "mandatory_layers": mandatory_layers,
    }


async def run_live_instagram_analyst_async(
    db: Any,
    settings: Any,
    cycle_idx: int,
    weather: dict | None = None,
) -> dict[str, Any]:
    """Run 'Halol O'g'ri' full internet + Instagram discovery, video-by-video analysis, DB accumulation & cross-agent briefing."""
    ig_user_id = getattr(settings, "ig_user_id", "") or ""
    ig_token = getattr(settings, "ig_access_token", "") or ""
    allow_net = bool(ig_token or getattr(settings, "gemini_api_key", ""))

    perms = await audit_ig_token_permissions(ig_token)
    own_perf = await fetch_own_instagram_performance(
        ig_user_id,
        ig_token,
        has_insights=perms.get("has_insights", False),
    )

    tracked_handles = ["_tima_shop", "stylesh.uz", "lookzona.uz", "menstyle.uz"]
    if db is not None:
        try:
            existing_accs = await db.list_competitor_accounts(limit=12)
            for acc in existing_accs:
                if acc["handle"] not in tracked_handles and not acc["handle"].startswith("web_"):
                    tracked_handles.append(acc["handle"])
        except Exception:
            pass

    comp_discovery = (
        await fetch_competitor_business_discovery(ig_user_id, ig_token, handles=tracked_handles[:5])
        if (ig_user_id and ig_token and perms.get("has_insights"))
        else {"ok": False, "permission_error": "instagram_manage_insights yo'q yoki hisob qulflangan", "competitors": {}, "raw_media": []}
    )
    rules = evaluate_seasonal_styling_rules(weather)
    web_intel = await discover_fashion_accounts_from_web(db, cycle_idx=cycle_idx, allow_network=allow_net)
    analyzed_videos = await analyze_competitor_videos_batch(db, settings, comp_discovery, web_intel, rules)

    # DB dan eng muvaffaqiyatli "Halol O'g'ri" andozalarini olish
    top_patterns = list(analyzed_videos[:4])
    all_accounts: list[dict] = []
    if db is not None:
        try:
            top_patterns = await db.get_halol_ogri_winning_patterns(limit=5) or top_patterns
            all_accounts = await db.list_competitor_accounts(limit=50)
        except Exception:
            pass

    winning_pick = top_patterns[cycle_idx % max(1, len(top_patterns))] if top_patterns else {}
    rec_style = str(winning_pick.get("editing_style") or "persona_spotlight_deck")
    rec_audio = str(winning_pick.get("audio_vibe") or "diplomat_old_money")
    rec_music_label = str(winning_pick.get("music_genre") or "Klassik Piano & Strings")
    comp_price = int(winning_pick.get("competitor_sell_price_uzs") or 950000)
    est_cost = int(winning_pick.get("estimated_pdd_cost_uzs") or 460000)
    est_profit = int(winning_pick.get("estimated_profit_uzs") or 340000)
    xan_target = int(winning_pick.get("xan_target_price_uzs") or 850000)

    scout_brief = (
        f"Halol O'g'ri → Pinduoduo Skaut: @{winning_pick.get('account_handle', 'stylesh.uz')} dagi "
        f"'{winning_pick.get('garment_type', 'Qishki Palto/Vodolazka')}' bozor narxi ~{comp_price:,} so'm "
        f"(tannarx ~{est_cost:,}, raqobatchi foydasi ~{est_profit:,}). "
        f"Pinduoduo'dan faqat qishki qalin klassik/street buyumlar topib, mijozga {xan_target:,} so'm (50% oldindan) atrofida foydali look yig'!"
    )
    video_brief = (
        f"Halol O'g'ri → Video Montajchi: Eng ko'p ko'rilgan ({winning_pick.get('views_est', 20000):,} ko'rish) uslub = '{rec_style}', "
        f"haqiqiy studio MP3 zvuk = '{rec_audio}' ({rec_music_label}). "
        f"Ma'no: {winning_pick.get('video_meaning', 'Tayyor kapsula')}. Sintetik bip-bip ishlatma, faqat data/audio/{rec_audio}.mp3 trekni qo'y!"
    )

    recent_looks: list[dict[str, Any]] = []
    recent_learnings: list[str] = []
    playbooks: dict[str, dict[str, Any]] = {}
    if db is not None:
        try:
            recent_looks = (await db.list_looks(only_active=False))[:6]
            agents = {a["agent_id"]: a for a in await db.list_agents()}
            raw_l = (agents.get("insta_analyst") or {}).get("learnings_json") or "[]"
            recent_learnings = json.loads(raw_l) if isinstance(raw_l, str) else []
            playbooks = await db.get_all_playbooks()
        except Exception:
            pass
    from app.source_learner import format_playbooks_for_ai
    learned_playbooks_text = format_playbooks_for_ai(playbooks)

    recent_styles = [str(l.get("style") or "") for l in recent_looks[:4]]
    recent_titles = [str(l.get("title") or "") for l in recent_looks[:4]]
    missing_perms = perms.get("missing") or []

    learning_note = (
        f"[Sikl #{cycle_idx + 1} | Halol O'g'ri] Kuzatuvda {len(all_accounts) or len(SEED_COMPETITOR_ACCOUNTS)} ta akkount, "
        f"{len(top_patterns)} ta TOP video andoza | Top: @{winning_pick.get('account_handle', 'stylesh.uz')} ({rec_audio}, raqobatchi foydasi ~{est_profit:,} so'm) | "
        f"Mavsum: {rules['season_label']} (futbolka={'TAQIQLANDI' if rules['forbid_tshirts'] else 'ruxsat'})."
    )

    if db is not None:
        try:
            await db.record_agent_learning("insta_analyst", learning_note, xp_gain=45)
        except Exception:
            pass

    return {
        "permissions": perms,
        "missing_permissions": missing_perms,
        "own_performance": own_perf,
        "competitor_discovery": comp_discovery,
        "seasonal_rules": rules,
        "recent_styles": recent_styles,
        "recent_titles": recent_titles,
        "prior_learnings": recent_learnings[-4:],
        "learning_note": learning_note,
        "learned_playbooks": playbooks,
        "learned_playbooks_text": learned_playbooks_text,
        "halol_ogri": {
            "accounts_tracked": len(all_accounts) or len(SEED_COMPETITOR_ACCOUNTS),
            "new_web_accounts": web_intel.get("discovered_handles", []),
            "videos_analyzed": len(analyzed_videos),
            "winning_pattern": winning_pick,
            "recommended_video_style": rec_style,
            "recommended_audio_vibe": rec_audio,
            "recommended_music_genre": rec_music_label,
            "scout_brief": scout_brief,
            "video_brief": video_brief,
        },
    }
