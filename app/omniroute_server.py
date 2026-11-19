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
    {"id": "auto", "provider": "omniroute-smart-router", "tier": "free-unlimited", "label": "⚡ Auto (Eng tezkor + Avto-zaxira)"},
    {"id": "xanshop-auto", "provider": "omniroute-combo", "tier": "free-unlimited", "label": "⚡ XAN SHOP Smart Combo"},
    {"id": "gemini-3.5-flash-lite", "provider": "google-ai-studio", "tier": "live-verified", "label": "Google Gemini 3.5 Flash-Lite (Tezkor)"},
    {"id": "gemini-3.1-flash-lite", "provider": "google-ai-studio", "tier": "live-verified", "label": "Google Gemini 3.1 Flash-Lite (Tezkor)"},
    {"id": "llm7/default", "provider": "llm7-keyless", "tier": "free-unlimited", "label": "LLM7 Default (Mistral Nemo • Cheksiz)"},
    {"id": "llm7/fast", "provider": "llm7-keyless", "tier": "free-unlimited", "label": "LLM7 Fast (Codestral • Cheksiz)"},
    {"id": "llm7/gpt-oss:20b", "provider": "llm7-keyless", "tier": "free-unlimited", "label": "LLM7 GPT-OSS 20B (Cheksiz)"},
    {"id": "llm7/codestral-latest", "provider": "llm7-keyless", "tier": "free-unlimited", "label": "LLM7 Codestral Latest (Cheksiz)"},
    {"id": "kilo-gateway/kilo-auto/free", "provider": "kilo-keyless", "tier": "free-unlimited", "label": "Kilo Gateway Auto Free (Cheksiz)"},
    {"id": "kilo-gateway/baidu/ernie-5.5-flash-preview:free", "provider": "kilo-keyless", "tier": "free-unlimited", "label": "Kilo ERNIE 5.5 Flash (Cheksiz)"},
    {"id": "gemini-3.6-flash", "provider": "google-ai-studio", "tier": "free-pool", "label": "Google Gemini 3.6 Flash"},
    {"id": "gemini-3.7-flash", "provider": "google-ai-studio", "tier": "free-pool", "label": "Google Gemini 3.7 Flash"},
    {"id": "gemini-3.8-flash", "provider": "google-ai-studio", "tier": "free-pool", "label": "Google Gemini 3.8 Flash"},
    {"id": "gemini-3.5-flash", "provider": "google-ai-studio", "tier": "free-pool", "label": "Google Gemini 3.5 Flash"},
    {"id": "ovhcloud/Mistral-Small-3.2-24B-Instruct-2506", "provider": "ovhcloud-keyless", "tier": "free-unlimited", "label": "OVHcloud Mistral-Small 3.2 24B"},
]

KEYLESS_MODEL_MAP: dict[str, tuple[str, str, str]] = {
    "llm7/default": ("https://api.llm7.io/v1/chat/completions", "unused", "default"),
    "llm7/fast": ("https://api.llm7.io/v1/chat/completions", "unused", "fast"),
    "llm7/gpt-oss:20b": ("https://api.llm7.io/v1/chat/completions", "unused", "gpt-oss:20b"),
    "llm7/codestral-latest": ("https://api.llm7.io/v1/chat/completions", "unused", "codestral-latest"),
    "kilo-gateway/kilo-auto/free": ("https://api.kilo.ai/api/gateway/chat/completions", "", "kilo-auto/free"),
    "kilo-gateway/baidu/ernie-5.5-flash-preview:free": ("https://api.kilo.ai/api/gateway/chat/completions", "", "baidu/ernie-5.5-flash-preview:free"),
    "ovhcloud/Mistral-Small-3.2-24B-Instruct-2506": (
        "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions",
        "",
        "Mistral-Small-3.2-24B-Instruct-2506",
    ),
}

