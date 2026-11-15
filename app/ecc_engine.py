"""ECC (Everything Claude Code — 71 Agent + 314 Skill) & Graphify Token-Optimizatsiya Dvigateli.

GitHub'dagi `affaan-m/ECC` plaginidagi 71 ta ixtisoslashgan agent va 314 ta skillni
XAN SHOP Virtual Ofisiga ulaydi hamda Graphify uslubida ixcham bilim grafigi (token tejash) quradi.
Barcha agent chaqiruvlari OmniRoute -> OpenRouter -> Gemini zaxira zanjiri orqali ishlaydi.
"""
from __future__ import annotations

import ast
import html
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ai import SalesAI
from .config import Settings

log = logging.getLogger(__name__)

DEPARTMENT_TITLES_UZ: dict[str, str] = {
    "director": "Boshqaruv (Direktor)",
    "insta_analyst": "Instagram Razvedka & Tahlil",
    "skaut": "Skaut & Trendlar",
    "smm_manager": "SMM & Marketing",
    "video_employee": "Reels & Dizayn Studiyasi",
    "sales_stylist": "Sotuv & Stilist",
    "accountant": "Moliya & Chek Auditi",
    "cargo_logistics": "Ombor, Kargo & Bojxona",
}

# Faqat XAN SHOP (onlayn kiyim do'koni, marketing, Reels, sotuv, moliya, kargo/bojxona) sohasiga
# to'g'ridan-to'g'ri ishlaydigan tanlangan ECC mutaxassis agentlar.
XAN_CURATED_AGENTS: dict[str, dict[str, str]] = {
    "chief-of-staff": {
        "department": "director",
        "title_uz": "Boshqaruvchi AI (Avtonom Direktor)",
        "role_uz": "Bozor va narxlarni tahlil qilish, rivojlanish strategiyasi va barcha bo'limlarga buyruq berish",
    },
    "planner": {
        "department": "director",
        "title_uz": "Biznes Rejalashtiruvchi",
        "role_uz": "Haftalik kolleksiya rejasi, mavsumiy aksiyalar va sotuv strategiyasi",
    },
    "harness-optimizer": {
        "department": "director",
        "title_uz": "Token & Limit Optimizatori",
        "role_uz": "OmniRoute kesh va bepul model zanjiri bilan AI xarajatini minimal ushlash",
    },
    "spec-miner": {
        "department": "skaut",
        "title_uz": "Pinduoduo Trend Skauti",
        "role_uz": "Xitoy bozorida talab yuqori erkaklar kiyimi va poyabzallarini ajratish",
    },
    "docs-lookup": {
        "department": "skaut",
        "title_uz": "Mahsulot & Razmer Tadqiqotchisi",
        "role_uz": "Razmer jadvallari, mato tarkibi va yetkazib beruvchi tafsilotlarini tekshirish",
    },
    "marketing-agent": {
        "department": "smm_manager",
        "title_uz": "SMM & Marketing Mutaxassisi",
        "role_uz": "Telegram va Instagram uchun sotuvchi postlar, reklama matnlari va aksiyalar",
    },
    "seo-specialist": {
        "department": "insta_analyst",
        "title_uz": "Instagram Hook, Bio & SEO Razvedkasi",
        "role_uz": "Raqobatchilar (@_tima_shop, @stylesh.uz) bio, opisaniya, zvuk va hashtaglarini tahlil qilish",
    },
    "comment-analyzer": {
        "department": "insta_analyst",
        "title_uz": "Raqobatchi Koment & Psixologiya Tahlilchisi",
        "role_uz": "Mijoz kommentariyalari, narxga munosabat va odamlarni og'dirish triggerlarini tahlil qilish",
    },
    "gan-planner": {
        "department": "video_employee",
        "title_uz": "Reels Ssenariy Rejissyori",
        "role_uz": "3 soniyalik kuchli hooklar va dinamik Reels kadrlari ssenariysi",
    },
    "gan-generator": {
        "department": "video_employee",
        "title_uz": "Look & Video Kreator",
        "role_uz": "Premium erkaklar look kolleksiyasi muqovalari va ovozli video ssenariysi",
    },
    "gan-evaluator": {
        "department": "video_employee",
        "title_uz": "Vizual Sifat Nazoratchisi",
        "role_uz": "Tayyor Reels va mahsulot kartochkalarini sotuv standartiga tekshirish",
    },
    "conversation-analyzer": {
        "department": "sales_stylist",
        "title_uz": "Sotuv & Stilist Tahlilchisi",
        "role_uz": "Mijoz yozishmalarini tahlil qilib konversiyani va o'rtacha chekni oshirish",
    },
    "security-reviewer": {
        "department": "accountant",
        "title_uz": "To'lov & Chek Xavfsizlik Auditi",
        "role_uz": "Soxta bank cheklari, duplikat skrinsthotlar va shubhali to'lovlarni aniqlash",
    },
    "agent-evaluator": {
        "department": "accountant",
        "title_uz": "Moliyaviy Hisob Nazoratchisi",
        "role_uz": "50% oldindan to'lov, CNY/UZS kursi va sof foyda marjasini tekshirish",
    },
    "loop-operator": {
        "department": "cargo_logistics",
        "title_uz": "24/7 Kargo & Jarayon Operatori",
        "role_uz": "TUJJOR-AVIA va Door-to-Door yuk holati, bojxona va avtonom sikllar",
    },
}

