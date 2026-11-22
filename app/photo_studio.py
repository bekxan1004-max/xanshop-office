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
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
from scipy import ndimage

from .config import Settings
from .cutout_agent import (
    _cloth_masks_all,
    _detect_human_head_above_garment,
    extract_main_item,
    guess_category,
)

log = logging.getLogger(__name__)

STUDIO_CACHE_DIR = Path("data/studio_cache")
STUDIO_MODELS = (
    "gemini-2.5-flash-image",
    "gemini-3.1-flash-image",
    "gemini-3.1-flash-lite-image",
    "gemini-nano-banana-2.1",
    "gemini-3-pro-image",
)
VISION_MODELS = (
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
)
_STUDIO_COOLDOWN_UNTIL: float = 0.0
_VISION_COOLDOWN_UNTIL: float = 0.0

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
        extra_remove = (
            "CRITICAL: Completely remove any shoes, sneakers, socks, belt, shirt hem, or human legs/feet — keep ONLY the trousers/jeans themselves! "
            "If the input photo shows 2 pairs of pants side-by-side (different colors), output ONLY ONE single pair of full-length straight upright trousers in the target color from waistband cleanly to ankle hems. "
        )
    elif cat in ("top", "outerwear"):
        extra_remove = (
            "CRITICAL: Completely remove any human head, face, neck, hair, hands, pants, hanger, orange fire stickers (加绒加厚), or background — reconstruct the inside back collar/neckline naturally as an invisible ghost-mannequin! "
            "If the input photo shows 2 stacked or folded sweaters/shirts/jackets together, output ONLY ONE single complete, fully unfolded, upright front-facing garment with full symmetrical sleeves. "
        )
    elif cat == "shoes":
        extra_remove = (
            "CRITICAL: Completely remove any human ankles, calves, socks, pants legs, shoebox clutter, floor shadows, or promotional badges — keep ONLY the exact pair of shoes! "
            "Position ONLY the pair of shoes standing upright on a flat horizontal studio surface at a clean 3/4 front-side angle (NEVER tilted diagonally on human legs). "
        )
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


def _translate_uz_color_to_en(color_uz: str) -> str:
    low = (color_uz or "").lower()
    mapping = (
        ("to'q jigarrang", "dark espresso brown"),
        ("qahva", "rich espresso coffee brown"),
        ("jigarrang", "warm vintage brown"),
        ("taupe", "muted taupe brown"),
        ("grafit", "dark charcoal graphite grey"),
        ("kulrang", "slate grey"),
        ("qora", "deep matte black"),
        ("to'q ko'k", "deep navy blue"),
        ("ko'k", "classic blue"),
        ("zaytun", "olive green"),
        ("yashil", "forest green"),
        ("xaki", "khaki olive"),
        ("och bej", "light warm beige"),
        ("bej", "warm beige"),
        ("krem", "soft cream ivory"),
        ("bordo", "deep burgundy maroon"),
        ("oq", "crisp white"),
    )
    for uz_k, en_v in mapping:
        if uz_k in low:
            return en_v
    return ""


def _deterministic_studio_regen_prompt(item: dict[str, Any], insta_pose_direction: str = "") -> str:
    """Vision API vaqtincha javob bermasa ham mahsulot nomi va kategoriyasidan toza studiya prompti tuzadi."""
    name_uz = str(item.get("name") or "menswear garment").strip()
    color_uz = str(item.get("color_uz") or "").strip()
    cat = str(item.get("category") or guess_category(name_uz) or "top").lower()
    custom_spec = str(item.get("studio_regen_prompt") or "").strip()
    en_color = _translate_uz_color_to_en(f"{name_uz} {color_uz}") or "classic neutral"
    low = f"{name_uz} {item.get('title_cn', '')} {custom_spec}".lower()

    if custom_spec:
        garment_desc = custom_spec
    elif cat == "outerwear":
        if any(k in low for k in ("palto", "overcoat", "trench", "大衣")):
            garment_desc = f"mens {en_color} tailored wool double-breasted overcoat with structured lapels and full long sleeves"
        elif any(k in low for k in ("blazer", "pidjak", "西装")):
            garment_desc = f"mens {en_color} tailored structured wool blazer jacket with notched lapel"
        elif any(k in low for k in ("zamsh", "suede", "kurtka", "shearling", "加绒", "bomber", "夹克")):
            lining = "with cream shearling fleece collar and inner placket trim, " if any(k in low for k in ("qo'y", "jun", "加绒", "shearling", "zamsh", "suede")) else ""
            garment_desc = f"mens {en_color} vintage suede bomber jacket {lining}ribbed collar, full-zip front, ribbed cuffs and hem, full symmetrical sleeves"
        else:
            garment_desc = f"mens {en_color} structured tailored winter jacket with clean seams and full sleeves"
    elif cat == "bottom":
        if any(k in low for k in ("jinsi", "denim", "jeans", "牛仔")):
            garment_desc = f"mens {en_color} relaxed wide-straight denim jeans from full waistband cleanly down to full uncut ankle hems"
        elif any(k in low for k in ("cho'ntak", "工装", "parashut", "cargo")):
            garment_desc = f"mens {en_color} relaxed wide-leg utility trousers with flap side pockets from full waistband down to complete uncut ankle hems"
        else:
            garment_desc = f"mens {en_color} tailored relaxed wide-straight pleated drape trousers from full structured waistband cleanly down to full uncut ankle hems"
    elif cat == "shoes":
        if any(k in low for k in ("chelsea", "etik", "botinka", "靴")):
            garment_desc = f"pair of mens {en_color} leather ankle chelsea combat boots with thick lugged sole, 3/4 side-front studio angle"
        elif any(k in low for k in ("lofer", "moccasin", "乐福")):
            garment_desc = f"pair of mens {en_color} luxury suede penny loafers, 3/4 side-front studio angle"
        else:
            garment_desc = f"pair of mens {en_color} luxury low-top chunky leather and suede sneakers, 3/4 dynamic studio angle"
    elif cat == "accessory":
        garment_desc = f"single menswear {en_color} luxury accessory ({name_uz}) with clean metallic/leather hardware details"
    else:
        if any(k in low for k in ("vodolazka", "turtleneck", "高领")):
            garment_desc = f"mens {en_color} fine-knit cashmere turtleneck sweater with full symmetrical sleeves and ribbed hem"
        elif any(k in low for k in ("xudi", "hoodie", "卫衣" if "连帽" in low else "hood")):
            garment_desc = f"mens {en_color} heavyweight oversized cotton hoodie sweatshirt with structured hood and full sleeves"
        elif any(k in low for k in ("half-zip", "zamok", "半拉链")):
            garment_desc = f"mens {en_color} heavyweight knitted half-zip collar pullover sweater with full symmetrical sleeves"
        else:
            garment_desc = f"mens {en_color} heavyweight oversized crewneck cotton fleece sweatshirt with ribbed crewneck, ribbed cuffs and hem, full symmetrical sleeves"

    posture = "3D invisible ghost-mannequin editorial volume" if cat in ("outerwear", "top", "bottom") else "luxury commercial e-commerce studio shot"
    pose_hint = (insta_pose_direction or "").split(".")[0].strip()
    if pose_hint and len(pose_hint) > 100:
        pose_hint = ""
    return (
        f"Luxury e-commerce catalog product photograph of ONE {garment_desc}, {posture}, "
        f"{pose_hint + ', ' if pose_hint else ''}"
        "complete full-length uncut garment centered with comfortable margins, strictly isolated on a completely solid pure white #FFFFFF studio background, "
        "no human model, no hands, no face, no feet, no Chinese characters, no text, no fire icons, no price stickers, no badges, sharp fabric texture, 8k softbox lighting."
    )


