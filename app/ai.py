"""Sotuvchi & Stilist AI (Gemini Interactions API).

Ham Sotuv Botda, ham Haqiqiy Shaxsiy Telegram Akkauntda (Userbot) ishlaydi.
Matn, rasm (Instagram skrinshot) va ovozli xabarlarni (multimodal) tushunadi.
"""
import asyncio
import base64
from html import escape
import json
import logging
import time
from typing import Any

import httpx
from google import genai

from .config import Settings
from .pricing import fmt
from .texts import STATUS_LABELS, look_50_values, look_items

log = logging.getLogger(__name__)
ADMIN_TAG = "[ADMIN]"
GEMINI_FALLBACK_MODELS = (
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
)
GEMINI_EXTENDED_POOL = (
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.7-flash",
    "gemini-3.8-flash",
    "gemini-3.5-flash",
)
FREE_OPENROUTER_MODELS = (
    "deepseek/deepseek-chat-v3-0324:free",
    "deepseek/deepseek-r1:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen3-235b-a22b:free",
)
FREE_OMNIROUTE_KEYLESS_ENDPOINTS = (
    ("kilo-gateway/kilo-auto/free", "https://api.kilo.ai/api/gateway", "", "kilo-auto/free"),
    ("ovhcloud/Mistral-Small-3.2-24B-Instruct-2506", "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1", "", "Mistral-Small-3.2-24B-Instruct-2506"),
    ("kilo-gateway/baidu/ernie-5.5-flash-preview:free", "https://api.kilo.ai/api/gateway", "", "baidu/ernie-5.5-flash-preview:free"),
    ("llm7/default", "https://api.llm7.io/v1", "unused", "default"),
    ("llm7/fast", "https://api.llm7.io/v1", "unused", "fast"),
    ("llm7/gpt-oss:20b", "https://api.llm7.io/v1", "unused", "gpt-oss:20b"),
    ("llm7/codestral-latest", "https://api.llm7.io/v1", "unused", "codestral-latest"),
)
_MODEL_COOLDOWN_UNTIL: dict[str, float] = {}


def extract_json_dict(raw_text: str) -> dict[str, Any] | None:
    """AI javobidan ```json ... ``` yoki oddiy JSON obyektni xavfsiz ajratib oladi."""
    txt = (raw_text or "").strip()
    if not txt:
        return None
    if "```json" in txt:
        txt = txt.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in txt:
        txt = txt.split("```", 1)[1].split("```", 1)[0].strip()
    try:
        parsed = json.loads(txt)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        start = txt.find("{")
        end = txt.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(txt[start : end + 1])
                return parsed if isinstance(parsed, dict) else None
            except Exception:
                return None
    return None


