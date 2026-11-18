"""XAN SHOP — Built-in OmniRoute 24/7 Multi-Provider Unlimited AI Gateway (http://localhost:20128).

Avtomatik ravishda 12+ bepul va zaxira AI modellarini bitta lokal OpenAI-compatible
shlyuzga (`http://localhost:20128/v1`) birlashtiradi:
1) Google Gemini Multi-Model Pool (`gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-3.5-flash-lite`,
   `gemini-3.1-flash-lite`, `gemini-2.5-flash`, `gemini-2.5-flash-lite`, `gemini-2.0-flash`) —
   har bir modelning kunlik bepul kvotasi alohida hisoblanadi;
2) OpenRouter Free Tier Pool (`deepseek/deepseek-chat-v3-0324:free`, `google/gemini-2.0-flash-exp:free`,
   `meta-llama/llama-3.3-70b-instruct:free`);
3) Keyless Free AI Pool (`pollinations/openai`, `pollinations/deepseek`, `pollinations/mistral`) —
   API kalitsiz 24/7 bepul zaxira.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx
from aiohttp import web
from google import genai

log = logging.getLogger("xanshop.omniroute")

OMNIROUTE_MODELS = [
    {"id": "auto", "provider": "omniroute-smart-router", "tier": "free-unlimited"},
    {"id": "gemini-3.6-flash", "provider": "google-ai-studio", "tier": "free-pool"},
    {"id": "gemini-3.5-flash", "provider": "google-ai-studio", "tier": "free-pool"},
    {"id": "gemini-3.5-flash-lite", "provider": "google-ai-studio", "tier": "free-pool"},
    {"id": "gemini-3.1-flash-lite", "provider": "google-ai-studio", "tier": "free-pool"},
    {"id": "gemini-2.5-flash", "provider": "google-ai-studio", "tier": "free-pool"},
    {"id": "gemini-2.5-flash-lite", "provider": "google-ai-studio", "tier": "free-pool"},
    {"id": "gemini-2.0-flash", "provider": "google-ai-studio", "tier": "free-pool"},
    {"id": "deepseek/deepseek-chat-v3-0324:free", "provider": "openrouter-free", "tier": "free-pool"},
    {"id": "google/gemini-2.0-flash-exp:free", "provider": "openrouter-free", "tier": "free-pool"},
    {"id": "meta-llama/llama-3.3-70b-instruct:free", "provider": "openrouter-free", "tier": "free-pool"},
    {"id": "pollinations/openai", "provider": "pollinations-keyless", "tier": "free-unlimited"},
]

_COOLDOWN_UNTIL: dict[str, float] = {}
_STATS = {"requests_total": 0, "success_total": 0, "last_model_used": "init", "started_at": int(time.time())}


def _extract_system_and_user(messages: list[dict[str, Any]]) -> tuple[str, str, str, str]:
    """OpenAI messages ro'yxatidan (system, user_text, media_b64, mime_type) ajratib oladi."""
    sys_parts: list[str] = []
    user_parts: list[str] = []
    media_b64 = ""
    mime_type = ""
    for m in messages or []:
        role = m.get("role", "user")
        content = m.get("content", "")
        if isinstance(content, str):
            if role == "system":
                sys_parts.append(content)
            else:
                user_parts.append(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        user_parts.append(str(item.get("text") or ""))
                    elif item.get("type") == "image_url":
                        url_val = str((item.get("image_url") or {}).get("url") or "")
                        if url_val.startswith("data:") and ";base64," in url_val:
                            header, b64_data = url_val.split(";base64,", 1)
                            mime_type = header.replace("data:", "").strip()
                            media_b64 = b64_data.strip()
    return "\n".join(sys_parts).strip(), "\n".join(user_parts).strip(), media_b64, mime_type


def build_omniroute_app(settings: Any) -> web.Application:
    app = web.Application()
    gemini_key = getattr(settings, "gemini_api_key", "") or ""
    openrouter_key = getattr(settings, "openrouter_api_key", "") or ""
    gem_client = (
        genai.Client(api_key=gemini_key, http_options={"timeout": 30000, "retry_options": {"attempts": 1}})
        if gemini_key
        else None
    )

    async def handle_health(_req: web.Request) -> web.Response:
        return web.json_response({
            "status": "ok",
            "gateway": "OmniRoute Local AI Gateway v3.5",
            "models_count": len(OMNIROUTE_MODELS),
            "stats": _STATS,
        })

    async def handle_models(_req: web.Request) -> web.Response:
        return web.json_response({"object": "list", "data": OMNIROUTE_MODELS})

    async def handle_dashboard(_req: web.Request) -> web.Response:
        html = (
            "<html><head><meta charset='utf-8'><title>OmniRoute AI Gateway</title></head>"
            "<body style='font-family:sans-serif;background:#111318;color:#f4f4f6;padding:32px'>"
            "<h2>🟢 XAN SHOP — OmniRoute Unlimited AI Token Gateway</h2>"
            f"<p>Models active: <b>{len(OMNIROUTE_MODELS)}</b> | Total requests: <b>{_STATS['requests_total']}</b> | "
            f"Last model: <code>{_STATS['last_model_used']}</code></p>"
            "<ul>" + "".join(f"<li><code>{m['id']}</code> ({m['provider']} — {m['tier']})</li>" for m in OMNIROUTE_MODELS) + "</ul>"
            "</body></html>"
        )
        return web.Response(text=html, content_type="text/html")

    async def handle_chat_completions(req: web.Request) -> web.Response:
        _STATS["requests_total"] += 1
        try:
            body = await req.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)

        messages = body.get("messages") or []
        sys_txt, usr_txt, media_b64, mime_type = _extract_system_and_user(messages)

        # 1. Google Gemini Multi-Model Pool (7 models with independent daily free quotas)
        if gem_client and usr_txt:
            now = time.monotonic()
            gem_models = [
                "gemini-3.5-flash-lite",
                "gemini-3.1-flash-lite",
                "gemini-3.5-flash",
                "gemini-2.5-flash",
                "gemini-2.5-flash-lite",
                "gemini-2.0-flash",
                "gemini-3.6-flash",
            ]
            active_gem = [m for m in gem_models if _COOLDOWN_UNTIL.get(m, 0.0) <= now] or gem_models[:2]
            for gm in active_gem:
                try:
                    inp: Any = usr_txt
                    if media_b64 and mime_type:
                        m_kind = "audio" if mime_type.startswith("audio/") else "image"
                        inp = [{"type": "text", "text": usr_txt}, {"type": m_kind, "data": media_b64, "mime_type": mime_type}]

                    def _call_g(model_name: str = gm) -> Any:
                        return gem_client.interactions.create(
                            model=model_name,
                            system_instruction=sys_txt or "Sen XAN SHOP AI yordamchisisan.",
                            input=inp,
                        )

                    inter = await asyncio.wait_for(asyncio.to_thread(_call_g), timeout=22.0)
                    out_txt = (getattr(inter, "output_text", None) or "").strip()
                    if out_txt:
                        _COOLDOWN_UNTIL.pop(gm, None)
                        _STATS["success_total"] += 1
                        _STATS["last_model_used"] = gm
                        return web.json_response({
                            "id": f"omni-{int(time.time()*1000)}",
                            "object": "chat.completion",
                            "model": gm,
                            "choices": [{"index": 0, "message": {"role": "assistant", "content": out_txt}, "finish_reason": "stop"}],
                        })
                except Exception as exc:
                    _COOLDOWN_UNTIL[gm] = time.monotonic() + 120.0
                    log.debug("OmniRoute Gemini (%s) skip: %s", gm, exc)

        # 2. OpenRouter Free Models Pool (if OPENROUTER_API_KEY configured)
        if openrouter_key and usr_txt and not media_b64:
            for orm in ("deepseek/deepseek-chat-v3-0324:free", "google/gemini-2.0-flash-exp:free", "meta-llama/llama-3.3-70b-instruct:free"):
                try:
                    async with httpx.AsyncClient(timeout=14.0) as client:
                        r = await client.post(
                            "https://openrouter.ai/api/v1/chat/completions",
                            headers={"Authorization": f"Bearer {openrouter_key}"},
                            json={"model": orm, "messages": messages, "temperature": 0.4},
                        )
                        if r.status_code == 200:
                            data = r.json()
                            txt = ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "").strip()
                            if txt:
                                _STATS["success_total"] += 1
                                _STATS["last_model_used"] = orm
                                return web.json_response(data)
                except Exception:
                    continue

        # 3. Keyless Free AI Pool (Pollinations OpenAI-compatible endpoint)
        if usr_txt and not media_b64:
            for pm in ("openai", "mistral"):
                try:
                    async with httpx.AsyncClient(timeout=15.0) as client:
                        r = await client.post(
                            "https://text.pollinations.ai/openai",
                            json={
                                "model": pm,
                                "messages": [
                                    {"role": "system", "content": sys_txt or "Sen XAN SHOP AI mutaxassisan."},
                                    {"role": "user", "content": usr_txt},
                                ],
                            },
                        )
                        if r.status_code == 200:
                            txt = ""
                            if r.headers.get("content-type", "").startswith("application/json"):
                                d = r.json()
                                txt = ((d.get("choices") or [{}])[0].get("message") or {}).get("content", "").strip()
                            else:
                                txt = r.text.strip()
                            if txt:
                                _STATS["success_total"] += 1
                                _STATS["last_model_used"] = f"pollinations/{pm}"
                                return web.json_response({
                                    "id": f"omni-free-{int(time.time()*1000)}",
                                    "object": "chat.completion",
                                    "model": f"pollinations/{pm}",
                                    "choices": [{"index": 0, "message": {"role": "assistant", "content": txt}, "finish_reason": "stop"}],
                                })
                except Exception:
                    continue

        return web.json_response({"error": "all providers busy"}, status=503)

    app.router.add_get("/api/health", handle_health)
    app.router.add_get("/v1/models", handle_models)
    app.router.add_get("/dashboard", handle_dashboard)
    app.router.add_post("/v1/chat/completions", handle_chat_completions)
    return app


async def start_omniroute_server(settings: Any, port: int = 20128) -> web.AppRunner | None:
    """Lokal 20128 portda OmniRoute AI Gateway serverini ishga tushiradi."""
    try:
        app = build_omniroute_app(settings)
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", port)
        await site.start()
        log.info("🟢 OmniRoute Local AI Gateway ishga tushdi: http://localhost:%d/v1 (%d modellar)", port, len(OMNIROUTE_MODELS))
        return runner
    except Exception as exc:
        log.debug("OmniRoute port %d band yoki ishga tushmadi: %s", port, exc)
        return None
