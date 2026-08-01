import asyncio
import io
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFilter, ImageFont


WIB = ZoneInfo("Asia/Jakarta")
BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_PATH = BASE_DIR / "data" / "arvelion.db"
FONT_DIR = BASE_DIR / "fonts"


def get_config() -> dict[str, str]:
    description = os.getenv(
        "ARVELION_ID_PANEL_DESCRIPTION",
        "Buat identitas komunitas kamu melalui tombol di bawah.\\n\\n**Buat ID** untuk mengisi atau memperbarui data.\\n**Lihat ID Saya** untuk menampilkan kartu milikmu.",
    ).strip()
    return {
        "community_name": os.getenv("ARVELION_ID_COMMUNITY_NAME", "ARVELION COMMUNITY").strip() or "ARVELION COMMUNITY",
        "bot_label": os.getenv("ARVELION_ID_BOT_LABEL", "ARVELION BOT").strip() or "ARVELION BOT",
        "card_title": os.getenv("ARVELION_ID_CARD_TITLE", "ARVELION ID CARD").strip() or "ARVELION ID CARD",
        "card_subtitle": os.getenv("ARVELION_ID_CARD_SUBTITLE", "OFFICIAL COMMUNITY PROFILE").strip() or "OFFICIAL COMMUNITY PROFILE",
        "member_label": os.getenv("ARVELION_ID_MEMBER_LABEL", "MEMBER").strip() or "MEMBER",
        "sid_prefix": os.getenv("ARVELION_ID_SID_PREFIX", "ARV").strip() or "ARV",
        "panel_title": os.getenv("ARVELION_ID_PANEL_TITLE", "Arvelion ID Card").strip() or "Arvelion ID Card",
        "panel_description": (description or "Buat identitas komunitas kamu melalui tombol di bawah.").replace("\\n", "\n"),
        "font_regular": os.getenv("ARVELION_ID_FONT_REGULAR", "fonts/Arvelion-Regular.ttf").strip(),
        "font_bold": os.getenv("ARVELION_ID_FONT_BOLD", "fonts/Arvelion-Bold.ttf").strip(),
    }