GEMINI_ACTIVE_POOL = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.7-flash",
    "gemini-3.8-flash",
    "gemini-3.5-flash",
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
        requested = str(body.get("model") or "auto").strip()
        strict_model = bool(body.get("strict_model", False))
        sys_txt, usr_txt, media_b64, mime_type = _extract_system_and_user(messages)
        if not usr_txt:
            return web.json_response({"error": "empty prompt"}, status=400)

        def _ok_resp(model_label: str, text: str) -> web.Response:
            _STATS["success_total"] += 1
            _STATS["last_model_used"] = model_label
            return web.json_response({
                "id": f"omni-{int(time.time()*1000)}",
                "object": "chat.completion",
                "model": model_label,
                "requested_model": requested,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
            })

        async def _try_gemini(gm: str, t_sec: float = 8.0) -> str | None:
            if not gem_client:
                return None
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

                inter = await asyncio.wait_for(asyncio.to_thread(_call_g), timeout=t_sec)
                out_txt = (getattr(inter, "output_text", None) or "").strip()
                if out_txt:
                    _COOLDOWN_UNTIL.pop(gm, None)
                    return out_txt
            except Exception as exc:
                _COOLDOWN_UNTIL[gm] = time.monotonic() + 180.0
                log.debug("OmniRoute Gemini (%s) skip: %s", gm, exc)
            return None

        async def _try_keyless(label: str, t_sec: float = 9.0) -> str | None:
            if media_b64 or label not in KEYLESS_MODEL_MAP:
                return None
            target_url, bearer_key, model_id = KEYLESS_MODEL_MAP[label]
            try:
                headers = {"Content-Type": "application/json"}
                if bearer_key:
                    headers["Authorization"] = f"Bearer {bearer_key}"
                async with httpx.AsyncClient(timeout=t_sec) as client:
                    r = await client.post(
                        target_url,
                        headers=headers,
                        json={
                            "model": model_id,
                            "messages": [
                                {"role": "system", "content": sys_txt or "Sen XAN SHOP AI mutaxassisan."},
                                {"role": "user", "content": usr_txt},
                            ],
                            "temperature": 0.4,
                            "max_tokens": 1200,
                        },
                    )
                    if r.status_code == 200:
                        d = r.json()
                        choices = d.get("choices") or []
                        msg = (choices[0].get("message") or {}) if choices and isinstance(choices[0], dict) else {}
                        txt = str(msg.get("content") or "").strip()
                        if txt and not txt.startswith("<|start|>"):
                            _COOLDOWN_UNTIL.pop(label, None)
                            return txt
                    _COOLDOWN_UNTIL[label] = time.monotonic() + 90.0
            except Exception as exc:
                _COOLDOWN_UNTIL[label] = time.monotonic() + 90.0
                log.debug("OmniRoute Keyless (%s) skip: %s", label, exc)
            return None

        async def _try_openrouter(orm: str) -> str | None:
            if not openrouter_key or media_b64:
                return None
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    r = await client.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers={"Authorization": f"Bearer {openrouter_key}"},
                        json={"model": orm, "messages": messages, "temperature": 0.4},
                    )
                    if r.status_code == 200:
                        data = r.json()
                        choices = data.get("choices") or []
                        msg = (choices[0].get("message") or {}) if choices and isinstance(choices[0], dict) else {}
                        txt = str(msg.get("content") or "").strip()
                        if txt:
                            return txt
            except Exception as exc:
                log.debug("OmniRoute OpenRouter (%s) skip: %s", orm, exc)
            return None

        # 0. Agar foydalanuvchi aniq model tanlagan bo'lsa (auto / xanshop-auto dan tashqari), BIRINCHI uni sinaymiz!
        is_explicit = requested and requested not in ("auto", "xanshop-auto")
        tried_gemini = False
        if is_explicit:
            direct_txt: str | None = None
            if requested.startswith("gemini-"):
                tried_gemini = True
                direct_txt = await _try_gemini(requested, t_sec=6.5)
            elif requested in KEYLESS_MODEL_MAP:
                direct_txt = await _try_keyless(requested, t_sec=11.0)
            elif requested.startswith("llm7/"):
                KEYLESS_MODEL_MAP[requested] = ("https://api.llm7.io/v1/chat/completions", "unused", requested.split("/", 1)[1])
                direct_txt = await _try_keyless(requested, t_sec=11.0)
            elif openrouter_key:
                direct_txt = await _try_openrouter(requested)

            if direct_txt:
                return _ok_resp(requested, direct_txt)
            if strict_model:
                return web.json_response({"error": f"Tanlangan model ({requested}) hozir band yoki javob bermadi"}, status=503)

        # 1. Google Gemini Active Pool (faqat 1 ta sog'lom tezkor model — agar Gemini sekin/503 bo'lsa darhol keyless'ga o'tadi!)
        if gem_client and not tried_gemini and not (is_explicit and requested in KEYLESS_MODEL_MAP):
            now = time.monotonic()
            active_gem = [m for m in GEMINI_ACTIVE_POOL if _COOLDOWN_UNTIL.get(m, 0.0) <= now]
            for gm in active_gem[:1]:
                out_txt = await _try_gemini(gm, t_sec=5.5)
                if out_txt:
                    return _ok_resp(gm, out_txt)

        # 2. OpenRouter Free Models Pool (if OPENROUTER_API_KEY configured)
        if openrouter_key and not media_b64:
            for orm in ("deepseek/deepseek-chat-v3-0324:free", "deepseek/deepseek-r1:free", "meta-llama/llama-3.3-70b-instruct:free", "qwen/qwen3-235b-a22b:free"):
                out_txt = await _try_openrouter(orm)
                if out_txt:
                    return _ok_resp(orm, out_txt)

        # 3. OmniRoute Keyless Free AI Pool (parallel race across ALL distinct free providers — 2-5s failover!)
        if not media_b64:
            now = time.monotonic()
            keyless_order = [
                "kilo-gateway/baidu/ernie-5.5-flash-preview:free",
                "ovhcloud/Mistral-Small-3.2-24B-Instruct-2506",
                "kilo-gateway/kilo-auto/free",
                "llm7/default",
                "llm7/fast",
                "llm7/gpt-oss:20b",
            ]
            healthy_k = [
                k for k in keyless_order
                if _COOLDOWN_UNTIL.get(k, 0.0) <= now and not (is_explicit and k == requested)
            ]
            for k in keyless_order:
                if k not in healthy_k and not (is_explicit and k == requested):
                    healthy_k.append(k)

            # Race up to 5 candidates concurrently so even under burst load one answers in ~2-6s!
            batch = healthy_k[:5]
            if batch:
                async def _run_labeled(lbl: str) -> tuple[str, str | None]:
                    return lbl, await _try_keyless(lbl, t_sec=11.0)

                tasks = [asyncio.create_task(_run_labeled(lbl)) for lbl in batch]
                try:
                    for fut in asyncio.as_completed(tasks):
                        lbl, out_txt = await fut
                        if out_txt:
                            for t in tasks:
                                if not t.done():
                                    t.cancel()
                            return _ok_resp(lbl, out_txt)
                finally:
                    for t in tasks:
                        if not t.done():
                            t.cancel()

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