# Faqat XAN SHOP biznesiga kerakli skillar (kodlash/C++/Rust/Java/Swift skillari filtrlangan)
XAN_CURATED_SKILLS: dict[str, tuple[str, str, str]] = {
    "marketing-campaign": ("Marketing", "Sotuv Kampaniyasi", "Mavsumiy aksiya va yangi kolleksiya chiqarish rejasi"),
    "brand-voice": ("Marketing", "Brend Ohangi", "XAN SHOP uslubida ishonchli, zamonaviy va erkakcha muloqot tili"),
    "brand-discovery": ("Marketing", "Brend Pozitsiyasi", "Raqobatchilardan ajralib turadigan brend qiymatini shakllantirish"),
    "content-engine": ("Marketing", "Kontent Tizimi", "Instagram Reels va Telegram kanal uchun kunlik kontent reja"),
    "market-research": ("Skaut", "Bozor Tadqiqoti", "O'zbekiston bozoridagi talab va narx segmentlarini o'rganish"),
    "competitive-report-structure": ("Skaut", "Raqobatchi Tahlili", "Boshqa onlayn do'konlar narxi va xizmatini solishtirish"),
    "seo": ("Marketing", "Qidiruv & Hashtag SEO", "Organik qamrovni oshiruvchi teglar va tavsiflar tuzish"),
    "social-publisher": ("Marketing", "Avto-Nashr Rejasi", "Eng faol soatlarda kontent joylash strategiyasi"),
    "crosspost": ("Marketing", "Kross-Platforma", "Bir lookni Telegram va Instagram Reels formatiga moslashtirish"),
    "recsys-pipeline-architect": ("Stilist", "Look Komplektlash", "Mijoz o'lchami, bo'yi va didiga mos kiyimlarni juftlash"),
    "video-editing": ("Reels Studio", "Reels Video Montaj", "Tezkor kadr almashinuvi, hook va dinamik subtitrlar"),
    "remotion-video-creation": ("Reels Studio", "Animatsion Katalog", "Narx va chegirma animatsiyali video ssenariysi"),
    "tasteforge-video": ("Reels Studio", "Vizual Did & Stil", "Premium kadr kompozitsiyasi va rang uyg'unligi"),
    "finance-billing-ops": ("Moliya", "Foyda & Narx Auditi", "Xitoy narxi, vukup, bank to'lovi va sof foyda nazorati"),
    "customer-billing-ops": ("Moliya", "50/50 To'lov Oqimi", "Oldindan to'lov, qoldiq va qaytim hisob-kitoblari"),
    "regex-vs-llm-structured-text": ("Moliya", "Bank SMS & Chek Tahlili", "HUMO/UZCARD SMS va cheklardan aniq summani ajratib olish"),
    "customs-trade-compliance": ("Kargo & Bojxona", "Bojxona $200 Limiti", "Oylik $200 bojxona limiti va posilka deklaratsiyasi nazorati"),
    "carrier-relationship-management": ("Kargo & Bojxona", "Kargo Liniyalar", "TUJJOR-AVIA (Toshkent) va Door-to-Door (Viloyatlar) tarifi"),
    "logistics-exception-management": ("Kargo & Bojxona", "Yuk Muammolari", "Kechikish, brak yoki noto'g'ri razmerda tezkor yechim"),
    "inventory-demand-planning": ("Skaut & Ombor", "Razmer & Talab Prognozi", "Eng tez sotiladigan o'lcham va ranglarni oldindan aniqlash"),
    "returns-reverse-logistics": ("Kargo & Bojxona", "Almashuv & Qaytarish", "Mijozga mos kelmagan kiyimni almashtirish qoidalari"),
    "token-budget-advisor": ("AI Tejamkorlik", "Token Byudjeti", "Agent javoblarini qisqa, aniq va kam tokenli qilish"),
    "cost-aware-llm-pipeline": ("AI Tejamkorlik", "OmniRoute Aqlli Zanjir", "Vazifaga qarab bepul/arzon modelni avtomatik tanlash"),
    "content-hash-cache-pattern": ("AI Tejamkorlik", "Takroriy So'rov Keshi", "Bir xil savol va cheklarda ortiqcha AI limit sarflamaslik"),
    "team-agent-orchestration": ("Boshqaruv", "AI Jamoa Koordinatsiyasi", "Skaut -> Studio -> SMM -> Sotuv bo'limlarini bog'lash"),
}

