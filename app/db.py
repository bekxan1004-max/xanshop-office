"""SQLite ma'lumotlar bazasi (looklar, buyurtmalar, AI suhbatlar, sozlamalar, AI Agent Office)."""
import json
import os
import time
from typing import Any

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS looks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    items_json TEXT NOT NULL,
    sizes TEXT DEFAULT '',
    colors TEXT DEFAULT '',
    photo_path TEXT,
    video_path TEXT,
    sales_file_id TEXT,
    palette_name TEXT DEFAULT '',
    palette_hex TEXT DEFAULT '',
    audio_vibe TEXT DEFAULT '',
    ig_media_id TEXT DEFAULT '',
    channel_msg_id INTEGER,
    prepay_uzs INTEGER NOT NULL,
    prepay_50_uzs INTEGER DEFAULT 0,
    remaining_50_uzs INTEGER DEFAULT 0,
    profit_uzs INTEGER NOT NULL,
    goods_cost_uzs INTEGER NOT NULL,
    weight_kg REAL NOT NULL,
    cargo_est_uzs INTEGER NOT NULL,
    active INTEGER DEFAULT 1,
    created_at INTEGER
);
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    username TEXT,
    full_name TEXT,
    phone TEXT,
    address TEXT,
    look_id INTEGER NOT NULL,
    size TEXT,
    color TEXT,
    payment_plan TEXT DEFAULT '50',
    prepay_due INTEGER DEFAULT 0,
    remaining_uzs INTEGER DEFAULT 0,
    profit_uzs INTEGER DEFAULT 0,
    goods_cost_uzs INTEGER DEFAULT 0,
    weight_kg REAL,
    cargo_due INTEGER DEFAULT 0,
    cargo_cost_uzs INTEGER DEFAULT 0,
    status TEXT NOT NULL,
    tracking TEXT,
    source TEXT DEFAULT 'bot',
    created_at INTEGER,
    updated_at INTEGER
);
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    last_interaction_id TEXT,
    updated_at INTEGER
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS agent_states (
    agent_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    boss_id TEXT DEFAULT '',
    status TEXT DEFAULT 'idle',
    current_task TEXT DEFAULT 'Buyruq kutilmoqda',
    tasks_done INTEGER DEFAULT 0,
    version TEXT DEFAULT 'v3.0',
    experience_years INTEGER DEFAULT 10,
    xp INTEGER DEFAULT 1000,
    level INTEGER DEFAULT 10,
    mastery_title TEXT DEFAULT '10-Yillik Pro Ekspert (v3.0)',
    learnings_json TEXT DEFAULT '[]',
    updated_at INTEGER
);
CREATE TABLE IF NOT EXISTS agent_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    target_id TEXT DEFAULT '',
    action TEXT NOT NULL,
    details TEXT DEFAULT '',
    created_at INTEGER
);
CREATE TABLE IF NOT EXISTS bank_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    amount_uzs INTEGER NOT NULL,
    card_last4 TEXT DEFAULT '',
    raw_text TEXT DEFAULT '',
    matched_order_id INTEGER,
    created_at INTEGER
);
CREATE TABLE IF NOT EXISTS receipt_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    tx_ref TEXT DEFAULT '',
    image_sha256 TEXT NOT NULL,
    parsed_amount INTEGER DEFAULT 0,
    parsed_last4 TEXT DEFAULT '',
    verdict TEXT NOT NULL,
    reason TEXT DEFAULT '',
    created_at INTEGER
);
CREATE TABLE IF NOT EXISTS competitor_accounts (
    handle TEXT PRIMARY KEY,
    platform TEXT DEFAULT 'instagram',
    region TEXT DEFAULT 'uzbekistan',
    style_focus TEXT DEFAULT '',
    followers_est INTEGER DEFAULT 0,
    avg_likes REAL DEFAULT 0,
    avg_views INTEGER DEFAULT 0,
    discovered_via TEXT DEFAULT 'seed',
    last_scanned_at INTEGER DEFAULT 0,
    notes_json TEXT DEFAULT '{}',
    active INTEGER DEFAULT 1,
    created_at INTEGER
);
CREATE TABLE IF NOT EXISTS competitor_videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_key TEXT UNIQUE NOT NULL,
    account_handle TEXT NOT NULL,
    video_url TEXT DEFAULT '',
    posted_at_info TEXT DEFAULT '',
    garment_type TEXT DEFAULT '',
    video_meaning TEXT DEFAULT '',
    editing_style TEXT DEFAULT '',
    video_quality TEXT DEFAULT '',
    music_genre TEXT DEFAULT '',
    audio_vibe TEXT DEFAULT 'diplomat_old_money',
    views_est INTEGER DEFAULT 0,
    likes_count INTEGER DEFAULT 0,
    comments_count INTEGER DEFAULT 0,
    competitor_sell_price_uzs INTEGER DEFAULT 0,
    estimated_pdd_cost_uzs INTEGER DEFAULT 0,
    estimated_profit_uzs INTEGER DEFAULT 0,
    xan_target_price_uzs INTEGER DEFAULT 0,
    insight_summary TEXT DEFAULT '',
    raw_json TEXT DEFAULT '{}',
    analyzed_at INTEGER
);
CREATE TABLE IF NOT EXISTS tracked_sources (
    source_key TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    url TEXT DEFAULT '',
    added_by TEXT DEFAULT 'owner',
    status TEXT DEFAULT 'active',
    style_summary TEXT DEFAULT '',
    posting_pattern TEXT DEFAULT '',
    pricing_pattern TEXT DEFAULT '',
    extracted_playbook_json TEXT DEFAULT '{}',
    last_analyzed_at INTEGER DEFAULT 0,
    created_at INTEGER
);
CREATE TABLE IF NOT EXISTS learned_playbooks (
    playbook_key TEXT PRIMARY KEY,
    rules_json TEXT NOT NULL,
    source_refs_json TEXT DEFAULT '[]',
    updated_at INTEGER
);
"""

ACTIVE_STATUSES = (
    "awaiting_payment", "payment_review", "paid", "bought", "china_warehouse",
    "in_transit", "arrived", "cargo_awaiting", "cargo_review", "cargo_paid",
)

DEFAULT_AGENTS = [
    ("director", "Boshqaruvchi AI (v3.0)", "10-Yillik E-Commerce CEO: Bozor, 0-Xarajat 50/50 Modeli & Buyruq Markazi", ""),
    ("insta_analyst", "Instagram Razvedka & Trend Analitik (v3.0)", "Butun Instagram Moda Tahlilchisi: Trend Kiyim/Aksessuarlarni Bo'laklab Tahlil Qiladi + Studiya Turish & Video Yo'nalishini Yaxshilaydi", "director"),
    ("skaut", "Pinduoduo Tahlilchi & Skaut Agent (v3.0)", "10-Yillik Pinduoduo Xaridori: Trenddagi Har Qanday Mahsulotni Sifatli/Arzon Topadi, Bazaga Saqlaydi va Photoshop Studiyaga Prompt Yozadi", "director"),
    ("photo_studio", "Photoshop Studio AI (Nano Banana)", "10-Yillik AI Fotostudiya: Pinduoduo Rasmini O'zgartirmasdan Faqat Mahsulotning O'zini Tabiiy Studiya Ko'rinishida Chiqaradi", "smm_manager"),
    ("smm_manager", "SMM Boshlig'i Agent (v3.0)", "10-Yillik Kontent & Voronka Direktori: Instagram Reels + '+' Komment Triggeri & Telegram Kanal (5–12 kun, 12k/100gr)", "director"),
    ("video_employee", "AI Kreativ Rejissyor & Video Montajchi (v3.0)", "10-Yillik Luxury Reels Montajchi: Photoshop Studiya Rasmlari + Trend Musiqa (TTS siz) bilan 1080p Reels", "smm_manager"),
    ("sales_stylist", "Sotuvchi & Stilist AI (v3.0)", "10-Yillik Stilist-Konsultant (@Bekshop_style + Bot): Do'kon Jadvali Bo'yicha Alohida Razmer & Color-Grading Maslahati", "director"),
    ("accountant", "AI Hisobchi Agent (v3.0)", "10-Yillik Moliyaviy Auditor: HUMO *4135 (POLVONOV BEKMUROD) Chek OCR Anti-Fake & Avto-Tasdiq", "director"),
    ("cargo_logistics", "Vykup & Kargo Agent (v3.0)", "10-Yillik Xitoy-Toshkent Logisti: MK Express / DTD Avia (5–12 kun, 12 000 so'm / 100 gr)", "director"),
]

INITIAL_AGENT_LEARNINGS: dict[str, list[str]] = {
    "director": [
        "Har bir Look narxi 65% marja ustiga hisoblanib, 50 000 yoki 100 000 so'm chegarasiga yuqoriga yaxlitlanishi shart (masalan 527k -> 550k).",
        "Mijoz buyurtmani 5–10 kunda qo'liga olganda 100% rozi bo'lishi — brendning uzoq muddatli foydasi garovidir.",
        "Oylik jismoniy shaxs bojxona limiti ($200) to'lishiga yaqinlashganda YaTT + 1688 ulgurji rejimiga o'tiladi.",
    ],
    "insta_analyst": [
        "Global va O'zbekiston Instagram tahlili (@_tima_shop, @stylesh.uz, @shams.labs): Reels'da sun'iy TTS ovoz emas, balki kuchli ritmik beat + saund-dizayn (whoosh/shutter) ishlaydi.",
        "Birinchi 1.2 soniyada Split-Screen / Bento preview va bo'y segmenti ('170–185 SM BO'YLI YIGITLAR UCHUN') ko'rinishi saqlash (Save) ulushini 3x oshiradi.",
        "Opisaniyada 'Izohda + yoki LOOK qoldiring — razmer va narxni Directga yuboramiz' triggeri kommentlar sonini keskin ko'paytirib videoni Explore/Rekka chiqaradi.",
        "Video Montajchiga shunchaki zoom emas, balki mato zichligi (420g), haqiqiy o'lcham jadvali va 50% xavfsiz to'lov kadrlarini buyurish shart.",
    ],
    "skaut": [
        "Xitoy ichki yetkazish (1–4 kun) + Avia kargo (3–7 kun) = 5–10 kunlik logistika oynasi uchun bugungi emas, 5–10 kun keyingi Toshkent ob-havo prognoziga mos kiyim tanlanadi.",
        "Mijoz aldangan his qilmasligi uchun faqat mato zichligi aniq (280g–420g paxta/drape) va Xitoy ombor QC tekshiruvidan o'tadigan buyumlar kapsulaga kiritiladi.",
    ],
    "smm_manager": [
        "Bio va barcha postlarda yetkazish muddati halol '5–10 kun (Avia)' va '@Bekshop_style' ko'rsatiladi.",
        "Har bir postda mijozning eng katta qo'rquvi — 'rasmdagidek chiqarmikan?' savoliga '50% hozir, qolgan 50% kiyim Toshkentga kelib sifatini ko'rganingizda' kafolati bilan javob beriladi.",
    ],
    "photo_studio": [
        "QAT'IY QOIDA: Mahsulotni qayta studiya ko'rinishida chiqarishda uning matosi, rangi, tugma/zamogi va logotipi 100% O'ZGARMASDAN qolishi shart!",
        "Pinduoduo Tahlilchidan mahsulot promptini, Instagram Tahlilchidan esa tabiiy turish (pose/drape/lighting) ko'rsatmasini olib birlashtiradi.",
        "Odam yuzi, qo'llari, shim tagidagi poyabzal, fon va xitoycha yozuvlar to'liq olib tashlanib, faqat toza mahsulotning o'zi qoldiriladi.",
    ],
    "video_employee": [
        "QAT'IY QOIDA: Reels videoda robot/TTS ovoz (voiceover) ishlatilmaydi! Faqat toza studiya beat + kadr almashinuvida whoosh/shutter/sub-bass saund-dizayn.",
        "Shunchaki oddiy cut va zoom-in taqiqlanadi: 1-kadrdan Bento/Split-Screen preview, qora kapsuladagi kinetik tipografiya va halol mato/razmer (M–2XL) pasporti ko'rsatiladi.",
        "Mahsulotni premium darajada ko'rsatish bilan birga uning haqiqiy matosi, vazni va bichimini halol aks ettirish shart — mijoz kiyimni olganda 100% mamnun bo'lsin.",
    ],
    "sales_stylist": [
        "Xitoy/Osiyo lekalasi Yevropa razmeridan 1 o'lcham kichik yuradi: mijozdan doim bo'yi va vaznini so'rab, 100% aniq razmer tavsiya qilinadi.",
        "To'lov uchun faqat rasmiy HUMO karta 9860 3501 4182 4135 (POLVONOV BEKMUROD) beriladi va chek AI Hisobchi tekshiruvidan o'tgach tasdiqlanadi.",
    ],
    "accountant": [
        "Barcha kirimlar HUMO 9860 3501 4182 4135 (*4135, POLVONOV BEKMUROD) kartasi va noyob summa orqali tekshiriladi.",
        "Og'zaki 'pul tashladim' xabariga hech qachon tasdiq berilmaydi — faqat haqiqiy chek skrinshoti (SHA-256 Anti-Duplicate) yoki bank bot tushumi asosida tasdiqlanadi.",
    ],
    "cargo_logistics": [
        "Asosiy tasdiqlangan Avia Kargo liniyalari: MK Express (114 000 so'm/kg, 30+ filiallar) va DTD / Door-to-Door ($9.49/kg, DUR keshbek, ID BP-1).",
        "5–12 kunlik Avia muddat va mijozga 12 000 so'm / 100 gr kargo tarifi doimiy nazoratda.",
    ],
}


class Database:
    def __init__(self, path: str):
        self.path = path
        self.conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.executescript(SCHEMA)
        await self._migrate_columns()
        await self._init_agents()
        await self.conn.commit()

    async def _migrate_columns(self) -> None:
        """Eski DB fayllariga yangi ustunlarni xavfsiz qo'shadi."""
        migrations = [
            ("looks", "video_path", "TEXT"),
            ("looks", "prepay_50_uzs", "INTEGER DEFAULT 0"),
            ("looks", "remaining_50_uzs", "INTEGER DEFAULT 0"),
            ("looks", "palette_name", "TEXT DEFAULT ''"),
            ("looks", "palette_hex", "TEXT DEFAULT ''"),
            ("looks", "audio_vibe", "TEXT DEFAULT ''"),
            ("looks", "ig_media_id", "TEXT DEFAULT ''"),
            ("looks", "channel_msg_id", "INTEGER"),
            ("orders", "payment_plan", "TEXT DEFAULT '50'"),
            ("orders", "remaining_uzs", "INTEGER DEFAULT 0"),
            ("orders", "source", "TEXT DEFAULT 'bot'"),
            ("agent_states", "version", "TEXT DEFAULT 'v3.0'"),
            ("agent_states", "experience_years", "INTEGER DEFAULT 10"),
            ("agent_states", "xp", "INTEGER DEFAULT 1000"),
            ("agent_states", "level", "INTEGER DEFAULT 10"),
            ("agent_states", "mastery_title", "TEXT DEFAULT '10-Yillik Pro Ekspert (v3.0)'"),
            ("agent_states", "learnings_json", "TEXT DEFAULT '[]'"),
        ]
        for table, col, col_type in migrations:
            try:
                await self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
            except Exception:
                pass

    async def _init_agents(self) -> None:
        now = int(time.time())
        for aid, name, role, boss in DEFAULT_AGENTS:
            seed_learnings = json.dumps(INITIAL_AGENT_LEARNINGS.get(aid, []), ensure_ascii=False)
            await self.conn.execute(
                "INSERT INTO agent_states(agent_id, name, role, boss_id, status, current_task, tasks_done, "
                "version, experience_years, xp, level, mastery_title, learnings_json, updated_at) "
                "VALUES(?, ?, ?, ?, 'idle', 'Tayyor (24/7 Online • v3.0 Pro)', 0, 'v3.0', 10, 1000, 10, '10-Yillik Pro Ekspert (v3.0)', ?, ?) "
                "ON CONFLICT(agent_id) DO UPDATE SET name=excluded.name, role=excluded.role, boss_id=excluded.boss_id, "
                "version='v3.0', experience_years=MAX(COALESCE(agent_states.experience_years, 10), 10), "
                "xp=MAX(COALESCE(agent_states.xp, 1000), 1000), level=MAX(COALESCE(agent_states.level, 10), 10), "
                "mastery_title=COALESCE(NULLIF(agent_states.mastery_title, ''), '10-Yillik Pro Ekspert (v3.0)'), "
                "learnings_json=CASE WHEN agent_states.learnings_json IS NULL OR agent_states.learnings_json IN ('', '[]') "
                "THEN excluded.learnings_json ELSE agent_states.learnings_json END",
                (aid, name, role, boss, seed_learnings, now),
            )

    async def close(self) -> None:
        if self.conn:
            await self.conn.close()

    async def _one(self, sql: str, args: tuple = ()) -> dict | None:
        async with self.conn.execute(sql, args) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def _all(self, sql: str, args: tuple = ()) -> list[dict]:
        async with self.conn.execute(sql, args) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def _exec(self, sql: str, args: tuple = ()) -> int:
        cur = await self.conn.execute(sql, args)
        await self.conn.commit()
        return cur.lastrowid

    # ---------- settings ----------
    async def get_setting(self, key: str) -> str | None:
        row = await self._one("SELECT value FROM settings WHERE key=?", (key,))
        return row["value"] if row else None

    async def set_setting(self, key: str, value: Any) -> None:
        await self._exec(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))

    # ---------- looks ----------
    async def add_look(
        self,
        title: str,
        items: list[dict],
        sizes: str,
        colors: str,
        price: dict,
        palette_name: str = "",
        palette_hex: str = "",
        audio_vibe: str = "",
    ) -> int:
        prepay_full = int(price["prepay_uzs"])
        prepay_50 = int(price.get("prepay_50_uzs") or (prepay_full // 2))
        rem_50 = int(price.get("remaining_50_uzs") or (prepay_full - prepay_50))
        return await self._exec(
            "INSERT INTO looks(title, items_json, sizes, colors, palette_name, palette_hex, audio_vibe, "
            "prepay_uzs, prepay_50_uzs, remaining_50_uzs, "
            "profit_uzs, goods_cost_uzs, weight_kg, cargo_est_uzs, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (title, json.dumps(items, ensure_ascii=False), sizes, colors, palette_name, palette_hex, audio_vibe,
             prepay_full, prepay_50, rem_50, price["profit_uzs"], price["goods_cost_uzs"], price["weight_kg"],
             price["cargo_client_uzs"], int(time.time())))

    async def update_look(self, look_id: int, **fields) -> None:
        if not fields:
            return
        cols = ", ".join(f"{k}=?" for k in fields)
        await self._exec(f"UPDATE looks SET {cols} WHERE id=?", (*fields.values(), look_id))

    async def get_look(self, look_id: int) -> dict | None:
        return await self._one("SELECT * FROM looks WHERE id=?", (look_id,))

    async def delete_look(self, look_id: int) -> None:
        await self._exec("DELETE FROM looks WHERE id=?", (look_id,))

    async def clear_all_looks(self) -> int:
        cur = await self.conn.execute("DELETE FROM looks")
        await self.conn.commit()
        return cur.rowcount or 0

    async def list_looks(self, only_active: bool = True) -> list[dict]:
        sql = "SELECT * FROM looks" + (" WHERE active=1" if only_active else "") + " ORDER BY id"
        return await self._all(sql)

    # ---------- orders ----------
    async def create_order(self, **fields) -> int:
        now = int(time.time())
        fields.update(created_at=now, updated_at=now)
        cols = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        return await self._exec(f"INSERT INTO orders({cols}) VALUES({marks})", tuple(fields.values()))

    async def update_order(self, order_id: int, **fields) -> None:
        fields["updated_at"] = int(time.time())
        cols = ", ".join(f"{k}=?" for k in fields)
        await self._exec(f"UPDATE orders SET {cols} WHERE id=?", (*fields.values(), order_id))

    async def get_order(self, order_id: int) -> dict | None:
        return await self._one("SELECT * FROM orders WHERE id=?", (order_id,))

    async def user_orders(self, user_id: int, limit: int = 10) -> list[dict]:
        return await self._all(
            "SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id, limit))

    async def payable_order(self, user_id: int) -> dict | None:
        return await self._one(
            "SELECT * FROM orders WHERE user_id=? AND status IN "
            "('awaiting_payment','payment_review','cargo_awaiting','cargo_review') "
            "ORDER BY id DESC LIMIT 1", (user_id,))

    async def active_orders(self, limit: int = 30) -> list[dict]:
        marks = ",".join("?" for _ in ACTIVE_STATUSES)
        return await self._all(
            f"SELECT * FROM orders WHERE status IN ({marks}) ORDER BY id DESC LIMIT ?",
            (*ACTIVE_STATUSES, limit))

    async def all_orders(self) -> list[dict]:
        return await self._all("SELECT * FROM orders")

    # ---------- AI suhbat ----------
    async def get_interaction(self, user_id: int) -> str | None:
        row = await self._one("SELECT last_interaction_id FROM users WHERE user_id=?", (user_id,))
        return row["last_interaction_id"] if row else None

    async def set_interaction(self, user_id: int, interaction_id: str | None) -> None:
        await self._exec(
            "INSERT INTO users(user_id, last_interaction_id, updated_at) VALUES(?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET last_interaction_id=excluded.last_interaction_id, "
            "updated_at=excluded.updated_at", (user_id, interaction_id, int(time.time())))

    # ---------- AI Agent Office ----------
    async def set_agent_status(self, agent_id: str, status: str, task: str, increment_done: bool = False) -> None:
        now = int(time.time())
        if increment_done:
            await self._exec(
                "UPDATE agent_states SET status=?, current_task=?, tasks_done=tasks_done+1, "
                "xp=COALESCE(xp, 1000)+20, level=MAX(10, 10 + ((COALESCE(xp, 1000)+20 - 1000) / 100)), "
                "updated_at=? WHERE agent_id=?",
                (status, task, now, agent_id),
            )
        else:
            await self._exec(
                "UPDATE agent_states SET status=?, current_task=?, updated_at=? WHERE agent_id=?",
                (status, task, now, agent_id),
            )

    async def get_agent_learnings(self, agent_id: str) -> list[str]:
        row = await self._one("SELECT learnings_json FROM agent_states WHERE agent_id=?", (agent_id,))
        if not row or not row.get("learnings_json"):
            return list(INITIAL_AGENT_LEARNINGS.get(agent_id, []))
        try:
            parsed = json.loads(row["learnings_json"])
            if isinstance(parsed, list):
                return [str(x) for x in parsed if x]
        except Exception:
            pass
        return list(INITIAL_AGENT_LEARNINGS.get(agent_id, []))

    async def record_agent_learning(self, agent_id: str, lesson: str, xp_gain: int = 25) -> list[str]:
        """Agentning o'z-o'zini rivojlantirish xotirasiga yangi tajriba darsini qo'shadi va XP/Level oshiradi."""
        clean_lesson = (lesson or "").strip()
        current = await self.get_agent_learnings(agent_id)
        if clean_lesson and clean_lesson not in current:
            current.append(clean_lesson)
            # Eng muhim va yangi 12 ta tajriba qoidasini saqlaymiz
            if len(current) > 12:
                current = current[:3] + current[-9:]
        row = await self._one("SELECT xp, tasks_done FROM agent_states WHERE agent_id=?", (agent_id,))
        cur_xp = int((row or {}).get("xp") or 1000) + max(0, int(xp_gain))
        new_level = max(10, 10 + (cur_xp - 1000) // 100)
        years_equiv = max(10, 10 + (new_level - 10) // 2)
        mastery = f"{years_equiv}-Yillik Pro Ekspert (v3.0 • Lvl {new_level})"
        await self._exec(
            "UPDATE agent_states SET xp=?, level=?, experience_years=?, mastery_title=?, learnings_json=?, updated_at=? WHERE agent_id=?",
            (cur_xp, new_level, years_equiv, mastery, json.dumps(current, ensure_ascii=False), int(time.time()), agent_id),
        )
        return current

    async def log_agent_action(self, agent_id: str, action: str, details: str = "", target_id: str = "") -> int:
        return await self._exec(
            "INSERT INTO agent_logs(agent_id, target_id, action, details, created_at) VALUES(?,?,?,?,?)",
            (agent_id, target_id, action, details, int(time.time())),
        )

    async def list_agents(self) -> list[dict]:
        return await self._all("SELECT * FROM agent_states ORDER BY rowid")

    async def list_agent_logs(self, limit: int = 40) -> list[dict]:
        return await self._all("SELECT * FROM agent_logs ORDER BY id DESC LIMIT ?", (limit,))

    # ---------- AI Hisobchi (Bank tarixi & Chek Anti-Fake) ----------
    async def add_bank_tx(
        self,
        source: str,
        amount_uzs: int,
        card_last4: str = "",
        raw_text: str = "",
        matched_order_id: int | None = None,
    ) -> int:
        return await self._exec(
            "INSERT INTO bank_transactions(source, amount_uzs, card_last4, raw_text, matched_order_id, created_at) "
            "VALUES(?,?,?,?,?,?)",
            (source, amount_uzs, card_last4, raw_text, matched_order_id, int(time.time())),
        )

    async def match_bank_tx(self, tx_id: int, order_id: int) -> None:
        await self._exec("UPDATE bank_transactions SET matched_order_id=? WHERE id=?", (order_id, tx_id))

    async def find_unmatched_bank_tx(self, amount_uzs: int, max_age_sec: int = 10800) -> dict | None:
        cutoff = int(time.time()) - max_age_sec
        return await self._one(
            "SELECT * FROM bank_transactions WHERE amount_uzs=? AND matched_order_id IS NULL AND created_at>=? "
            "ORDER BY id DESC LIMIT 1",
            (amount_uzs, cutoff),
        )

    async def find_pending_order_by_amount(self, amount_uzs: int) -> dict | None:
        """Noyob summa bo'yicha to'lov kutayotgan buyurtmani topadi."""
        order = await self._one(
            "SELECT * FROM orders WHERE status IN ('awaiting_payment','payment_review') AND prepay_due=? "
            "ORDER BY id DESC LIMIT 1",
            (amount_uzs,),
        )
        if order:
            return order
        return await self._one(
            "SELECT * FROM orders WHERE status IN ('cargo_awaiting','cargo_review') AND cargo_due=? "
            "ORDER BY id DESC LIMIT 1",
            (amount_uzs,),
        )

    async def is_duplicate_receipt(self, image_sha256: str, tx_ref: str = "", exclude_order_id: int = 0) -> dict | None:
        dup = await self._one(
            "SELECT * FROM receipt_checks WHERE image_sha256=? AND order_id!=? LIMIT 1",
            (image_sha256, exclude_order_id),
        )
        if dup:
            return dup
        if tx_ref and len(tx_ref.strip()) >= 6:
            return await self._one(
                "SELECT * FROM receipt_checks WHERE tx_ref=? AND order_id!=? LIMIT 1",
                (tx_ref.strip(), exclude_order_id),
            )
        return None

    async def add_receipt_check(
        self,
        order_id: int,
        tx_ref: str,
        image_sha256: str,
        parsed_amount: int,
        parsed_last4: str,
        verdict: str,
        reason: str,
    ) -> int:
        return await self._exec(
            "INSERT INTO receipt_checks(order_id, tx_ref, image_sha256, parsed_amount, parsed_last4, verdict, reason, created_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (order_id, tx_ref, image_sha256, parsed_amount, parsed_last4, verdict, reason, int(time.time())),
        )

    async def list_bank_transactions(self, limit: int = 25) -> list[dict]:
        return await self._all("SELECT * FROM bank_transactions ORDER BY id DESC LIMIT ?", (limit,))

    async def upsert_competitor_account(
        self,
        handle: str,
        platform: str = "instagram",
        region: str = "uzbekistan",
        style_focus: str = "",
        followers_est: int = 0,
        avg_likes: float = 0.0,
        avg_views: int = 0,
        discovered_via: str = "web_crawler",
        notes: dict | None = None,
    ) -> None:
        clean = handle.strip().lstrip("@").lower()
        if not clean:
            return
        now = int(time.time())
        notes_str = json.dumps(notes or {}, ensure_ascii=False)
        existing = await self._one("SELECT handle FROM competitor_accounts WHERE handle=?", (clean,))
        if existing:
            await self._exec(
                "UPDATE competitor_accounts SET style_focus=CASE WHEN ?!='' THEN ? ELSE style_focus END, "
                "followers_est=CASE WHEN ?>0 THEN ? ELSE followers_est END, "
                "avg_likes=CASE WHEN ?>0 THEN ? ELSE avg_likes END, "
                "avg_views=CASE WHEN ?>0 THEN ? ELSE avg_views END, "
                "last_scanned_at=?, notes_json=CASE WHEN ?!='' THEN ? ELSE notes_json END WHERE handle=?",
                (
                    style_focus, style_focus,
                    followers_est, followers_est,
                    avg_likes, avg_likes,
                    avg_views, avg_views,
                    now, notes_str, notes_str, clean,
                ),
            )
        else:
            await self._exec(
                "INSERT INTO competitor_accounts(handle, platform, region, style_focus, followers_est, avg_likes, avg_views, "
                "discovered_via, last_scanned_at, notes_json, active, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,1,?)",
                (clean, platform, region, style_focus, followers_est, avg_likes, avg_views, discovered_via, now, notes_str, now),
            )

    async def list_competitor_accounts(self, limit: int = 30) -> list[dict]:
        return await self._all(
            "SELECT * FROM competitor_accounts WHERE active=1 ORDER BY avg_likes DESC, last_scanned_at DESC LIMIT ?",
            (limit,),
        )

    async def add_competitor_video(self, payload: dict[str, Any]) -> int:
        vkey = str(payload.get("video_key") or "").strip()
        if not vkey:
            return 0
        now = int(time.time())
        existing = await self._one("SELECT id FROM competitor_videos WHERE video_key=?", (vkey,))
        cols = (
            str(payload.get("account_handle") or "").lstrip("@").lower(),
            str(payload.get("video_url") or ""),
            str(payload.get("posted_at_info") or ""),
            str(payload.get("garment_type") or ""),
            str(payload.get("video_meaning") or ""),
            str(payload.get("editing_style") or ""),
            str(payload.get("video_quality") or ""),
            str(payload.get("music_genre") or ""),
            str(payload.get("audio_vibe") or "diplomat_old_money"),
            int(payload.get("views_est") or 0),
            int(payload.get("likes_count") or 0),
            int(payload.get("comments_count") or 0),
            int(payload.get("competitor_sell_price_uzs") or 0),
            int(payload.get("estimated_pdd_cost_uzs") or 0),
            int(payload.get("estimated_profit_uzs") or 0),
            int(payload.get("xan_target_price_uzs") or 0),
            str(payload.get("insight_summary") or ""),
            json.dumps(payload.get("raw_json") or {}, ensure_ascii=False),
            now,
        )
        if existing:
            await self._exec(
                "UPDATE competitor_videos SET account_handle=?, video_url=?, posted_at_info=?, garment_type=?, "
                "video_meaning=?, editing_style=?, video_quality=?, music_genre=?, audio_vibe=?, views_est=?, "
                "likes_count=?, comments_count=?, competitor_sell_price_uzs=?, estimated_pdd_cost_uzs=?, "
                "estimated_profit_uzs=?, xan_target_price_uzs=?, insight_summary=?, raw_json=?, analyzed_at=? WHERE video_key=?",
                (*cols, vkey),
            )
            return int(existing["id"])
        return await self._exec(
            "INSERT INTO competitor_videos(video_key, account_handle, video_url, posted_at_info, garment_type, "
            "video_meaning, editing_style, video_quality, music_genre, audio_vibe, views_est, likes_count, "
            "comments_count, competitor_sell_price_uzs, estimated_pdd_cost_uzs, estimated_profit_uzs, "
            "xan_target_price_uzs, insight_summary, raw_json, analyzed_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (vkey, *cols),
        )

    async def list_competitor_videos(self, limit: int = 50, account_handle: str | None = None) -> list[dict]:
        if account_handle:
            return await self._all(
                "SELECT * FROM competitor_videos WHERE account_handle=? ORDER BY (likes_count + comments_count*3) DESC, analyzed_at DESC LIMIT ?",
                (account_handle.strip().lstrip("@").lower(), limit),
            )
        return await self._all(
            "SELECT * FROM competitor_videos ORDER BY (likes_count + comments_count*3 + views_est/100) DESC, analyzed_at DESC LIMIT ?",
            (limit,),
        )

    async def get_halol_ogri_winning_patterns(self, limit: int = 5) -> list[dict]:
        return await self._all(
            "SELECT * FROM competitor_videos ORDER BY (likes_count + comments_count*4 + views_est/200) DESC, analyzed_at DESC LIMIT ?",
            (limit,),
        )

    async def upsert_tracked_source(
        self,
        source_key: str,
        platform: str,
        url: str,
        added_by: str = "owner",
        status: str = "active",
        style_summary: str = "",
        posting_pattern: str = "",
        pricing_pattern: str = "",
        extracted_playbook: dict | None = None,
    ) -> None:
        clean_key = source_key.strip().lower()
        if not clean_key:
            return
        now = int(time.time())
        pb_str = json.dumps(extracted_playbook or {}, ensure_ascii=False)
        existing = await self._one("SELECT source_key FROM tracked_sources WHERE source_key=?", (clean_key,))
        if existing:
            await self._exec(
                "UPDATE tracked_sources SET platform=?, url=CASE WHEN ?!='' THEN ? ELSE url END, status=?, "
                "style_summary=CASE WHEN ?!='' THEN ? ELSE style_summary END, "
                "posting_pattern=CASE WHEN ?!='' THEN ? ELSE posting_pattern END, "
                "pricing_pattern=CASE WHEN ?!='' THEN ? ELSE pricing_pattern END, "
                "extracted_playbook_json=CASE WHEN ?!='' THEN ? ELSE extracted_playbook_json END, "
                "last_analyzed_at=? WHERE source_key=?",
                (
                    platform, url, url, status,
                    style_summary, style_summary,
                    posting_pattern, posting_pattern,
                    pricing_pattern, pricing_pattern,
                    pb_str, pb_str,
                    now, clean_key,
                ),
            )
        else:
            await self._exec(
                "INSERT INTO tracked_sources(source_key, platform, url, added_by, status, style_summary, "
                "posting_pattern, pricing_pattern, extracted_playbook_json, last_analyzed_at, created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (clean_key, platform, url, added_by, status, style_summary, posting_pattern, pricing_pattern, pb_str, now, now),
            )

    async def list_tracked_sources(self, limit: int = 40) -> list[dict]:
        return await self._all("SELECT * FROM tracked_sources ORDER BY last_analyzed_at DESC LIMIT ?", (limit,))

    async def save_learned_playbook(self, playbook_key: str, rules: dict[str, Any], source_refs: list[str] | None = None) -> None:
        now = int(time.time())
        r_str = json.dumps(rules, ensure_ascii=False)
        refs_str = json.dumps(source_refs or [], ensure_ascii=False)
        existing = await self._one("SELECT playbook_key FROM learned_playbooks WHERE playbook_key=?", (playbook_key,))
        if existing:
            await self._exec(
                "UPDATE learned_playbooks SET rules_json=?, source_refs_json=?, updated_at=? WHERE playbook_key=?",
                (r_str, refs_str, now, playbook_key),
            )
        else:
            await self._exec(
                "INSERT INTO learned_playbooks(playbook_key, rules_json, source_refs_json, updated_at) VALUES(?,?,?,?)",
                (playbook_key, r_str, refs_str, now),
            )

    async def get_all_playbooks(self) -> dict[str, dict[str, Any]]:
        rows = await self._all("SELECT * FROM learned_playbooks")
        out: dict[str, dict[str, Any]] = {}
        for r in rows:
            try:
                out[r["playbook_key"]] = json.loads(r["rules_json"] or "{}")
            except Exception:
                out[r["playbook_key"]] = {}
        return out
