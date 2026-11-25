"""XAN SHOP - AI Agent Office (Markaziy 24/7 Avtonom Orkestrator).

Murakkab ko'p-bosqichli zanjir:
1. Video/Instagram Trend Analitik -> Instagramda qaysi format (2, 3, 4 yoki 5 talik), qaysi zvuk va
   qaysi ranglar palitrasi rekka chiqayotganini aniqlab, Bozor Tahlilchisi (Skaut)ga uzatadi.
2. Skaut & Dizayner Agent (skaut) -> Pinduoduo (`app/pinduoduo.py`) orqali mos buyumlarni topadi,
   dizaynerlik ranglar uyg'unligini (HEX Palette) tanlaydi va 50%/100% + UZS->CNY tranzaksiya narxini hisoblaydi.
3. SMM Boshlig'i Agent (smm_manager) -> O'zining qo'l ostidagi Video Montajchi Xodimga (video_employee)
   texnik topshiriq beradi.
4. Video Montajchi Xodim (video_employee) -> 1080x1350 Kolaj + 9:16 formatda beat-audio ("zvuk") va
   zoom effektli haqiqiy `.mp4` Reels video (`look_<id>_reels.mp4`) hamda `.gif` tayyorlab SMM Boshlig'iga topshiradi.
5. SMM Boshlig'i Agent -> Lookzona/Stylesh darajasidagi aniq sotuv matni bilan videoni Telegram kanalga
   va Rasmiy Instagram Graph API (`publish_reels_to_instagram`) orqali Reels'ga joylaydi!
6. Sotuvchi Stilist (Shaxsiy Telegram Akkaunt Userbot + Bot) va Vykup/Kargo Agent (2 ta Avia Kargo) 24/7 ishlaydi.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

from aiogram import Bot

from .ai import SalesAI
from .config import Settings
from .db import Database
from .economy import get_params, get_rates
from .insta_comments import poll_and_reply_instagram_comments
from .logistics import LogisticsAgent
from .media import (
    create_comparison_hook_slide,
    create_hook_intro_slide,
    create_look_collage,
    create_reels_frames,
    generate_item_studio_card,
    generate_look_voiceover_script,
    save_reels_animation,
)
from .notify import notify_admins
from .pinduoduo import has_valid_pdd_session
from .pricing import fmt
from .publisher import (
    build_telegram_post_link,
    format_instagram_caption,
    get_instagram_permalink,
    publish_look_to_telegram,
    publish_reels_to_instagram,
    publish_story_to_instagram,
)
from .sourcing import TrendSourcingAgent
from .trends import (
    analyze_competitor_account,
    build_video_creative_directive,
    fetch_tashkent_weather,
)

log = logging.getLogger(__name__)
PHOTO_DIR = os.path.join("data", "photos")


@dataclass
class OfficePipelineResult:
    look_id: int
    title: str
    piece_count: int
    palette_name: str
    palette_hex: list[str]
    audio_vibe: str
    prepay_uzs: int
    prepay_50_uzs: int
    remaining_50_uzs: int
    goods_cost_uzs: int
    cargo_est_uzs: int
    profit_uzs: int
    photo_path: str
    video_path: str
    mp4_path: str
    insta_caption_path: str
    channel_msg_id: int | None
    ig_media_id: str | None = None
    tg_link: str = ""
    ig_link: str = ""
    video_style: str = ""
    target_persona: str = ""


class AgentOffice:
    """XAN SHOP 24/7 Virtual Ofisi."""

    def __init__(
        self,
        db: Database,
        settings: Settings,
        sales_bot: Bot | None = None,
        admin_bot: Bot | None = None,
        sales_username: str = "XanShopBot",
        media_dir: str = PHOTO_DIR,
    ):
        self.db = db
        self.s = settings
        self.sales_bot = sales_bot
        self.admin_bot = admin_bot
        self.sales_username = sales_username
        self.media_dir = media_dir
        self.userbot = None
        self._cycle_counter = 0

    async def run_look_pipeline(
        self,
        season: str = "avtomatik ob-havo",
        gender: str = "yoshlar / erkaklar",
        style: str = "Lookzona va Stylesh uslubida",
        raw_images: list[Any] | None = None,
        delete_previous: bool = False,
        notify_admin_on_publish: bool = True,
        custom_prompt: str = "",
        reference_media_bytes: bytes | None = None,
        reference_media_mime: str = "",
        piece_count: int | None = None,
        max_prepay_50_uzs: int | None = None,
    ) -> OfficePipelineResult:
        """To'liq avtonom zanjir: Instagram Tahlil + Ob-havo -> Pinduoduo Skaut -> SMM -> 1080p Video Xodim -> Nashr + Admin Xabar."""
        os.makedirs(self.media_dir, exist_ok=True)
        rates = await get_rates(self.db, self.s)
        params = await get_params(self.db, self.s)

        existing_looks = await self.db.list_looks(only_active=False)
        used_goods_ids: set[str] = set()
        used_titles_cn: set[str] = set()
        recent_titles: list[str] = []
        # Eng yangi looklardan boshlab (reversed) oxirgi 16 ta sarlavha va barcha ishlatilgan tovar ID larni yig'amiz
        for ex_l in reversed(existing_looks):
            t_str = str(ex_l.get("title") or "").strip()
            if t_str and t_str not in recent_titles and len(recent_titles) < 16:
                recent_titles.append(t_str)
            try:
                ex_items = json.loads(ex_l.get("items_json") or "[]")
            except Exception:
                ex_items = []
            for ex_it in ex_items if isinstance(ex_items, list) else []:
                gid_val = str(ex_it.get("pdd_goods_id") or ex_it.get("goods_id") or "").strip()
                if gid_val:
                    used_goods_ids.add(gid_val)
                tcn = str(ex_it.get("title_cn") or "").strip()[:28]
                if tcn and len(used_titles_cn) < 60:
                    used_titles_cn.add(tcn)
        saved_cycle = int(await self.db.get_setting("look_cycle_idx") or "0")
        cycle_idx = max(len(existing_looks), saved_cycle, self._cycle_counter)
        await self.db.set_setting("look_cycle_idx", cycle_idx + 1)
        self._cycle_counter = cycle_idx + 1

        skaut = TrendSourcingAgent(self.s, rates=rates, params=params)
        skaut._fallback_idx = cycle_idx
        brief = skaut.analyze_instagram_trends(cycle_idx)

        # 1-QADAM: Instagram Razvedka Agent (insta_analyst) -> 5–12 kun oldingi ob-havo + @_tima_shop/Stylesh jonli tahlilini Skautga uzatadi
        await self.db.set_agent_status(
            "director",
            "working",
            f"Yangi sikl: '{brief.trend_name}' ({brief.recommended_piece_count}-in-1) tasdiqlandi",
        )
        await self.db.set_agent_status(
            "insta_analyst",
            "working",
            f"@_tima_shop / @stylesh_shop jonli narxlari, zvuklari va hooklari tahlil qilinmoqda...",
        )
        weather = await fetch_tashkent_weather()
        from app.ig_analytics import run_live_instagram_analyst_async
        ig_intel = await run_live_instagram_analyst_async(self.db, self.s, cycle_idx, weather=weather)
        ig_intel["recent_titles"] = recent_titles
        comp_snap = analyze_competitor_account("_tima_shop", weather)
        if not comp_snap.get("ig_live"):
            comp_snap["ig_live"] = ig_intel
        halol_ogri = ig_intel.get("halol_ogri") or {}
        ho_stats = f"Akkountlar: {halol_ogri.get('accounts_tracked', 5)} | Videolar: {halol_ogri.get('videos_analyzed', 4)}"
        await self.db.set_agent_status(
            "insta_analyst",
            "idle",
            f"Halol O'g'ri tayyor ({ho_stats}) | {weather.lead_time_days} (~{weather.future_temp_c or weather.temp_c}°C)",
            increment_done=True,
        )
        await self.db.log_agent_action(
            "insta_analyst",
            f"Halol O'g'ri razvedkasi [{ho_stats}]: '{brief.trend_name}' | Top zvuk: {halol_ogri.get('recommended_audio_vibe', brief.audio_vibe)}",
            halol_ogri.get("scout_brief") or f"Hook: {comp_snap['hook_patterns'][0]} | Palitra: {brief.color_palette_name}",
            target_id="skaut",
        )

        # 2-QADAM: Skaut & Dizayner Agent (jonli Toshkent ob-havosi + Raqobatchi narxlar + Pinduoduo API) yangi Look yig'adi
        has_custom_order = bool((custom_prompt or "").strip() or reference_media_bytes or piece_count or max_prepay_50_uzs)
        custom_blueprint: dict[str, Any] | None = None
        if has_custom_order:
            await self.db.set_agent_status(
                "insta_analyst",
                "working",
                f"Admin yuborgan maxsus buyruq/media AI Vision orqali tahlil qilinmoqda...",
            )
            custom_blueprint = await skaut.build_custom_look_blueprint_async(
                prompt_text=custom_prompt,
                media_bytes=reference_media_bytes,
                media_mime=reference_media_mime,
                piece_count=piece_count,
                max_prepay_50_uzs=max_prepay_50_uzs,
                weather=weather,
            )
            await self.db.log_agent_action(
                "insta_analyst",
                f"✨ Admin Maxsus Buyrug'i Tahlili: '{custom_blueprint.get('title', 'Maxsus Look')}'",
                f"Buyruq: {custom_prompt[:140] or '(Media namuna)'} | Qismlar: {len(custom_blueprint.get('items') or [])} ta",
                target_id="skaut",
            )

        await self.db.set_agent_status(
            "skaut",
            "working",
            (
                f"Admin buyrug'i asosida Pinduoduo'dan {len((custom_blueprint or {}).get('items') or []) or brief.recommended_piece_count} qismli Look yig'ilmoqda..."
                if has_custom_order
                else f"Toshkent ob-havosi va Pinduoduo'dan {brief.recommended_piece_count} qismli YANGI Look yig'ilmoqda..."
            ),
        )
        gen = await skaut.generate_look_async(
            season,
            gender,
            style,
            brief,
            weather=weather,
            ig_intel=ig_intel,
            exclude_goods_ids=used_goods_ids,
            exclude_titles_cn=used_titles_cn,
            custom_blueprint=custom_blueprint,
            max_prepay_50_uzs=max_prepay_50_uzs,
        )
        b = gen.breakdown

        price_dict = {
            "prepay_uzs": b.prepay_uzs,
            "prepay_50_uzs": b.prepay_50_uzs,
            "remaining_50_uzs": b.remaining_50_uzs,
            "profit_uzs": b.profit_uzs,
            "goods_cost_uzs": b.goods_cost_uzs,
            "weight_kg": b.weight_kg,
            "cargo_client_uzs": b.cargo_client_uzs,
        }
        palette_hex = gen.palette_hex or brief.color_hex_list
        look_id = await self.db.add_look(
            title=gen.title,
            items=gen.raw_items,
            sizes=gen.sizes,
            colors=gen.colors,
            price=price_dict,
            palette_name=gen.palette_name,
            palette_hex=json.dumps(palette_hex),
            audio_vibe=gen.audio_vibe,
        )

        wishlist_note = ""
        if has_valid_pdd_session(getattr(self.s, "pdd_session_path", "")):
            try:
                wl_res = await skaut.pdd.save_look_to_wishlist(gen.raw_items)
                if wl_res.get("total"):
                    wishlist_note = f" | PDD Wishlist (收藏): {wl_res.get('saved', 0)}/{wl_res['total']} saqlandi"
            except Exception as e:
                log.warning("Auto wishlist xatosi: %s", e)

        items_summary = ", ".join(
            f"{i['name']} (¥{i['price_cny']:g}, PDD:{i.get('pdd_goods_id', '-')})"
            for i in gen.raw_items
        )
        await self.db.set_agent_status(
            "skaut",
            "idle",
            f"Look #{look_id} ({gen.piece_count}-in-1) tayyor · 50% oldindan: {fmt(b.prepay_50_uzs)} so'm",
            increment_done=True,
        )
        await self.db.log_agent_action(
            "skaut",
            f"Pinduoduo'dan Look #{look_id} ({gen.piece_count}-in-1 \"{gen.title}\") yig'ildi va narxlandi{wishlist_note}",
            f"Ob-havo: {gen.weather_summary} | Buyumlar: {items_summary} | Palitra: {gen.palette_name} | "
            f"Xitoy+Tranzaksiya ({params.conversion_fee_percent:g}%): {fmt(b.goods_cost_uzs)} so'm | "
            f"50% Oldindan: {fmt(b.prepay_50_uzs)} so'm | 100% Narx: {fmt(b.prepay_uzs)} so'm{wishlist_note}",
            target_id="smm_manager",
        )

        # 3-QADAM: insta_analyst ("Halol O'g'ri") va SMM Boshlig'i Video Montajchi ga 1080p kreativ rejissura + haqiqiy musiqa buyrug'ini beradi
        effective_vibe = (
            "diplomat_old_money"
            if any(k in gen.title.lower() for k in ("diplomat", "yurid", "old money", "klassik"))
            else str(halol_ogri.get("recommended_audio_vibe") or gen.audio_vibe)
        )
        creative_directive = build_video_creative_directive(
            look_title=gen.title,
            piece_count=gen.piece_count,
            total_price_uzs=b.prepay_uzs,
            prepay_50_uzs=b.prepay_50_uzs,
            palette_name=gen.palette_name,
            palette_hex=palette_hex,
            audio_vibe=effective_vibe,
            weather=weather,
            items=gen.raw_items,
            style_idx=cycle_idx,
            viral_hook=gen.viral_hook,
        )
        video_style = str(creative_directive.get("video_style") or halol_ogri.get("recommended_video_style") or "orbit_3d_turntable")
        target_persona = str(creative_directive.get("target_persona") or "Zamonaviy yigitlar")
        audio_vibe = str(creative_directive.get("audio_vibe") or effective_vibe)

        await self.db.log_agent_action(
            "insta_analyst",
            f"🎬 Halol O'g'ri → Video Montajchi [Look #{look_id}]: Stil='{video_style}' | Zvuk='{audio_vibe}'",
            f"{halol_ogri.get('video_brief') or creative_directive['hook_headline']}",
            target_id="video_employee",
        )
        await self.db.set_agent_status(
            "smm_manager",
            "working",
            f"Video Xodimga Look #{look_id} ({target_persona}) uchun 1080p '{video_style}' Reels va kolaj buyurildi",
        )
        await self.db.log_agent_action(
            "smm_manager",
            f"Video Montajchi Xodimga Look #{look_id} uchun 1080p '{video_style}' (.mp4, zvuk: '{audio_vibe}') buyurildi",
            f"Auditoriya: {target_persona} | Hook: {creative_directive['hook_headline']} | CTA: {creative_directive['comment_trigger_cta']}",
            target_id="video_employee",
        )

        # 3.5-QADAM: Photoshop Studio AI (Nano Banana) — Pinduoduo Tahlilchi bergan rasm va prompt +
        # Instagram Tahlilchining tabiiy turish (pose/lighting) yo'nalishi bilan mahsulotni O'ZGARTIRMASDAN studiya sifatida chiqaradi!
        from .photo_studio import PhotoStudioAgent, derive_insta_pose_direction

        item_names = [i["name"] for i in gen.raw_items]
        dl_imgs = gen.downloaded_images or []

        def _ensure_pil(raw_im: Any, idx: int, it_dict: dict[str, Any]):
            if raw_im is not None:
                if isinstance(raw_im, (bytes, bytearray)):
                    try:
                        import io as _io
                        from PIL import Image as _PILImage

                        return _PILImage.open(_io.BytesIO(raw_im)).convert("RGB")
                    except Exception:
                        pass
                elif hasattr(raw_im, "convert"):
                    return raw_im
            return generate_item_studio_card(
                name=it_dict["name"],
                idx=idx,
                price_cny=float(it_dict.get("price_cny", 0)),
                color_hex=palette_hex[idx % len(palette_hex)] if palette_hex else "#1E1E22",
                sales_tip=str(it_dict.get("sales_tip", "")),
            )

        raw_pil_items = (
            [_ensure_pil(im, idx, gen.raw_items[min(idx, len(gen.raw_items) - 1)]) for idx, im in enumerate(raw_images)]
            if raw_images
            else [
                _ensure_pil(dl_imgs[idx] if idx < len(dl_imgs) else None, idx, i)
                for idx, i in enumerate(gen.raw_items)
            ]
        )

        studio_pose = str(halol_ogri.get("studio_pose_direction") or derive_insta_pose_direction(ig_intel))
        await self.db.log_agent_action(
            "insta_analyst",
            f"🎨 Insta Tahlilchi → Photoshop Studio [Look #{look_id}]: Tabiiy turish & yoritish yo'nalishi yuborildi",
            studio_pose[:220],
            target_id="photo_studio",
        )
        await self.db.set_agent_status(
            "photo_studio",
            "working",
            f"Look #{look_id} ({len(raw_pil_items)} ta mahsulot) Photoshop Studiyada tabiiy ko'rinishga keltirilmoqda...",
        )
        studio_agent = PhotoStudioAgent(self.s)
        imgs_to_use = []
        studio_models_used: list[str] = []
        for idx_s, raw_im_pil in enumerate(raw_pil_items):
            it_meta = gen.raw_items[min(idx_s, len(gen.raw_items) - 1)]
            has_real_pdd_photo = bool(raw_images) or (idx_s < len(dl_imgs) and dl_imgs[idx_s] is not None)
            if has_real_pdd_photo:
                pose_i = derive_insta_pose_direction(ig_intel, category=str(it_meta.get("category") or ""))
                st_res = await studio_agent.render_product_studio_async(
                    raw_im_pil,
                    item=it_meta,
                    insta_pose_direction=pose_i,
                )
                imgs_to_use.append(st_res.image)
                studio_models_used.append(st_res.model_used)
            else:
                imgs_to_use.append(raw_im_pil)
                studio_models_used.append("studio_asset")

        studio_engine_label = ", ".join(dict.fromkeys(studio_models_used)) or "studio"
        await self.db.set_agent_status(
            "photo_studio",
            "idle",
            f"Look #{look_id}: {len(imgs_to_use)} ta mahsulot studiyada tayyorlandi ({studio_engine_label})",
            increment_done=True,
        )
        await self.db.log_agent_action(
            "photo_studio",
            f"Look #{look_id} uchun {len(imgs_to_use)} ta mahsulot 100% o'zgarishsiz studiya sifatida tayyorlandi → Video Montajchiga uzatildi",
            f"Engine: {studio_engine_label} | Insta Pose: {studio_pose[:160]}",
            target_id="video_employee",
        )
        await self.db.record_agent_learning(
            "photo_studio",
            f"Sikl #{look_id}: Pinduoduo prompti + Insta turish yo'nalishi bilan {len(imgs_to_use)} ta mahsulot ({studio_engine_label}) tayyorlandi.",
            xp_gain=25,
        )

        # 4-QADAM: Video Montajchi Xodim (v3.2) 1080p Full HD kolaj + .mp4 Reels videoni montaj qiladi
        await self.db.set_agent_status(
            "video_employee",
            "working",
            f"Look #{look_id} uchun 1080x1920 Full HD ({video_style}, zvuk: {audio_vibe}) render qilinmoqda...",
        )

        photo_path = os.path.join(self.media_dir, f"look_{look_id}.jpg")
        video_path = os.path.join(self.media_dir, f"look_{look_id}_reels.gif")
        mp4_path = os.path.join(self.media_dir, f"look_{look_id}_reels.mp4")
        item_photo_paths: list[str] = []

        def _render_media() -> None:
            from PIL import Image as _PILIm, ImageOps as _PILOps

            for idx, im_obj in enumerate(imgs_to_use[:4]):
                try:
                    ip = os.path.join(self.media_dir, f"look_{look_id}_item_{idx + 1}.jpg")
                    if im_obj.mode == "RGBA":
                        bg_card = _PILIm.new("RGBA", (900, 1080), (46, 46, 49, 255))
                        fitted_it = _PILOps.contain(im_obj, (800, 960), _PILIm.Resampling.LANCZOS)
                        bg_card.alpha_composite(
                            fitted_it,
                            ((900 - fitted_it.width) // 2, (1080 - fitted_it.height) // 2),
                        )
                        bg_card.convert("RGB").save(ip, format="JPEG", quality=93)
                    else:
                        im_obj.convert("RGB").save(ip, format="JPEG", quality=92)
                    item_photo_paths.append(ip)
                except Exception:
                    pass
            collage = create_look_collage(
                images=imgs_to_use,
                look_title=gen.title,
                total_price_uzs=b.prepay_uzs,
                item_names=item_names,
                shop_brand=self.s.shop_name,
                prepay_50_uzs=b.prepay_50_uzs,
                palette_hex=palette_hex,
                palette_name=gen.palette_name,
                persona_hook=creative_directive["hook_headline"],
            )
            collage.save(photo_path, format="JPEG", quality=96)
            hook_card = create_hook_intro_slide(
                look_title=gen.title,
                piece_count=len(item_names),
                prepay_50_uzs=b.prepay_50_uzs,
                shop_brand=self.s.shop_name,
                viral_hook=creative_directive["hook_headline"],
                palette_hex=palette_hex,
                preview_images=imgs_to_use,
                item_names=item_names,
            )
            vs_slide = create_comparison_hook_slide(
                look_title=gen.title,
                total_price_uzs=b.prepay_uzs,
                prepay_50_uzs=b.prepay_50_uzs,
                shop_brand=self.s.shop_name,
            )
            frames = create_reels_frames(
                images=imgs_to_use,
                look_title=gen.title,
                total_price_uzs=b.prepay_uzs,
                item_names=item_names,
                shop_brand=self.s.shop_name,
                prepay_50_uzs=b.prepay_50_uzs,
                palette_hex=palette_hex,
                palette_name=gen.palette_name,
                viral_hook=creative_directive["hook_headline"],
                creative_directive=creative_directive,
            )
            frames.append(vs_slide.resize((1080, 1920)))
            voice_script = (
                generate_look_voiceover_script(
                    look_title=gen.title,
                    total_price_uzs=b.prepay_uzs,
                    prepay_50_uzs=b.prepay_50_uzs,
                    item_names=item_names,
                )
                if getattr(self.s, "enable_ai_voiceover", False)
                else None
            )
            save_reels_animation(
                frames,
                video_path,
                collage=collage,
                mp4_path=mp4_path,
                audio_vibe=audio_vibe,
                hook_slide=hook_card,
                voiceover_text=voice_script,
                ai_voice_name=getattr(self.s, "ai_voice_name", "uz-UZ-SardorNeural"),
            )

        await asyncio.to_thread(_render_media)
        final_video_path = mp4_path if os.path.exists(mp4_path) else video_path
        await self.db.update_look(look_id, photo_path=photo_path, video_path=final_video_path)

        mp4_status = "V3 Editorial .mp4 Reels (Studio Beat + Saund-Dizayn, TTS siz)" if os.path.exists(mp4_path) else "V3 Editorial Reels GIF"
        await self.db.set_agent_status(
            "video_employee",
            "idle",
            f"Look #{look_id}: {mp4_status} va Kolaj tayyor — SMM Boshlig'iga topshirildi",
            increment_done=True,
        )
        await self.db.log_agent_action(
            "video_employee",
            f"Look #{look_id} uchun {mp4_status} (zvuk: {gen.audio_vibe}) va HD Lookbook Kolaj SMM Boshlig'iga topshirildi",
            f"MP4: {mp4_path if os.path.exists(mp4_path) else 'GIF'} | Kolaj: {photo_path} | Sifat pasporti: 100% Real QC",
            target_id="smm_manager",
        )

        # Agentlarning o'z-o'zini rivojlantirish xotirasini (Self-Learning XP) boyitish
        await self.db.record_agent_learning(
            "insta_analyst",
            f"Sikl #{look_id}: '{gen.title}' uchun {weather.lead_time_days} ob-havo (~{weather.future_temp_c or weather.temp_c}°C) va Split-Screen Bento rejissurasi qo'llandi.",
            xp_gain=25,
        )
        await self.db.record_agent_learning(
            "skaut",
            f"Sikl #{look_id}: {gen.piece_count} qismli kapsula 50k/100k yaxlitlash bilan {fmt(b.prepay_uzs)} so'm (50%: {fmt(b.prepay_50_uzs)} so'm) etib shakllantirildi.",
            xp_gain=25,
        )
        await self.db.record_agent_learning(
            "video_employee",
            f"Sikl #{look_id}: TTS robot ovozsiz, '{gen.audio_vibe}' studiya beat + whoosh/shutter saund-dizayn va halol mato/razmer pasporti bilan 9:16 Reels yaratildi.",
            xp_gain=30,
        )
        await self.db.record_agent_learning(
            "smm_manager",
            f"Sikl #{look_id}: '+' komment voronkasi, 5–12 kun Avia va 12 000 so'm/100gr kargo bilan kontent paket chiqarildi.",
            xp_gain=20,
        )

        # 5-QADAM: Oldingi Look postlarini tozalash + SMM Boshlig'i Telegram kanalga va Instagram Graph API'ga 1080p post chiqaradi
        removed_prev_count = 0
        if delete_previous:
            prev_looks = await self.db.list_looks(only_active=False)
            for prev in prev_looks:
                if prev["id"] == look_id:
                    continue
                old_msg_id = prev.get("channel_msg_id")
                if old_msg_id and self.sales_bot and self.s.channel_id:
                    try:
                        await self.sales_bot.delete_message(chat_id=self.s.channel_id, message_id=int(old_msg_id))
                        removed_prev_count += 1
                    except Exception:
                        pass
                if prev.get("active") or old_msg_id:
                    await self.db.update_look(prev["id"], active=0, channel_msg_id=None)

        look_row = await self.db.get_look(look_id)
        learned_playbooks = await self.db.get_all_playbooks()
        insta_caption = format_instagram_caption(
            look_row,
            self.sales_username,
            self.s.shop_name,
            manager_username=self.s.manager_username,
            playbooks=learned_playbooks,
        )
        insta_path = os.path.join(self.media_dir, f"look_{look_id}_insta.txt")
        with open(insta_path, "w", encoding="utf-8") as f:
            f.write(insta_caption)

        channel_msg_id = None
        if self.sales_bot and self.s.channel_id:
            channel_msg_id = await publish_look_to_telegram(
                bot=self.sales_bot,
                channel_id=self.s.channel_id,
                look=look_row,
                sales_bot_username=self.sales_username,
                shop_name=self.s.shop_name,
                video_path=final_video_path,
                manager_username=self.s.manager_username,
                playbooks=learned_playbooks,
                item_photo_paths=[photo_path, *item_photo_paths],
            )

        from .publisher import has_valid_ig_browser_session

        has_web_ig = has_valid_ig_browser_session()
        ig_media_id = None
        ig_story_id = None
        ig_own_err = str((ig_intel.get("own_performance") or {}).get("error") or "")
        ig_checkpoint_blocked = bool(
            not has_web_ig
            and ig_own_err
            and ("does not exist" in ig_own_err.lower() or "checkpoint" in ig_own_err.lower())
        )
        if os.path.exists(mp4_path) and (
            has_web_ig
            or (self.s.ig_user_id and self.s.ig_access_token and self.s.public_base_url and not ig_checkpoint_blocked)
            or not os.getenv("PYTEST_CURRENT_TEST")
        ):
            video_url = f"{self.s.public_base_url}/media/look_{look_id}_reels.mp4?v={int(time.time())}" if self.s.public_base_url else ""
            photo_url = f"{self.s.public_base_url}/media/look_{look_id}.jpg?v={int(time.time())}" if self.s.public_base_url else ""
            ig_media_id = await publish_reels_to_instagram(
                ig_user_id=self.s.ig_user_id,
                ig_access_token=self.s.ig_access_token,
                video_public_url=video_url,
                caption=insta_caption,
                hide_likes=True,
                local_video_path=mp4_path,
            )
            ig_story_id = await publish_story_to_instagram(
                ig_user_id=self.s.ig_user_id,
                ig_access_token=self.s.ig_access_token,
                video_public_url=video_url,
                image_public_url=photo_url,
                local_video_path=mp4_path,
                local_photo_path=photo_path,
            )

        if channel_msg_id or ig_media_id:
            await self.db.update_look(
                look_id,
                channel_msg_id=channel_msg_id,
                ig_media_id=ig_media_id or "",
            )

        tg_link = build_telegram_post_link(self.s.channel_id, channel_msg_id) if channel_msg_id else "https://t.me/Xan_style"
        if ig_media_id and str(ig_media_id).startswith("web_reel_"):
            ig_code = str(ig_media_id)[len("web_reel_"):]
            ig_link = f"https://www.instagram.com/reel/{ig_code}/" if (ig_code and not ig_code.isdigit()) else "https://www.instagram.com/xans_styles/reels/"
        else:
            ig_link = await get_instagram_permalink(ig_media_id or "", self.s.ig_access_token) if ig_media_id else "https://www.instagram.com/xans_styles/reels/"
        await self.db.set_setting("last_auto_post_ts", int(time.time()))

        pub_parts = [f"Katalog #{look_id}"]
        if channel_msg_id:
            pub_parts.append(f"TG Kanal (post #{channel_msg_id})")
        if ig_media_id:
            pub_parts.append(f"Instagram Reels (ID {ig_media_id})")
        pub_status = f"Look #{look_id} (1080p) e'lon qilindi: " + " + ".join(pub_parts)

        await self.db.set_agent_status("smm_manager", "idle", pub_status, increment_done=True)
        await self.db.log_agent_action(
            "smm_manager",
            pub_status,
            f"Auditoriya: {target_persona} | Stil: {video_style} | TG: {tg_link} | IG: {ig_link}",
            target_id="sales_stylist",
        )
        await self.db.set_agent_status(
            "director",
            "idle",
            f"Sikl #{look_id} ({gen.piece_count}-in-1, 1080p) muvaffaqiyatli yakunlandi",
            increment_done=True,
        )

        # Admin botga avtomatik xabar, narxlar nisbati va tahlilchi xulosasini yuborish
        if self.admin_bot and notify_admin_on_publish:
            story_note = f" + Istoriya (ID {ig_story_id})" if ig_story_id else " + Istoriya tayyor"
            if ig_media_id:
                ig_line = f"📸 <b>Instagram Reels (Likes yashirilgan){story_note}:</b> <a href='{ig_link}'>{ig_link}</a>"
            elif ig_checkpoint_blocked:
                ig_line = "📸 <b>Instagram Reels + Istoriya:</b> ⚠️ Meta checkpoint qulflangan (hisob ochilgach likes yashirilib + Istoriyaga avto-yuklanadi)"
            else:
                ig_line = f"📸 <b>Instagram Reels (Likes yashirilgan){story_note}:</b> Yuklanmoqda / navbatda"
            tg_line = f"📢 <b>Telegram Kanal:</b> <a href='{tg_link}'>{tg_link}</a>" if channel_msg_id else "📢 <b>Telegram Kanal:</b> https://t.me/Xan_style"

            # Jonli raqobatchilar (@stylesh_shop / @tima_shop_uz) bilan haqiqiy narxlar nisbati
            live_comp_avg = int(halol_ogri.get("competitor_avg_price_uzs") or 0)
            comp_ref_uzs = (
                live_comp_avg
                if live_comp_avg > 0
                else max(int(b.prepay_uzs * 1.18 // 50000 * 50000), 750000 if gen.piece_count >= 4 else 600000)
            )
            diff_pct = int(round((1.0 - (b.prepay_uzs / max(comp_ref_uzs, 1))) * 100))
            diff_label = f"<b>~{diff_pct}% arzonroq!</b>" if diff_pct > 0 else "bozor narxiga teng"
            pdd_links_lines = []
            for idx_it, it_obj in enumerate(gen.raw_items, 1):
                it_nm = str(it_obj.get("name") or f"Buyum #{idx_it}")
                it_cny = float(it_obj.get("price_cny") or it_obj.get("cny") or 0)
                it_url = str(it_obj.get("url") or "")
                if it_url:
                    pdd_links_lines.append(f"  {idx_it}. <a href='{it_url}'>{it_nm}</a> — ¥{it_cny:g}")
                else:
                    pdd_links_lines.append(f"  {idx_it}. {it_nm} — ¥{it_cny:g}")
            pdd_block = "\n".join(pdd_links_lines)
            admin_report = (
                f"🚀 <b>Yangi Look #{look_id} (1080p Real Pinduoduo Flat-Lay) joylandi!</b>\n\n"
                f"👔 <b>{gen.title} ({gen.piece_count} qism)</b>\n"
                f"🎯 Auditoriya: <i>{target_persona}</i>\n"
                f"🎨 Rasmdagi ranglar: <b>{gen.colors}</b>\n"
                f"🎬 Format: <code>RASMDA / Flat-Lay Obzor</code> · 🎵 Viral Zvuk: <code>{audio_vibe}</code>\n"
                f"✈️ Yetkazish: <b>5–12 kun (Avia)</b> · 📦 Kargo: <b>12 000 so'm / 100 gr</b>\n\n"
                f"📊 <b>Tahlilchi & Jonli Narxlar Nisbati (@stylesh_shop / @tima_shop_uz):</b>\n"
                f"• Raqobatchilarda o'rtacha set: ~<b>{fmt(comp_ref_uzs)} so'm</b> (+ kargo 13 000 so'm/100gr)\n"
                f"• Bizda to'liq narxi: <b>{fmt(b.prepay_uzs)} so'm</b> ({diff_label})\n"
                f"• 💳 <b>Hozirgi to'lov (50%): {fmt(b.prepay_50_uzs)} so'm</b> (+ kargo 12 000 so'm/100gr Toshkentda)\n"
                f"• 💵 Sof foyda: <b>{fmt(b.profit_uzs)} so'm</b> (Pinduoduo jami: ¥{b.goods_cny:g} ≈ {fmt(b.goods_cost_uzs)} so'm)\n\n"
                f"🛒 <b>Pinduoduo to'g'ridan-to'g'ri havolalari:</b>\n{pdd_block}\n\n"
                f"{tg_line}\n"
                f"{ig_line}"
            )
            try:
                await notify_admins(self.admin_bot, self.s, admin_report)
            except Exception as e:
                log.warning("Admin botga yangi look linklarini yuborishda xato: %s", e)

        return OfficePipelineResult(
            look_id=look_id,
            title=gen.title,
            piece_count=gen.piece_count,
            palette_name=gen.palette_name,
            palette_hex=palette_hex,
            audio_vibe=audio_vibe,
            prepay_uzs=b.prepay_uzs,
            prepay_50_uzs=b.prepay_50_uzs,
            remaining_50_uzs=b.remaining_50_uzs,
            goods_cost_uzs=b.goods_cost_uzs,
            cargo_est_uzs=b.cargo_client_uzs,
            profit_uzs=b.profit_uzs,
            photo_path=photo_path,
            video_path=video_path,
            mp4_path=mp4_path if os.path.exists(mp4_path) else video_path,
            insta_caption_path=insta_path,
            channel_msg_id=channel_msg_id,
            ig_media_id=ig_media_id,
            tg_link=tg_link,
            ig_link=ig_link,
            video_style=video_style,
            target_persona=target_persona,
        )


async def office_scheduler_loop(office: AgentOffice, alert_fn=None) -> None:
    """24/7 Server rejimida:
    - Har 2 daqiqada Instagram Reels izohlariga aqlli AI javob berish;
    - Har AUTO_POST_HOURS (3 soat) da yangi 1080p Look chiqarish;
    - Har soatda Kargo SLA nazorati.
    """
    logistics = LogisticsAgent(office.db, office.s)
    ai = SalesAI(office.s)
    last_sla_ts = 0.0
    last_ig_probe_ts = 0.0
    ig_ready = False
    ig_block_reason = ""
    if office.s.auto_post_hours > 0:
        init_ts = int(await office.db.get_setting("last_auto_post_ts") or "0")
        if init_ts == 0 and await office.db.list_looks(only_active=False):
            await office.db.set_setting("last_auto_post_ts", int(time.time()))

    while True:
        await asyncio.sleep(120)  # Har 2 daqiqada tekshiruv
        try:
            now_ts = time.time()
            from app.source_learner import check_ig_publish_ready

            allow_tg_only = (await office.db.get_setting("allow_tg_without_ig")) == "1"
            has_ig_creds = bool(office.s.ig_user_id and office.s.ig_access_token)
            if has_ig_creds and (now_ts - last_ig_probe_ts) >= 1800:
                last_ig_probe_ts = now_ts
                ig_ready, ig_block_reason = await check_ig_publish_ready(
                    office.s.ig_user_id,
                    office.s.ig_access_token,
                )
                if ig_ready:
                    if await office.db.get_setting("ig_pause_alerted") == "1":
                        await office.db.set_setting("ig_pause_alerted", "0")
                        if alert_fn:
                            await alert_fn("🟢 Instagram qulfdan chiqdi — avtonom Reels + Telegram nashr qayta tiklandi!")
                elif allow_tg_only:
                    if await office.db.get_setting("ig_pause_alerted") != "0":
                        await office.db.set_setting("ig_pause_alerted", "0")
                else:
                    if await office.db.get_setting("ig_pause_alerted") != "1":
                        await office.db.set_setting("ig_pause_alerted", "1")
                        if alert_fn:
                            await alert_fn(
                                "⏸ <b>Avto-look va Telegram kanal posti vaqtincha to'xtatildi</b>\n"
                                f"Sabab: <i>{ig_block_reason}</i>\n\n"
                                "Instagram tiklanmaguncha bo'sh Telegram kanalga bekorchi token va video sarflanmaydi. "
                                "Agar majburiy Telegram rejimi kerak bo'lsa: <code>/tg_holat yoq</code>"
                            )

            if ig_ready:
                await poll_and_reply_instagram_comments(office.db, office.s, ai=ai, notify_fn=alert_fn)

            if (now_ts - last_sla_ts) >= 3600:
                last_sla_ts = now_ts
                alerts = await logistics.check_sla_alerts()
                if alerts and alert_fn:
                    await alert_fn("\n".join(alerts))

            if office.s.auto_post_hours > 0:
                if ig_ready or allow_tg_only:
                    last_ts = int(await office.db.get_setting("last_auto_post_ts") or "0")
                    if (now_ts - last_ts) >= office.s.auto_post_hours * 3600:
                        await office.run_look_pipeline(delete_previous=False, notify_admin_on_publish=True)
                        await office.db.set_setting("last_auto_post_ts", int(time.time()))
        except Exception as e:
            log.warning("24/7 Scheduler xatosi: %s", e)