def _build_forensic_vision_prompt(
    item: dict[str, Any],
    scout_prompt: str = "",
    insta_pose_direction: str = "",
) -> str:
    """Gemini Vision uchun Pinduoduo xom rasmiga qarab faqat maqsadli kiyimning forensik studio promptini tuzish buyrug'i."""
    name_uz = str(item.get("name") or "kiyim").strip()
    title_cn = str(item.get("title_cn") or item.get("cn_keyword") or "").strip()
    cat = str(item.get("category") or guess_category(name_uz) or "top").lower()
    color_uz = str(item.get("color_uz") or "").strip()
    en_color = _translate_uz_color_to_en(f"{name_uz} {color_uz}")
    custom_spec = str(item.get("studio_regen_prompt") or "").strip()

    pose_snippet = (insta_pose_direction or DEFAULT_INSTA_POSE_DIRECTIONS.get(cat, "")).strip()[:220]
    color_rule = (
        f"Target variant color in capsule: '{en_color}' (Uzbek label: '{color_uz}'). If the photo clearly matches this color keep the exact shade; if it shows multiple variants or another tint, regenerate this EXACT garment design in clean {en_color}. "
        if en_color
        else "Keep the exact garment color visible in the photo. "
    )
    length_rule = (
        "CRITICAL FOR TROUSERS/JEANS: Even if the bottom of the trousers in the input photo is cut off or hidden behind shoes/watermarks, describe the FULL complete waist-to-ankle trousers down to clean flat ankle hems with ZERO shoes, feet, or uneven cropped legs. "
        if cat == "bottom"
        else "Ensure BOTH sleeves/sides and the complete hem/silhouette are fully visible, symmetrical, and NEVER cropped at the edges. "
    )

    return (
        f"You are an expert menswear studio photography director regenerating a noisy Pinduoduo marketplace image into a clean studio product prompt.\n"
        f"Target Item Name (Uzbek): '{name_uz}' | Category: '{cat}' | Raw Chinese title: '{title_cn[:80]}'.\n"
        + (f"Admin/Custom visual requirement: {custom_spec}\n" if custom_spec else "")
        + f"{color_rule}\n"
        f"{length_rule}\n"
        "INSTRUCTIONS:\n"
        "1. Look closely at the target clothing/shoe/accessory in this Pinduoduo image and capture its EXACT design details: fabric texture (suede, fleece, wool, knit, leather), collar/lapel/hood shape, inner shearling lining if visible, front zipper/button count, pockets, cuffs, sole tread/stitching.\n"
        "2. COMPLETELY IGNORE all Chinese promo banners, fire stickers, discount badges, yellow vertical text strips, background scenery, hangers, and any human model face, hair, hands, or legs wearing it.\n"
        f"3. Apply natural studio staging: {pose_snippet}.\n"
        "4. Output ONLY ONE single plain-English image generation prompt (55-85 words, no quotes, no markdown, no labels) ready for a studio product generator. "
        "It MUST specify: 'isolated completely alone on a solid pure white #FFFFFF studio background, ghost-mannequin editorial volume, full uncut edges, no human body parts, no text, no badges, no watermarks, softbox commercial lighting'."
    )


