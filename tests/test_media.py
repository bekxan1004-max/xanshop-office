from PIL import Image
from app.media import (
    create_look_collage,
    create_reels_frames,
    create_comparison_hook_slide,
    generate_look_voiceover_script,
)


def test_create_look_collage():
    # 3 ta test rasm
    img1 = Image.new("RGBA", (300, 300), (255, 100, 100, 255))
    img2 = Image.new("RGBA", (300, 300), (100, 255, 100, 255))
    img3 = Image.new("RGBA", (300, 300), (100, 100, 255, 255))

    collage = create_look_collage(
        images=[img1, img2, img3],
        look_title="Streetwear Autumn Look",
        total_price_uzs=650000,
        item_names=["Kurtka", "Shim", "Sneakers"],
        shop_brand="XAN SHOP",
    )

    assert collage.size == (1080, 1350)
    assert collage.mode == "RGB"


def test_create_reels_frames():
    img1 = Image.new("RGBA", (300, 300), (200, 200, 200, 255))
    frames = create_reels_frames(
        images=[img1],
        look_title="Minimal Casual",
        total_price_uzs=450000,
        item_names=["Xudi"],
        shop_brand="XAN SHOP",
    )
    assert len(frames) == 1
    assert frames[0].size == (1080, 1920)


def test_create_comparison_hook_slide_and_voiceover_script():
    slide = create_comparison_hook_slide(
        look_title="Old Money Vintage Look",
        total_price_uzs=499000,
        prepay_50_uzs=249500,
    )
    assert slide.size == (1080, 1920)
    assert slide.mode == "RGB"

    script = generate_look_voiceover_script(
        look_title="Old Money Vintage Look",
        total_price_uzs=499000,
        prepay_50_uzs=249500,
        item_names=["Palto", "Vodolazka", "Klassik shim"],
    )
    assert "50 foiz" in script
    assert "249 500" in script
    assert "Toshkentga kelganda" in script

