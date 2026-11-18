# XAN SHOP — AI Agentlar va Asosiy Ishlash Qonunlari (GEMINI.md)

Ushbu fayl loyiha bo'yicha eng yuqori ustuvorlikdagi qoidalar to'plamidir. Har bir qadamda quyidagi tamoyillarga 100% amal qilinishi shart:

## 1. Yuzaki Tahlil Taqiqlanadi (Chuqur Analizer Tamoyili)
- Foydalanuvchi Telegram botga yoki chatga **Instagram profil, Reels, YouTube yoki Telegram kanal linkini** yuborganda, faqatgina kanal obunachisi yoki umumiy 2 qator holatini aytib qo'yish **QAT'IYAN MAN ETILADI**.
- Tizim (`app/source_learner.py`) kanal ichidagi **har bir post va videoni birma-bir** yuklab olib tahlil qilishi shart:
  1. **Videolar:** Kadrlar ketma-ketligi (`0-4s` hook / `RASMDA:` flat-lay kolaj -> `4-5s` beat-drop o'tish -> `5-11s` kiyilgan ko'rinish yoki mato/zamok/furnitura yaqin plan ASMR isboti).
  2. **Zvuk va Audio:** Qanday musiqa (slowed vocal beat-drop, rep beat yoki real ASMR mato ovozi) ishlatilgani, robot TTS ovoz yo'qligi.
  3. **Post va Opisaniya qolipi:** Narx qanday yozilgani (`-| Narxi: ...` yoki `- 850.000 so'm ...`), fotoalbom (karusel: umumiy flat-lay + alohida buyum rasmlari) va video uyg'unligi.
- Agar Instagram Graph API yopiq bo'lsa, profilning o'zbekcha Telegram ko'zgusi (`@_tima_shop` -> `@tima_shop_uz`, `@stylesh.uz` -> `@stylesh_shop`) avtomatik topilib, uning ichidagi haqiqiy videolar va postlar tahlil qilinadi. Hech qachon mavzudan tashqari ("kosmetika, parfyumeriya") taxminlar yozilmasin.

## 2. Agentlar O'rganganini O'zi Amalda Qo'llashi Shart (Avtonom SMM va Video Jamoa)
- Foydalanuvchi har safar *"postni bunday yoz, videoni bunday qil"* deb o'rgatib o'tirmaydi:
  - **Tahlilchi (`insta_analyst` / `source_learner`)** o'rgangan shablon va video formulasini `learned_playbooks` bazasiga yozadi.
  - **SMM Boshlig'i (`smm_manager` / `app/publisher.py`)** post matnini va formatini (masalan `@stylesh_shop` chiziqli-punktli qolipi yoki `@_tima_shop` minimal qolipi + Fotoalbom karusel) o'sha playbook'dan olib avtomatik yuritadi.
  - **Video Montajchi (`video_employee` / `remotion_studio` / `app/media.py`)** o'rganilgan kadr tempi, flat-lay obzor va haqiqiy musiqa bilan 1080x1920 Reels chiqaradi.
  - **Skaut (`skaut` / `app/sourcing.py`)** faqat Pinduoduo (`yangkeduo.com`) orqali mavsumga va auditoriyaga (Diplomatiya/Yuridika Old Money, Cleanfit, Oversize) mos, sotiladigan salmoqli kapsulalarni (50% oldindan to'lov + kargo Toshkentda) yig'adi.

## 3. Foydalanuvchi Bilan Ishlash Tartibi
- O'zboshimchalik bilan foydalanuvchi so'ramagan ortiqcha narsalarni qo'shib tashlama.
- Har bir o'zgarishni faqat `pytest` da emas, real ma'lumot (`data/shop.db`, real video/kanal tahlili) ustida tekshirib ko'rsat.