def _build_kontext_edit_instruction(
    item: dict[str, Any],
    insta_pose_direction: str = "",
) -> str:
    """FLUX.1-Kontext-Dev (haqiqiy Image-to-Image) uchun aynan Pinduoduo kiyimini o'zgartirmasdan tozalash buyrug'i."""
    name_uz = str(item.get("name") or "garment").strip()
    color_uz = str(item.get("color_uz") or "").strip()
    cat = str(item.get("category") or guess_category(name_uz) or "top").lower()
    en_color = _translate_uz_color_to_en(f"{name_uz} {color_uz}")
    custom_spec = str(item.get("studio_regen_prompt") or "").strip()
    preserve_custom = bool(item.get("_preserve_custom_spec"))

    low = f"{name_uz} {item.get('title_cn', '')} {custom_spec}".lower()
    if cat == "outerwear":
        instr = (
            "Remove the orange fire sticker badge (加绒加厚), all Chinese text banners, hangers, human hands, neck, face, and background clutter. "
            "If two jackets/coats appear stacked or side-by-side, show ONLY ONE single complete upright unfolded front-facing jacket or coat with full symmetrical sleeves "
            "(keeping 100% of its exact original color shade, fabric texture, inner lining, collar, zipper, and pockets) "
            "isolated alone on a solid pure white #FFFFFF studio background."
        )
    elif cat == "bottom":
        instr = (
            "Remove the black shoes and boots at the bottom, the shirt sleeves at the waist, all floor shadows, Chinese text or badges, and the room wall and wooden floor background. "
            "If the photo shows 2 pairs of pants side-by-side, keep ONLY ONE single pair of full-length straight upright wide-leg trousers or jeans in the target color from waistband down to clean symmetrical ankle hems "
            "(keeping 100% of its exact color and fabric) isolated alone on a solid pure white #FFFFFF studio background."
        )
    elif cat == "shoes":
        instr = (
            "Remove the human ankles, calves, trousers, socks, wristwatch, hands, wooden table or floor surface, corner round logos, and all Chinese promotional text or calligraphy. "
            "Position ONLY ONE exact pair of footwear / boots standing upright on a clean flat horizontal studio surface at a clean 3/4 front-side angle (NEVER tilted diagonally on human legs), "
            "(keeping 100% of the exact original colors, panels, sole, laces, and stitching) isolated alone on a solid pure white #FFFFFF studio background."
        )
    elif cat == "accessory":
        instr = (
            "Remove any human hand, wrist, face, display stand, and all Chinese text or promotional stickers. "
            "Keep ONLY the exact single accessory from the input image isolated alone on a solid pure white #FFFFFF studio background."
        )
    else:
        garment_label = (
            f"{en_color} heavyweight oversized sweater/sweatshirt"
            if (en_color and ("svitshot" in low or "sviter" in low))
            else f"{en_color} garment".strip()
        )
        instr = (
            "Remove the yellow vertical Chinese banner, orange fire stickers (加绒加厚), hangers, extra garments behind, and human hand. "
            f"If stacked/folded or two sweaters appear together, reconstruct and show ONLY ONE complete, fully unfolded, upright front-facing {garment_label} with full symmetrical long sleeves and ribbed hem "
            "in a clean invisible ghost-mannequin studio shot isolated alone on a solid pure white #FFFFFF background, "
            "with no mannequin head, no human model, no hands, and no pants."
        )

    if custom_spec and preserve_custom:
        instr += f" Exact visual detail: {custom_spec[:140]}."
    elif insta_pose_direction and cat == "shoes":
        first_sentence = insta_pose_direction.split(".")[0].strip()
        if first_sentence and len(first_sentence) <= 100:
            instr += f" Angle: {first_sentence}."
    return instr