DEPARTMENT_AGENT_MAP: dict[str, list[str]] = {}
for _aid, _meta in XAN_CURATED_AGENTS.items():
    DEPARTMENT_AGENT_MAP.setdefault(_meta["department"], []).append(_aid)

RECOMMENDED_XAN_SKILLS: list[str] = list(XAN_CURATED_SKILLS.keys())


@dataclass
class ECCAgentSpec:
    agent_id: str
    name: str
    description: str
    model: str
    tools: str
    department: str
    prompt_body: str


@dataclass
class ECCSkillSpec:
    skill_id: str
    name: str
    description: str
    path: str
    content: str


def _parse_frontmatter(raw: str) -> tuple[dict[str, str], str]:
    meta: dict[str, str] = {}
    body = raw
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        if end != -1:
            fm_block = raw[3:end]
            body = raw[end + 4 :].strip()
            for line in fm_block.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip().lower()] = v.strip().strip("\"'")
    return meta, body


def _infer_department(agent_id: str) -> str:
    for dept, ids in DEPARTMENT_AGENT_MAP.items():
        if agent_id in ids:
            return dept
    if "security" in agent_id or "reviewer" in agent_id:
        return "accountant"
    if "architect" in agent_id or "planner" in agent_id:
        return "director"
    return "cargo_logistics"


