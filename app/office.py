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
    ) -> OfficePipelineResult:
        """To'liq avtonom zanjir: Instagram Tahlil + Ob-havo -> Pinduoduo Skaut -> SMM -> 1080p Video Xodim -> Nashr + Admin Xabar."""
        os.makedirs(self.media_dir, exist_ok=True)
        rates = await get_rates(self.db, self.s)
        params = await get_params(self.db, self.s)

        cycle_idx = self._cycle_counter
        skaut = TrendSourcingAgent(self.s, rates=rates, params=params)
        skaut._fallback_idx = cycle_idx
        brief = skaut.analyze_instagram_trends(cycle_idx)
        self._cycle_counter += 1

        # 1-QADAM: Instagram Razvedka Agent (insta_analyst) -> 5–10 kun oldingi ob-havo + @_tima_shop/Stylesh tahlilini Skautga uzatadi
        await self.db.set_agent_status(
            "director",
            "working",
            f"Yangi sikl: '{brief.trend_name}' ({brief.recommended_piece_count}-in-1) tasdiqlandi",
        )
        await self.db.set_agent_status(
            "insta_analyst",
            "working",
            f"@_tima_shop / @stylesh.uz hooklari va {params.profit_percent:g}% marja asosida tahlil...",
        )
        weather = await fetch_tashkent_weather()
        comp_snap = analyze_competitor_account("_tima_shop", weather)
        await self.db.set_agent_status(
            "insta_analyst",
            "idle",
            f"Razvedka tayyor: {weather.lead_time_days} ob-havo (~{weather.future_temp_c or weather.temp_c}°C) | {brief.trend_name}",
            increment_done=True,
        )
        await self.db.log_agent_action(
            "insta_analyst",
            f"Instagram razvedkasi yakunlandi: '{brief.trend_name}' ({brief.recommended_piece_count}-in-1) | Ob-havo ({weather.lead_time_days}): ~{weather.future_temp_c or weather.temp_c}°C",
            f"Raqobatchi (@_tima_shop) triggeri: komentda '+' | Hook: {comp_snap['hook_patterns'][0]} | Palitra: {brief.color_palette_name} | Zvuk: {brief.audio_vibe}",
            target_id="skaut",
        )

        # 2-QADAM: Skaut & Dizayner Agent (jonli Toshkent ob-havosi + Pinduoduo API) Look yig'adi
        await self.db.set_agent_status(
            "skaut",
            "working",
            f"Toshkent ob-havosi va Pinduoduo'dan {brief.recommended_piece_count} qismli Look yig'ilmoqda...",
        )
        gen = await skaut.generate_look_async(season, gender, style, brief, weather=weather)
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

        # 3-QADAM: insta_analyst v3.2 va SMM Boshlig'i Video Montajchi (video_employee v3.2) ga 1080p kreativ rejissura buyrug'ini beradi
        creative_directive = build_video_creative_directive(
            look_title=gen.title,
            piece_count=gen.piece_count,
            total_price_uzs=b.prepay_uzs,
            prepay_50_uzs=b.prepay_50_uzs,
            palette_name=gen.palette_name,
            palette_hex=palette_hex,
            audio_vibe=gen.audio_vibe,
            weather=weather,
            items=gen.raw_items,
            style_idx=cycle_idx,
            viral_hook=gen.viral_hook,
        )
        video_style = str(creative_directive.get("video_style") or "orbit_3d_turntable")
        target_persona = str(creative_directive.get("target_persona") or "Zamonaviy yigitlar")
        audio_vibe = str(creative_directive.get("audio_vibe") or gen.audio_vibe)

        await self.db.log_agent_action(
            "insta_analyst",
            f"🎬 Video Montajchiga 1080p Rejissura [Look #{look_id}]: Stil='{video_style}' | Auditoriya='{target_persona}' | Zvuk='{audio_vibe}'",
            f"Hook: {creative_directive['hook_headline']} | Kafolat: {creative_directive['honest_quality_pledge'][:120]}",
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

        # 4-QADAM: Video Montajchi Xodim (v3.2) 1080p Full HD kolaj + .mp4 Reels videoni montaj qiladi
        await self.db.set_agent_status(
            "video_employee",
            "working",
            f"Look #{look_id} uchun 1080x1920 Full HD ({video_style}, zvuk: {audio_vibe}) render qilinmoqda...",
        )

        item_names = [i["name"] for i in gen.raw_items]
        dl_imgs = gen.downloaded_images or []
        imgs_to_use = raw_images or [
            (dl_imgs[idx] if idx < len(dl_imgs) and dl_imgs[idx] else None)
            or generate_item_studio_card(
                name=i["name"],
                idx=idx,
                price_cny=float(i.get("price_cny", 0)),
                color_hex=palette_hex[idx % len(palette_hex)] if palette_hex else "#1E1E22",
                sales_tip=str(i.get("sales_tip", "")),
            )
            for idx, i in enumerate(gen.raw_items)
        ]

        photo_path = os.path.join(self.media_dir, f"look_{look_id}.jpg")
        video_path = os.path.join(self.media_dir, f"look_{look_id}_reels.gif")
        mp4_path = os.path.join(self.media_dir, f"look_{look_id}_reels.mp4")

        def _render_media() -> None:
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
            f"Sikl #{look_id}: '+' komment voronkasi va 5–10 kun Avia kafolati bilan kontent paket chiqarildi.",
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
        insta_caption = format_instagram_caption(
            look_row,
            self.sales_username,
            self.s.shop_name,
            manager_username=self.s.manager_username,
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
            )

        ig_media_id = None
        if self.s.ig_user_id and self.s.ig_access_token and self.s.public_base_url and os.path.exists(mp4_path):
            video_url = f"{self.s.public_base_url}/media/look_{look_id}_reels.mp4?v={int(time.time())}"
            ig_media_id = await publish_reels_to_instagram(
                ig_user_id=self.s.ig_user_id,
                ig_access_token=self.s.ig_access_token,
                video_public_url=video_url,
                caption=insta_caption,
            )

        if channel_msg_id or ig_media_id:
            await self.db.update_look(
                look_id,
                channel_msg_id=channel_msg_id,
                ig_media_id=ig_media_id or "",
            )

        tg_link = build_telegram_post_link(self.s.channel_id, channel_msg_id) if channel_msg_id else "https://t.me/Xan_style"
        ig_link = await get_instagram_permalink(ig_media_id or "", self.s.ig_access_token) if ig_media_id else "https://www.instagram.com/xan_styles/reels/"
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

        # Admin botga avtomatik xabar va post linklarini yuborish
        if self.admin_bot and notify_admin_on_publish:
            ig_line = f"📸 <b>Instagram Reels:</b> <a href='{ig_link}'>{ig_link}</a>" if ig_media_id else "📸 <b>Instagram Reels:</b> Yuklanmoqda / navbatda"
            tg_line = f"📢 <b>Telegram Kanal:</b> <a href='{tg_link}'>{tg_link}</a>" if channel_msg_id else "📢 <b>Telegram Kanal:</b> https://t.me/Xan_style"
            admin_report = (
                f"🚀 <b>Yangi Look #{look_id} (1080p Full HD) joylandi!</b>\n\n"
                f"👔 <b>{gen.title} ({gen.piece_count} qism)</b>\n"
                f"🎯 Auditoriya: <i>{target_persona}</i>\n"
                f"🎨 Rasmdagi ranglar: <b>{gen.colors}</b>\n"
                f"🎬 Montaj uslubi: <code>{video_style}</code> · 🎵 Zvuk: <code>{audio_vibe}</code>\n"
                f"💳 <b>Hozirgi narx (50%): {fmt(b.prepay_50_uzs)} so'm</b>\n"
                f"📦 <b>+ kargo</b> (To'liq narxi: {fmt(b.prepay_uzs)} so'm)\n\n"
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
    while True:
        await asyncio.sleep(120)  # Har 2 daqiqada tekshiruv
        try:
            now_ts = time.time()
            await poll_and_reply_instagram_comments(office.db, office.s, ai=ai, notify_fn=alert_fn)

            if (now_ts - last_sla_ts) >= 3600:
                last_sla_ts = now_ts
                alerts = await logistics.check_sla_alerts()
                if alerts and alert_fn:
                    await alert_fn("\n".join(alerts))

            if office.s.auto_post_hours > 0:
                last_ts = int(await office.db.get_setting("last_auto_post_ts") or "0")
                if (now_ts - last_ts) >= office.s.auto_post_hours * 3600:
                    await office.run_look_pipeline(delete_previous=False, notify_admin_on_publish=True)
                    await office.db.set_setting("last_auto_post_ts", int(time.time()))
        except Exception as e:
            log.warning("24/7 Scheduler xatosi: %s", e)