def build_system_prompt(
    s: Settings,
    looks: list[dict],
    orders: list[dict],
    is_personal_account: bool = False,
) -> str:
    catalog = []
    for lk in looks:
        lk_items = look_items(lk)
        item_details: list[str] = []
        for it in lk_items:
            parts = [str(it.get("name") or "Buyum")]
            st_cols = it.get("store_colors") or []
            if st_cols:
                parts.append(f"do'kon ranglari: {', '.join(st_cols)}")
            st_sz = it.get("store_sizes") or []
            if st_sz:
                parts.append(f"do'kon razmerlari: {', '.join(st_sz)}")
            if it.get("fit_note"):
                parts.append(f"bichim izohi: {it['fit_note']}")
            sch = it.get("size_chart") or []
            if isinstance(sch, list) and sch:
                rows_txt = "; ".join(
                    f"{r.get('size')}: {r.get('height_cm','')}"
                    + (f"sm/{r.get('weight_kg')}kg" if r.get("weight_kg") else "")
                    + (f"/oyoq {r.get('foot_cm')}sm" if r.get("foot_cm") else "")
                    for r in sch[:6]
                    if isinstance(r, dict) and r.get("size")
                )
                if rows_txt:
                    parts.append(f"do'kon jadvali [{rows_txt}]")
            item_details.append(" (" + " | ".join(parts[1:]) + ")" if len(parts) > 1 else "")
            item_details[-1] = parts[0] + item_details[-1]
        p50, rem50 = look_50_values(lk)
        catalog.append(
            f"- Look #{lk['id']} \"{lk['title']}\": {'; '.join(item_details)}. Jami narx (100%): {fmt(lk['prepay_uzs'])} so'm. "
            f"50% oldindan to'lov: {fmt(p50)} so'm (qolgan 50%: {fmt(rem50)} so'm). "
            f"Kargo taxminan {fmt(lk['cargo_est_uzs'])} so'm ({lk['weight_kg']} kg). "
            f"Asosiy stilist ranglari (rasmdagidek): {lk['colors'] or 'rasmdagidek'}. "
            f"Kiyim razmerlari: {lk['sizes'] or 'M, L, XL, 2XL'}."
        )
    my_orders = [
        f"- #{o['id']}: {STATUS_LABELS.get(o['status'], o['status'])}"
        + (f", trek {o['tracking']}" if o.get("tracking") else "")
        for o in orders
    ]

    if is_personal_account:
        mode_instructions = f"""MULOQOT REJIMI (HAQIQIY SHAXSIY TELEGRAM PROFIL — STILIST MENEJER):
- Sen bot emassan! Sen "{s.shop_name}" do'konining bosh stilist-menejerisan (jonli inson sifatida yozasan).
- Mijoz Look rasmini ko'rmoqchi bo'lsa, javobing oxiriga [SHOW_LOOK:id] (masalan [SHOW_LOOK:1]) tegini qo'sh — tizim o'sha Look rasmini avtomatik yuboradi.
- Mijoz buyurtma bermoqchi bo'lsa, undan muloyimlik bilan:
  1) Bo'yi va vaznini (yoki razmerini) hamda rangini,
  2) To'lov rejasini (50% oldindan yoki 100% to'liq),
  3) Ism-familiyasi, telefon raqami va yetkazish manzilini so'ra.
- Barcha ma'lumotni olgach, javobing oxiriga AYNAN mana bu tegni qo'sh (tizim avtomatik buyurtma yaratib karta raqamni chiqaradi):
  [ORDER:look_id=1|size=XL|color=Qora|plan=50|name=Ism|phone=+998901234567|address=Manzil]"""
    else:
        mode_instructions = """MULOQOT REJIMI (SOTUV BOT):
- Buyurtma berish uchun mijozga "🛍 Looklar" tugmasini bosib, look ostidagi "🛒 Buyurtma berish" ni bosishni ayt."""

    return f"""Sen "{s.shop_name}" onlayn erkaklar kiyimi brendining 10 yillik tajribaga ega V3 Bosh Stilist-Konsultantisan.
Mijoz qaysi tilda yozsa (o'zbek, rus), o'sha tilda qisqa, samimiy, ekspert darajasida va 100% halol javob ber.
Bosh maqsading: Mijozga shunchaki kiyim sotish emas, balki kiyim 5–12 kunda qo'liga yetib borganda u matosi, bichimi va razmeridan 100% rozi bo'lishini ta'minlash!

DO'KON, HALOL SIFAT VA TO'LOV TARTIBI (50% / 100% MODELI):
- Tayyor looklar (2, 3, 4 yoki 5 qismli kapsula to'plamlar) Pinduoduo / Taobao'dagi tekshirilgan fabrikalardan keltiriladi va Xitoy omborimizda jo'natishdan oldin sifat nazoratidan (QC) o'tadi.
- TO'LOV 2 XIL (mijoz ixtiyoriy tanlaydi, rasmiy HUMO karta: {s.card_number} — {s.card_owner}):
  1) 50% OLDINDAN TO'LOV (0% Xavf): Mijoz hozir faqat 50% to'laydi. Qolgan 50% tovar narxini + kargo pulini (12 000 so'm / 100 gr = {fmt(s.cargo_client_uzs_per_kg)} so'm/kg) buyurtma Toshkentga yetib kelib, sifatini ko'rganda to'laydi!
  2) 100% TO'LIQ TO'LOV: Mijoz hozir 100% tovar narxini to'laydi, yuk Toshkentga kelganda faqat kargo pulini (12 000 so'm / 100 gr) to'laydi.
- Yetkazish: {s.delivery_text} (5–12 kun Avia). Har bir bosqich haqida avtomatik xabar beriladi.
- O'LCHAM VA BICHIM QOIDASI (ALOHIDA RAZMERLAR + DO'KON JADVALI):
  • Lookdagi 3 ta turkum uchun ALOHIDA razmer tanlanadi: 1) Ust kiyim (kurtka, palto, sviter, xudi), 2) Shim (kargo, klassik, jinsi), 3) Oyoq kiyim (etik, lofer, krossovka).
  • MUHIM: OYOQ KIYIM HECH QACHON BO'Y VA VAZNGA QARAB TAXMIN QILINMAYDI! Oyoq kiyim uchun faqat mijozning o'zi kiyadigan oyoq razmerini (38–46) yoki oyoq uzunligini (sm) so'ra.
  • Ust kiyim va shim uchun birinchi navbatda yuqoridagi KATALOGda aynan o'sha mahsulot yonida berilgan do'kon razmer jadvali va bichim izohiga tayan!
  • QISHKI TASHQI KIYIM VA "1 RAZMER KATTA" QOIDASI: Asosan kiyimlarda (ayniqsa qishki tashqi kiyim — palto/kurtkada ichidan qalin sviter kiyilishini hisobga olib) FAQAT do'kon izohida "biroz tor / 1 razmer kattasini oling" deyilgan bo'lsa (yoki qishki qalin tashqi kiyimda ixtiyoriy maslahat sifatida) mijozga samimiy inson kabi tushuntir. Oyoq kiyim yoki odatiy kiyimlarga asossiz +1 razmer qo'shib yuborma!
  • Agar do'kon jadvali berilmagan bo'lsa, Osiyo/Xitoy umumiy jadvalidan foydalan: 160–170 sm / 50–62 kg → M; 170–176 sm / 63–72 kg → L; 175–182 sm / 73–82 kg → XL; 180–190 sm / 83–96 kg → 2XL.
- RANG TANLOVI VA 10 YILLIK COLOR-GRADING STILIST TAMOYILI:
  • Har bir lookning rasmdagi rang uyg'unligi bizning 10 yillik tajribali color-grading stilistimiz tomonidan maxsus terilgan.
  • Mijozga avval aynan stilistimiz tanlagan rasmdagi ranglar uyg'unligini birinchi raqamli tavsiya sifatida ayt; do'kondagi boshqa ranglarni esa faqat ixtiyoriy taklif sifatida bildir (masalan: "Stilistimiz rang uyg'unligi uchun aynan rasmdagi variantni tavsiya qilgan, lekin xohlasangiz do'konda shu buyumning boshqa ranglari ham bor").

KATALOG (faqat shu looklar va narxlar mavjud):
{chr(10).join(catalog) or "- Hozircha katalog bo'sh"}

MIJOZNING BUYURTMALARI:
{chr(10).join(my_orders) or "- Buyurtma yo'q"}

{mode_instructions}

QOIDALAR:
- Chegirma va'da qilma, katalogda yo'q narsani bor dema.
- JUDA MUHIM: Mijoz "to'lov qildim", "pul tashladim", "o'tkazdim" deb yozsa HAM, HECH QACHON "to'lov tasdiqlandi", "qabul qilindi", "rasmiylashtirildi" DEMA! Agar MIJOZNING BUYURTMALARI ro'yxatida status hali "Oldindan to'lov kutilmoqda" yoki "To'lov tekshirilmoqda" bo'lsa, faqat to'lov chekini (skrinshot/rasm) yuborishni so'ra va chek tekshirilgandan keyin tasdiqlanishini ayt.
- Shikoyat, nuqsonli tovar, pul qaytarish yoki javobini bilmagan murakkab savol bo'lsa — katta menejer hozir bog'lanishini ayt va javob oxiriga {ADMIN_TAG} qo'sh.
- Javob 600 belgidan oshmasin. Markdown (** yoki ##) ishlatma."""