def _isolate_from_clean_white_studio_bg(studio_pil: Image.Image, category: str = "") -> Image.Image:
    """Qayta generatsiya qilingan toza studiya rasmidan (#FFFFFF / tekis fon) mahsulotni matosini yemirmasdan va oq qirrasiz ajratadi."""
    rgb_im = studio_pil.convert("RGB")
    arr = np.asarray(rgb_im, dtype=np.float32)
    h, w, _ = arr.shape
    if h < 64 or w < 64:
        return studio_pil.convert("RGBA")

    border = np.concatenate(
        [
            arr[:10, :, :].reshape(-1, 3),
            arr[h - 10 :, :, :].reshape(-1, 3),
            arr[:, :10, :].reshape(-1, 3),
            arr[:, w - 10 :, :].reshape(-1, 3),
        ],
        axis=0,
    )
    bg_col = np.median(border, axis=0)
    dist = np.linalg.norm(arr - bg_col[None, None, :], axis=2)
    lum = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
    chroma = np.max(arr, axis=2) - np.min(arr, axis=2)

    cat_low = (category or "").lower()
    is_white_backdrop = float(np.mean(bg_col)) > 205.0
    if is_white_backdrop:
        is_bg_cand = (dist < 38.0) | ((lum > 214.0) & (chroma < 24.0))
        y_frac = np.linspace(0.0, 1.0, h)[:, None]
        if cat_low == "shoes":
            is_bg_cand = is_bg_cand | ((y_frac > 0.62) & (lum > 170.0) & (chroma < 20.0) & (dist < 90.0))
        else:
            is_bg_cand = is_bg_cand | ((y_frac > 0.70) & (lum > 186.0) & (chroma < 18.0) & (dist < 72.0))
    else:
        is_bg_cand = (dist < 26.0) & (chroma < 24.0)

    labeled_bg, num_bg = ndimage.label(is_bg_cand)
    if num_bg > 0:
        edge_labels = np.unique(
            np.concatenate(
                [
                    labeled_bg[0, :],
                    labeled_bg[h - 1, :],
                    labeled_bg[:, 0],
                    labeled_bg[:, w - 1],
                ]
            )
        )
        edge_labels = edge_labels[edge_labels > 0]
        outer_bg = np.isin(labeled_bg, edge_labels)
    else:
        outer_bg = is_bg_cand

    fg_mask = ~outer_bg
    inner_holes = ndimage.binary_fill_holes(fg_mask) ^ fg_mask
    if np.any(inner_holes):
        hole_thr = 192.0 if (category or "").lower() == "bottom" else 212.0
        pure_bg_holes = inner_holes & ((dist < 28.0) | ((lum > hole_thr) & (chroma < 24.0)))
        fg_mask = fg_mask & ~pure_bg_holes

    if cat_low in ("top", "outerwear") and os.getenv("XAN_DISABLE_AI_CUTOUT") != "1":
        try:
            all_ch = _cloth_masks_all(rgb_im)
            if all_ch is not None:
                c0, c1, c2 = all_ch
                upper_cloth = np.maximum(c0, c2) if cat_low == "outerwear" else c0
                has_pants = float((c1 > 0.45).mean()) > 0.025
                has_head = _detect_human_head_above_garment(fg_mask.astype(np.float32), upper_cloth)
                if (has_pants or has_head) and float((upper_cloth > 0.5).mean()) >= 0.06:
                    upper_keep = upper_cloth > 0.45
                    fg_mask = ndimage.binary_opening(fg_mask & upper_keep & (c1 < 0.20), iterations=2)
                    if has_pants:
                        p_rows = np.where((c1 > 0.45).mean(axis=1) > 0.10)[0]
                        if len(p_rows):
                            fg_mask[int(p_rows[0]) + 4 :, :] = False
        except Exception as exc:
            log.debug("Maneken tozalash zaxiraga o'tdi: %s", exc)

    labeled_fg, num_fg = ndimage.label(fg_mask)
    if num_fg > 1:
        sizes = ndimage.sum(fg_mask, labeled_fg, range(1, num_fg + 1))
        max_sz = float(np.max(sizes)) if len(sizes) else 0.0
        keep = [idx_c + 1 for idx_c, sz in enumerate(sizes) if sz >= max(max_sz * 0.04, 150.0)]
        fg_mask = np.isin(labeled_fg, keep)

    if float(np.mean(fg_mask)) < 0.04:
        return studio_pil.convert("RGBA")

    # 2px ichkari kirib oq fon halo'sini kesamiz va qirra rangini ichki mato rangiga almashtiramiz
    eroded = ndimage.binary_erosion(fg_mask, iterations=2)
    if float(np.mean(eroded)) < 0.03:
        eroded = fg_mask
    soft_alpha = ndimage.gaussian_filter(eroded.astype(np.float32), sigma=0.75)
    soft_alpha = np.where(eroded, np.clip(soft_alpha * 1.15, 0.0, 1.0), 0.0)
    interior = ndimage.binary_erosion(eroded, iterations=2)
    soft_alpha = np.where(interior, 1.0, soft_alpha)

    rgb_out = arr.copy()
    if is_white_backdrop and np.any(interior):
        edge_zone = (soft_alpha > 0.01) & (~interior)
        if np.any(edge_zone):
            # Yaqin ichki piksel rangini ko'chirib oq chiziq (white halo) ni 100% yo'qotamiz
            _, nearest_idx = ndimage.distance_transform_edt(~interior, return_indices=True)
            nearest_rgb = arr[nearest_idx[0], nearest_idx[1]]
            rgb_out[edge_zone] = np.clip(nearest_rgb[edge_zone] * 0.85 + arr[edge_zone] * 0.15, 0.0, 255.0)

    mask_u8 = np.clip(soft_alpha * 255.0, 0, 255).astype(np.uint8)
    mask_im = Image.fromarray(mask_u8, mode="L")
    rgba = Image.fromarray(np.clip(rgb_out, 0, 255).astype(np.uint8), mode="RGB").convert("RGBA")
    rgba.putalpha(mask_im)
    rgba.info["xan_studio_fg_ratio"] = f"{float(np.mean(soft_alpha > 0.15)):.4f}"

    bb = mask_im.point(lambda p: 255 if p > 22 else 0).getbbox()
    if bb:
        pad = 6
        x0 = max(0, bb[0] - pad)
        y0 = max(0, bb[1] - pad)
        x1 = min(w, bb[2] + pad)
        y1 = min(h, bb[3] + pad)
        rgba = rgba.crop((x0, y0, x1, y1))
    rgba.info["xan_studio_regenerated"] = "1"
    return rgba


