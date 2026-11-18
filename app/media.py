"""XAN SHOP - AI Kreativ Rejissyor & 1080p Full HD Video Montajchi v3.2 (VideoEmployeeAgent).

1) True 1080p Full HD (`1080x1920`, H.264 High-Bitrate `8 Mbps`, `-crf 17`) — Instagram va Telegramga
   yuklanganda sifat tushib ketmaydi, kiyimlar ekranning markazida katta va tiniq ko'rinadi.
2) Avto-kadr (`_auto_crop_studio_subject`): studiya rasmidagi ortiqcha bo'sh chetlarni qirqib,
   kiyimning o'zini maksimal katta va aniq ko'rsatadi; qora-oltin kontrast fon esa kiyimni ajratib ko'rsatadi.
3) `insta_analyst` uzatgan auditoriya-persona ("Diplomatiya va Yuridikada o'qiydiganlar uchun",
   "Oversize kiyishni yoqtiradiganlar uchun", "175–188 sm bo'yli yigitlar uchun", "IT va Biznes uchun")
   asosida 4 xil video montaj uslubi (`orbit_3d_turntable`, `persona_spotlight_deck`,
   `editorial_split_showcase`, `bento_zoom_reveal`) va 5 xil musiqa (`diplomat_old_money`,
   `phonk_bass`, `luxury_chill`, `lofi_editorial`, `uk_drill_beat`) bilan ishlaydi.
"""
from __future__ import annotations

import io
import logging
import math
import os
import re
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

BG_COLOR = (244, 243, 239)          # Soft Alabaster Studio (#F4F3EF)
log = logging.getLogger(__name__)


def _item_display_name(raw: Any, idx: int = 0) -> str:
    """Buyum nomini toza matnga aylantiradi (dict/JSON bo'lsa faqat 'name' maydoni — xom dict ekranga chiqmasin)."""
    if isinstance(raw, dict):
        return str(raw.get("name") or raw.get("title") or f"Kiyim {idx + 1}")
    txt = str(raw or "").strip()
    if txt.startswith("{") and "'name'" in txt or txt.startswith('{"name"'):
        m = re.search(r"""['"]name['"]\s*:\s*['"]([^'"]+)['"]""", txt)
        if m:
            return m.group(1)
    return txt or f"Kiyim {idx + 1}"
OBSIDIAN = (14, 16, 22)             # Chuqur Obsidian fon (yuqori kontrast uchun)
DARK_CARD = (22, 25, 34)            # Qora kapsula
DARK_ELEVATED = (30, 35, 46)        # Ikkinchi qavat kapsula
TEXT_MAIN = (18, 20, 24)
TEXT_MUTED = (105, 110, 120)
ACCENT_COLOR = (18, 20, 26)
GOLD_ACCENT = (220, 174, 82)        # Oltin aksent
EMERALD_OK = (46, 204, 138)         # Ishonch yashil rangi
BADGE_BORDER = (218, 214, 204)

ASSET_DIR = Path("data/pdd_assets")


def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    h = (hex_str or "").lstrip("#")
    if len(h) == 6:
        try:
            return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        except ValueError:
            pass
    return (36, 38, 46)


def _clean_canvas_text(text: str) -> str:
    """Pillow shriftida '□' bo'lib chiqadigan emoji va CJK belgilarni tozalaydi."""
    if not text:
        return ""
    replacements = {
        "✈️": "",
        "✈": "",
        "⚡": "",
        "💬": "",
        "🛡️": "",
        "🛡": "",
        "✅": "",
        "✓": "",
        "❌": "",
        "🔥": "",
        "👑": "",
        "🎯": "",
        "万+件": "0K+",
        "万+": "0K+",
        "件": "",
    }
    out = str(text)
    for k, v in replacements.items():
        out = out.replace(k, v)
    cleaned_chars = []
    for ch in out:
        cp = ord(ch)
        if cp < 0x2500 or ch in ("•", "—", "–", "’", "‘", "“", "”", "°", "¥"):
            cleaned_chars.append(ch)
    return " ".join("".join(cleaned_chars).split())


def _load_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    font_names = (
        ["segoeuib.ttf", "arialbd.ttf", "calibrib.ttf", "DejaVuSans-Bold.ttf"]
        if bold
        else ["segoeui.ttf", "arial.ttf", "calibri.ttf", "DejaVuSans.ttf"]
    )
    for name in font_names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _auto_crop_studio_subject(img: Image.Image) -> Image.Image:
    """Studiya rasmining fonini va soyasini xavfsiz qirqib (hech qachon yeng yoki oq krossovkani kesib yubormasdan) qaytaradi."""
    return _extract_garment_cutout_rgba(img)


def _extract_garment_cutout_rgba(img: Image.Image, category: str = "") -> Image.Image:
    """Asosiy buyumni ajratadi: 1) AI Cutout Agent (BiRefNet/ISNet/cloth-seg), 2) zaxira — klassik fon-qirqish."""
    if img.mode == "RGBA":
        a = np.asarray(img.split()[3])
        if (a < 250).mean() > 0.05:  # allaqachon kesilgan (shaffof) rasm
            bb = img.getbbox()
            return img.crop(bb) if bb else img
    try:
        from .cutout_agent import extract_main_item

        ai_cut = extract_main_item(img, category)
        if ai_cut is not None:
            return ai_cut
    except Exception as exc:  # AI ishlamasa ham Reels to'xtamasin
        log.warning("AI cutout zaxiraga o'tdi: %s", exc)
    return _classic_garment_cutout_rgba(img)


