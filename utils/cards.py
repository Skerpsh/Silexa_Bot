import asyncio
import io
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from PIL import Image, ImageDraw, ImageFont

FONT_REGULAR_PATHS = [
    "/usr/share/fonts/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/Adwaita/AdwaitaSans-Regular.ttf",
    "/usr/share/fonts/TTF/JetBrainsMonoNerdFontPropo-Light.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

FONT_BOLD_PATHS = [
    "/usr/share/fonts/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/Adwaita/AdwaitaMono-Bold.ttf",
    "/usr/share/fonts/TTF/JetBrainsMonoNerdFontPropo-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]

FONT_ITALIC_PATHS = [
    "/usr/share/fonts/liberation/LiberationSans-Italic.ttf",
    "/usr/share/fonts/Adwaita/AdwaitaSans-Italic.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
]

# Base Discord Modern Dark Palette (RGB)
BG_OUTER = (30, 31, 34)        # #1E1F22
BG_CARD = (43, 45, 49)         # #2B2D31
BG_ELEVATED = (49, 51, 56)     # #313338
BORDER_SUBTLE = (63, 65, 71)   # #3F4147
BLURPLE = (88, 101, 242)       # #5865F2
BLURPLE_DARK = (71, 82, 196)   # #4752C4
GOLD = (240, 178, 50)          # #F0B232
GREEN = (35, 165, 90)          # #23A55A
TEXT_WHITE = (242, 243, 245)   # #F2F3F5
TEXT_MUTED = (148, 155, 164)   # #949BA4
TEXT_SUB = (181, 186, 193)     # #B5BAC1

PROFILE_THEMES: dict[str, dict[str, tuple[int, int, int]]] = {
    "default": {
        "bg_outer": (30, 31, 34),
        "bg_card": (43, 45, 49),
        "bg_elevated": (49, 51, 56),
        "border": (63, 65, 71),
        "banner_base": (71, 82, 196),
        "banner_accent": (88, 101, 242),
        "primary": (88, 101, 242),
        "secondary": (240, 178, 50),
    },
    "cyberpunk": {
        "bg_outer": (14, 15, 24),
        "bg_card": (22, 24, 38),
        "bg_elevated": (30, 33, 52),
        "border": (0, 240, 255),
        "banner_base": (140, 20, 90),
        "banner_accent": (255, 42, 133),
        "primary": (0, 240, 255),
        "secondary": (255, 42, 133),
    },
    "crimson": {
        "bg_outer": (20, 13, 15),
        "bg_card": (34, 22, 25),
        "bg_elevated": (46, 30, 34),
        "border": (140, 40, 50),
        "banner_base": (135, 22, 34),
        "banner_accent": (230, 57, 70),
        "primary": (230, 57, 70),
        "secondary": (255, 183, 3),
    },
    "emerald": {
        "bg_outer": (13, 22, 18),
        "bg_card": (20, 33, 28),
        "bg_elevated": (28, 45, 38),
        "border": (16, 185, 129),
        "banner_base": (6, 95, 70),
        "banner_accent": (16, 185, 129),
        "primary": (52, 211, 153),
        "secondary": (240, 178, 50),
    },
    "royal": {
        "bg_outer": (22, 19, 14),
        "bg_card": (35, 30, 22),
        "bg_elevated": (48, 41, 30),
        "border": (245, 158, 11),
        "banner_base": (146, 92, 14),
        "banner_accent": (245, 158, 11),
        "primary": (251, 191, 36),
        "secondary": (254, 240, 138),
    },
}


def _load_font(paths: list[str], size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for p in paths:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size=size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _make_circular_avatar(
    avatar_bytes: bytes | None,
    size: int,
    fallback_letter: str = "S",
    fallback_bg: tuple[int, int, int] = BLURPLE,
) -> Image.Image:
    """Create a crisp circular RGBA avatar using 2x supersampling."""
    ss = size * 2
    if avatar_bytes:
        try:
            raw = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
            raw = raw.resize((ss, ss), Image.Resampling.LANCZOS)
        except Exception:
            raw = None
    else:
        raw = None

    if raw is None:
        raw = Image.new("RGBA", (ss, ss), fallback_bg + (255,))
        draw = ImageDraw.Draw(raw)
        font = _load_font(FONT_BOLD_PATHS, int(ss * 0.48))
        letter = (fallback_letter or "S")[0].upper()
        bbox = draw.textbbox((0, 0), letter, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(((ss - tw) / 2, (ss - th) / 2 - bbox[1]), letter, font=font, fill=TEXT_WHITE)

    mask = Image.new("L", (ss, ss), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((0, 0, ss - 1, ss - 1), fill=255)

    out = Image.new("RGBA", (ss, ss), (0, 0, 0, 0))
    out.paste(raw, (0, 0), mask)
    return out.resize((size, size), Image.Resampling.LANCZOS)


def _format_voice_time(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    rem = minutes % 60
    return f"{hours}h {rem}m" if rem else f"{hours}h"


def _render_profile_card_sync(
    display_name: str,
    username: str,
    avatar_bytes: bytes | None,
    level: int,
    xp_current: int,
    xp_needed: int,
    rank: int,
    coins: int,
    messages_sent: int,
    voice_minutes: int,
    lfg_count: int,
    hof_count: int,
    daily_streak: int,
    bio: str,
    badges: list[dict[str, str]],
    contracts_done: int,
    contracts_total: int,
    theme: str = "default",
    equipped_title: str = "",
    xp_boost_active: bool = False,
) -> io.BytesIO:
    pal = PROFILE_THEMES.get(theme, PROFILE_THEMES["default"])
    width, height = 920, 450
    img = Image.new("RGBA", (width, height), pal["bg_outer"] + (255,))
    draw = ImageDraw.Draw(img)

    # Outer main card container
    draw.rounded_rectangle(
        (16, 16, width - 16, height - 16),
        radius=20,
        fill=pal["bg_card"],
        outline=pal["border"],
        width=2,
    )

    # Top accent banner strip inside card
    draw.rounded_rectangle(
        (18, 18, width - 18, 108),
        radius=18,
        fill=pal["banner_base"],
    )
    draw.rectangle((18, 80, width - 18, 108), fill=pal["banner_base"])
    draw.polygon(
        [(width - 340, 18), (width - 18, 18), (width - 18, 108), (width - 240, 108)],
        fill=pal["banner_accent"],
    )

    # Fonts
    font_name = _load_font(FONT_BOLD_PATHS, 30)
    font_sub = _load_font(FONT_REGULAR_PATHS, 17)
    font_bio = _load_font(FONT_ITALIC_PATHS, 16)
    font_pill = _load_font(FONT_BOLD_PATHS, 16)
    font_stat_val = _load_font(FONT_BOLD_PATHS, 24)
    font_stat_lbl = _load_font(FONT_BOLD_PATHS, 13)
    font_badge = _load_font(FONT_BOLD_PATHS, 13)

    # Rank & Level Pills in top-right of banner
    rank_text = f"RANK #{rank}"
    lvl_text = f"LEVEL {level}"

    lvl_bbox = draw.textbbox((0, 0), lvl_text, font=font_pill)
    lvl_w = (lvl_bbox[2] - lvl_bbox[0]) + 32
    lvl_x2 = width - 38
    lvl_x1 = lvl_x2 - lvl_w
    draw.rounded_rectangle(
        (lvl_x1, 38, lvl_x2, 76),
        radius=19,
        fill=pal["bg_outer"],
        outline=pal["secondary"],
        width=2,
    )
    draw.text((lvl_x1 + 16, 48), lvl_text, font=font_pill, fill=pal["secondary"])

    rnk_bbox = draw.textbbox((0, 0), rank_text, font=font_pill)
    rnk_w = (rnk_bbox[2] - rnk_bbox[0]) + 32
    rnk_x2 = lvl_x1 - 12
    rnk_x1 = rnk_x2 - rnk_w
    draw.rounded_rectangle(
        (rnk_x1, 38, rnk_x2, 76),
        radius=19,
        fill=pal["bg_outer"],
        outline=pal["border"],
        width=2,
    )
    draw.text((rnk_x1 + 16, 48), rank_text, font=font_pill, fill=TEXT_WHITE)

    # Avatar with cut-out ring
    av_size = 124
    av_x, av_y = 44, 46
    draw.ellipse(
        (av_x - 6, av_y - 6, av_x + av_size + 6, av_y + av_size + 6),
        fill=pal["bg_card"],
        outline=pal["primary"],
        width=3,
    )
    avatar_img = _make_circular_avatar(avatar_bytes, av_size, display_name, pal["primary"])
    img.paste(avatar_img, (av_x, av_y), avatar_img)

    # User Identity, Title Tag & Bio
    name_x = av_x + av_size + 24
    clean_name = display_name[:20]
    draw.text((name_x, 116), clean_name, font=font_name, fill=TEXT_WHITE)

    name_bbox = draw.textbbox((name_x, 116), clean_name, font=font_name)
    tag_x = name_bbox[2] + 12
    tag_str = f"@{username[:18]}"
    draw.text((tag_x, 125), tag_str, font=font_sub, fill=TEXT_MUTED)

    if equipped_title:
        tag_bbox = draw.textbbox((tag_x, 125), tag_str, font=font_sub)
        title_x = tag_bbox[2] + 14
        t_label = f"★ {equipped_title.upper()[:20]}"
        tb = draw.textbbox((0, 0), t_label, font=font_badge)
        tw = (tb[2] - tb[0]) + 20
        if title_x + tw < width - 36:
            draw.rounded_rectangle(
                (title_x, 120, title_x + tw, 146),
                radius=8,
                fill=pal["bg_outer"],
                outline=pal["secondary"],
                width=1,
            )
            draw.text((title_x + 10, 126), t_label, font=font_badge, fill=pal["secondary"])

    clean_bio = (bio or "Server Member & Adventurer").strip()
    if len(clean_bio) > 70:
        clean_bio = clean_bio[:67] + "..."
    draw.text((name_x, 154), f'"{clean_bio}"', font=font_bio, fill=TEXT_SUB)

    # XP Progress Bar section
    bar_x1, bar_y1 = 44, 198
    bar_x2, bar_y2 = width - 44, 224
    bar_w = bar_x2 - bar_x1

    pct = min(1.0, max(0.0, xp_current / max(1, xp_needed)))
    boost_tag = "  •  [2X XP BOOST ACTIVE]" if xp_boost_active else ""
    xp_label = f"XP PROGRESS: {xp_current:,} / {xp_needed:,} XP ({int(pct * 100)}%){boost_tag}"
    draw.text((bar_x1, bar_y1 - 20), xp_label, font=font_stat_lbl, fill=pal["primary"] if xp_boost_active else TEXT_MUTED)

    streak_label = f"DAILY STREAK: {daily_streak}d  |  CONTRACTS TODAY: {contracts_done}/{contracts_total}"
    st_bbox = draw.textbbox((0, 0), streak_label, font=font_stat_lbl)
    draw.text((bar_x2 - (st_bbox[2] - st_bbox[0]), bar_y1 - 20), streak_label, font=font_stat_lbl, fill=pal["secondary"])

    draw.rounded_rectangle((bar_x1, bar_y1, bar_x2, bar_y2), radius=13, fill=pal["bg_outer"], outline=pal["border"], width=1)
    fill_w = max(26, int(bar_w * pct)) if pct > 0 else 0
    if fill_w > 0:
        draw.rounded_rectangle((bar_x1, bar_y1, bar_x1 + fill_w, bar_y2), radius=13, fill=pal["primary"])

    # 4 Stat Boxes row
    stats = [
        ("BALANCE", f"{coins:,} Coins", pal["secondary"]),
        ("MESSAGES", f"{messages_sent:,}", pal["primary"]),
        ("VOICE TIME", _format_voice_time(voice_minutes), GREEN),
        ("SQUADS & HOF", f"{lfg_count} LFG  •  {hof_count} HoF", pal["secondary"]),
    ]
    gap = 16
    box_w = (bar_w - gap * 3) // 4
    box_y1, box_y2 = 244, 332

    for idx, (label, val, accent) in enumerate(stats):
        bx1 = bar_x1 + idx * (box_w + gap)
        bx2 = bx1 + box_w
        draw.rounded_rectangle(
            (bx1, box_y1, bx2, box_y2),
            radius=14,
            fill=pal["bg_elevated"],
            outline=BORDER_SUBTLE,
            width=1,
        )
        draw.rounded_rectangle((bx1 + 10, box_y1 + 14, bx1 + 15, box_y2 - 14), radius=2, fill=accent)
        draw.text((bx1 + 26, box_y1 + 16), label, font=font_stat_lbl, fill=TEXT_MUTED)
        draw.text((bx1 + 26, box_y1 + 40), val, font=font_stat_val, fill=TEXT_WHITE)

    # Bottom Badges Bar
    badge_y1, badge_y2 = 352, 412
    draw.rounded_rectangle(
        (bar_x1, badge_y1, bar_x2, badge_y2),
        radius=14,
        fill=pal["bg_outer"],
        outline=BORDER_SUBTLE,
        width=1,
    )
    draw.text((bar_x1 + 18, badge_y1 + 22), "BADGES:", font=font_stat_lbl, fill=TEXT_MUTED)

    bx_cursor = bar_x1 + 98
    if not badges:
        draw.text(
            (bx_cursor, badge_y1 + 22),
            "No badges unlocked yet — chat, join voice, or complete contracts to earn!",
            font=font_sub,
            fill=TEXT_MUTED,
        )
    else:
        for b in badges[:6]:
            b_text = f"★ {b['name'].upper()}"
            bb = draw.textbbox((0, 0), b_text, font=font_badge)
            bw = (bb[2] - bb[0]) + 24
            if bx_cursor + bw > bar_x2 - 14:
                break
            draw.rounded_rectangle(
                (bx_cursor, badge_y1 + 13, bx_cursor + bw, badge_y2 - 13),
                radius=10,
                fill=pal["bg_elevated"],
                outline=pal["primary"],
                width=1,
            )
            draw.text((bx_cursor + 12, badge_y1 + 21), b_text, font=font_badge, fill=TEXT_WHITE)
            bx_cursor += bw + 10

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf


async def render_profile_card(**kwargs: Any) -> io.BytesIO:
    """Async wrapper to generate a user profile card off the event loop."""
    return await asyncio.to_thread(_render_profile_card_sync, **kwargs)


def _render_quote_card_sync(
    quote_text: str,
    author_display_name: str,
    author_username: str,
    author_avatar_bytes: bytes | None,
    channel_name: str,
    stars_count: int,
    timestamp: datetime | None = None,
) -> io.BytesIO:
    font_quote = _load_font(FONT_ITALIC_PATHS, 24)
    font_author = _load_font(FONT_BOLD_PATHS, 22)
    font_meta = _load_font(FONT_REGULAR_PATHS, 16)
    font_badge = _load_font(FONT_BOLD_PATHS, 15)
    font_big_quote = _load_font(FONT_BOLD_PATHS, 88)

    cleaned = " ".join((quote_text or "").strip().split())
    if not cleaned:
        cleaned = "[Attachment / Media Moment]"
    if len(cleaned) > 360:
        cleaned = cleaned[:357] + "..."

    wrapped_lines = textwrap.wrap(cleaned, width=54) or [cleaned]
    line_height = 34
    text_block_h = max(68, len(wrapped_lines) * line_height)

    width = 880
    height = max(310, 195 + text_block_h)

    img = Image.new("RGBA", (width, height), BG_OUTER + (255,))
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle(
        (16, 16, width - 16, height - 16),
        radius=20,
        fill=BG_CARD,
        outline=BORDER_SUBTLE,
        width=2,
    )

    draw.rounded_rectangle(
        (36, 38, 44, height - 38),
        radius=4,
        fill=GOLD,
    )

    hof_label = f"★ HALL OF FAME  •  {stars_count}"
    hb = draw.textbbox((0, 0), hof_label, font=font_badge)
    hw = (hb[2] - hb[0]) + 30
    hx2 = width - 40
    hx1 = hx2 - hw
    draw.rounded_rectangle((hx1, 36, hx2, 70), radius=17, fill=BG_OUTER, outline=GOLD, width=2)
    draw.text((hx1 + 15, 44), hof_label, font=font_badge, fill=GOLD)

    draw.text((64, 24), "“", font=font_big_quote, fill=BLURPLE)

    y_cursor = 88
    for line in wrapped_lines:
        draw.text((76, y_cursor), line, font=font_quote, fill=TEXT_WHITE)
        y_cursor += line_height

    footer_y = height - 96
    draw.line((76, footer_y, width - 44, footer_y), fill=BORDER_SUBTLE, width=1)

    av_size = 52
    av_x, av_y = 76, footer_y + 16
    avatar_img = _make_circular_avatar(author_avatar_bytes, av_size, author_display_name)
    img.paste(avatar_img, (av_x, av_y), avatar_img)

    draw.text(
        (av_x + av_size + 16, av_y + 4),
        f"— {author_display_name[:28]}",
        font=font_author,
        fill=TEXT_WHITE,
    )
    dt_str = (timestamp or datetime.now(timezone.utc)).strftime("%b %d, %Y")
    meta_str = f"@{author_username[:22]}  •  #{channel_name[:24]}  •  {dt_str}"
    draw.text(
        (av_x + av_size + 18, av_y + 31),
        meta_str,
        font=font_meta,
        fill=TEXT_MUTED,
    )

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf


async def render_quote_card(**kwargs: Any) -> io.BytesIO:
    """Async wrapper to generate a Hall of Fame quote card off the event loop."""
    return await asyncio.to_thread(_render_quote_card_sync, **kwargs)


def _render_weekly_wrapped_sync(
    guild_name: str,
    chatter_name: str,
    chatter_stats: str,
    voice_name: str,
    voice_stats: str,
    lfg_name: str,
    lfg_stats: str,
    top_game_name: str,
    top_game_stats: str,
    quote_snippet: str,
    quote_author: str,
    total_messages: int,
    total_voice_minutes: int,
    total_lfg: int,
    active_members: int,
) -> io.BytesIO:
    width, height = 920, 520
    img = Image.new("RGBA", (width, height), BG_OUTER + (255,))
    draw = ImageDraw.Draw(img)

    # Outer frame
    draw.rounded_rectangle(
        (16, 16, width - 16, height - 16),
        radius=20,
        fill=BG_CARD,
        outline=BORDER_SUBTLE,
        width=2,
    )

    # Top Header Banner
    draw.rounded_rectangle((18, 18, width - 18, 106), radius=18, fill=BLURPLE_DARK)
    draw.rectangle((18, 76, width - 18, 106), fill=BLURPLE_DARK)
    draw.polygon(
        [(width - 360, 18), (width - 18, 18), (width - 18, 106), (width - 250, 106)],
        fill=BLURPLE,
    )

    font_title = _load_font(FONT_BOLD_PATHS, 28)
    font_sub = _load_font(FONT_REGULAR_PATHS, 16)
    font_pill = _load_font(FONT_BOLD_PATHS, 15)
    font_box_lbl = _load_font(FONT_BOLD_PATHS, 13)
    font_box_name = _load_font(FONT_BOLD_PATHS, 22)
    font_box_stat = _load_font(FONT_REGULAR_PATHS, 16)
    font_quote = _load_font(FONT_ITALIC_PATHS, 17)

    draw.text((44, 34), "SERVER WEEKLY WRAPPED", font=font_title, fill=TEXT_WHITE)
    draw.text((44, 70), f"{guild_name[:38]}  •  Community Pulse & Highlights", font=font_sub, fill=TEXT_SUB)

    badge_txt = "★ WEEKLY DIGEST"
    bb = draw.textbbox((0, 0), badge_txt, font=font_pill)
    bw = (bb[2] - bb[0]) + 32
    bx2 = width - 40
    bx1 = bx2 - bw
    draw.rounded_rectangle((bx1, 40, bx2, 76), radius=18, fill=BG_OUTER, outline=GOLD, width=2)
    draw.text((bx1 + 16, 49), badge_txt, font=font_pill, fill=GOLD)

    # 2x2 Grid of Spotlight Cards
    cards = [
        ("TOP CHATTER OF THE WEEK", chatter_name[:22], chatter_stats, BLURPLE, 44, 126),
        ("VOICE LOUNGE CHAMPION", voice_name[:22], voice_stats, GREEN, 470, 126),
        ("SQUAD LEADER MVP", lfg_name[:22], lfg_stats, GOLD, 44, 236),
        ("MOST PLAYED LFG GAME", top_game_name[:22], top_game_stats, BLURPLE, 470, 236),
    ]
    card_w, card_h = 406, 94

    for label, main_val, sub_val, accent, cx, cy in cards:
        draw.rounded_rectangle(
            (cx, cy, cx + card_w, cy + card_h),
            radius=14,
            fill=BG_ELEVATED,
            outline=BORDER_SUBTLE,
            width=1,
        )
        draw.rounded_rectangle((cx + 12, cy + 14, cx + 18, cy + card_h - 14), radius=3, fill=accent)
        draw.text((cx + 30, cy + 14), label, font=font_box_lbl, fill=TEXT_MUTED)
        draw.text((cx + 30, cy + 36), main_val, font=font_box_name, fill=TEXT_WHITE)
        draw.text((cx + 30, cy + 65), sub_val, font=font_box_stat, fill=accent)

    # Quote of the Week Box
    qy1, qy2 = 348, 428
    draw.rounded_rectangle(
        (44, qy1, width - 44, qy2),
        radius=14,
        fill=BG_ELEVATED,
        outline=GOLD,
        width=1,
    )
    draw.text((64, qy1 + 14), "★ HALL OF FAME QUOTE OF THE WEEK", font=font_box_lbl, fill=GOLD)
    q_clean = " ".join((quote_snippet or "No quotes saved this week yet — right-click a message to add one!").split())
    if len(q_clean) > 78:
        q_clean = q_clean[:75] + "..."
    q_line = f'"{q_clean}"'
    if quote_author:
        q_line += f"  — {quote_author[:20]}"
    draw.text((64, qy1 + 40), q_line, font=font_quote, fill=TEXT_WHITE)

    # Server Weekly Totals Footer Strip
    fy1, fy2 = 442, 488
    draw.rounded_rectangle(
        (44, fy1, width - 44, fy2),
        radius=12,
        fill=BG_OUTER,
        outline=BORDER_SUBTLE,
        width=1,
    )
    totals_str = (
        f"WEEKLY TOTALS:   {total_messages:,} Messages   •   "
        f"{_format_voice_time(total_voice_minutes)} Voice Time   •   "
        f"{total_lfg:,} LFG Squads   •   "
        f"{active_members:,} Active Members"
    )
    draw.text((64, fy1 + 15), totals_str, font=font_box_lbl, fill=TEXT_SUB)

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf


async def render_weekly_wrapped_card(**kwargs: Any) -> io.BytesIO:
    """Async wrapper to generate a Server Weekly Wrapped infographic off the event loop."""
    return await asyncio.to_thread(_render_weekly_wrapped_sync, **kwargs)
