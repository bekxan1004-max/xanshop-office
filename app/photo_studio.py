"""XAN SHOP — Photoshop Studio AI Agent (Nano Banana Image-to-Image Fotostudiya).

Vazifasi:
  1. Pinduoduo Tahlilchi (skaut) yuborgan real mahsulot rasmi va aniq mahsulot promptini qabul qiladi.
  2. Instagram Tahlilchi (insta_analyst) videolarni va viral rasmlarni tahlil qilib shakllantirgan
     tabiiy turish (pose/drape/lighting) ko'rsatmasini promptga birlashtiradi.
  3. Gemini Nano Banana (`gemini-nano-banana-2.1` -> `gemini-3.1-flash-lite-image` -> `gemini-3-pro-image`)
     orqali rasmni QAYTA STUDIYA SIFATIDA ISHLAB CHIQARADI:
       - Mahsulotning o'zi (matosi, rangi, choklari, tugma/zamok, cho'ntak, logotip va fasoni)
         100% O'ZGARMASDAN aynan o'zidek saqlanadi!
       - Odam yuzi, boshi, qo'llari, oyoqlari, kiyimdan tashqari poyabzal, orqa fon, ilgich,
         reklama yozuvlari va xitoycha belgilar BUTUNLAY olib tashlanadi.
       - Mahsulot xuddi professional ghost-mannequin / editorial fotostudiyada suratga olingandek
         tabiiy, toza va hajmli ko'rinishda chiqadi.
  4. Kesh (`data/studio_cache/`) va xavfsiz zaxira (AI cutout) bilan 24/7 barqaror ishlaydi.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageEnhance, ImageFilter

from .config import Settings
from .cutout_agent import extract_main_item, guess_category

log = logging.getLogger(__name__)

STUDIO_CACHE_DIR = Path("data/studio_cache")
STUDIO_MODELS = (
    "gemini-nano-banana-2.1",
    "gemini-3.1-flash-lite-image",
    "gemini-3-pro-image",
)
_STUDIO_COOLDOWN_UNTIL: float = 0.0

DEFAULT_INSTA_POSE_DIRECTIONS: dict[str, str] = {
    "outerwear": (
        "Front-facing luxury editorial ghost-mannequin / flat-lay presentation: jacket/coat naturally structured "
        "with crisp standing collar, balanced natural shoulder volume, relaxed sleeves angled slightly inward "
        "like high-end Zara/Massimo Dutti Instagram lookbooks, soft directional top-left studio lighting."
    ),
    "top": (
        "Clean minimalist flat-lay / subtle 3D ghost-mannequin posture: neat natural neckline and collar drape, "
        "soft natural fabric folds along the torso and sleeves, centered symmetric luxury menswear magazine styling."
    ),
    "bottom": (
        "Full-length straight vertical ghost-mannequin / flat-lay presentation of ONLY the trousers/jeans: "
        "clean natural waistband (no cut-off waist gap), crisp vertical leg drape with subtle natural hem fall, "
        "completely removing any shoes, socks, or human feet/legs at the bottom."
    ),
    "shoes": (
        "Clean luxury sneaker/footwear editorial studio shot: pair of shoes positioned at an appealing dynamic "
        "3/4 side-and-front profile angle (one slightly angled forward) showing sole profile, upper texture, and stitching clearly."
    ),
    "accessory": (
        "Luxury editorial still-life studio staging: accessory (watch, leather belt, sunglasses, scarf, bag, or cap) "
        "centered cleanly at a natural hero angle with crisp metallic/leather specular highlights and realistic gentle surface depth."
    ),
}


@dataclass
class StudioRenderResult:
    image: Image.Image
    used_nano_banana: bool
    model_used: str
    prompt_used: str
    cache_hit: bool = False


def derive_insta_pose_direction(ig_intel: dict[str, Any] | None, category: str = "") -> str:
    """Instagram Tahlilchi videolardan/rasmlardan o'rgangan kiyim turish (pose/drape/lighting) uslubini qaytaradi."""
    cat = (category or "").lower()
    base = DEFAULT_INSTA_POSE_DIRECTIONS.get(cat) or DEFAULT_INSTA_POSE_DIRECTIONS["top"]
    if not ig_intel or not isinstance(ig_intel, dict):
        return base

    halol = ig_intel.get("halol_ogri") or {}
    custom_pose = str(halol.get("studio_pose_direction") or "").strip()
    playbooks = ig_intel.get("learned_playbooks") or {}
    vp = playbooks.get("video_editing_blueprint") or {}
    visual_mix = str(vp.get("visual_mix") or "").strip()
    style_hint = str(halol.get("recommended_video_style") or "").strip()

    extras: list[str] = []
    if custom_pose:
        extras.append(custom_pose)
    if visual_mix and len(visual_mix) < 160:
        extras.append(f"Instagram trend reference: {visual_mix}.")
    if "diplomat" in style_hint.lower() or "persona" in style_hint.lower():
        extras.append("Quiet Luxury / Old Money editorial lighting: soft warm-neutral highlights, rich fabric texture clarity.")
    elif "orbit" in style_hint.lower() or "bento" in style_hint.lower():
        extras.append("Clean modern streetwear lookbook crispness: sharp silhouette edges, vibrant true-to-life fabric tones.")
    return f"{base} {' '.join(extras)}".strip()