class ECCRegistry:
    """71 ta ECC agent va 314 ta skill reestri + Graphify ixcham bilim grafigi."""

    def __init__(self, ecc_root: str = "vendor/ecc"):
        self.ecc_root = Path(ecc_root)
        self.agents: dict[str, ECCAgentSpec] = {}
        self.skills: dict[str, ECCSkillSpec] = {}
        self.reload()

    def reload(self) -> None:
        self.agents.clear()
        self.skills.clear()

        agents_dir = self.ecc_root / "agents"
        if agents_dir.is_dir():
            for md_file in sorted(agents_dir.glob("*.md")):
                try:
                    raw = md_file.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                meta, body = _parse_frontmatter(raw)
                aid = md_file.stem
                self.agents[aid] = ECCAgentSpec(
                    agent_id=aid,
                    name=meta.get("name", aid),
                    description=meta.get("description", ""),
                    model=meta.get("model", "auto"),
                    tools=meta.get("tools", ""),
                    department=_infer_department(aid),
                    prompt_body=body,
                )

        skills_dir = self.ecc_root / "skills"
        if skills_dir.is_dir():
            for sub in sorted(skills_dir.iterdir()):
                if not sub.is_dir():
                    continue
                skill_md = sub / "SKILL.md"
                if not skill_md.is_file():
                    continue
                try:
                    raw = skill_md.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                meta, body = _parse_frontmatter(raw)
                sid = sub.name
                self.skills[sid] = ECCSkillSpec(
                    skill_id=sid,
                    name=meta.get("name", sid),
                    description=meta.get("description", ""),
                    path=str(skill_md),
                    content=body,
                )

    def summary_for_dashboard(self, include_all: bool = False) -> dict[str, Any]:
        curated_agents = []
        for aid, cmeta in XAN_CURATED_AGENTS.items():
            spec = self.agents.get(aid)
            if not spec:
                continue
            dept = cmeta["department"]
            curated_agents.append({
                "id": spec.agent_id,
                "name": cmeta["title_uz"],
                "raw_name": spec.name,
                "description": cmeta["role_uz"],
                "department": dept,
                "department_uz": DEPARTMENT_TITLES_UZ.get(dept, dept),
                "model": spec.model,
            })

        curated_skills = []
        for sid, (cat_uz, title_uz, desc_uz) in XAN_CURATED_SKILLS.items():
            spec = self.skills.get(sid)
            if not spec:
                continue
            curated_skills.append({
                "id": spec.skill_id,
                "name": title_uz,
                "raw_name": spec.name,
                "category": cat_uz,
                "description": desc_uz,
                "recommended": True,
            })

        if include_all:
            agents_out = [
                {
                    "id": a.agent_id,
                    "name": XAN_CURATED_AGENTS.get(a.agent_id, {}).get("title_uz", a.name),
                    "description": XAN_CURATED_AGENTS.get(a.agent_id, {}).get("role_uz", a.description),
                    "department": a.department,
                    "department_uz": DEPARTMENT_TITLES_UZ.get(a.department, a.department),
                    "model": a.model,
                    "curated": a.agent_id in XAN_CURATED_AGENTS,
                }
                for a in self.agents.values()
            ]
            skills_out = [
                {
                    "id": s.skill_id,
                    "name": XAN_CURATED_SKILLS.get(s.skill_id, ("Texnik", s.name, s.description))[1],
                    "category": XAN_CURATED_SKILLS.get(s.skill_id, ("Texnik", s.name, s.description))[0],
                    "description": XAN_CURATED_SKILLS.get(s.skill_id, ("Texnik", s.name, s.description))[2],
                    "recommended": s.skill_id in XAN_CURATED_SKILLS,
                }
                for s in self.skills.values()
            ]
        else:
            agents_out = curated_agents
            skills_out = curated_skills

        return {
            "ecc_installed": self.ecc_root.is_dir() and len(self.agents) > 0,
            "domain_filter": "XAN SHOP — Kiyim, Marketing, Reels, Sotuv, Moliya & Kargo",
            "agents_count": len(agents_out),
            "skills_count": len(skills_out),
            "repo_agents_count": len(self.agents),
            "repo_skills_count": len(self.skills),
            "departments": DEPARTMENT_AGENT_MAP,
            "department_titles": DEPARTMENT_TITLES_UZ,
            "agents": agents_out,
            "skills": skills_out,
        }