def _classic_garment_cutout_rgba(img: Image.Image) -> Image.Image:
    """Studiya rasmining yorqin/bej fonini va ostidagi yumshoq soyasini toza qirqib (transparent PNG cutout) qaytaradi."""
    from collections import deque

    rgb = img.convert("RGB")
    arr = np.asarray(rgb, dtype=np.float32)
    h, w, _ = arr.shape
    if h < 40 or w < 40:
        return img.convert("RGBA")

    patch_h, patch_w = max(4, h // 20), max(4, w // 20)
    top_corners = np.concatenate([
        arr[:patch_h, :patch_w, :].reshape(-1, 3),
        arr[:patch_h, w - patch_w:, :].reshape(-1, 3),
    ], axis=0)
    bg_col = np.median(top_corners, axis=0)

    dist = np.linalg.norm(arr - bg_col[None, None, :], axis=2)
    lum = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
    chroma = np.max(arr, axis=2) - np.min(arr, axis=2)

    gx = np.zeros_like(lum)
    gy = np.zeros_like(lum)
    gx[:, 1:-1] = np.abs(lum[:, 2:] - lum[:, :-2])
    gy[1:-1, :] = np.abs(lum[2:, :] - lum[:-2, :])
    grad = np.hypot(gx, gy)

    y_grid = np.linspace(0.0, 1.0, h)[:, None]
    center_lum = float(np.median(lum[int(h * 0.25):int(h * 0.75), int(w * 0.25):int(w * 0.75)]))
    upper_thr = 19.0 if center_lum > 120.0 else 28.0
    is_neutral_wall_shadow = (lum > 175.0) & (chroma < 17.0) & (dist < 68.0)
    is_upper_bg = (dist < upper_thr) | is_neutral_wall_shadow
    is_lower_bg = (dist < (28.0 if center_lum > 120.0 else 44.0)) | is_neutral_wall_shadow | (
        (center_lum <= 120.0) & (lum > 115.0) & (chroma < 38.0) & (dist < 100.0)
    )
    is_bg_cand = np.where(y_grid < 0.80, is_upper_bg, is_lower_bg)

    sh, sw = max(1, h // 2), max(1, w // 2)
    cand_s = is_bg_cand[::2, ::2]
    sh_actual, sw_actual = cand_s.shape
    vis_s = np.zeros((sh_actual, sw_actual), dtype=bool)
    qs: deque[tuple[int, int]] = deque()

    for x in range(sw_actual):
        if cand_s[0, x]:
            vis_s[0, x] = True
            qs.append((0, x))
        if cand_s[sh_actual - 1, x]:
            vis_s[sh_actual - 1, x] = True
            qs.append((sh_actual - 1, x))
    for y in range(sh_actual):
        if cand_s[y, 0] and not vis_s[y, 0]:
            vis_s[y, 0] = True
            qs.append((y, 0))
        if cand_s[y, sw_actual - 1] and not vis_s[y, sw_actual - 1]:
            vis_s[y, sw_actual - 1] = True
            qs.append((y, sw_actual - 1))

    while qs:
        cy, cx = qs.popleft()
        for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
            if 0 <= ny < sh_actual and 0 <= nx < sw_actual and not vis_s[ny, nx] and cand_s[ny, nx]:
                vis_s[ny, nx] = True
                qs.append((ny, nx))

    fg_small = ~vis_s
    lum_s = lum[::2, ::2]
    chroma_s = chroma[::2, ::2]
    dist_s = dist[::2, ::2]

    # Agar sintetik test rasmi (bir xil tekis rangli kvadrat) bo'lsa, o'z holicha qaytaramiz
    if int(fg_small.sum()) < int(sh_actual * sw_actual * 0.04):
        return img.convert("RGBA")

    # Yeng va tana orasidagi yopiq oq/kulrang devor soyasini tozalash (bej matoga tegmasdan)
    if 120.0 < center_lum < 205.0:
        fg_small = fg_small & ~((lum_s > 180.0) & (chroma_s < 16.5) & (dist_s < 65.0))
    elif fg_small.any() and float(np.median(lum_s[fg_small])) < 95.0:
        fg_small = fg_small & (lum_s < 158.0)

    comp_id = np.zeros((sh_actual, sw_actual), dtype=np.int32)
    comp_sizes: dict[int, int] = {}
    cid = 0
    for y in range(sh_actual):
        for x in range(sw_actual):
            if fg_small[y, x] and comp_id[y, x] == 0:
                cid += 1
                cnt = 0
                comp_id[y, x] = cid
                qc: deque[tuple[int, int]] = deque([(y, x)])
                while qc:
                    yy, xx = qc.popleft()
                    cnt += 1
                    for nyy, nxx in ((yy - 1, xx), (yy + 1, xx), (yy, xx - 1), (yy, xx + 1)):
                        if 0 <= nyy < sh_actual and 0 <= nxx < sw_actual and fg_small[nyy, nxx] and comp_id[nyy, nxx] == 0:
                            comp_id[nyy, nxx] = cid
                            qc.append((nyy, nxx))
                comp_sizes[cid] = cnt

    if comp_sizes:
        max_sz = max(comp_sizes.values())
        keep_ids = {k for k, v in comp_sizes.items() if v >= max_sz * 0.12}
        fg_small = np.isin(comp_id, list(keep_ids))

    mask_im = Image.fromarray((fg_small.astype(np.uint8) * 255), mode="L").resize((w, h), Image.Resampling.BILINEAR)
    mask_im = mask_im.filter(ImageFilter.MinFilter(5)).filter(ImageFilter.MedianFilter(3)).filter(ImageFilter.GaussianBlur(1.2))

    mask_np = np.asarray(mask_im, dtype=np.float32) / 255.0
    rgb_defringed = arr.copy()
    edge_zone = (mask_np > 0.01) & (mask_np < 0.96)
    rgb_defringed[edge_zone] = rgb_defringed[edge_zone] * (mask_np[edge_zone, None] ** 0.85)

    bbox = mask_im.point(lambda p: 255 if p > 25 else 0).getbbox()
    rgba = Image.fromarray(np.clip(rgb_defringed, 0, 255).astype(np.uint8), mode="RGB").convert("RGBA")
    rgba.putalpha(mask_im)
    if bbox:
        rgba = rgba.crop(bbox)
    return rgba


def _paste_cutout_with_shadow(canvas: Image.Image, cutout: Image.Image, box: tuple[int, int, int, int]) -> None:
    """Kesilgan kiyimni (@_tima_shop uslubida) yumshoq tabiiy soya bilan to'q mat fonga joylashtiradi."""
    sx, sy, sw, sh = box
    fitted = ImageOps.contain(cutout, (sw, sh), Image.Resampling.LANCZOS)
    px = sx + (sw - fitted.width) // 2
    py = sy + (sh - fitted.height) // 2

    alpha = fitted.split()[3]
    shadow = Image.new("RGBA", (fitted.width + 64, fitted.height + 64), (0, 0, 0, 0))
    sh_mask = alpha.point(lambda p: int(p * 0.78))
    shadow.paste((5, 5, 7, 255), (34, 34), sh_mask)
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))

    canvas.alpha_composite(shadow, (px - 18, py - 12))
    canvas.alpha_composite(fitted, (px, py))


def resolve_real_item_photo(name: str, idx: int = 0, category: str = "") -> Image.Image | None:
    """Buyum nomi yoki kategoriyasiga mos HAQIQIY studiya kiyim rasmini (`data/pdd_assets/`) qaytaradi."""
    if not ASSET_DIR.is_dir():
        return None

    low = f"{name or ''} {category or ''}".lower()
    candidates: list[str] = []

    if any(k in low for k in ("palto", "overcoat", "trench", "plosh", "ikki qatorli")):
        candidates = ["studio_overcoat.jpg", "studio_bomber.jpg"]
    elif any(k in low for k in ("blazer", "pidjak", "kostyum", "ko'k jun")):
        candidates = ["studio_blazer_navy.jpg", "studio_overcoat.jpg"]
    elif any(k in low for k in ("bomber", "kurtka", "vetrovka", "kardigan", "outerwear", "jacket", "coat")):
        candidates = ["studio_bomber.jpg", "studio_overcoat.jpg"]
    elif any(k in low for k in ("vodolazka", "turtleneck", "kashemir", "kashmir", "qahva sviter", "to'q jigarrang sviter")):
        candidates = ["studio_turtleneck.jpg", "studio_halfzip.jpg"]
    elif any(k in low for k in ("svitshot", "half-zip", "zamok", "sviter", "polo", "trikotaj", "jemper", "pullover")):
        candidates = ["studio_halfzip.jpg", "studio_turtleneck.jpg"]
    elif any(k in low for k in ("xudi", "hoodie", "tolstovka", "top")):
        candidates = ["studio_hoodie.jpg", "studio_halfzip.jpg"]
    elif any(k in low for k in ("kargo", "parachute", "jinsi", "denim", "cho'ntak", "cargo", "jeans")):
        candidates = ["studio_cargo.jpg", "studio_trousers.jpg"]
    elif any(k in low for k in ("taupe", "jigarrang", "mocha", "qahva shim", "brown")) and any(k in low for k in ("shim", "bryuk", "trouser", "pants", "bottom")):
        candidates = ["studio_trousers_brown.jpg", "studio_trousers.jpg"]
    elif any(k in low for k in ("shim", "bryuk", "drape", "joger", "bottom", "klassik", "trousers", "pants")):
        candidates = ["studio_trousers.jpg", "studio_trousers_brown.jpg"]
    elif any(k in low for k in ("chelsea", "etik", "botinka", "qishki poyabzal")):
        candidates = ["studio_chelsea_boots.jpg", "studio_loafers.jpg"]
    elif any(k in low for k in ("lofer", "zamsh", "tufli", "moccasin", "klassik poyabzal", "loafer")):
        candidates = ["studio_loafers.jpg", "studio_chelsea_boots.jpg"]
    elif any(k in low for k in ("krossovka", "sneaker", "runner", "oyoq", "poyabzal", "shoes")):
        candidates = ["shoes_sneaker_retro.jpg", "studio_loafers.jpg", "studio_chelsea_boots.jpg"]
    elif any(k in low for k in ("kepka", "shapka", "aksessuar", "accessory", "cap", "hat", "sumka", "soat", "ko'zoynak")):
        candidates = ["studio_cap.jpg"]

    default_cycle = [
        "studio_overcoat.jpg",
        "studio_turtleneck.jpg",
        "studio_trousers_brown.jpg",
        "studio_chelsea_boots.jpg",
        "studio_blazer_navy.jpg",
        "studio_halfzip.jpg",
        "studio_trousers.jpg",
        "studio_loafers.jpg",
        "studio_bomber.jpg",
        "studio_hoodie.jpg",
        "studio_cargo.jpg",
        "studio_sneakers.jpg",
        "studio_cap.jpg",
    ]
    candidates.append(default_cycle[idx % len(default_cycle)])

    for fname in candidates:
        fpath = ASSET_DIR / fname
        if fpath.is_file():
            try:
                raw = Image.open(fpath)
                return raw.convert("RGBA")
            except Exception:
                continue
    return None