def build_scout_studio_prompt(
    item: dict[str, Any],
    insta_pose_direction: str = "",
) -> str:
    """Pinduoduo Tahlilchi (skaut) har bir mahsulot uchun Photoshop Studiyaga aniq, mahsulotni O'ZGARTIRMAYDIGAN prompt tuzadi."""
    name_uz = str(item.get("name") or "kiyim").strip()
    title_cn = str(item.get("title_cn") or item.get("cn_keyword") or "").strip()
    cat = str(item.get("category") or guess_category(name_uz) or "top").lower()
    color_uz = str(item.get("color_uz") or "").strip()

    is_light_item = any(
        w in f"{name_uz} {color_uz}".lower()
        for w in ("oq", "och bej", "krem", "white", "cream", "ivory", "beige", "muzdek")
    )
    backdrop_desc = (
        "a completely uniform, solid flat neutral dark charcoal studio background (#2E2E31) with ZERO gradients, props, or floor lines"
        if is_light_item
        else "a completely uniform, solid pure white studio background (#FFFFFF) with ZERO gradients, props, or floor lines"
    )

    extra_remove = ""
    if cat == "bottom":
        extra_remove = "CRITICAL: Completely remove any shoes, sneakers, socks, belt, shirt hem, or human legs/feet — keep ONLY the trousers/jeans themselves! "
    elif cat in ("top", "outerwear"):
        extra_remove = "CRITICAL: Completely remove any human head, face, neck, hair, hands, pants, hanger, or background — reconstruct the inside back collar/neckline naturally as an invisible ghost-mannequin! "
    elif cat == "shoes":
        extra_remove = "CRITICAL: Completely remove any human ankles, socks, pants legs, shoebox clutter, floor shadows, or promotional badges — keep ONLY the exact pair of shoes! "
    elif cat == "accessory":
        extra_remove = "CRITICAL: Completely remove any human wrist, face, neck, hand, stand, or cluttered background — keep ONLY the exact accessory! "

    pose_block = insta_pose_direction.strip() or DEFAULT_INSTA_POSE_DIRECTIONS.get(cat, DEFAULT_INSTA_POSE_DIRECTIONS["top"])

    return (
        f"ROLE: Senior E-Commerce Photoshop Studio Retoucher for a luxury menswear brand.\n"
        f"TARGET PRODUCT TO ISOLATE: {name_uz} (category: {cat}"
        + (f", source detail: {title_cn[:60]}" if title_cn else "")
        + ").\n"
        "STRICT 100% PRODUCT FIDELITY RULE (NEVER VIOLATE):\n"
        "- Preserve the EXACT product from the input photo with 100% identical fabric weave, exact color shade, "
        "exact seams, pockets, zippers, buttons, collar shape, cuffs, hardware, patterns, and small brand patch/logo.\n"
        "- DO NOT redesign, invent, hallucinate, add, or remove ANY design element of the actual product.\n"
        "- The customer will receive this exact physical item — it MUST look 100% authentic and identical to the original item.\n"
        "CLEANUP & ISOLATION:\n"
        f"- {extra_remove}"
        "- Remove 100% of Chinese/English text overlays, price tags, watermarks, circle inset badges, logos outside the product, and background scenery.\n"
        "- If the photo shows multiple duplicate color variants side-by-side, isolate ONLY the single cleanest hero garment.\n"
        "NATURAL STUDIO PRESENTATION (Guided by Instagram Trend Analyst):\n"
        f"- {pose_block}\n"
        f"- Place the single isolated product centered with generous margin on {backdrop_desc}.\n"
        "- Soft, even commercial studio lighting so the garment looks natural, crisp, and ready for a luxury Instagram lookbook."
    )


