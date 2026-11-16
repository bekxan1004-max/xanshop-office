from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

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
        async with httpx.AsyncClient(timeout=20) as client:
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

                # Check live comments on recent/commented posts
                if mid and (cmts > 0 or idx < 4):
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

                # Attempt insights only if scope is granted (or first post probe)
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
        return {"ok": False, "error": "Token yo'q", "competitors": {}}

    targets = [h.lstrip("@").strip() for h in (handles or ["_tima_shop", "stylesh.uz", "lookzona.uz"]) if h.strip()]
    results: dict[str, Any] = {}
    perm_error = ""

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            for handle in targets:
                fields = (
                    f"business_discovery.username({handle})"
                    "{username,followers_count,media_count,"
                    "media.limit(5){caption,like_count,comments_count,media_product_type,timestamp}}"
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
                else:
                    err = (payload.get("error") or {}).get("message", f"HTTP {resp.status_code}")
                    if "permission" in err.lower() or (payload.get("error") or {}).get("code") in (10, 100):
                        perm_error = err
                        break
    except Exception as exc:
        perm_error = str(exc)[:160]

    return {
        "ok": bool(results),
        "permission_error": perm_error,
        "competitors": results,
    }


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
            "Qalin qishki/kuz-qish palto, kaşmir/jun sviter, qalin fлис xudi yoki kurtka, "
            "qalin jun/klassik shim va yopiq etik/lofer bo'lishi SHART."
        )
    elif is_cold_season:
        weather_tier = "kech_kuz_qish_boshi"
        season_label = "Kuz-Qish"
        mandatory_layers = (
            "Qalin zamokli sviter, jemper, kaşmir vodolazka, bomber/kurtka yoki palto, "
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
    """Run real Instagram Graph API audit + DB self-learning + seasonal/audience direction."""
    ig_user_id = getattr(settings, "ig_user_id", "") or ""
    ig_token = getattr(settings, "ig_access_token", "") or ""

    perms = await audit_ig_token_permissions(ig_token)
    own_perf = await fetch_own_instagram_performance(
        ig_user_id,
        ig_token,
        has_insights=perms.get("has_insights", False),
    )
    comp_discovery = await fetch_competitor_business_discovery(
        ig_user_id,
        ig_token,
        handles=["_tima_shop", "stylesh.uz", "lookzona.uz"],
    )
    rules = evaluate_seasonal_styling_rules(weather)

    # Read recent looks from DB to enforce strong variety and prevent identical looks
    recent_looks: list[dict[str, Any]] = []
    recent_learnings: list[str] = []
    if db is not None:
        try:
            recent_looks = (await db.list_looks(only_active=False))[:6]
        except Exception:
            recent_looks = []
        try:
            agents = {a["agent_id"]: a for a in await db.list_agents()}
            raw_l = (agents.get("insta_analyst") or {}).get("learnings_json") or "[]"
            recent_learnings = json.loads(raw_l) if isinstance(raw_l, str) else []
        except Exception:
            recent_learnings = []

    recent_styles = [str(l.get("style") or "") for l in recent_looks[:4]]
    recent_titles = [str(l.get("title") or "") for l in recent_looks[:4]]

    missing_perms = perms.get("missing") or []
    own_top = own_perf.get("top_post")
    own_summary = (
        f"@{own_perf.get('username', 'xan_styles')}: {own_perf.get('media_count', 0)} ta post, "
        f"jami {own_perf.get('total_likes', 0)} layk, {own_perf.get('total_comments', 0)} komment"
    )
    if own_top:
        own_summary += f" | TOP Reels: '{own_top.get('title_line', '')}' ({own_top.get('likes', 0)} layk, {own_top.get('comments', 0)} izoh)"

    learning_note = (
        f"[Sikl #{cycle_idx + 1}] {own_summary} | Mavsum: {rules['season_label']} ({rules['arr_min']:.0f}..{rules['arr_max']:.0f}°C, "
        f"futbolka={'TAQIQLANDI' if rules['forbid_tshirts'] else 'ruxsat'}). "
        f"Yetishmayotgan IG ruxsatlar: {', '.join(missing_perms) if missing_perms else 'BARCHASI FAOL'}."
    )

    if db is not None:
        try:
            await db.record_agent_learning("insta_analyst", learning_note, xp_gain=35)
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
    }