def resolve_font_path(configured: str, bold: bool) -> Path | None:
    candidates: list[Path] = []
    if configured:
        configured_path = Path(configured)
        candidates.append(configured_path if configured_path.is_absolute() else BASE_DIR / configured_path)
    candidates.extend(
        [
            FONT_DIR / ("Arvelion-Bold.ttf" if bold else "Arvelion-Regular.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
        ]
    )
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def get_font(size: int, bold: bool, config: dict[str, str]) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = resolve_font_path(config["font_bold"] if bold else config["font_regular"], bold)
    if path:
        return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def fit_font(text: str, max_width: int, start_size: int, minimum: int, bold: bool, config: dict[str, str]) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for size in range(start_size, minimum - 1, -1):
        font = get_font(size, bold, config)
        if font.getlength(text) <= max_width:
            return font
    return get_font(minimum, bold, config)


def truncate(font: ImageFont.FreeTypeFont | ImageFont.ImageFont, text: str, max_width: int) -> str:
    value = str(text)
    if font.getlength(value) <= max_width:
        return value
    while value and font.getlength(value + "...") > max_width:
        value = value[:-1]
    return value + "..." if value else ""


def vertical_gradient(size: tuple[int, int], top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    width, height = size
    image = Image.new("RGB", size)
    pixels = image.load()
    for y in range(height):
        ratio = y / max(height - 1, 1)
        color = tuple(int(top[index] + (bottom[index] - top[index]) * ratio) for index in range(3))
        for x in range(width):
            pixels[x, y] = color
    return image.convert("RGBA")


def rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return mask


def create_avatar(avatar_bytes: bytes | None, size: int, fallback: str, config: dict[str, str]) -> Image.Image:
    if avatar_bytes:
        try:
            avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
            side = min(avatar.width, avatar.height)
            left = (avatar.width - side) // 2
            top = (avatar.height - side) // 2
            avatar = avatar.crop((left, top, left + side, top + side)).resize((size, size), Image.Resampling.LANCZOS)
        except Exception:
            avatar = vertical_gradient((size, size), (25, 50, 105), (8, 20, 52))
    else:
        avatar = vertical_gradient((size, size), (25, 50, 105), (8, 20, 52))

    if not avatar_bytes:
        initials = "".join(part[0] for part in fallback.split()[:2] if part).upper() or "A"
        draw = ImageDraw.Draw(avatar)
        font = fit_font(initials, size - 50, size // 3, 26, True, config)
        box = draw.textbbox((0, 0), initials, font=font)
        draw.text(
            ((size - (box[2] - box[0])) / 2, (size - (box[3] - box[1])) / 2 - 6),
            initials,
            font=font,
            fill=(242, 247, 255),
        )

    avatar.putalpha(rounded_mask((size, size), 45))
    return avatar


def draw_glow_rect(image: Image.Image, box: tuple[int, int, int, int], radius: int, color: tuple[int, int, int], width: int = 3, blur: int = 16) -> None:
    glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.rounded_rectangle(box, radius=radius, outline=(*color, 210), width=max(width * 3, 8))
    glow = glow.filter(ImageFilter.GaussianBlur(blur))
    image.alpha_composite(glow)
    ImageDraw.Draw(image).rounded_rectangle(box, radius=radius, outline=(*color, 255), width=width)


def draw_logo(draw: ImageDraw.ImageDraw, x: int, y: int, scale: float = 1.0) -> None:
    blue = (65, 128, 255)
    light = (106, 166, 255)
    dark = (25, 75, 190)
    points_left = [(x, y + int(92 * scale)), (x + int(42 * scale), y), (x + int(68 * scale), y + int(20 * scale)), (x + int(25 * scale), y + int(100 * scale))]
    points_right = [(x + int(48 * scale), y + int(44 * scale)), (x + int(88 * scale), y + int(106 * scale)), (x + int(58 * scale), y + int(91 * scale)), (x + int(35 * scale), y + int(58 * scale))]
    draw.polygon(points_left, fill=light)
    draw.polygon(points_right, fill=blue)
    draw.polygon([(x + int(31 * scale), y + int(58 * scale)), (x + int(51 * scale), y + int(28 * scale)), (x + int(58 * scale), y + int(42 * scale)), (x + int(43 * scale), y + int(66 * scale))], fill=dark)


def draw_robot(draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
    blue = (61, 122, 255)
    draw.rounded_rectangle((x, y + 7, x + 54, y + 48), radius=12, outline=blue, width=3)
    draw.line((x + 27, y, x + 27, y + 8), fill=blue, width=3)
    draw.ellipse((x + 23, y - 5, x + 31, y + 3), fill=blue)
    draw.ellipse((x + 13, y + 21, x + 20, y + 28), fill=blue)
    draw.ellipse((x + 34, y + 21, x + 41, y + 28), fill=blue)
    draw.arc((x + 17, y + 25, x + 38, y + 40), start=10, end=170, fill=blue, width=2)


def render_card(data: dict[str, Any], member: discord.Member, avatar_bytes: bytes | None, config: dict[str, str]) -> io.BytesIO:
    width = 1672
    height = 941
    image = vertical_gradient((width, height), (3, 10, 25), (1, 6, 17))

    ambient = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ambient_draw = ImageDraw.Draw(ambient)
    ambient_draw.ellipse((-250, -280, 760, 620), fill=(20, 70, 210, 70))
    ambient_draw.ellipse((970, 250, 1880, 1120), fill=(0, 45, 170, 55))
    ambient = ambient.filter(ImageFilter.GaussianBlur(120))
    image.alpha_composite(ambient)

    draw = ImageDraw.Draw(image)
    outer_box = (31, 32, width - 31, height - 35)
    draw_glow_rect(image, outer_box, 35, (48, 108, 255), 3, 18)

    header_box = (52, 50, 1620, 210)
    draw.rounded_rectangle(header_box, radius=34, fill=(5, 13, 33, 235), outline=(41, 94, 208), width=2)
    draw.line((56, 211, 1598, 211), fill=(42, 113, 255), width=2)
    draw_logo(draw, 92, 78, 0.9)

    title = config["card_title"].upper()
    if "ID CARD" in title:
        left = title.replace("ID CARD", "").strip() or "ARVELION"
        left_font = fit_font(left, 430, 61, 36, True, config)
        id_font = fit_font("ID CARD", 310, 58, 36, True, config)
        draw.text((235, 82), left, font=left_font, fill=(239, 243, 252))
        draw.text((235 + int(left_font.getlength(left)) + 15, 82), "ID CARD", font=id_font, fill=(61, 122, 255))
    else:
        title_font = fit_font(title, 750, 58, 34, True, config)
        draw.text((235, 82), truncate(title_font, title, 750), font=title_font, fill=(239, 243, 252))

    subtitle_font = fit_font(config["card_subtitle"].upper(), 720, 27, 16, False, config)
    draw.text((237, 157), truncate(subtitle_font, config["card_subtitle"].upper(), 720), font=subtitle_font, fill=(137, 157, 207))

    bot_box = (1175, 84, 1562, 177)
    draw.rounded_rectangle(bot_box, radius=28, fill=(5, 13, 33, 220), outline=(36, 85, 185), width=2)
    draw_robot(draw, 1220, 105)
    bot_font = fit_font(config["bot_label"].upper(), 255, 34, 18, True, config)
    draw.text((1300, 115), truncate(bot_font, config["bot_label"].upper(), 245), font=bot_font, fill=(242, 245, 252))

    avatar_box = (82, 249, 482, 704)
    draw.rounded_rectangle(avatar_box, radius=48, fill=(4, 13, 34, 245))
    draw_glow_rect(image, avatar_box, 48, (61, 122, 255), 3, 16)
    avatar = create_avatar(avatar_bytes, 330, member.display_name, config)
    image.alpha_composite(avatar, (117, 311))

    label_color = (143, 161, 207)
    value_color = (244, 247, 253)
    blue = (61, 122, 255)
    label_font = get_font(27, True, config)
    value_font = get_font(34, True, config)
    rows = [
        ("SID NO", data["sid"]),
        ("NAMA", data["name"]),
        ("JENIS KELAMIN", data["gender"]),
        ("DOMISILI", data["domicile"]),
        ("CITA-CITA", data["aspiration"]),
        ("HOBI", data["hobby"]),
    ]
    row_x = 530
    value_x = 770
    row_y = 270
    for label, value in rows:
        draw.text((row_x, row_y), label, font=label_font, fill=label_color)
        draw.text((731, row_y - 2), ":", font=get_font(35, True, config), fill=blue)
        chosen = fit_font(str(value), 455, 34, 18, True, config)
        draw.text((value_x, row_y - 2), truncate(chosen, str(value), 455), font=chosen, fill=value_color)
        draw.line((row_x, row_y + 53, 1240, row_y + 53), fill=(33, 57, 105), width=2)
        row_y += 78

    joined_at = member.joined_at.astimezone(WIB).strftime("%d-%m-%Y") if member.joined_at else "Tidak diketahui"
    created_at = datetime.fromisoformat(data["created_at"]).astimezone(WIB).strftime("%d-%m-%Y")
    account_created = member.created_at.astimezone(WIB).strftime("%d-%m-%Y")

    member_box = (1280, 244, 1572, 703)
    draw.rounded_rectangle(member_box, radius=43, fill=(5, 13, 33, 238))
    draw_glow_rect(image, member_box, 43, (61, 122, 255), 3, 15)
    draw.ellipse((1324, 286, 1344, 306), fill=blue)
    draw.ellipse((1348, 286, 1368, 306), fill=blue)
    draw.rounded_rectangle((1322, 307, 1370, 331), radius=10, fill=blue)
    member_label_font = fit_font(config["member_label"].upper(), 150, 26, 17, True, config)
    draw.text((1382, 286), truncate(member_label_font, config["member_label"].upper(), 145), font=member_label_font, fill=blue)
    name_font = fit_font(member.display_name, 230, 28, 16, True, config)
    draw.text((1321, 350), truncate(name_font, member.display_name, 225), font=name_font, fill=value_color)
    username = f"@{member.name}"
    username_font = fit_font(username, 225, 23, 15, False, config)
    draw.text((1322, 399), truncate(username_font, username, 225), font=username_font, fill=(165, 181, 220))
    draw.line((1322, 458, 1530, 458), fill=(45, 96, 210), width=2)
    draw.text((1345, 494), "JOIN SERVER", font=get_font(18, True, config), fill=blue)
    draw.text((1345, 533), joined_at, font=get_font(27, True, config), fill=value_color)
    draw.line((1322, 575, 1530, 575), fill=(28, 54, 105), width=2)
    draw.text((1345, 610), "ID DIBUAT", font=get_font(18, True, config), fill=blue)
    draw.text((1345, 649), created_at, font=get_font(27, True, config), fill=value_color)

    footer_box = (70, 747, 1600, 864)
    draw.rounded_rectangle(footer_box, radius=34, fill=(5, 13, 33, 238), outline=(32, 76, 165), width=2)
    draw.ellipse((118, 777, 177, 836), outline=blue, width=3)
    draw.rounded_rectangle((133, 790, 162, 818), radius=4, outline=blue, width=3)
    draw.line((138, 785, 138, 797), fill=blue, width=3)
    draw.line((157, 785, 157, 797), fill=blue, width=3)
    draw.text((208, 773), "AKUN DIBUAT", font=get_font(17, True, config), fill=blue)
    draw.text((208, 811), account_created, font=get_font(28, True, config), fill=value_color)
    draw.line((510, 771, 510, 839), fill=(32, 67, 135), width=2)

    draw.ellipse((555, 777, 614, 836), outline=blue, width=3)
    draw.arc((568, 792, 602, 819), start=200, end=340, fill=blue, width=4)
    draw.ellipse((570, 795, 577, 802), fill=blue)
    draw.ellipse((592, 795, 599, 802), fill=blue)
    draw.text((643, 773), "DISCORD ID", font=get_font(17, True, config), fill=blue)
    id_font = fit_font(str(member.id), 400, 28, 18, False, config)
    draw.text((643, 811), truncate(id_font, str(member.id), 400), font=id_font, fill=value_color)
    draw.line((1110, 771, 1110, 839), fill=(32, 67, 135), width=2)

    draw_logo(draw, 1162, 779, 0.55)
    community_font = fit_font(config["community_name"].upper(), 350, 24, 15, True, config)
    draw.text((1232, 801), truncate(community_font, config["community_name"].upper(), 335), font=community_font, fill=blue)

    output = io.BytesIO()
    image.convert("RGB").save(output, format="PNG", optimize=True, quality=95)
    output.seek(0)
    return output


class IDCardDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = asyncio.Lock()

    async def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(self._initialize_sync)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize_sync(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS id_cards (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    sid TEXT NOT NULL,
                    name TEXT NOT NULL,
                    gender TEXT NOT NULL,
                    domicile TEXT NOT NULL,
                    aspiration TEXT NOT NULL,
                    hobby TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (guild_id, user_id),
                    UNIQUE (guild_id, sid)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS id_counters (
                    guild_id INTEGER PRIMARY KEY,
                    last_number INTEGER NOT NULL
                )
                """
            )

    async def get_card(self, guild_id: int, user_id: int) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_card_sync, guild_id, user_id)

    def _get_card_sync(self, guild_id: int, user_id: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM id_cards WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ).fetchone()
            return dict(row) if row else None

    async def save_card(self, guild_id: int, user_id: int, values: dict[str, str], sid_prefix: str) -> tuple[dict[str, Any], bool]:
        async with self.lock:
            return await asyncio.to_thread(self._save_card_sync, guild_id, user_id, values, sid_prefix)

    def _save_card_sync(self, guild_id: int, user_id: int, values: dict[str, str], sid_prefix: str) -> tuple[dict[str, Any], bool]:
        now = datetime.now(timezone.utc).isoformat()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT sid, created_at FROM id_cards WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ).fetchone()
            created = existing is None

            if existing:
                sid = existing["sid"]
                created_at = existing["created_at"]
            else:
                counter = connection.execute(
                    "SELECT last_number FROM id_counters WHERE guild_id = ?",
                    (guild_id,),
                ).fetchone()
                next_number = (counter["last_number"] if counter else 0) + 1
                connection.execute(
                    "INSERT INTO id_counters (guild_id, last_number) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET last_number = excluded.last_number",
                    (guild_id, next_number),
                )
                sid = f"{sid_prefix}-{next_number:05d}"
                created_at = now

            connection.execute(
                """
                INSERT INTO id_cards (
                    guild_id, user_id, sid, name, gender, domicile,
                    aspiration, hobby, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    name = excluded.name,
                    gender = excluded.gender,
                    domicile = excluded.domicile,
                    aspiration = excluded.aspiration,
                    hobby = excluded.hobby,
                    updated_at = excluded.updated_at
                """,
                (
                    guild_id,
                    user_id,
                    sid,
                    values["name"],
                    values["gender"],
                    values["domicile"],
                    values["aspiration"],
                    values["hobby"],
                    created_at,
                    now,
                ),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM id_cards WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ).fetchone()
            return dict(row), created
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


class IDCardModal(discord.ui.Modal, title="Isi Data Arvelion ID"):
    name = discord.ui.TextInput(label="Nama", placeholder="Masukkan nama yang ingin ditampilkan", min_length=2, max_length=32)
    gender = discord.ui.TextInput(label="Jenis Kelamin", placeholder="Contoh: Laki-laki atau Perempuan", min_length=3, max_length=20)
    domicile = discord.ui.TextInput(label="Domisili", placeholder="Contoh: Indonesia", min_length=2, max_length=32)
    aspiration = discord.ui.TextInput(label="Cita-Cita", placeholder="Masukkan cita-cita kamu", min_length=2, max_length=50)
    hobby = discord.ui.TextInput(label="Hobi", placeholder="Masukkan hobi kamu", min_length=2, max_length=50)

    def __init__(self, cog: "IDCard") -> None:
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Sistem ini hanya bisa digunakan di dalam server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        values = {
            "name": self.name.value.strip(),
            "gender": self.gender.value.strip(),
            "domicile": self.domicile.value.strip(),
            "aspiration": self.aspiration.value.strip(),
            "hobby": self.hobby.value.strip(),
        }

        try:
            data, created = await self.cog.database.save_card(
                interaction.guild.id,
                interaction.user.id,
                values,
                self.cog.config["sid_prefix"],
            )
            file = await self.cog.build_file(data, interaction.user)
            embed = self.cog.result_embed(interaction.user, created)
            embed.set_image(url=f"attachment://{file.filename}")
            await interaction.followup.send(embed=embed, file=file, ephemeral=True)
        except Exception:
            await interaction.followup.send("ID Card gagal diproses. Coba kembali beberapa saat lagi.", ephemeral=True)


class IDCardView(discord.ui.View):
    def __init__(self, cog: "IDCard") -> None:
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Buat ID", style=discord.ButtonStyle.primary, custom_id="arvelion:id_card:create")
    async def create_id(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(IDCardModal(self.cog))

    @discord.ui.button(label="Lihat ID Saya", style=discord.ButtonStyle.secondary, custom_id="arvelion:id_card:view")
    async def view_id(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Sistem ini hanya bisa digunakan di dalam server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        data = await self.cog.database.get_card(interaction.guild.id, interaction.user.id)
        if not data:
            embed = discord.Embed(
                title=self.cog.config["panel_title"],
                description="Kamu belum mempunyai Arvelion ID. Klik tombol **Buat ID** untuk membuatnya.",
                color=discord.Color.from_rgb(61, 122, 255),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        try:
            file = await self.cog.build_file(data, interaction.user)
            embed = discord.Embed(
                title=self.cog.config["panel_title"],
                description=f"ID milik {interaction.user.mention}",
                color=discord.Color.from_rgb(61, 122, 255),
            )
            embed.set_image(url=f"attachment://{file.filename}")
            await interaction.followup.send(embed=embed, file=file, ephemeral=True)
        except Exception:
            await interaction.followup.send("ID Card gagal ditampilkan. Coba kembali beberapa saat lagi.", ephemeral=True)


class IDCard(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.database = IDCardDatabase(DATABASE_PATH)
        self.config = get_config()

    async def build_file(self, data: dict[str, Any], member: discord.Member) -> discord.File:
        try:
            avatar_bytes = await member.display_avatar.with_size(512).read()
        except Exception:
            avatar_bytes = None
        buffer = await asyncio.to_thread(render_card, data, member, avatar_bytes, self.config)
        return discord.File(buffer, filename=f"arvelion_id_{member.id}.png")

    def result_embed(self, member: discord.Member, created: bool) -> discord.Embed:
        action = "berhasil dibuat" if created else "berhasil diperbarui"
        return discord.Embed(
            title=self.config["panel_title"],
            description=f"ID milik {member.mention} {action}.",
            color=discord.Color.from_rgb(61, 122, 255),
        )

    @app_commands.command(name="id-panel", description="Mengirim panel pembuatan Arvelion ID Card")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def id_panel(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title=self.config["panel_title"],
            description=self.config["panel_description"],
            color=discord.Color.from_rgb(61, 122, 255),
        )
        embed.set_footer(text=self.config["bot_label"])
        await interaction.response.send_message(embed=embed, view=IDCardView(self))

    @id_panel.error
    async def id_panel_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        message = "Kamu memerlukan izin Manage Server untuk menggunakan command ini."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    cog = IDCard(bot)
    await cog.database.initialize()
    await bot.add_cog(cog)
    bot.add_view(IDCardView(cog))