class PhotoStudioAgent:
    """9-asosiy AI agent: Gemini Nano Banana orqali mahsulot rasmini professional fotostudiyada qayta ishlaydi."""

    def __init__(self, settings: Settings):
        self.s = settings
        self.api_key = (getattr(settings, "gemini_api_key", "") or os.getenv("GEMINI_API_KEY", "")).strip()
        self._client = None
        if self.api_key:
            try:
                from google import genai

                self._client = genai.Client(api_key=self.api_key)
            except Exception as e:
                log.warning("PhotoStudio Gemini client ulanmadi: %s", e)

    @property
    def enabled(self) -> bool:
        if os.getenv("XAN_DISABLE_PHOTO_STUDIO") == "1":
            return False
        if os.getenv("PYTEST_CURRENT_TEST") and os.getenv("XAN_PHOTO_STUDIO_IN_TESTS") != "1":
            return False
        return self._client is not None

    @staticmethod
    def _cache_key(img_bytes: bytes, prompt: str) -> str:
        h = hashlib.sha1()
        h.update(img_bytes[:16384])
        h.update(str(len(img_bytes)).encode("utf-8"))
        h.update(prompt.encode("utf-8"))
        return h.hexdigest()[:24]

    @staticmethod
    def _pil_to_jpeg_bytes(im: Image.Image | bytes) -> bytes:
        if isinstance(im, (bytes, bytearray)):
            return bytes(im)
        buf = io.BytesIO()
        im.convert("RGB").save(buf, format="JPEG", quality=92)
        return buf.getvalue()

    def _call_nano_banana_sync(self, model_name: str, img_bytes: bytes, prompt: str) -> bytes | None:
        if self._client is None:
            return None
        inter = self._client.interactions.create(
            model=model_name,
            input=[
                {"type": "text", "text": prompt},
                {
                    "type": "image",
                    "data": base64.b64encode(img_bytes).decode("utf-8"),
                    "mime_type": "image/jpeg",
                },
            ],
        )
        out_img = getattr(inter, "output_image", None)
        if out_img and getattr(out_img, "data", None):
            return base64.b64decode(out_img.data)
        return None

    @staticmethod
    def _polish_studio_lighting(rgba_img: Image.Image) -> Image.Image:
        """Mahsulotning rangini va fasonini O'ZGARTIRMASDAN yumshoq studiya yoritishi va mato aniqligini kuchaytiradi."""
        im = rgba_img.convert("RGBA")
        rgb = im.convert("RGB")
        alpha = im.split()[3]
        # Yumshoq studiya kontrasti + mato to'qimasini aniqlashtirish (100% haqiqiy rang saqlanadi)
        rgb = ImageEnhance.Contrast(rgb).enhance(1.06)
        rgb = ImageEnhance.Sharpness(rgb).enhance(1.18)
        rgb = ImageEnhance.Brightness(rgb).enhance(1.02)
        out = rgb.convert("RGBA")
        out.putalpha(alpha)
        return out

    async def render_product_studio_async(
        self,
        raw_image: Image.Image | bytes,
        item: dict[str, Any],
        insta_pose_direction: str = "",
        timeout_sec: float = 28.0,
        use_cache: bool = True,
    ) -> StudioRenderResult:
        """Pinduoduo rasmini Nano Banana Photoshop Studio orqali tabiiy toza mahsulot rasmiga aylantiradi."""
        global _STUDIO_COOLDOWN_UNTIL

        cat = str(item.get("category") or guess_category(str(item.get("name") or "")) or "top").lower()
        scout_prompt = str(item.get("studio_prompt") or "").strip() or build_scout_studio_prompt(
            item, insta_pose_direction=insta_pose_direction
        )
        raw_bytes = self._pil_to_jpeg_bytes(raw_image)
        raw_pil = (
            raw_image.convert("RGBA")
            if isinstance(raw_image, Image.Image)
            else Image.open(io.BytesIO(raw_bytes)).convert("RGBA")
        )

        ckey = self._cache_key(raw_bytes, scout_prompt)
        cache_file = STUDIO_CACHE_DIR / f"{ckey}.png"
        if use_cache and cache_file.is_file():
            try:
                cached_im = Image.open(cache_file).convert("RGBA")
                return StudioRenderResult(
                    image=cached_im,
                    used_nano_banana=True,
                    model_used="cache",
                    prompt_used=scout_prompt,
                    cache_hit=True,
                )
            except Exception:
                pass

        if self.enabled and time.monotonic() >= _STUDIO_COOLDOWN_UNTIL:
            for model_name in STUDIO_MODELS:
                try:
                    out_bytes = await asyncio.wait_for(
                        asyncio.to_thread(self._call_nano_banana_sync, model_name, raw_bytes, scout_prompt),
                        timeout=timeout_sec,
                    )
                    if out_bytes and len(out_bytes) > 4000:
                        studio_pil = Image.open(io.BytesIO(out_bytes)).convert("RGBA")
                        isolated = extract_main_item(studio_pil, category=cat, use_cache=False, has_human=False)
                        final_im = self._polish_studio_lighting(isolated if isolated is not None else studio_pil)
                        if use_cache:
                            try:
                                STUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                                final_im.save(cache_file, format="PNG")
                            except Exception:
                                pass
                        return StudioRenderResult(
                            image=final_im,
                            used_nano_banana=True,
                            model_used=model_name,
                            prompt_used=scout_prompt,
                            cache_hit=False,
                        )
                except Exception as exc:
                    err_s = str(exc)
                    log.warning("Photoshop Studio (%s) zaxiraga o'tdi (%s): %s", model_name, type(exc).__name__, err_s[:140])
                    if "429" in err_s or "RESOURCE_EXHAUSTED" in err_s or "quota" in err_s.lower() or isinstance(exc, TimeoutError):
                        _STUDIO_COOLDOWN_UNTIL = time.monotonic() + 600.0
                        break

        # Lokal Fotostudiya zaxirasi: AI mato ajratish + studiya yoritishi (API kvotasi yopiq bo'lganda ham 0 xato!)
        fallback = extract_main_item(raw_pil, category=cat, use_cache=use_cache)
        polished = self._polish_studio_lighting(fallback) if fallback is not None else raw_pil
        return StudioRenderResult(
            image=polished,
            used_nano_banana=False,
            model_used="local_studio_retouch",
            prompt_used=scout_prompt,
            cache_hit=False,
        )
