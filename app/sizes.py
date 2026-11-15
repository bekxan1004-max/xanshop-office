"""Bo'y va vazn bo'yicha o'lcham tavsiyasi (Xitoy/Osiyo o'lchamlari, taxminiy).

Taobao sotuvchilari odatda vazn bo'yicha jadval beradi. Bu jadval o'rtacha qiymat,
aniq sotuvchi jadvali bilan farq qilishi mumkin.
"""

ORDER = ["XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL", "6XL"]
# (vazn chegarasi kg, o'lcham)
WEIGHT_TABLE = [(50, "S"), (57, "M"), (65, "L"), (72, "XL"), (80, "2XL"),
                (87, "3XL"), (95, "4XL"), (105, "5XL"), (999, "6XL")]
ALIASES = {"XXL": "2XL", "XXXL": "3XL", "XXXXL": "4XL", "XXXXXL": "5XL"}


def normalize(size: str) -> str:
    s = size.strip().upper().replace(" ", "")
    return ALIASES.get(s, s)


def recommend(height_cm: float, weight_kg: float, available: list[str]) -> str | None:
    idx = next(ORDER.index(s) for limit, s in WEIGHT_TABLE if weight_kg <= limit)
    if height_cm >= 185:
        idx += 1
    if height_cm >= 195:
        idx += 1
    idx = min(idx, len(ORDER) - 1)
    wanted = ORDER[idx]
    if not available:
        return wanted

    letter = {normalize(a): a for a in available if normalize(a) in ORDER}
    if not letter:
        return None  # raqamli o'lchamlar (44, 46, 30...) — operator/jadval kerak
    if wanted in letter:
        return letter[wanted]
    bigger = [s for s in ORDER[idx:] if s in letter]
    if bigger:
        return letter[bigger[0]]
    return letter[max(letter, key=ORDER.index)]