def _scrub_promo_fire_stickers_rgba(rgba_img: Image.Image) -> Image.Image:
    """Qora/neytral kiyim burchak va chetlarida qolib ketgan yorqin olov/sariq reklama stikerlarini (加绒加厚) tozalaydi."""
    rgba = rgba_img.convert("RGBA")
    arr = np.asarray(rgba, dtype=np.uint8).copy()
    h, w, _ = arr.shape
    if h < 48 or w < 48:
        return rgba

    rgb = arr[:, :, :3].astype(np.int16)
    alpha = arr[:, :, 3]
    fg = alpha > 25

    # Kiyimning o'zi apelsin/sariq bo'lsa tegmaymiz
    cy0, cy1 = int(h * 0.28), int(h * 0.72)
    cx0, cx1 = int(w * 0.28), int(w * 0.72)
    core_fg = fg[cy0:cy1, cx0:cx1]
    if np.any(core_fg):
        core_rgb = rgb[cy0:cy1, cx0:cx1][core_fg]
        core_flame_ratio = float(
            np.mean((core_rgb[:, 0] > 185) & (core_rgb[:, 1] >= 40) & (core_rgb[:, 1] <= 215) & (core_rgb[:, 2] < 75) & ((core_rgb[:, 0] - core_rgb[:, 2]) > 115))
        )
        if core_flame_ratio > 0.28:
            return rgba

    # Olov/reklama stiker piksellari (yuqori to'yingan olov rang + ichidagi sariq xitoy yozuvisimon chegara)
    flame_px = (
        fg
        & (rgb[:, :, 0] > 185)
        & (rgb[:, :, 1] >= 40)
        & (rgb[:, :, 1] <= 215)
        & (rgb[:, :, 2] < 75)
        & ((rgb[:, :, 0] - rgb[:, :, 2]) > 115)
    )
    if float(np.mean(flame_px)) < 0.002:
        return rgba

    # Faqat chet/burchak zonalarga tushgan olov orollarini stiker deb aniqlaymiz
    yy, xx = np.ogrid[:h, :w]
    periph = (yy < int(h * 0.24)) | (yy > int(h * 0.62)) | (xx < int(w * 0.24)) | (xx > int(w * 0.68))

    labeled, n_comp = ndimage.label(flame_px)
    if n_comp == 0:
        return rgba
    scrub_mask = np.zeros((h, w), dtype=bool)
    total_px = h * w
    for comp_id in range(1, n_comp + 1):
        comp = labeled == comp_id
        cnt = int(np.sum(comp))
        if cnt < 25 or cnt > total_px * 0.22:
            continue
        if np.any(comp & periph):
            scrub_mask |= comp

    if not np.any(scrub_mask):
        return rgba

    # Stikerning tashqi qora/qizil hoshiyasini ham qo'shib tozalash
    scrub_mask = ndimage.binary_dilation(scrub_mask, iterations=4)
    arr[scrub_mask, 3] = 0
    out = Image.fromarray(arr, mode="RGBA")
    for k, v in rgba_img.info.items():
        out.info[k] = v
    return out


def _verify_regenerated_rgba(rgba: Image.Image) -> bool:
    """Qayta yaratilgan studiya rasmi sifat darvozasidan o'tishini tekshiradi."""
    if rgba.width < 120 or rgba.height < 120:
        return False
    ratio_str = rgba.info.get("xan_studio_fg_ratio")
    if ratio_str:
        try:
            fg_ratio = float(ratio_str)
            if not (0.10 <= fg_ratio <= 0.88):
                return False
        except ValueError:
            pass
    alpha = np.asarray(rgba.convert("RGBA").split()[3])
    crop_fg = float(np.mean(alpha > 25))
    return 0.12 <= crop_fg <= 0.96