def _prepare_clean_product_card(
    raw_img: Image.Image,
    target_size: tuple[int, int] = (780, 940),
    gold_border: bool = True,
) -> Image.Image:
    """Kiyim studiya rasmini @_tima_shop uslubida fon-qirqilgan (transparent cutout + 3D soya) holatda qaytaradi."""
    tw, th = target_size
    card = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    cutout = _extract_garment_cutout_rgba(raw_img)
    _paste_cutout_with_shadow(card, cutout, (24, 24, tw - 48, th - 48))
    return card


def _load_raw_image(
    raw: Image.Image | str | bytes | Path | None,
    fallback_name: str,
    idx: int,
    color_hex: str = "#1E1E22",
) -> Image.Image:
    try:
        if isinstance(raw, (str, Path)) and os.path.exists(str(raw)):
            return Image.open(raw).convert("RGBA")
        if isinstance(raw, bytes):
            return Image.open(io.BytesIO(raw)).convert("RGBA")
        if isinstance(raw, Image.Image):
            return raw.convert("RGBA")
    except Exception:
        pass
    real_photo = resolve_real_item_photo(fallback_name, idx)
    if real_photo is not None:
        return real_photo
    return generate_item_studio_card(fallback_name, idx, color_hex=color_hex)


def generate_item_studio_card(
    name: str,
    idx: int,
    price_cny: float = 0,
    color_hex: str = "#1E1E22",
    sales_tip: str = "",
    size: tuple[int, int] = (640, 760),
) -> Image.Image:
    """Chizilgan eskiz o'rniga yiriklashtirilgan haqiqiy studiya kiyim rasmini qaytaradi."""
    real_photo = resolve_real_item_photo(name, idx)
    if real_photo is not None:
        bg_col = real_photo.convert("RGB").getpixel((2, 2))
        canvas = Image.new("RGBA", size, (*bg_col, 255))
        fitted = ImageOps.contain(real_photo, (size[0] - 16, size[1] - 16), Image.Resampling.LANCZOS)
        px = (size[0] - fitted.width) // 2
        py = (size[1] - fitted.height) // 2
        canvas.alpha_composite(fitted, (px, py))
        return canvas

    img = Image.new("RGBA", size, (*BG_COLOR, 255))
    draw = ImageDraw.Draw(img)
    w, h = size
    fg = _hex_to_rgb(color_hex)
    draw.rounded_rectangle([24, 24, w - 24, h - 24], radius=28, fill=(255, 255, 255, 255), outline=BADGE_BORDER, width=2)
    draw.ellipse([w // 2 - 90, h // 2 - 90, w // 2 + 90, h // 2 + 90], fill=(*fg, 255))
    return img


def find_ffmpeg_binary() -> str | None:
    """Tizimdagi yoki lokal (CapCut / Winget / Docker) FFmpeg binar faylini topadi."""
    sys_ff = shutil.which("ffmpeg")
    if sys_ff:
        return sys_ff

    candidates = [
        r"C:\Users\user\CapCut\8.3.0.3497\ffmpeg.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe"),
    ]
    capcut_root = os.path.expandvars(r"%USERPROFILE%\CapCut")
    if os.path.isdir(capcut_root):
        for sub in sorted(os.listdir(capcut_root), reverse=True):
            cand = os.path.join(capcut_root, sub, "ffmpeg.exe")
            if os.path.isfile(cand):
                candidates.insert(0, cand)

    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def synthesize_reels_beat_wav(
    output_wav: str | Path,
    duration_sec: float = 6.8,
    vibe: str = "phonk_bass",
    sample_rate: int = 44100,
    transition_times: Sequence[float] | None = None,
) -> str:
    """5 xil auditoriya musiqasi (`diplomat_old_money`, `phonk_bass`, `luxury_chill`, `lofi_editorial`, `uk_drill_beat`)
    + Whoosh & Camera Shutter saund-dizayn sintezatori."""
    out = Path(output_wav)
    out.parent.mkdir(parents=True, exist_ok=True)

    custom_dir = Path("data/audio")
    if custom_dir.is_dir():
        vibe_clean = re.sub(r"[^a-zA-Z0-9_-]", "", vibe or "").lower()
        viral_vibe_matches: list[Path] = []
        vibe_matches: list[Path] = []
        viral_all: list[Path] = []
        all_tracks: list[Path] = []
        for ext in ("wav", "mp3", "m4a"):
            if vibe_clean:
                viral_vibe_matches.extend(sorted(custom_dir.glob(f"{vibe_clean}*viral*.{ext}")))
                vibe_matches.extend(sorted(custom_dir.glob(f"{vibe_clean}*.{ext}")))
            viral_all.extend(sorted(custom_dir.glob(f"*viral*.{ext}")))
            all_tracks.extend(sorted(custom_dir.glob(f"*.{ext}")))
        pool = viral_vibe_matches or viral_all or vibe_matches or all_tracks
        if pool:
            picked = pool[int(duration_sec * 10) % len(pool)]
            ff = find_ffmpeg_binary()
            if ff:
                try:
                    fade_out_st = max(0.4, round(float(duration_sec) - 0.55, 2))
                    proc = subprocess.run(
                        [
                            ff, "-y", "-stream_loop", "-1", "-i", str(picked),
                            "-t", f"{max(1.5, float(duration_sec)):.2f}",
                            "-af", f"afade=t=in:st=0:d=0.35,afade=t=out:st={fade_out_st:.2f}:d=0.55,volume=0.88",
                            "-ar", str(sample_rate), "-ac", "2",
                            str(out),
                        ],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=25,
                    )
                    if proc.returncode == 0 and out.exists() and out.stat().st_size > 2000:
                        return str(out)
                except Exception:
                    pass
            return str(picked)

    n_samples = int(max(1.5, duration_sec) * sample_rate)
    t = np.linspace(0, duration_sec, n_samples, endpoint=False)

    bpm_map = {
        "diplomat_old_money": 104.0,
        "phonk_bass": 126.0,
        "luxury_chill": 112.0,
        "lofi_editorial": 96.0,
        "uk_drill_beat": 138.0,
    }
    bpm = bpm_map.get(vibe, 120.0)
    beat_period = 60.0 / bpm
    beat_phase = (t % beat_period) / beat_period

    riser_sec = 0.50
    riser_env = np.clip(t / riser_sec, 0.0, 1.0) ** 1.5
    riser_mask = (t < riser_sec).astype(float)
    riser_freq = 105.0 + 420.0 * (t / riser_sec)
    riser = np.sin(2 * np.pi * riser_freq * t) * 0.16 * riser_env * riser_mask

    drop_mask = (t >= riser_sec).astype(float)
    kick_freq = 48.0 + 105.0 * np.exp(-beat_phase * 20.0)
    kick_env = np.exp(-beat_phase * 5.2)
    sub_808 = np.sin(2 * np.pi * 45.0 * t) * np.exp(-beat_phase * 2.4) * 0.28 * drop_mask
    kick = np.sin(2 * np.pi * kick_freq * (t % beat_period)) * kick_env * 0.52 * drop_mask

    chord_progressions = {
        "diplomat_old_money": [110.0, 130.81, 164.81, 146.83],  # A minor -> C major -> E minor -> D minor (Royal Piano/Strings)
        "phonk_bass": [110.0, 116.54, 130.81, 116.54],          # Dark Phonk minor second
        "luxury_chill": [130.81, 164.81, 196.0, 220.0],         # Warm Lounge Cmaj7 -> Am7
        "lofi_editorial": [146.83, 174.61, 196.0, 164.81],      # Neo-Soul Dm7 -> Fmaj7 -> G6
        "uk_drill_beat": [98.0, 116.54, 110.0, 92.50],          # Drill dark glide
    }
    notes = chord_progressions.get(vibe, chord_progressions["phonk_bass"])
    bar_idx = (t // (beat_period * 2)).astype(int) % len(notes)
    base_freq = np.choose(bar_idx, notes)

    # Boyitilgan akkord tembri
    pad = (
        0.18 * np.sin(2 * np.pi * base_freq * t)
        + 0.11 * np.sin(2 * np.pi * (base_freq * 1.25) * t)
        + 0.08 * np.sin(2 * np.pi * (base_freq * 1.5) * t)
    ) * (0.60 + 0.40 * np.exp(-beat_phase * 3.6)) * drop_mask

    hat_div = 3.0 if vibe == "uk_drill_beat" else 2.0
    hat_phase = (t % (beat_period / hat_div)) / (beat_period / hat_div)
    rng = np.random.default_rng(42)
    noise = rng.uniform(-1.0, 1.0, n_samples)
    hihat = noise * np.exp(-hat_phase * 34.0) * 0.10 * drop_mask

    sfx = np.zeros(n_samples, dtype=float)
    cuts = list(transition_times) if transition_times else [0.8, 2.0, 3.2, 4.4, 5.4]
    for cut_t in cuts:
        if 0.1 < cut_t < duration_sec - 0.08:
            w_mask = (t >= cut_t - 0.14) & (t < cut_t)
            if np.any(w_mask):
                wt = (t[w_mask] - (cut_t - 0.14)) / 0.14
                sfx[w_mask] += noise[w_mask] * (wt ** 2) * 0.19
            c_mask = (t >= cut_t) & (t < cut_t + 0.04)
            if np.any(c_mask):
                ct = (t[c_mask] - cut_t) / 0.04
                soft_thump = np.sin(2 * np.pi * 165.0 * (t[c_mask] - cut_t)) * np.exp(-ct * 14.0)
                sfx[c_mask] += (soft_thump * 0.08) + (noise[c_mask] * np.exp(-ct * 18.0) * 0.04)

    mix_l = np.clip(riser + kick + sub_808 + pad + hihat * 1.04 + sfx, -0.95, 0.95)
    mix_r = np.clip(riser + kick + sub_808 + pad * 0.96 + hihat * 0.92 + sfx, -0.95, 0.95)
    pcm_l = (mix_l * 32767).astype(np.int16)
    pcm_r = (mix_r * 32767).astype(np.int16)
    stereo = np.column_stack((pcm_l, pcm_r)).ravel()

    with wave.open(str(out), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(stereo.tobytes())

    return str(out)


def _estimate_item_prices_uzs(total_price_uzs: int, count: int) -> list[int]:
    if count <= 1:
        return [total_price_uzs]
    weights_map = {
        2: [0.58, 0.42],
        3: [0.42, 0.32, 0.26],
        4: [0.34, 0.26, 0.24, 0.16],
        5: [0.30, 0.22, 0.20, 0.18, 0.10],
    }
    w = weights_map.get(count, [1.0 / count] * count)
    out = [int(round((total_price_uzs * wi) / 5000.0) * 5000) for wi in w]
    diff = total_price_uzs - sum(out)
    out[0] += diff
    return out


def _fit_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    start_size: int = 32,
    min_size: int = 16,
    bold: bool = True,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Matnni kesmasdan (qisqartirmasdan) qutiga sig'dirish uchun mos shrift o'lchamini tanlaydi."""
    for sz in range(start_size, min_size - 1, -2):
        fnt = _load_font(sz, bold=bold)
        try:
            bbox = draw.textbbox((0, 0), text, font=fnt)
            if (bbox[2] - bbox[0]) <= max_width:
                return fnt
        except Exception:
            return fnt
    return _load_font(min_size, bold=bold)


def create_look_collage(
    images: Sequence[Image.Image | str | bytes | Path],
    look_title: str,
    total_price_uzs: int,
    item_names: Sequence[str] | None = None,
    shop_brand: str = "XAN SHOP",
    canvas_size: tuple[int, int] = (1080, 1350),
    prepay_50_uzs: int | None = None,
    palette_hex: Sequence[str] | None = None,
    palette_name: str = "",
    persona_hook: str = "",
) -> Image.Image:
    """@_tima_shop ('RASMDA:' / 'TRENDA YURGAN LOOKGA OBZOR') uslubidagi toza Dark Matte Flat-Lay Lookbook Kolaj."""
    width, height = canvas_size
    canvas = Image.new("RGBA", canvas_size, (46, 46, 49, 255))
    draw = ImageDraw.Draw(canvas)
    for y in range(0, height, 4):
        u = y / max(height - 1, 1)
        v = int(52 * (1 - u) + 32 * u)
        draw.rectangle([0, y, width, y + 4], fill=(v, v, v + 2, 255))

    half_val = prepay_50_uzs or (total_price_uzs // 2)
    half_str = f"{half_val:,}".replace(",", " ") + " so'm"
    price_str = f"{total_price_uzs:,}".replace(",", " ") + " so'm"
    clean_title = _clean_canvas_text(look_title)

    hdr_text = "RASMDA:" if ("diplomat" in clean_title.lower() or "klassik" in clean_title.lower() or "old money" in clean_title.lower()) else "TRENDA YURGAN LOOKGA OBZOR"
    f_hdr = _fit_font(draw, hdr_text, width - 120, start_size=44, min_size=26, bold=True)
    bbox = draw.textbbox((0, 0), hdr_text, font=f_hdr)
    tw = bbox[2] - bbox[0]
    draw.text(((width - tw) // 2 + 2, 58 + 3), hdr_text, fill=(0, 0, 0, 170), font=f_hdr)
    draw.text(((width - tw) // 2, 58), hdr_text, fill=(255, 255, 255, 255), font=f_hdr)

    cutouts: list[Image.Image] = []
    max_items = min(max(len(images), 1), 5)
    for idx, item in enumerate(images[:max_items]):
        nm = _item_display_name(item_names[idx], idx) if item_names and idx < len(item_names) else f"Kiyim {idx + 1}"
        hx = palette_hex[idx % len(palette_hex)] if palette_hex else "#1E1E22"
        raw_im = _load_raw_image(item, nm, idx, hx)
        from .cutout_agent import guess_category

        cutouts.append(_extract_garment_cutout_rgba(raw_im, guess_category(nm)))

    count = len(cutouts)
    top_area = 136
    bottom_area = height - 118
    usable_h = bottom_area - top_area
    usable_w = width - 96

    if count == 1:
        slots = [(48, top_area, usable_w, usable_h)]
    elif count == 2:
        slot_w = (usable_w - 24) // 2
        slots = [
            (48, top_area, slot_w, usable_h),
            (48 + slot_w + 24, top_area, slot_w, usable_h),
        ]
    elif count == 3:
        slots = [
            (54, top_area, 460, int(usable_h * 0.50)),
            (546, top_area + 14, 460, int(usable_h * 0.48)),
            (270, top_area + int(usable_h * 0.47), 540, int(usable_h * 0.53)),
        ]
    elif count == 4:
        slots = [
            (60, top_area + 10, 450, int(usable_h * 0.45)),
            (520, top_area - 6, 490, int(usable_h * 0.49)),
            (85, top_area + int(usable_h * 0.45), 430, int(usable_h * 0.55)),
            (535, top_area + int(usable_h * 0.54), 460, int(usable_h * 0.36)),
        ]
    else:
        top_w = (usable_w - 20) // 2
        bot_w = (usable_w - 40) // 3
        row_h = (usable_h - 20) // 2
        slots = [
            (48, top_area, top_w, row_h),
            (48 + top_w + 20, top_area, top_w, row_h),
            (48, top_area + row_h + 20, bot_w, row_h),
            (48 + bot_w + 20, top_area + row_h + 20, bot_w, row_h),
            (48 + (bot_w + 20) * 2, top_area + row_h + 20, bot_w, row_h),
        ]

    for cut, slot in zip(cutouts, slots):
        _paste_cutout_with_shadow(canvas, cut, slot)

    # Pastda faqat ixcham, minimalistik ma'lumot chizig'i (ekranni to'sib qo'ymaydigan)
    bar_str = f"{clean_title}  •  50% oldindan: {half_str}  (To'liq: {price_str})"
    f_bar = _fit_font(draw, bar_str, width - 120, start_size=24, min_size=16, bold=True)
    b_box = draw.textbbox((0, 0), bar_str, font=f_bar)
    bw = b_box[2] - b_box[0]
    pill_x0 = max(36, (width - bw) // 2 - 28)
    pill_x1 = min(width - 36, (width + bw) // 2 + 28)
    draw.rounded_rectangle([pill_x0, height - 88, pill_x1, height - 28], radius=30, fill=(20, 20, 23, 215))
    draw.text(((width - bw) // 2, height - 73), bar_str, fill=(242, 242, 245), font=f_bar)

    return canvas.convert("RGB")


def _draw_1080p_header_and_footer(
    draw: ImageDraw.ImageDraw,
    w: int,
    h: int,
    shop_brand: str,
    persona_hook: str,
    sub_hook: str,
    look_title: str,
    cur_name: str,
    cur_price_uzs: int,
    active_idx: int,
    total_items: int,
    total_price_uzs: int,
    prepay_50_uzs: int,
    pop_scale: float = 1.0,
) -> None:
    """1080x1920 Full HD kadrning yuqori (Persona Hook) va pastki (Hozirgi narx 50% + kargo) bloklarini chizadi."""
    clean_brand = _clean_canvas_text(shop_brand).upper()
    clean_hook = _clean_canvas_text(persona_hook or look_title).upper()
    clean_sub = _clean_canvas_text(sub_hook or "Avia 5–10 kun • Toshkentda ko'rib olasiz")

    # 1. Yuqori Auditoriya-Persona Kapsulasi (ortiqcha 3-QISM / 1080P STUDIO yozuvlarisiz, so'zlarni kesmasdan!)
    draw.rounded_rectangle([48, 52, w - 48, 232], radius=34, fill=(22, 26, 36, 245), outline=GOLD_ACCENT, width=3)
    draw.rounded_rectangle([74, 74, 260, 118], radius=14, fill=GOLD_ACCENT)
    draw.text((94, 82), clean_brand, fill=OBSIDIAN, font=_load_font(22, bold=True))
    draw.text((284, 81), "AVIA 5–10 KUN", fill=EMERALD_OK, font=_load_font(22, bold=True))

    max_txt_w = w - 148
    f_hook = _fit_font(draw, clean_hook, max_txt_w, start_size=31, min_size=19, bold=True)
    draw.text((74, 132), clean_hook, fill=(255, 255, 255), font=f_hook)
    f_sub = _fit_font(draw, clean_sub, max_txt_w, start_size=22, min_size=16, bold=False)
    draw.text((74, 180), clean_sub, fill=(195, 202, 216), font=f_sub)

    # 2. O'rtadagi Kiyimning Chiqib Turadigan Narxi
    cur_price_str = f"{cur_price_uzs:,}".replace(",", " ") + " so'm"
    pill_y = int(h * 0.720 - 14 * pop_scale)
    draw.rounded_rectangle(
        [56, pill_y, w - 56, pill_y + 124],
        radius=42,
        fill=(18, 21, 30, 248),
        outline=GOLD_ACCENT,
        width=3,
    )
    clean_cur = _clean_canvas_text(cur_name)
    f_cur = _fit_font(draw, clean_cur, w - 330, start_size=34, min_size=20, bold=True)
    draw.text((92, pill_y + 20), clean_cur, fill=(255, 255, 255), font=f_cur)
    draw.text((92, pill_y + 70), f"Alohida qiymati: ~{cur_price_str}", fill=GOLD_ACCENT, font=_load_font(27, bold=True))
    draw.rounded_rectangle([w - 210, pill_y + 32, w - 88, pill_y + 92], radius=22, fill=DARK_ELEVATED)
    draw.text((w - 180, pill_y + 44), f"{active_idx + 1} / {total_items}", fill=(235, 238, 246), font=_load_font(28, bold=True))

    # 3. Pastki Sodda Ishonch va 50% + Kargo Xarid Bloki
    tot_str = f"{total_price_uzs:,}".replace(",", " ") + " so'm"
    half_str = f"{prepay_50_uzs:,}".replace(",", " ") + " so'm"
    dock_y = h - 364
    draw.rounded_rectangle([48, dock_y, w - 48, h - 64], radius=44, fill=(18, 21, 30, 252), outline=(68, 76, 96), width=2)
    draw.text((84, dock_y + 24), f"To'liq narxi: {tot_str}", fill=(205, 212, 226), font=_load_font(27, bold=True))
    draw.text((84, dock_y + 66), f"Hozirgi narx (50%): {half_str}", fill=GOLD_ACCENT, font=_load_font(44, bold=True))
    draw.text(
        (84, dock_y + 126),
        "+ kargo (qolgan 50% + kargo Toshkentga kelganda)",
        fill=EMERALD_OK,
        font=_load_font(26, bold=True),
    )
    draw.text(
        (84, dock_y + 172),
        "Kiyim Toshkentga kelib, ko'rganingizda to'laysiz!",
        fill=(242, 244, 250),
        font=_load_font(24, bold=False),
    )
    draw.text(
        (84, dock_y + 216),
        "Buyurtma va razmer uchun izohda '+' qoldiring",
        fill=GOLD_ACCENT,
        font=_load_font(25, bold=True),
    )


def _render_1080p_styled_frame(
    product_cards: Sequence[Image.Image],
    item_names: Sequence[str],
    item_prices_uzs: Sequence[int],
    progress: float,
    active_idx: int,
    sub_u: float,
    look_title: str,
    total_price_uzs: int,
    prepay_50_uzs: int,
    shop_brand: str = "XAN SHOP",
    persona_hook: str = "",
    sub_hook: str = "",
    video_style: str = "orbit_3d_turntable",
    frame_size: tuple[int, int] = (1080, 1920),
) -> Image.Image:
    """@_tima_shop ('RASMDA:' / 'TRENDA YURGAN LOOKGA OBZOR') uslubida 1080x1920 Dark Matte Cutout kadr chizadi."""
    w, h = frame_size
    n = max(len(product_cards), 1)
    frame = Image.new("RGBA", (w, h), (46, 46, 49, 255))
    draw = ImageDraw.Draw(frame)

    for y in range(0, h, 8):
        u = y / max(h - 1, 1)
        v = int(52 * (1 - u) + 32 * u)
        draw.rectangle([0, y, w, y + 8], fill=(v, v, v + 2, 255))

    clean_title = _clean_canvas_text(look_title)
    is_classic = any(k in clean_title.lower() for k in ("diplomat", "old money", "klassik"))
    hdr_txt = "RASMDA:" if is_classic else "TRENDA YURGAN LOOKGA OBZOR"

    if progress < 0.45 and n >= 2:
        # 1-qism: Barcha buyumlar toza Flat-Lay ko'rinishida ("RASMDA:" / "TRENDA YURGAN LOOKGA OBZOR")
        f_hdr = _fit_font(draw, hdr_txt, w - 120, start_size=48, min_size=28, bold=True)
        bbox = draw.textbbox((0, 0), hdr_txt, font=f_hdr)
        tw = bbox[2] - bbox[0]
        draw.text(((w - tw) // 2 + 2, 160 + 3), hdr_txt, fill=(0, 0, 0, 170), font=f_hdr)
        draw.text(((w - tw) // 2, 160), hdr_txt, fill=(255, 255, 255, 255), font=f_hdr)

        top_y = 260
        stage_h = int(h * 0.68)
        if n == 2:
            slots = [(60, top_y, 460, stage_h), (560, top_y, 460, stage_h)]
        elif n == 3:
            slots = [
                (60, top_y, 460, int(stage_h * 0.48)),
                (550, top_y + 14, 460, int(stage_h * 0.46)),
                (270, top_y + int(stage_h * 0.46), 540, int(stage_h * 0.54)),
            ]
        else:
            slots = [
                (65, top_y + 10, 445, int(stage_h * 0.45)),
                (520, top_y - 6, 490, int(stage_h * 0.48)),
                (85, top_y + int(stage_h * 0.45), 430, int(stage_h * 0.55)),
                (535, top_y + int(stage_h * 0.54), 460, int(stage_h * 0.36)),
            ]
        for card_im, (sx, sy, sw, sh) in zip(product_cards[:4], slots):
            fitted = ImageOps.contain(card_im, (sw, sh), Image.Resampling.LANCZOS)
            frame.alpha_composite(fitted, (sx + (sw - fitted.width) // 2, sy + (sh - fitted.height) // 2))
    else:
        # 2-qism: Har bir buyum ekran markazida yirik planda (proportsiyasi buzilmasdan!)
        cur_name = _clean_canvas_text(item_names[active_idx] if active_idx < len(item_names) else f"Kiyim {active_idx + 1}")
        f_hdr = _fit_font(draw, clean_title.upper(), w - 120, start_size=40, min_size=24, bold=True)
        bbox = draw.textbbox((0, 0), clean_title.upper(), font=f_hdr)
        tw = bbox[2] - bbox[0]
        draw.text(((w - tw) // 2 + 2, 130 + 3), clean_title.upper(), fill=(0, 0, 0, 170), font=f_hdr)
        draw.text(((w - tw) // 2, 130), clean_title.upper(), fill=(255, 255, 255, 255), font=f_hdr)

        zoom = 0.94 + 0.08 * math.sin(sub_u * math.pi)
        max_w, max_h = int(860 * zoom), int(1160 * zoom)
        fitted = ImageOps.contain(product_cards[active_idx], (max_w, max_h), Image.Resampling.LANCZOS)
        frame.alpha_composite(fitted, ((w - fitted.width) // 2, 240 + (1200 - fitted.height) // 2))

        f_nm = _fit_font(draw, cur_name, w - 140, start_size=36, min_size=22, bold=True)
        nb = draw.textbbox((0, 0), cur_name, font=f_nm)
        nw = nb[2] - nb[0]
        draw.text(((w - nw) // 2 + 2, h - 250 + 2), cur_name, fill=(0, 0, 0, 180), font=f_nm)
        draw.text(((w - nw) // 2, h - 250), cur_name, fill=(255, 255, 255, 255), font=f_nm)

    # Pastki ixcham, ekranni to'smaydigan minimalistik satr
    half_str = f"{prepay_50_uzs:,}".replace(",", " ") + " so'm"
    tot_str = f"{total_price_uzs:,}".replace(",", " ") + " so'm"
    bar_str = f"50% oldindan: {half_str}  •  To'liq: {tot_str}  •  Izohga «+»"
    f_bar = _fit_font(draw, bar_str, w - 120, start_size=26, min_size=18, bold=True)
    bb = draw.textbbox((0, 0), bar_str, font=f_bar)
    bw = bb[2] - bb[0]
    px0 = max(40, (w - bw) // 2 - 32)
    px1 = min(w - 40, (w + bw) // 2 + 32)
    draw.rounded_rectangle([px0, h - 140, px1, h - 72], radius=34, fill=(18, 18, 21, 220))
    draw.text(((w - bw) // 2, h - 122), bar_str, fill=(242, 242, 245, 255), font=f_bar)

    return frame.convert("RGB")


def create_reels_frames(
    images: Sequence[Image.Image | str | bytes | Path],
    look_title: str,
    total_price_uzs: int,
    item_names: Sequence[str] | None = None,
    shop_brand: str = "XAN SHOP",
    frame_size: tuple[int, int] = (1080, 1920),
    prepay_50_uzs: int | None = None,
    palette_hex: Sequence[str] | None = None,
    palette_name: str = "",
    viral_hook: str = "TAYYOR OBRAZ",
    creative_directive: dict[str, Any] | None = None,
) -> list[Image.Image]:
    """True 1080x1920 Full HD Reels kadrlari va 3D/Multi-Style metadata tayyorlovchisi."""
    half_val = prepay_50_uzs or (total_price_uzs // 2)
    total_items = max(len(images), 1)
    names = [_item_display_name(n, i) for i, n in enumerate(item_names)] if item_names else [f"Kiyim {i + 1}" for i in range(total_items)]

    product_cards: list[Image.Image] = []
    cutout_cards: list[Image.Image] = []
    from .cutout_agent import guess_category

    for idx, raw_img in enumerate(images):
        nm = names[idx] if idx < len(names) else f"Kiyim {idx + 1}"
        hx = palette_hex[idx % len(palette_hex)] if palette_hex else "#1E1E22"
        raw_loaded = _load_raw_image(raw_img, nm, idx, hx)
        cut = _extract_garment_cutout_rgba(raw_loaded, guess_category(nm))
        cutout_cards.append(cut)
        product_cards.append(_prepare_clean_product_card(cut, (800, 950), gold_border=True))

    part_prices = _estimate_item_prices_uzs(total_price_uzs, total_items)
    hook_txt = str((creative_directive or {}).get("hook_headline") or viral_hook or look_title)
    sub_hook = str((creative_directive or {}).get("sub_hook") or "Avia 5–10 kun • Toshkentda ko'rib olasiz")
    video_style = str((creative_directive or {}).get("video_style") or "orbit_3d_turntable")
    vibe = str((creative_directive or {}).get("audio_vibe") or "phonk_bass")

    orbit_meta = {
        "product_cards": product_cards,
        "cutout_cards": cutout_cards,
        "item_names": names,
        "item_prices_uzs": part_prices,
        "look_title": look_title,
        "total_price_uzs": total_price_uzs,
        "prepay_50_uzs": half_val,
        "shop_brand": shop_brand,
        "subtitle_hook": hook_txt,
        "sub_hook": sub_hook,
        "video_style": video_style,
        "audio_vibe": vibe,
    }

    frames: list[Image.Image] = []
    for idx in range(total_items):
        fr_1080 = _render_1080p_styled_frame(
            product_cards=product_cards,
            item_names=names,
            item_prices_uzs=part_prices,
            progress=idx / float(total_items),
            active_idx=idx,
            sub_u=0.25,
            look_title=look_title,
            total_price_uzs=total_price_uzs,
            prepay_50_uzs=half_val,
            shop_brand=shop_brand,
            persona_hook=hook_txt,
            sub_hook=sub_hook,
            video_style=video_style,
            frame_size=(1080, 1920),
        )
        if frame_size != (1080, 1920):
            fr_1080 = fr_1080.resize(frame_size, Image.Resampling.LANCZOS)
        fr_1080.info["xan_orbit_meta"] = orbit_meta
        frames.append(fr_1080)

    return frames


def create_hook_intro_slide(
    look_title: str,
    piece_count: int,
    prepay_50_uzs: int,
    shop_brand: str = "XAN SHOP",
    viral_hook: str = "TAYYOR OBRAZ",
    palette_hex: Sequence[str] | None = None,
    frame_size: tuple[int, int] = (1080, 1920),
    preview_images: Sequence[Image.Image | str | bytes | Path] | None = None,
    item_names: Sequence[str] | None = None,
) -> Image.Image:
    total_est = prepay_50_uzs * 2
    cnt = max(piece_count, len(preview_images or []), 2)
    names = list(item_names) if item_names else [f"Kiyim {i + 1}" for i in range(cnt)]
    cards: list[Image.Image] = []
    for i in range(cnt):
        nm = names[i] if i < len(names) else f"Kiyim {i + 1}"
        raw = preview_images[i] if preview_images and i < len(preview_images) else None
        hx = palette_hex[i % len(palette_hex)] if palette_hex else "#1E1E22"
        cards.append(_prepare_clean_product_card(_load_raw_image(raw, nm, i, hx), (800, 950), gold_border=True))

    part_prices = _estimate_item_prices_uzs(total_est, cnt)
    fr = _render_1080p_styled_frame(
        product_cards=cards,
        item_names=names,
        item_prices_uzs=part_prices,
        progress=0.0,
        active_idx=0,
        sub_u=0.0,
        look_title=look_title,
        total_price_uzs=total_est,
        prepay_50_uzs=prepay_50_uzs,
        shop_brand=shop_brand,
        persona_hook=viral_hook,
        frame_size=(1080, 1920),
    )
    return fr.resize(frame_size, Image.Resampling.LANCZOS) if frame_size != (1080, 1920) else fr


def create_comparison_hook_slide(
    look_title: str,
    total_price_uzs: int,
    prepay_50_uzs: int,
    market_price_uzs: int | None = None,
    shop_brand: str = "XAN SHOP",
    frame_size: tuple[int, int] = (1080, 1920),
) -> Image.Image:
    w, h = (1080, 1920)
    card = Image.new("RGB", (w, h), OBSIDIAN)
    draw = ImageDraw.Draw(card)

    tot_str = f"{total_price_uzs:,}".replace(",", " ") + " so'm"
    half_str = f"{prepay_50_uzs:,}".replace(",", " ") + " so'm"

    clean_title = _clean_canvas_text(look_title)
    draw.text((64, 110), _clean_canvas_text(shop_brand).upper(), fill=GOLD_ACCENT, font=_load_font(32, bold=True))
    f_tit = _fit_font(draw, clean_title, w - 128, start_size=46, min_size=24, bold=True)
    draw.text((64, 168), clean_title, fill=(255, 255, 255), font=f_tit)

    draw.rounded_rectangle([56, 280, w - 56, 1020], radius=48, fill=DARK_CARD, outline=GOLD_ACCENT, width=3)
    draw.text((104, 340), "TO'LIQ OBRAZ NARXI:", fill=(190, 196, 210), font=_load_font(34, bold=True))
    draw.text((104, 398), tot_str, fill=(255, 255, 255), font=_load_font(72, bold=True))

    draw.rounded_rectangle([96, 540, w - 96, 940], radius=36, fill=DARK_ELEVATED, outline=GOLD_ACCENT, width=2)
    draw.text((136, 586), "HOZIRGI NARX (50%):", fill=GOLD_ACCENT, font=_load_font(34, bold=True))
    draw.text((136, 646), half_str, fill=(255, 255, 255), font=_load_font(66, bold=True))
    draw.text((136, 744), "+ kargo (Toshkentga kelganda)", fill=EMERALD_OK, font=_load_font(30, bold=True))
    draw.text((136, 804), "Qolgan 50% + kargo — kiyimni ko'rib olganda!", fill=(235, 238, 246), font=_load_font(26, bold=False))

    draw.rounded_rectangle([56, h - 260, w - 56, h - 120], radius=54, fill=GOLD_ACCENT)
    draw.text((120, h - 214), "Buyurtma uchun izohda '+' qoldiring", fill=OBSIDIAN, font=_load_font(38, bold=True))
    return card.resize(frame_size, Image.Resampling.LANCZOS) if frame_size != (1080, 1920) else card


async def synthesize_uzbek_voiceover_async(
    text: str,
    output_path: str | Path,
    voice: str = "uz-UZ-SardorNeural",
) -> str | None:
    try:
        import edge_tts

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        comm = edge_tts.Communicate(text, voice)
        await comm.save(str(out))
        if out.exists() and out.stat().st_size > 500:
            return str(out)
    except Exception:
        pass
    return None


def synthesize_uzbek_voiceover(
    text: str,
    output_path: str | Path,
    voice: str = "uz-UZ-SardorNeural",
) -> str | None:
    import asyncio
    import concurrent.futures

    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, synthesize_uzbek_voiceover_async(text, output_path, voice)).result()
        return asyncio.run(synthesize_uzbek_voiceover_async(text, output_path, voice))
    except Exception:
        return None


def generate_look_voiceover_script(
    look_title: str,
    total_price_uzs: int,
    prepay_50_uzs: int,
    item_names: Sequence[str] | None = None,
) -> str:
    half_str = f"{prepay_50_uzs:,}".replace(",", " ") + " so'm"
    tot_str = f"{total_price_uzs:,}".replace(",", " ") + " so'm"
    items_text = ", ".join(item_names[:3]) if item_names else look_title
    return (
        f"Yangi tayyor obraz: {items_text}. "
        f"Jami narxi {tot_str}. "
        f"Hozir faqat 50 foiz, ya'ni {half_str} to'laysiz, "
        f"qolganini kiyim Toshkentga kelganda ko'rib to'laysiz!"
    )


def save_reels_animation(
    frames: Sequence[Image.Image],
    output_path: str | Path,
    collage: Image.Image | None = None,
    duration_ms: int = 900,
    mp4_path: str | Path | None = None,
    audio_vibe: str = "phonk_bass",
    hook_slide: Image.Image | None = None,
    voiceover_path: str | Path | None = None,
    voiceover_text: str | None = None,
    ai_voice_name: str = "uz-UZ-SardorNeural",
) -> str:
    """GIF preview (540x960) va haqiqiy 1080p Full HD (`1080x1920`, High-Bitrate) `.mp4` Reels yaratadi."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    orbit_meta = None
    for fr in frames:
        if hasattr(fr, "info") and isinstance(fr.info, dict) and fr.info.get("xan_orbit_meta"):
            orbit_meta = fr.info["xan_orbit_meta"]
            break

    gif_size = (540, 960)
    seq_gif: list[Image.Image] = []
    if hook_slide is not None:
        seq_gif.append(hook_slide.resize(gif_size, Image.Resampling.LANCZOS).convert("RGB"))
    for fr in frames:
        seq_gif.append(fr.resize(gif_size, Image.Resampling.LANCZOS).convert("RGB"))

    if collage is not None:
        final_fr = Image.new("RGB", gif_size, OBSIDIAN)
        fitted_c = ImageOps.contain(collage.convert("RGB"), (516, 900), Image.Resampling.LANCZOS)
        final_fr.paste(fitted_c, ((gif_size[0] - fitted_c.width) // 2, (gif_size[1] - fitted_c.height) // 2))
        seq_gif.append(final_fr)

    if not seq_gif:
        seq_gif = [Image.new("RGB", gif_size, OBSIDIAN)]

    seq_gif[0].save(
        str(out),
        format="GIF",
        save_all=True,
        append_images=seq_gif[1:],
        duration=duration_ms,
        loop=0,
        optimize=True,
    )

    if mp4_path is None and str(out).endswith(".gif"):
        mp4_path = str(out)[:-4] + ".mp4"
    if mp4_path:
        actual_voice = voiceover_path
        if not actual_voice and voiceover_text:
            voice_tmp = out.parent / f"{out.stem}_voice.mp3"
            synth_res = synthesize_uzbek_voiceover(voiceover_text, voice_tmp, voice=ai_voice_name)
            if synth_res:
                actual_voice = synth_res
        render_reels_mp4_with_audio(
            frames,
            mp4_path,
            audio_vibe=(orbit_meta or {}).get("audio_vibe") or audio_vibe,
            voiceover_path=actual_voice,
            orbit_meta=orbit_meta,
            collage=collage,
        )

    return str(out)


def render_reels_with_remotion(
    mp4_path: str | Path,
    orbit_meta: dict[str, Any],
    audio_vibe: str = "diplomat_old_money",
) -> str | None:
    """Remotion (React 30fps spring-motion + kinetic subtitles + real MP3 audio) orqali 1080p Reels render qiladi."""
    import json
    import time

    node_bin = shutil.which("node")
    studio_dir = Path("remotion_studio")
    script_path = studio_dir / "render_reel.mjs"
    if not node_bin or not script_path.is_file() or not (studio_dir / "node_modules").is_dir():
        return None

    cards = orbit_meta.get("product_cards") or []
    if not cards:
        return None

    job_id = f"job_{int(time.time() * 1000)}"
    job_public_dir = studio_dir / "public" / "render_jobs" / job_id
    job_public_dir.mkdir(parents=True, exist_ok=True)
    mp4_out = Path(mp4_path)
    mp4_out.parent.mkdir(parents=True, exist_ok=True)

    try:
        names = orbit_meta.get("item_names") or []
        prices = orbit_meta.get("item_prices_uzs") or []
        cutouts = orbit_meta.get("cutout_cards") or []
        items_payload: list[dict[str, Any]] = []
        for idx, card in enumerate(cards):
            img_name = f"item_{idx}.png"
            card_path = job_public_dir / img_name
            src_im = cutouts[idx] if idx < len(cutouts) and cutouts[idx] is not None else _extract_garment_cutout_rgba(card)
            src_im.convert("RGBA").save(card_path, format="PNG")
            items_payload.append({
                "name": str(names[idx] if idx < len(names) else f"Kiyim #{idx + 1}"),
                "priceUzs": int(prices[idx] if idx < len(prices) else 250000),
                "imageFile": f"render_jobs/{job_id}/{img_name}",
            })

        # Haqiqiy MP3/WAV musiqa trekini Remotion public papkasiga ulash
        audio_rel = ""
        audio_tmp = job_public_dir / "track.wav"
        chosen_audio = synthesize_reels_beat_wav(
            audio_tmp,
            duration_sec=max(4.0, len(items_payload) * 1.6 + 1.8),
            vibe=audio_vibe,
        )
        if chosen_audio and os.path.isfile(chosen_audio):
            src_p = Path(chosen_audio)
            if src_p.resolve() != audio_tmp.resolve():
                dest_audio = job_public_dir / f"track{src_p.suffix}"
                shutil.copy2(src_p, dest_audio)
                audio_rel = f"render_jobs/{job_id}/{dest_audio.name}"
            else:
                audio_rel = f"render_jobs/{job_id}/{audio_tmp.name}"

        v_style = str(orbit_meta.get("video_style") or "")
        theme_variant = "obsidian_gold" if "orbit" in v_style or "dark" in v_style else "editorial_light"
        props = {
            "shopBrand": str(orbit_meta.get("shop_brand") or "XAN SHOP"),
            "lookTitle": str(orbit_meta.get("look_title") or "XAN SHOP Kapsula"),
            "subtitleHook": str(orbit_meta.get("subtitle_hook") or "Toshkentga 5–10 kunda yetib keladi"),
            "totalPriceUzs": int(orbit_meta.get("total_price_uzs") or 600000),
            "prepay50Uzs": int(orbit_meta.get("prepay_50_uzs") or 300000),
            "themeVariant": theme_variant,
            "audioFile": audio_rel,
            "items": items_payload,
        }
        props_file = job_public_dir / "props.json"
        props_file.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")

        proc = subprocess.run(
            [node_bin, str(script_path.resolve()), str(props_file.resolve()), str(mp4_out.resolve())],
            cwd=str(studio_dir.resolve()),
            capture_output=True,
            text=True,
            timeout=140,
        )
        if proc.returncode == 0 and mp4_out.exists() and mp4_out.stat().st_size > 5000:
            return str(mp4_out)
    except Exception:
        pass
    finally:
        shutil.rmtree(job_public_dir, ignore_errors=True)
    return None


def render_reels_mp4_with_audio(
    frames: Sequence[Image.Image],
    mp4_path: str | Path,
    audio_vibe: str = "phonk_bass",
    fps: int = 20,
    voiceover_path: str | Path | None = None,
    orbit_meta: dict[str, Any] | None = None,
    collage: Image.Image | None = None,
) -> str | None:
    """True 1080p Full HD (`1080x1920`, High-Bitrate `8 Mbps`, `-crf 17`) MP4 Reels renderi (Remotion + FFmpeg)."""
    if orbit_meta is None:
        for fr in frames:
            if hasattr(fr, "info") and isinstance(fr.info, dict) and fr.info.get("xan_orbit_meta"):
                orbit_meta = fr.info["xan_orbit_meta"]
                break

    use_remotion = (os.getenv("USE_REMOTION", "1") == "1") and (
        bool(os.getenv("FORCE_REMOTION")) or not os.getenv("PYTEST_CURRENT_TEST")
    )
    if use_remotion and orbit_meta and not voiceover_path:
        remotion_out = render_reels_with_remotion(mp4_path, orbit_meta, audio_vibe=audio_vibe)
        if remotion_out:
            return remotion_out

    ffmpeg_bin = find_ffmpeg_binary()
    if not ffmpeg_bin:
        return None

    mp4_out = Path(mp4_path)
    mp4_out.parent.mkdir(parents=True, exist_ok=True)

    if orbit_meta is None:
        for fr in frames:
            if hasattr(fr, "info") and isinstance(fr.info, dict) and fr.info.get("xan_orbit_meta"):
                orbit_meta = fr.info["xan_orbit_meta"]
                break

    with tempfile.TemporaryDirectory() as tmpdir:
        frame_idx = 0
        w, h = 1080, 1920
        transition_timestamps: list[float] = []

        if orbit_meta and orbit_meta.get("product_cards"):
            cards = orbit_meta["product_cards"]
            names = orbit_meta["item_names"]
            prices = orbit_meta["item_prices_uzs"]
            video_style = orbit_meta.get("video_style", "orbit_3d_turntable")
            n_items = max(len(cards), 1)
            frames_per_item = int(fps * 1.45)

            for i in range(n_items):
                transition_timestamps.append((i * frames_per_item) / float(fps))
                for step in range(frames_per_item):
                    sub_u = step / max(frames_per_item - 1, 1)
                    fr_img = _render_1080p_styled_frame(
                        product_cards=cards,
                        item_names=names,
                        item_prices_uzs=prices,
                        progress=(i + sub_u) / float(n_items),
                        active_idx=i,
                        sub_u=sub_u,
                        look_title=orbit_meta["look_title"],
                        total_price_uzs=orbit_meta["total_price_uzs"],
                        prepay_50_uzs=orbit_meta["prepay_50_uzs"],
                        shop_brand=orbit_meta["shop_brand"],
                        persona_hook=orbit_meta["subtitle_hook"],
                        sub_hook=orbit_meta.get("sub_hook", ""),
                        video_style=video_style,
                        frame_size=(w, h),
                    )
                    fr_img.save(os.path.join(tmpdir, f"f_{frame_idx:04d}.jpg"), format="JPEG", quality=96)
                    frame_idx += 1

            # Yakuniy 1.3 soniya: 1080p Full HD Lookbook Kolaj
            if collage is not None:
                transition_timestamps.append(frame_idx / float(fps))
                end_steps = int(fps * 1.3)
                base_col = Image.new("RGB", (w, h), OBSIDIAN)
                fit_c = ImageOps.contain(collage.convert("RGB"), (w - 32, h - 80), Image.Resampling.LANCZOS)
                base_col.paste(fit_c, ((w - fit_c.width) // 2, (h - fit_c.height) // 2))
                for step in range(end_steps):
                    u = step / max(end_steps - 1, 1)
                    scale = 1.0 + 0.025 * u
                    zw, zh = int(w * scale), int(h * scale)
                    zoomed = base_col.resize((zw, zh), Image.Resampling.BILINEAR)
                    px, py = (zw - w) // 2, (zh - h) // 2
                    cropped = zoomed.crop((px, py, px + w, py + h))
                    cropped.save(os.path.join(tmpdir, f"f_{frame_idx:04d}.jpg"), format="JPEG", quality=96)
                    frame_idx += 1
        else:
            for slide_idx, slide in enumerate(frames):
                base = slide.resize((w, h), Image.Resampling.LANCZOS).convert("RGB")
                steps = int(fps * 1.2)
                if slide_idx > 0:
                    transition_timestamps.append(frame_idx / float(fps))
                for step in range(steps):
                    u = step / max(steps - 1, 1)
                    scale = 1.0 + 0.035 * (1.0 - (1.0 - u) ** 2)
                    zw, zh = int(w * scale), int(h * scale)
                    zoomed = base.resize((zw, zh), Image.Resampling.BILINEAR)
                    px, py = (zw - w) // 2, (zh - h) // 2
                    cropped = zoomed.crop((px, py, px + w, py + h))
                    cropped.save(os.path.join(tmpdir, f"f_{frame_idx:04d}.jpg"), format="JPEG", quality=96)
                    frame_idx += 1

        total_sec = max(2.0, frame_idx / float(fps))
        wav_path = os.path.join(tmpdir, "beat.wav")
        audio_input_path = synthesize_reels_beat_wav(
            wav_path,
            duration_sec=total_sec,
            vibe=audio_vibe,
            transition_times=transition_timestamps,
        ) or wav_path

        has_voice = voiceover_path and os.path.isfile(str(voiceover_path))

        for vcodec in ("libx264", "h264_mf", "mpeg4"):
            quality_flags = (
                ["-crf", "17", "-preset", "fast", "-b:v", "8M", "-maxrate", "10M", "-bufsize", "16M", "-movflags", "+faststart"]
                if vcodec == "libx264"
                else ["-b:v", "8M"]
            )
            if has_voice:
                cmd = [
                    ffmpeg_bin,
                    "-y",
                    "-framerate", str(fps),
                    "-i", os.path.join(tmpdir, "f_%04d.jpg"),
                    "-i", audio_input_path,
                    "-i", str(voiceover_path),
                    "-filter_complex", "[1:a]volume=0.25[bg];[2:a]volume=1.20[vox];[bg][vox]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                    "-map", "0:v",
                    "-map", "[aout]",
                    "-c:v", vcodec,
                    *quality_flags,
                    "-pix_fmt", "yuv420p",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-shortest",
                    str(mp4_out),
                ]
            else:
                cmd = [
                    ffmpeg_bin,
                    "-y",
                    "-framerate", str(fps),
                    "-i", os.path.join(tmpdir, "f_%04d.jpg"),
                    "-i", audio_input_path,
                    "-c:v", vcodec,
                    *quality_flags,
                    "-pix_fmt", "yuv420p",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-shortest",
                    str(mp4_out),
                ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res.returncode == 0 and mp4_out.exists() and mp4_out.stat().st_size > 1000:
                return str(mp4_out)

    return None