async def check_omniroute_status(
    base_url: str = "http://localhost:20128/v1",
    api_key: str = "omniroute-local",
) -> dict[str, Any]:
    """Lokal OmniRoute shlyuzi (http://localhost:20128) ishlayotganini va mavjud modellarni tekshiradi."""
    base = base_url.rstrip("/")
    root = base[:-3] if base.endswith("/v1") else base
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            health_resp = await client.get(f"{root}/api/health")
            if health_resp.status_code == 200:
                models: list[str] = []
                model_items: list[dict[str, Any]] = []
                try:
                    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
                    m_resp = await client.get(f"{base}/models", headers=headers)
                    if m_resp.status_code == 200:
                        data = m_resp.json()
                        for m in data.get("data", []):
                            if isinstance(m, dict) and m.get("id"):
                                models.append(str(m["id"]))
                                model_items.append(m)
                except Exception:
                    pass
                return {
                    "online": True,
                    "base_url": base,
                    "dashboard_url": f"{root}/dashboard",
                    "models_count": len(models),
                    "sample_models": models[:8],
                    "models": model_items,
                }
    except Exception:
        pass
    return {
        "online": False,
        "base_url": base,
        "dashboard_url": f"{root}/dashboard",
        "models_count": 0,
        "sample_models": [],
        "models": [],
    }