def build_graphify_context_index(app_dir: str = "app") -> dict[str, Any]:
    """Graphify tamoyili bo'yicha loyiha fayllarining AST bilim grafigini quradi (tokenni ~80% tejash)."""
    nodes: list[dict[str, Any]] = []
    app_path = Path(app_dir)
    if not app_path.is_dir():
        return {"modules": 0, "functions": 0, "classes": 0, "compact_map": ""}

    total_funcs = 0
    total_classes = 0
    compact_lines: list[str] = []

    for py_file in sorted(app_path.glob("*.py")):
        if py_file.name == "__init__.py":
            continue
        try:
            src = py_file.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(src)
        except Exception:
            continue
        classes = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
        funcs = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        total_classes += len(classes)
        total_funcs += len(funcs)
        nodes.append({"file": py_file.name, "classes": classes, "functions": funcs})
        parts = []
        if classes:
            parts.append("C:" + ",".join(classes[:4]))
        if funcs:
            parts.append("F:" + ",".join(funcs[:6]))
        compact_lines.append(f"{py_file.name}[{' | '.join(parts)}]")

    return {
        "modules": len(nodes),
        "classes": total_classes,
        "functions": total_funcs,
        "nodes": nodes,
        "compact_map": "\n".join(compact_lines),
    }


async def run_ecc_specialist(
    registry: ECCRegistry,
    settings: Settings,
    agent_id: str,
    task_prompt: str,
    skill_ids: list[str] | None = None,
    db: Any = None,
) -> dict[str, Any]:
    """Tanlangan ECC agent va skillni OmniRoute -> OpenRouter -> Gemini orqali ishga tushiradi."""
    agent = registry.agents.get(agent_id)
    if not agent:
        return {"ok": False, "error": f"ECC agent '{agent_id}' topilmadi"}

    # Token tejamkor Prompt: faqat agent asosiy qoidasi + kerakli skill + Graphify xarita
    agent_instructions = agent.prompt_body[:2400]
    skills_block_parts: list[str] = []
    used_skills: list[str] = []
    for sid in (skill_ids or []):
        sk = registry.skills.get(sid)
        if sk:
            used_skills.append(sid)
            skills_block_parts.append(f"### SKILL: {sk.name}\n{sk.content[:1400]}")

    graph_idx = build_graphify_context_index("app")
    system_prompt = (
        f"Sen XAN SHOP Virtual Ofisining ECC '{agent.name}' mutaxassis agentisan.\n"
        f"Mutaxassislik: {agent.description}\n\n"
        f"Loyiha Graphify xaritasi ({graph_idx['modules']} modul, {graph_idx['functions']} funksiya):\n"
        f"{graph_idx['compact_map'][:900]}\n\n"
        f"Agent yo'riqnomasi:\n{agent_instructions}\n\n"
        + ("\n".join(skills_block_parts) if skills_block_parts else "")
        + "\n\nQISQA, ANIQ va AMALIY javob ber (o'zbek tilida, kerak bo'lsa kod/reja bilan)."
    )

    ai = SalesAI(settings)
    if not ai.enabled:
        return {"ok": False, "error": "AI provayder (OmniRoute / OpenRouter / Gemini) ulanmagan"}

    dept = XAN_CURATED_AGENTS.get(agent_id, {}).get("department", agent.department)
    if db is not None:
        await db.set_agent_status(dept, "working", f"ECC [{agent_id}] ishlamoqda: {task_prompt[:45]}...")

    answer, _, _ = await ai.reply(system_prompt, task_prompt, previous_id=None)
    provider = ai.last_provider_used
    if answer:
        answer = html.unescape(answer).strip()

    if db is not None:
        await db.set_agent_status(dept, "idle", f"AI [{agent_id}] vazifani yakunladi", increment_done=True)
        await db.log_agent_action(
            dept,
            f"Mutaxassis '{agent_id}' ({', '.join(used_skills) or 'asosiy'}) vazifani bajardi [{provider}]",
            f"So'rov: {task_prompt[:120]} | Javob uzunligi: {len(answer or '')} belgi",
        )

    if not answer:
        return {"ok": False, "error": "AI provayder javob bermadi (OmniRoute/Gemini holatini tekshiring)"}

    return {
        "ok": True,
        "agent_id": agent_id,
        "department": dept,
        "skills": used_skills,
        "provider": provider,
        "answer": answer,
    }
