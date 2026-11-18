"""XAN SHOP — AI Cutout Agent (Instagram-darajadagi buyum ajratish).

Vazifasi: har qanday rasmdan (studiya foni, ko'cha fotosi, odam kiyib turgan holat,
Pinduoduo kartochkasi, bir juft krossovka va h.k.) ASOSIY buyumni piksel-aniq
ajratib, shaffof PNG (RGBA) qaytarish.

Pipeline:
  1. Kesh (data/cutout_cache/<sha1>_<cat>.png) — bir rasm faqat bir marta qayta ishlanadi.
  2. Kiyim + odam bo'lsa (`u2net_cloth_seg`) — faqat kerakli kiyim qismi (ust / past / to'liq) olinadi,
     yuz, qo'l, teri, fon tashlab yuboriladi.
  3. Mahsulot fotosi uchun salient-object AI modeli (`birefnet-general` -> `isnet-general-use` -> `u2net`).
  4. Post-processing: mayda orolchalarni tozalash, juft buyumlarni (poyabzal) saqlash,
     yumshoq qirra (feather), oq/kulrang "halo"ni yo'qotish, bbox bo'yicha qirqish.
  5. Sifat nazorati: maska juda kichik/katta yoki bo'lak-bo'lak bo'lsa -> keyingi model.
AI kutubxonasi yo'q bo'lsa `None` qaytaradi va media.py eski algoritmga o'tadi.
"""
from __future__ import annotations

import hashlib
import io
import logging
import os
import threading
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

log = logging.getLogger(__name__)

CACHE_DIR = Path("data/cutout_cache")
GENERAL_MODELS = ("u2netp", "silueta")
_SESSIONS: dict[str, object] = {}
_LOCK = threading.Lock()
_DISABLED_MODELS: set[str] = set()

# kategoriya -> u2net_cloth_seg kanali (0=ust kiyim, 1=past kiyim, 2=to'liq kiyim)
_CLOTH_CHANNEL = {"top": 0, "outerwear": 0, "bottom": 1, "dress": 2, "full": 2}


def ai_available() -> bool:
    if os.getenv("XAN_DISABLE_AI_CUTOUT") == "1":
        return False
    if os.getenv("PYTEST_CURRENT_TEST") and os.getenv("XAN_AI_CUTOUT_IN_TESTS") != "1":
        return False
    try:
        import rembg  # noqa: F401
        return True
    except Exception:
        return False


def _session(name: str):
    with _LOCK:
        if name in _SESSIONS:
            return _SESSIONS[name]
        from rembg import new_session

        sess = new_session(name)
        _SESSIONS[name] = sess
        return sess


def _mask_for(img: Image.Image, model: str) -> np.ndarray | None:
    if model in _DISABLED_MODELS:
        return None
    try:
        from rembg import remove

        out = remove(img.convert("RGB"), session=_session(model), only_mask=True, post_process_mask=True)
        return np.asarray(out.convert("L"), dtype=np.float32) / 255.0
    except Exception as exc:
        log.warning("Cutout modeli %s ishlamadi: %s", model, exc)
        _DISABLED_MODELS.add(model)
        return None


def _cloth_mask(img: Image.Image, category: str) -> np.ndarray | None:
    """Odam kiyib turgan fotodan faqat kerakli kiyimni ajratadi (faqat model fayli mavjud bo'lsa)."""
    ch = _CLOTH_CHANNEL.get(category)
    cloth_model_path = Path.home() / ".rembg" / "models" / "u2net_cloth_seg" / "u2net_cloth_seg.onnx"
    if ch is None or not cloth_model_path.is_file() or "u2net_cloth_seg" in _DISABLED_MODELS:
        return None
    try:
        from rembg import remove

        out = remove(img.convert("RGB"), session=_session("u2net_cloth_seg"), only_mask=True)
        m = np.asarray(out.convert("L"), dtype=np.float32) / 255.0
        h = img.height
        # rembg cloth_seg 3 ta maskani vertikal ketma-ket qaytaradi (H*3)
        if m.shape[0] >= h * 3:
            m = m[ch * h:(ch + 1) * h]
        return m
    except Exception as exc:
        log.warning("Cloth-seg ishlamadi: %s", exc)
        _DISABLED_MODELS.add("u2net_cloth_seg")
        return None