class SalesAI:
    def __init__(self, s: Settings):
        self.model = s.gemini_model
        # Google SDK min deadline >= 10s; 35s allows multimodal audio+grid analysis without premature 12s cutoff
        self.client = (
            genai.Client(
                api_key=s.gemini_api_key,
                http_options={"timeout": 35000, "retry_options": {"attempts": 1}},
            )
            if s.gemini_api_key
            else None
        )
        # Tier-1: OmniRoute Lokal AI Gateway (380 provayder, bepul tierlar & auto-fallback)
        self.use_omniroute = bool(getattr(s, "use_omniroute", True))
        self.omniroute_base_url = getattr(s, "omniroute_base_url", "http://localhost:20128/v1").strip().rstrip("/")
        self.omniroute_api_key = getattr(s, "omniroute_api_key", "omniroute-local").strip() or "omniroute-local"
        self.omniroute_model = getattr(s, "omniroute_model", "auto").strip() or "auto"
        # Tier-2: OpenRouter Cloud Token Routing
        self.openrouter_api_key = getattr(s, "openrouter_api_key", "").strip()
        self.openrouter_model = getattr(s, "openrouter_model", "deepseek/deepseek-chat").strip()
        self.openrouter_base_url = getattr(s, "openrouter_base_url", "https://openrouter.ai/api/v1").strip().rstrip("/")
        self.last_provider_used: str = "init"
        self._last_compat_model: str = ""

    @property
    def enabled(self) -> bool:
        return (self.client is not None) or bool(self.openrouter_api_key) or self.use_omniroute

    def _gemini_model_candidates(self, preferred: str | None = None) -> list[str]:
        candidates: list[str] = []
        ordered = (preferred, self.model, *GEMINI_FALLBACK_MODELS) if preferred else (self.model, *GEMINI_FALLBACK_MODELS)
        for m in ordered:
            name = (m or "").strip()
            if name and name not in candidates:
                candidates.append(name)
        return candidates

    async def _call_openai_compat(
        self,
        base_url: str,
        api_key: str,
        model: str,
        system: str,
        text: str,
        media_bytes: bytes | None = None,
        mime_type: str = "",
        timeout_sec: float = 25.0,
    ) -> str | None:
        """OmniRoute yoki OpenRouter (OpenAI-compatible) endpointidan javob oladi."""
        url = f"{base_url}/chat/completions"
        headers = {
            "HTTP-Referer": "https://xanshop.uz",
            "X-Title": "XAN SHOP AI Office",
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        user_content: Any = text
        if media_bytes and mime_type and mime_type.startswith("image/"):
            b64 = base64.b64encode(media_bytes).decode("utf-8")
            user_content = [
                {"type": "text", "text": text},
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}},
            ]
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.4,
            "max_tokens": 1500,
        }
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_sec, connect=2.5)) as http_client:
                resp = await http_client.post(url, json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    self._last_compat_model = str(data.get("model") or model)
                    choices = data.get("choices") or []
                    if choices and isinstance(choices[0], dict):
                        content = str((choices[0].get("message") or {}).get("content") or "").strip()
                        if content and not content.startswith("<|start|>"):
                            return content
                log.debug("Gateway %s status %s: %s", base_url, resp.status_code, resp.text[:160])
        except Exception as e:
            log.debug("Gateway %s ulanmadi: %s", base_url, e)
        return None

    def _create(
        self,
        system: str,
        text: str,
        previous_id: str | None,
        media_bytes: bytes | None = None,
        mime_type: str = "",
        model_override: str | None = None,
    ):
        input_payload: Any = text
        if media_bytes and mime_type:
            media_type = "audio" if mime_type.startswith("audio/") else "image"
            input_payload = [
                {"type": "text", "text": text},
                {
                    "type": media_type,
                    "data": base64.b64encode(media_bytes).decode("utf-8"),
                    "mime_type": mime_type,
                },
            ]
        kwargs = dict(model=model_override or self.model, system_instruction=system, input=input_payload)
        if previous_id:
            kwargs["previous_interaction_id"] = previous_id
        return self.client.interactions.create(**kwargs)

    async def _call_gemini_models(
        self,
        system: str,
        text: str,
        previous_id: str | None = None,
        media_bytes: bytes | None = None,
        mime_type: str = "",
        timeout_sec: float = 16.0,
        preferred_model: str | None = None,
    ) -> tuple[str | None, str | None]:
        """Birlamchi va zaxira Gemini modellarini timeout va cooldown nazorati bilan sinaydi."""
        if not self.client:
            return None, None
        candidates = self._gemini_model_candidates(preferred=preferred_model)
        is_real_client = isinstance(self.client, genai.Client)
        if is_real_client:
            for ext_m in GEMINI_EXTENDED_POOL:
                if ext_m not in candidates:
                    candidates.append(ext_m)
            now = time.monotonic()
            active = [c for c in candidates if _MODEL_COOLDOWN_UNTIL.get(c, 0.0) <= now]
            candidates = active[:2] if active else []
            timeout_sec = min(timeout_sec, 9.0)

        for idx, candidate in enumerate(candidates):
            use_prev = previous_id if idx == 0 else None
            attempts = (use_prev, None) if use_prev else (None,)
            candidate_failed = True
            for prev_token in attempts:
                try:
                    inter = await asyncio.wait_for(
                        asyncio.to_thread(
                            self._create,
                            system,
                            text,
                            prev_token,
                            media_bytes,
                            mime_type,
                            candidate,
                        ),
                        timeout=timeout_sec,
                    )
                    out = (getattr(inter, "output_text", None) or "").strip()
                    if out:
                        self.last_provider_used = f"Gemini ({candidate})"
                        _MODEL_COOLDOWN_UNTIL.pop(candidate, None)
                        candidate_failed = False
                        return out, getattr(inter, "id", None)
                except Exception as e:
                    log.warning("Gemini modeli (%s) zaxiraga o'tdi (%s): %s", candidate, type(e).__name__, e)
            if candidate_failed and is_real_client:
                _MODEL_COOLDOWN_UNTIL[candidate] = time.monotonic() + 180.0
        return None, None

    async def _call_providers(
        self,
        system: str,
        text: str,
        previous_id: str | None = None,
        media_bytes: bytes | None = None,
        mime_type: str = "",
        timeout_sec: float = 16.0,
        model_override: str | None = None,
    ) -> tuple[str | None, str | None]:
        """3 bosqichli avto-zaxira zanjiri: OmniRoute -> OpenRouter -> Google Gemini -> Keyless Pool."""
        import os

        req_model = (model_override or "").strip()
        is_explicit = bool(req_model and req_model not in ("auto", "xanshop-auto"))

        if self.use_omniroute and self.omniroute_base_url:
            omni_target = req_model or self.omniroute_model
            omni_resp = await self._call_openai_compat(
                self.omniroute_base_url,
                self.omniroute_api_key,
                omni_target,
                system,
                text,
                media_bytes,
                mime_type,
                timeout_sec=max(26.0, timeout_sec),
            )
            if omni_resp and omni_resp.strip():
                used_m = self._last_compat_model or omni_target
                self.last_provider_used = f"OmniRoute ({used_m})"
                return omni_resp.strip(), None

        # Agar OmniRoute ishlamay turgan bo'lsa va foydalanuvchi aniq keyless model tanlagan bo'lsa, to'g'ridan-to'g'ri chaqiramiz
        if is_explicit and not os.getenv("PYTEST_CURRENT_TEST") and not media_bytes:
            for label, base_u, key_u, mod_u in FREE_OMNIROUTE_KEYLESS_ENDPOINTS:
                if req_model == label or req_model == mod_u:
                    free_resp = await self._call_openai_compat(
                        base_u, key_u, mod_u, system, text, None, "", timeout_sec=min(15.0, timeout_sec)
                    )
                    if free_resp and free_resp.strip():
                        self.last_provider_used = f"OmniRouteFree ({label})"
                        return free_resp.strip(), None
            if req_model.startswith("llm7/"):
                sub_m = req_model.split("/", 1)[1]
                free_resp = await self._call_openai_compat(
                    "https://api.llm7.io/v1", "unused", sub_m, system, text, None, "", timeout_sec=min(15.0, timeout_sec)
                )
                if free_resp and free_resp.strip():
                    self.last_provider_used = f"OmniRouteFree ({req_model})"
                    return free_resp.strip(), None

        if self.openrouter_api_key:
            or_list = ([req_model] if is_explicit and "/" in req_model else []) + [self.openrouter_model, *FREE_OPENROUTER_MODELS]
            for or_m in dict.fromkeys(m for m in or_list if m):
                or_resp = await self._call_openai_compat(
                    self.openrouter_base_url,
                    self.openrouter_api_key,
                    or_m,
                    system,
                    text,
                    media_bytes,
                    mime_type,
                    timeout_sec=min(16.0, timeout_sec),
                )
                if or_resp and or_resp.strip():
                    self.last_provider_used = f"OpenRouter ({or_m})"
                    return or_resp.strip(), None

        gem_pref = req_model if (is_explicit and req_model.startswith("gemini-")) else None
        gem_out, gem_id = await self._call_gemini_models(
            system,
            text,
            previous_id=previous_id,
            media_bytes=media_bytes,
            mime_type=mime_type,
            timeout_sec=timeout_sec,
            preferred_model=gem_pref,
        )
        if gem_out:
            return gem_out, gem_id

        # Tier-4: OmniRoute Keyless Free Providers Pool (parallel race across LLM7, Kilo Gateway, OVHcloud)
        if not os.getenv("PYTEST_CURRENT_TEST") and not media_bytes:
            async def _race_one(lbl: str, b_u: str, k_u: str, m_u: str) -> tuple[str, str | None]:
                r = await self._call_openai_compat(b_u, k_u, m_u, system, text, None, "", timeout_sec=min(11.0, timeout_sec))
                return lbl, r

            tasks = [asyncio.create_task(_race_one(l, b, k, m)) for l, b, k, m in FREE_OMNIROUTE_KEYLESS_ENDPOINTS[:5]]
            try:
                for fut in asyncio.as_completed(tasks):
                    lbl, free_resp = await fut
                    if free_resp and free_resp.strip():
                        for t in tasks:
                            if not t.done():
                                t.cancel()
                        self.last_provider_used = f"OmniRouteFree ({lbl})"
                        return free_resp.strip(), None
            finally:
                for t in tasks:
                    if not t.done():
                        t.cancel()
        return None, None

    async def ask_json(
        self,
        prompt: str,
        *,
        system: str = "",
        media_bytes: bytes | None = None,
        mime_type: str = "",
        timeout_sec: float = 16.0,
        model_override: str | None = None,
    ) -> dict[str, Any] | None:
        """Skaut, Tahlilchi va AI Hisobchi uchun OmniRoute/OpenRouter/Gemini orqali toza JSON oladi."""
        sys_prompt = system or (
            "Sen XAN SHOP tizimidagi aniq va professional AI mutaxassissan. "
            "Faqat so'ralgan formatdagi toza JSON obyektini qaytar."
        )
        raw, _ = await self._call_providers(
            sys_prompt,
            prompt,
            previous_id=None,
            media_bytes=media_bytes,
            mime_type=mime_type,
            timeout_sec=timeout_sec,
            model_override=model_override,
        )
        return extract_json_dict(raw or "")

    async def reply(
        self,
        system: str,
        text: str,
        previous_id: str | None,
        media_bytes: bytes | None = None,
        mime_type: str = "",
        model_override: str | None = None,
    ) -> tuple[str | None, str | None, bool]:
        """(javob matni HTML-xavfsiz, interaction_id, operator kerakmi).
        3 bosqichli avto-zaxira zanjiri: OmniRoute -> OpenRouter -> Google Gemini.
        """
        raw, inter_id = await self._call_providers(
            system,
            text,
            previous_id=previous_id,
            media_bytes=media_bytes,
            mime_type=mime_type,
            timeout_sec=18.0,
            model_override=model_override,
        )
        if not raw:
            return None, None, True
        need_admin = ADMIN_TAG in raw
        answer = raw.replace(ADMIN_TAG, "").strip()
        return escape(answer) or None, inter_id, need_admin
