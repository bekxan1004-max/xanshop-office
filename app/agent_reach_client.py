"""Agent-Reach (MIT-ilhomlangan) ochiq internet qidiruv va o'qish moduli.

API kalitsiz ishlaydi:
- Web Search: Exa MCP (`https://mcp.exa.ai/mcp`)
- Universal Page Reader: Jina Reader (`https://r.jina.ai/<url>`)
- Video & Shorts Intelligence: YouTube (`youtube.com/results`) + ixtiyoriy `yt-dlp`
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from typing import Any

import httpx

logger = logging.getLogger("xanshop.agent_reach")

EXA_MCP_URL = "https://mcp.exa.ai/mcp"
JINA_READER_BASE = "https://r.jina.ai/"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


async def exa_web_search(query: str, num_results: int = 6, timeout_sec: float = 12.0) -> list[dict[str, str]]:
    """API kalitsiz Exa MCP orqali ochiq internetdan maqola, trend va narxlarni qidiradi."""
    q = (query or "").strip()
    if not q:
        return []
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "web_search_exa",
            "arguments": {"query": q, "numResults": max(1, min(10, int(num_results)))},
        },
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "User-Agent": _UA,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_sec, follow_redirects=True) as client:
            resp = await client.post(EXA_MCP_URL, json=payload, headers=headers)
            if resp.status_code != 200:
                return []
            raw_text = resp.text
            json_blob = raw_text
            for line in raw_text.splitlines():
                if line.startswith("data:"):
                    json_blob = line[5:].strip()
                    break
            data = json.loads(json_blob)
            contents = ((data.get("result") or {}).get("content") or [])
            combined = "\n".join(str(c.get("text") or "") for c in contents if isinstance(c, dict))
            if not combined:
                return []

            results: list[dict[str, str]] = []
            # Exa formats entries with Title: ... URL: ... Text: ...
            blocks = re.split(r"(?=^Title:\s)", combined, flags=re.M)
            for blk in blocks:
                if "Title:" not in blk:
                    continue
                t_m = re.search(r"^Title:\s*(.+)$", blk, flags=re.M)
                u_m = re.search(r"^URL:\s*(.+)$", blk, flags=re.M)
                p_m = re.search(r"^Published:\s*(.+)$", blk, flags=re.M)
                body = re.sub(r"^(?:Title|URL|Published|Author):.*$", "", blk, flags=re.M).strip()
                results.append({
                    "title": (t_m.group(1).strip() if t_m else "")[:180],
                    "url": (u_m.group(1).strip() if u_m else "")[:300],
                    "published": (p_m.group(1).strip() if p_m else "")[:60],
                    "snippet": re.sub(r"\s+", " ", body)[:500],
                })
            return results[:num_results]
    except Exception as exc:
        logger.debug("Exa search fallback: %s", exc)
        return []


async def jina_read_url(url: str, max_chars: int = 4000, timeout_sec: float = 12.0) -> dict[str, Any]:
    """Jina Reader orqali istalgan ochiq sahifa, GitHub repo yoki saytni Markdown holida o'qiydi."""
    clean_url = (url or "").strip()
    if not clean_url.startswith(("http://", "https://")):
        return {"ok": False, "text": "", "error": "Noto'g'ri URL"}
    try:
        async with httpx.AsyncClient(timeout=timeout_sec, follow_redirects=True) as client:
            resp = await client.get(
                f"{JINA_READER_BASE}{clean_url}",
                headers={"Accept": "text/plain", "User-Agent": _UA},
            )
            if resp.status_code != 200:
                return {"ok": False, "text": "", "error": f"HTTP {resp.status_code}"}
            txt = resp.text.strip()
            return {"ok": True, "url": clean_url, "text": txt[:max_chars], "length": len(txt)}
    except Exception as exc:
        return {"ok": False, "text": "", "error": str(exc)[:140]}


async def youtube_search_videos(query: str, limit: int = 6, timeout_sec: float = 10.0) -> list[dict[str, Any]]:
    """API kalitsiz YouTube video va Shorts qidiruvi (kanal, ko'rishlar, sana va URL bilan)."""
    q = (query or "").strip()
    if not q:
        return []
    try:
        headers = {"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9"}
        async with httpx.AsyncClient(timeout=timeout_sec, follow_redirects=True) as client:
            resp = await client.get("https://www.youtube.com/results", params={"search_query": q}, headers=headers)
            if resp.status_code != 200:
                return []
            html = resp.text
            m_yt = re.search(r"var ytInitialData = (\{.*?\});</script>", html)
            yt_txt = m_yt.group(1) if m_yt else html
            vids = re.findall(
                r'"videoRenderer":\{"videoId":"([^"]+)".*?"title":\{"runs":\[\{"text":"([^"]+)"\}\].*?"ownerText":\{"runs":\[\{"text":"([^"]+)"',
                yt_txt,
            )
            views_raw = re.findall(r'"viewCountText":\{"simpleText":"([^"]+)"\}', yt_txt)
            pub_raw = re.findall(r'"publishedTimeText":\{"simpleText":"([^"]+)"\}', yt_txt)
            out: list[dict[str, Any]] = []
            for i, (vid, raw_title, raw_channel) in enumerate(vids[:limit]):
                title_clean = raw_title.encode("utf-8").decode("unicode_escape", errors="ignore") if "\\u" in raw_title else raw_title
                v_str = views_raw[i] if i < len(views_raw) else "12,000 views"
                v_digits = re.sub(r"\D", "", v_str)
                out.append({
                    "video_id": vid,
                    "url": f"https://www.youtube.com/watch?v={vid}",
                    "title": title_clean[:180],
                    "channel": raw_channel.strip()[:80],
                    "views_text": v_str,
                    "views_est": int(v_digits) if v_digits else 12000,
                    "published": pub_raw[i] if i < len(pub_raw) else "Yaqinda",
                })
            return out
    except Exception as exc:
        logger.debug("YouTube search fallback: %s", exc)
        return []


def fetch_video_metadata_ytdlp(url: str) -> dict[str, Any]:
    """Agar tizimda yt-dlp mavjud bo'lsa, videoning aniq metama'lumoti (izoh, ko'rishlar, muallif, davomiylik) ni oladi."""
    ytdlp = shutil.which("yt-dlp")
    if not ytdlp or not url:
        return {}
    try:
        proc = subprocess.run(
            [ytdlp, "--dump-single-json", "--no-warnings", "--skip-download", url],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            data = json.loads(proc.stdout)
            return {
                "title": str(data.get("title") or "")[:180],
                "uploader": str(data.get("uploader") or data.get("channel") or "")[:80],
                "view_count": int(data.get("view_count") or 0),
                "like_count": int(data.get("like_count") or 0),
                "duration": float(data.get("duration") or 0),
                "description": str(data.get("description") or "")[:800],
            }
    except Exception:
        pass
    return {}