class PhotoStudioAgent:
    """9-asosiy AI agent: Pinduoduo xom rasmidan toza, to'liq va xitoycha yozuvsiz studiya rasmini AI orqali qayta yaratadi."""

    def __init__(self, settings: Settings):
        self.s = settings
        env_key = "" if os.getenv("PYTEST_CURRENT_TEST") else os.getenv("GEMINI_API_KEY", "")
        self.api_key = (getattr(settings, "gemini_api_key", "") or env_key).strip()
        self.hf_token = (getattr(settings, "hf_token", "") or os.getenv("HF_TOKEN", "")).strip()
        fal_env = "" if os.getenv("PYTEST_CURRENT_TEST") else os.getenv("FAL_KEY", "")
        self.fal_key = (getattr(settings, "fal_key", "") or fal_env).strip()
        self._client = None
        if self.api_key:
            try:
                from google import genai

                try:
                    self._client = genai.Client(api_key=self.api_key, http_options={"timeout": 20000})
                except TypeError:
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

    @property
    def cloud_regen_enabled(self) -> bool:
        if os.getenv("XAN_DISABLE_PHOTO_STUDIO") == "1":
            return False
        if os.getenv("PYTEST_CURRENT_TEST") and os.getenv("XAN_PHOTO_STUDIO_IN_TESTS") != "1":
            return False
        return True

    @staticmethod
    def _cache_key(img_bytes: bytes, prompt: str) -> str:
        h = hashlib.sha1()
        h.update(b"kontext_v4|")
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
        try:
            from google.genai import types

            resp = self._client.models.generate_content(
                model=model_name,
                contents=[
                    types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                    prompt,
                ],
                config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
            )
            for cand in getattr(resp, "candidates", None) or []:
                content = getattr(cand, "content", None)
                for part in getattr(content, "parts", None) or []:
                    inline = getattr(part, "inline_data", None)
                    if inline and getattr(inline, "data", None):
                        raw_d = inline.data
                        return base64.b64decode(raw_d) if isinstance(raw_d, str) else bytes(raw_d)
        except Exception as exc:
            err_s = str(exc)
            if "429" in err_s or "RESOURCE_EXHAUSTED" in err_s or "quota" in err_s.lower():
                raise
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

    def _extract_forensic_garment_prompt_sync(
        self,
        raw_bytes: bytes,
        item: dict[str, Any],
        scout_prompt: str = "",
        insta_pose_direction: str = "",
    ) -> str:
        """Gemini Vision orqali Pinduoduo xom rasmidan xitoycha yozuvsiz aniq inglizcha studiya promptini chiqaradi."""
        global _VISION_COOLDOWN_UNTIL
        fallback = _deterministic_studio_regen_prompt(item, insta_pose_direction=insta_pose_direction)
        if self._client is None or not raw_bytes or time.monotonic() < _VISION_COOLDOWN_UNTIL:
            return fallback

        vision_q = _build_forensic_vision_prompt(
            item,
            scout_prompt=scout_prompt,
            insta_pose_direction=insta_pose_direction,
        )
        from google.genai import types

        for model_name in VISION_MODELS:
            try:
                resp = self._client.models.generate_content(
                    model=model_name,
                    contents=[
                        types.Part.from_bytes(data=raw_bytes, mime_type="image/jpeg"),
                        vision_q,
                    ],
                )
                txt = re.sub(r"\s+", " ", (getattr(resp, "text", None) or "").strip()).strip("\"'` ")
                if len(txt) >= 45 and not txt.startswith("{"):
                    if "#ffffff" not in txt.lower() and "white background" not in txt.lower():
                        txt += ", isolated alone on a solid pure white #FFFFFF background, no text, no badges, no human model"
                    return txt[:480]
            except Exception as exc:
                err_s = str(exc)
                log.warning("PhotoStudio Vision (%s) zaxiraga o'tdi: %s", model_name, err_s[:120])
                if "429" in err_s or "RESOURCE_EXHAUSTED" in err_s:
                    _VISION_COOLDOWN_UNTIL = time.monotonic() + 180.0
                    break
        return fallback

    def _call_fal_kontext_sync(
        self,
        raw_bytes: bytes,
        edit_prompt: str,
        seed: int = 42,
    ) -> bytes | None:
        """Fal.ai (FLUX.1-Kontext-Dev — arzon va tezkor ~$0.025/rasm) orqali rasmni studiya sifatida qayta chizadi."""
        if not self.fal_key:
            return None
        b64 = "data:image/jpeg;base64," + base64.b64encode(raw_bytes).decode("ascii")
        headers = {
            "Authorization": f"Key {self.fal_key}",
            "Content-Type": "application/json",
        }
        for ep in (
            "https://fal.run/fal-ai/flux-kontext/dev",
            "https://fal.run/fal-ai/flux-pro/kontext",
        ):
            try:
                with httpx.Client(timeout=45.0, follow_redirects=True) as client:
                    resp = client.post(
                        ep,
                        headers=headers,
                        json={
                            "prompt": edit_prompt,
                            "image_url": b64,
                            "seed": int(seed),
                            "output_format": "png",
                        },
                    )
                    if resp.status_code != 200:
                        log.warning("Fal.ai Kontext (%s) xato %s: %s", ep, resp.status_code, resp.text[:140])
                        continue
                    data = resp.json()
                    imgs = data.get("images") if isinstance(data, dict) else None
                    if isinstance(imgs, list) and imgs and isinstance(imgs[0], dict) and imgs[0].get("url"):
                        dl = client.get(str(imgs[0]["url"]))
                        if dl.status_code == 200 and len(dl.content) > 500:
                            im = Image.open(io.BytesIO(dl.content)).convert("RGB")
                            buf = io.BytesIO()
                            im.save(buf, format="PNG")
                            return buf.getvalue()
            except Exception as exc:
                log.warning("Fal.ai Kontext xatosi: %s", exc)
        return None

    def _call_hf_kontext_img2img_sync(
        self,
        raw_bytes: bytes,
        edit_prompt: str,
        seed: int = 42,
    ) -> bytes | None:
        """FLUX.1-Kontext-Dev haqiqiy Image-to-Image API orqali mahsulotni o'zgartirmasdan toza studiya rasmini yaratadi."""
        base = "https://black-forest-labs-flux-1-kontext-dev.hf.space"
        headers = {"User-Agent": "Mozilla/5.0 XANSHOP-PhotoStudio/3.0"}
        if self.hf_token:
            headers["Authorization"] = f"Bearer {self.hf_token}"
        try:
            with httpx.Client(timeout=45.0, follow_redirects=True, headers=headers) as client:
                up = client.post(
                    f"{base}/gradio_api/upload",
                    files={"files": ("product.jpg", raw_bytes, "image/jpeg")},
                )
                if up.status_code != 200 or not isinstance(up.json(), list) or not up.json():
                    log.warning("HF Kontext upload xatosi (%s): %s", up.status_code, up.text[:120])
                    return None
                srv_path = up.json()[0]
                call = client.post(
                    f"{base}/gradio_api/call/infer",
                    json={
                        "data": [
                            {"path": srv_path, "meta": {"_type": "gradio.FileData"}},
                            edit_prompt,
                            int(seed),
                            False,
                            2.5,
                            20,
                        ]
                    },
                )
                if call.status_code != 200:
                    log.warning("HF Kontext call xatosi (%s): %s", call.status_code, call.text[:120])
                    return None
                ev = call.json().get("event_id")
                if not ev:
                    return None
                out_url = ""
                with client.stream("GET", f"{base}/gradio_api/call/infer/{ev}", timeout=50.0) as stream:
                    cur_event = ""
                    for line in stream.iter_lines():
                        if not line:
                            continue
                        if line.startswith("event:"):
                            cur_event = line.split(":", 1)[1].strip()
                            if cur_event == "error":
                                log.warning("HF Kontext SSE error qaytardi")
                                return None
                        elif line.startswith("data: [") and cur_event in ("complete", ""):
                            arr = json.loads(line[5:].strip())
                            if isinstance(arr, list) and arr and isinstance(arr[0], dict):
                                out_url = str(arr[0].get("url") or "").strip()
                                break
                if not out_url:
                    return None
                img_resp = client.get(out_url)
                if img_resp.status_code == 200 and len(img_resp.content) > 6000:
                    im = Image.open(io.BytesIO(img_resp.content)).convert("RGB")
                    buf = io.BytesIO()
                    im.save(buf, format="PNG")
                    return buf.getvalue()
        except Exception as exc:
            log.warning("HF Kontext img2img xatosi: %s", exc)
        return None

    def _call_hf_flux_schnell_sync(self, regen_prompt: str, seed: int = 42) -> bytes | None:
        """Zaxira AI Studio generator (Hugging Face FLUX.1-schnell) orqali toza studiya rasmini yaratadi."""
        base = "https://black-forest-labs-flux-1-schnell.hf.space"
        headers = {"User-Agent": "Mozilla/5.0 XANSHOP-PhotoStudio/3.0"}
        if self.hf_token:
            headers["Authorization"] = f"Bearer {self.hf_token}"
        try:
            with httpx.Client(timeout=35.0, follow_redirects=True, headers=headers) as client:
                call = client.post(
                    f"{base}/gradio_api/call/infer",
                    json={"data": [regen_prompt[:480], int(seed), False, 768, 768, 4]},
                )
                if call.status_code != 200:
                    return None
                ev = call.json().get("event_id")
                if not ev:
                    return None
                out_url = ""
                with client.stream("GET", f"{base}/gradio_api/call/infer/{ev}", timeout=35.0) as stream:
                    for line in stream.iter_lines():
                        if line.startswith("data: ["):
                            arr = json.loads(line[5:].strip())
                            if isinstance(arr, list) and arr and isinstance(arr[0], dict):
                                out_url = str(arr[0].get("url") or "").strip()
                                break
                if not out_url:
                    return None
                img_resp = client.get(out_url)
                if img_resp.status_code == 200 and len(img_resp.content) > 6000:
                    im = Image.open(io.BytesIO(img_resp.content)).convert("RGB")
                    buf = io.BytesIO()
                    im.save(buf, format="PNG")
                    return buf.getvalue()
        except Exception as exc:
            log.warning("HF FLUX.1-schnell zaxira xatosi: %s", exc)
        return None

    @staticmethod
    def _polish_studio_lighting(rgba_img: Image.Image) -> Image.Image:
        """Mahsulotning rangini va fasonini O'ZGARTIRMASDAN yumshoq studiya yoritishi va mato aniqligini kuchaytiradi."""
        im = rgba_img.convert("RGBA")
        rgb = im.convert("RGB")
        alpha = im.split()[3]
        rgb = ImageEnhance.Contrast(rgb).enhance(1.06)
        rgb = ImageEnhance.Sharpness(rgb).enhance(1.18)
        rgb = ImageEnhance.Brightness(rgb).enhance(1.02)
        out = rgb.convert("RGBA")
        out.putalpha(alpha)
        for k, v in rgba_img.info.items():
            out.info[k] = v
        out.info["xan_studio_regenerated"] = "1"
        return out

    async def render_product_studio_async(
        self,
        raw_image: Image.Image | bytes,
        item: dict[str, Any],
        insta_pose_direction: str = "",
        timeout_sec: float = 28.0,
        use_cache: bool = True,
    ) -> StudioRenderResult:
        """Pinduoduo rasmini haqiqiy AI Image-to-Image Regenerator (Nano Banana / FLUX.1-Kontext-Dev) orqali to'liq va xitoycha yozuvsiz studiya rasmiga aylantiradi."""
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

        regen_sig = f"{cat}|{bool(item.get('_preserve_custom_spec'))}|{item.get('studio_regen_prompt', '')}|{item.get('name', '') if item.get('_preserve_custom_spec') else ''}"
        ckey = self._cache_key(raw_bytes, regen_sig)
        cache_file = STUDIO_CACHE_DIR / f"{ckey}.png"
        if use_cache and cache_file.is_file():
            try:
                cached_im = Image.open(cache_file).convert("RGBA")
                cached_im.info["xan_studio_regenerated"] = "1"
                if _verify_regenerated_rgba(cached_im):
                    return StudioRenderResult(
                        image=cached_im,
                        used_nano_banana=True,
                        model_used="cache_kontext_v3",
                        prompt_used=scout_prompt,
                        cache_hit=True,
                    )
            except Exception:
                pass

        # 1-ENGINE: Gemini Nano Banana Image-to-Image (to'lovli kalit ulanganda avtomatik ishlaydi)
        if self.enabled and time.monotonic() >= _STUDIO_COOLDOWN_UNTIL:
            attempted_primary: set[str] = set()
            for model_name in STUDIO_MODELS:
                if model_name in ("gemini-2.5-flash-image", "gemini-nano-banana-2.1"):
                    attempted_primary.add(model_name)
                try:
                    out_bytes = await asyncio.wait_for(
                        asyncio.to_thread(self._call_nano_banana_sync, model_name, raw_bytes, scout_prompt),
                        timeout=timeout_sec,
                    )
                    if out_bytes and len(out_bytes) > 4000:
                        studio_pil = Image.open(io.BytesIO(out_bytes)).convert("RGBA")
                        isolated = _isolate_from_clean_white_studio_bg(studio_pil, category=cat)
                        final_im = self._polish_studio_lighting(isolated)
                        if _verify_regenerated_rgba(final_im):
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
                        if {"gemini-2.5-flash-image", "gemini-nano-banana-2.1"}.issubset(attempted_primary):
                            _STUDIO_COOLDOWN_UNTIL = time.monotonic() + 30.0
                            break

        # 2-ENGINE: Fal.ai (agar FAL_KEY ulangan bo'lsa) -> FLUX.1-Kontext-Dev HF Image-to-Image Regenerator
        if self.cloud_regen_enabled:
            edit_prompt = _build_kontext_edit_instruction(item, insta_pose_direction=insta_pose_direction)
            seed_base = int(hashlib.sha1(ckey.encode("utf-8")).hexdigest()[:8], 16) % 100000
            if self.fal_key:
                try:
                    fal_bytes = await asyncio.wait_for(
                        asyncio.to_thread(self._call_fal_kontext_sync, raw_bytes, edit_prompt, seed_base),
                        timeout=45.0,
                    )
                    if fal_bytes and len(fal_bytes) > 500:
                        studio_pil = Image.open(io.BytesIO(fal_bytes)).convert("RGBA")
                        isolated = _isolate_from_clean_white_studio_bg(studio_pil, category=cat)
                        final_im = self._polish_studio_lighting(isolated)
                        if _verify_regenerated_rgba(final_im):
                            if use_cache:
                                try:
                                    STUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                                    final_im.save(cache_file, format="PNG")
                                except Exception:
                                    pass
                            return StudioRenderResult(
                                image=final_im,
                                used_nano_banana=True,
                                model_used="fal_flux_kontext",
                                prompt_used=edit_prompt,
                                cache_hit=False,
                            )
                except Exception as exc:
                    log.warning("Fal.ai Kontext zaxiraga tushdi: %s", exc)
            try:
                for attempt in range(2):
                    kontext_bytes = await asyncio.wait_for(
                        asyncio.to_thread(
                            self._call_hf_kontext_img2img_sync,
                            raw_bytes,
                            edit_prompt,
                            seed_base + attempt * 13,
                        ),
                        timeout=55.0,
                    )
                    if kontext_bytes and len(kontext_bytes) > 500:
                        studio_pil = Image.open(io.BytesIO(kontext_bytes)).convert("RGBA")
                        isolated = _isolate_from_clean_white_studio_bg(studio_pil, category=cat)
                        final_im = self._polish_studio_lighting(isolated)
                        if _verify_regenerated_rgba(final_im):
                            if use_cache:
                                try:
                                    STUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                                    final_im.save(cache_file, format="PNG")
                                except Exception:
                                    pass
                            return StudioRenderResult(
                                image=final_im,
                                used_nano_banana=True,
                                model_used="hf_flux_kontext_img2img",
                                prompt_used=edit_prompt,
                                cache_hit=False,
                            )
            except Exception as exc:
                log.warning("HF FLUX.1-Kontext-Dev zaxiraga tushdi: %s", exc)

            # 2B-ENGINE: Gemini Vision Forensik Tahlil + HF FLUX.1-schnell (agar Kontext xato bersa)
            try:
                regen_prompt = await asyncio.wait_for(
                    asyncio.to_thread(
                        self._extract_forensic_garment_prompt_sync,
                        raw_bytes,
                        item,
                        scout_prompt,
                        insta_pose_direction,
                    ),
                    timeout=18.0,
                )
                flux_bytes = await asyncio.wait_for(
                    asyncio.to_thread(self._call_hf_flux_schnell_sync, regen_prompt, seed_base),
                    timeout=40.0,
                )
                if flux_bytes and len(flux_bytes) > 500:
                    studio_pil = Image.open(io.BytesIO(flux_bytes)).convert("RGBA")
                    isolated = _isolate_from_clean_white_studio_bg(studio_pil, category=cat)
                    final_im = self._polish_studio_lighting(isolated)
                    if _verify_regenerated_rgba(final_im):
                        if use_cache:
                            try:
                                STUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                                final_im.save(cache_file, format="PNG")
                            except Exception:
                                pass
                        return StudioRenderResult(
                            image=final_im,
                            used_nano_banana=True,
                            model_used="hf_flux_schnell_regen",
                            prompt_used=regen_prompt,
                            cache_hit=False,
                        )
            except Exception as exc:
                log.warning("HF FLUX.1-schnell zaxiraga tushdi: %s", exc)

        # 3-ZAXIRA (bulutli GPU band/oflayn bo'lganda): reklama stikerlarini o'tkazmasdan toza studiya natijasini berish
        from .media import resolve_real_item_photo

        fallback = extract_main_item(raw_pil, category=cat, use_cache=use_cache)
        if fallback is not None:
            fallback = _scrub_promo_fire_stickers_rgba(fallback)
        # Agar xom rasmda sariq/olovli xitoy reklama stikerlari ustun bo'lsa va fallback faqat kichik/sariq dog' qoldirsa, toza studiya rasmini olamiz
        raw_rgb_arr = np.asarray(raw_pil.convert("RGB"), dtype=np.float32)
        yellow_orange_ratio = float(
            np.mean((raw_rgb_arr[:, :, 0] > 190) & (raw_rgb_arr[:, :, 1] >= 40) & (raw_rgb_arr[:, :, 1] <= 215) & (raw_rgb_arr[:, :, 2] < 75) & ((raw_rgb_arr[:, :, 0] - raw_rgb_arr[:, :, 2]) > 115))
        )
        fb_is_bad = (fallback is None) or (not _verify_regenerated_rgba(fallback))
        if fallback is not None and not fb_is_bad:
            fb_alpha = np.asarray(fallback.convert("RGBA").split()[3]) > 30
            fb_rgb = np.asarray(fallback.convert("RGB"), dtype=np.float32)
            if np.any(fb_alpha):
                fb_yo = float(
                    np.mean((fb_rgb[fb_alpha, 0] > 190) & (fb_rgb[fb_alpha, 1] >= 40) & (fb_rgb[fb_alpha, 1] <= 215) & (fb_rgb[fb_alpha, 2] < 75) & ((fb_rgb[fb_alpha, 0] - fb_rgb[fb_alpha, 2]) > 115))
                )
                if (fb_yo > 0.035) or (yellow_orange_ratio > 0.08 and fb_yo > 0.025) or (
                    fallback.width * fallback.height < raw_pil.width * raw_pil.height * 0.22
                ):
                    fb_is_bad = True
        if fb_is_bad:
            asset_fallback = resolve_real_item_photo(str(item.get("name") or ""), 0, cat)
            if asset_fallback is not None:
                fallback = _isolate_from_clean_white_studio_bg(asset_fallback, category=cat)
        polished = self._polish_studio_lighting(fallback) if fallback is not None else raw_pil
        return StudioRenderResult(
            image=polished,
            used_nano_banana=False,
            model_used="local_studio_retouch",
            prompt_used=scout_prompt,
            cache_hit=False,
        )