def _components(binary: np.ndarray) -> tuple[np.ndarray, list[int]]:
    """4-bog'lanishli komponentlar (scipy bo'lsa tez, bo'lmasa sekin BFS kichraytirilgan rasmda)."""
    try:
        from scipy import ndimage

        lab, n = ndimage.label(binary)
        sizes = ndimage.sum(binary, lab, range(1, n + 1)).astype(int).tolist() if n else []
        return lab, sizes
    except Exception:
        from collections import deque

        h, w = binary.shape
        lab = np.zeros((h, w), dtype=np.int32)
        sizes: list[int] = []
        cid = 0
        for y in range(h):
            for x in range(w):
                if binary[y, x] and lab[y, x] == 0:
                    cid += 1
                    cnt = 0
                    q = deque([(y, x)])
                    lab[y, x] = cid
                    while q:
                        cy, cx = q.popleft()
                        cnt += 1
                        for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                            if 0 <= ny < h and 0 <= nx < w and binary[ny, nx] and lab[ny, nx] == 0:
                                lab[ny, nx] = cid
                                q.append((ny, nx))
                    sizes.append(cnt)
        return lab, sizes


def _clean_mask(mask: np.ndarray, keep_pairs: bool) -> np.ndarray:
    """Mayda dog'larni olib tashlaydi; juft buyum (2 ta poyabzal) bo'lsa ikkalasini saqlaydi."""
    binary = mask > 0.5
    lab, sizes = _components(binary)
    if not sizes:
        return mask
    biggest = max(sizes)
    ratio = 0.18 if keep_pairs else 0.30
    keep = [i + 1 for i, s in enumerate(sizes) if s >= biggest * ratio]
    keep_mask = np.isin(lab, keep)
    # Ichki teshiklarni (maskaning ichidagi yopiq bo'shliqlarni) to'ldirish — mato ichida tirqish qolmasin
    try:
        from scipy import ndimage

        keep_mask = ndimage.binary_fill_holes(keep_mask)
    except Exception:
        pass
    soft = np.where(keep_mask, np.maximum(mask, 0.0), 0.0)
    # yarim-shaffof qirralarni saqlab qolamiz, lekin tashqi shovqinni 0 ga tushiramiz
    grown = Image.fromarray((keep_mask * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(5))
    near = np.asarray(grown, dtype=np.float32) / 255.0
    return np.clip(np.maximum(soft, mask * near), 0.0, 1.0)


def _quality_ok(mask: np.ndarray) -> bool:
    cov = float((mask > 0.5).mean())
    if cov < 0.03 or cov > 0.97:
        return False
    binary = mask > 0.5
    _, sizes = _components(binary[::4, ::4])
    if not sizes:
        return False
    sorted_sizes = sorted(sizes, reverse=True)
    # 1 ta kiyim yoki juft buyum (2 ta poyabzal) umumiy maydonning kamida 65% ini egallashi kerak
    top2 = sum(sorted_sizes[:2])
    return top2 >= 0.65 * sum(sizes)


def _decontaminate(rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """Qirradagi oq/kulrang fon rangini (halo) olib tashlash: qirra piksellarini ichki rangga yaqinlashtirish."""
    edge = (alpha > 0.02) & (alpha < 0.9)
    if not edge.any():
        return rgb
    a_img = Image.fromarray((alpha * 255).astype(np.uint8))
    inner = np.asarray(a_img.filter(ImageFilter.MinFilter(7)), dtype=np.float32) / 255.0 > 0.9
    if not inner.any():
        return rgb
    blur_rgb = np.asarray(
        Image.fromarray((rgb * inner[..., None]).astype(np.uint8)).filter(ImageFilter.BoxBlur(6)), dtype=np.float32
    )
    weight = np.asarray(Image.fromarray((inner * 255).astype(np.uint8)).filter(ImageFilter.BoxBlur(6)), dtype=np.float32) / 255.0
    inner_col = blur_rgb / np.maximum(weight[..., None], 1e-3)
    mix = (1.0 - alpha)[..., None] * edge[..., None]
    out = rgb * (1.0 - mix) + inner_col * mix
    return np.clip(out, 0, 255)


def _hash(img: Image.Image, category: str) -> str:
    buf = io.BytesIO()
    small = img.convert("RGB")
    small.thumbnail((256, 256))
    small.save(buf, format="PNG")
    return hashlib.sha1(buf.getvalue() + category.encode()).hexdigest()[:20]


def guess_category(name: str) -> str:
    low = (name or "").lower()
    if any(k in low for k in ("krossovka", "sneaker", "poyabzal", "etik", "botinka", "lofer", "tufli", "chelsea", "shoes", "loafer")):
        return "shoes"
    if any(k in low for k in ("shim", "kargo", "jinsi", "bryuk", "trouser", "pants", "jeans", "bottom", "joger")):
        return "bottom"
    if any(k in low for k in ("palto", "kurtka", "bomber", "blazer", "pidjak", "coat", "jacket", "outerwear")):
        return "outerwear"
    if any(k in low for k in ("kepka", "shapka", "sumka", "soat", "cap", "hat", "bag")):
        return "accessory"
    if any(k in low for k in ("sviter", "xudi", "vodolazka", "futbolka", "ko'ylak", "polo", "top", "hoodie", "shirt", "tee")):
        return "top"
    return ""


def extract_main_item(img: Image.Image, category: str = "", use_cache: bool = True) -> Image.Image | None:
    """Rasmdan asosiy buyumni AI bilan ajratib, qirqilgan RGBA qaytaradi (yoki None)."""
    if not ai_available():
        return None
    src = img.convert("RGBA")
    # Allaqachon shaffof PNG bo'lsa (alpha bor) — qayta ishlash shart emas
    a = np.asarray(src.split()[3])
    if (a < 250).mean() > 0.05:
        bbox = src.getbbox()
        return src.crop(bbox) if bbox else src

    key = _hash(src, category)
    cache_path = CACHE_DIR / f"{key}.png"
    if use_cache and cache_path.is_file():
        try:
            return Image.open(cache_path).convert("RGBA")
        except Exception:
            pass

    work = src.convert("RGB")
    max_side = 1600
    if max(work.size) > max_side:
        work.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)

    mask: np.ndarray | None = None
    general: np.ndarray | None = None
    for model in GENERAL_MODELS:
        m = _mask_for(work, model)
        if m is not None and _quality_ok(m):
            general = m
            break
        if m is not None and general is None:
            general = m

    # Odam kiyib turgan foto: umumiy maska kiyimdan ancha katta bo'lsa (bosh/qo'l/oyoq), kiyim kanalini olamiz
    cloth = _cloth_mask(work, category) if category in _CLOTH_CHANNEL else None
    if cloth is not None and general is not None:
        cov_g = float((general > 0.5).mean())
        cov_c = float((cloth > 0.5).mean())
        if cov_c > 0.04 and cov_c < cov_g * 0.82:
            mask = cloth * (general > 0.3)
    if mask is None:
        mask = general
    if mask is None:
        return None

    mask = _clean_mask(mask, keep_pairs=(category in ("shoes", "accessory") or category == ""))
    if float((mask > 0.5).mean()) < 0.02:
        return None

    # To'q yoki rangli kiyimlarda qo'ltiq ostidagi studiya devori qoldig'ini xavfsiz tozalash
    # (Och/bej/oq kiyimlarga va poyabzalga aslo tegmaymiz — kiyim qirqilmasligi uchun)
    rgb = np.asarray(work, dtype=np.float32)
    if category != "shoes":
        fg_pix = rgb[mask > 0.5]
        if len(fg_pix):
            lum = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]
            fg_lum = 0.299 * fg_pix[:, 0] + 0.587 * fg_pix[:, 1] + 0.114 * fg_pix[:, 2]
            if float(np.median(fg_lum)) < 100.0:
                bg_corner = np.median(rgb[:15, :15], axis=(0, 1))
                dist_bg = np.linalg.norm(rgb - bg_corner, axis=2)
                chroma = np.max(rgb, axis=2) - np.min(rgb, axis=2)
                is_wall = (dist_bg < 35.0) & (lum > 140.0) & (chroma < 20.0)
                mask = np.where(is_wall, 0.0, mask)

    alpha_img = Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6))
    alpha = np.asarray(alpha_img, dtype=np.float32) / 255.0
    rgb = _decontaminate(rgb, alpha)
    out = Image.fromarray(rgb.astype(np.uint8), "RGB").convert("RGBA")
    out.putalpha(alpha_img)
    bbox = alpha_img.point(lambda p: 255 if p > 12 else 0).getbbox()
    if bbox:
        pad = 6
        bbox = (max(0, bbox[0] - pad), max(0, bbox[1] - pad), min(out.width, bbox[2] + pad), min(out.height, bbox[3] + pad))
        out = out.crop(bbox)

    if use_cache:
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            out.save(cache_path, format="PNG")
        except Exception:
            pass
    return out


def warmup() -> bool:
    """Modelni oldindan yuklab oladi (birinchi Reels kechikmasligi uchun)."""
    if not ai_available():
        return False
    try:
        _session(GENERAL_MODELS[0])
        return True
    except Exception:
        return False
