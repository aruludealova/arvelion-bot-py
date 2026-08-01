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
from PIL import Image, ImageDraw, ImageFont


WIB = ZoneInfo("Asia/Jakarta")
BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_PATH = BASE_DIR / "data" / "arvelion.db"
TEMPLATE_PATH = BASE_DIR / "assets" / "id_card_template.png"


def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def fit_font(text: str, max_width: int, start_size: int, minimum: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for size in range(start_size, minimum - 1, -1):
        font = get_font(size, bold)
        if font.getlength(text) <= max_width:
            return font
    return get_font(minimum, bold)


def shorten_text(font: ImageFont.FreeTypeFont | ImageFont.ImageFont, text: str, max_width: int) -> str:
    value = str(text)
    if font.getlength(value) <= max_width:
        return value
    while value and font.getlength(value + "...") > max_width:
        value = value[:-1]
    return (value + "...") if value else ""


def draw_text(draw: ImageDraw.ImageDraw, position: tuple[int, int], text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont, fill: tuple[int, int, int], max_width: int | None = None) -> None:
    value = shorten_text(font, text, max_width) if max_width is not None else str(text)
    draw.text(position, value, font=font, fill=fill)


def get_config() -> dict[str, str]:
    return {
        "community_name": os.getenv("ARVELION_ID_COMMUNITY_NAME", "ARVELION COMMUNITY").strip() or "ARVELION COMMUNITY",
        "bot_label": os.getenv("ARVELION_ID_BOT_LABEL", "ARVELION BOT").strip() or "ARVELION BOT",
        "card_title": os.getenv("ARVELION_ID_CARD_TITLE", "ARVELION ID CARD").strip() or "ARVELION ID CARD",
        "card_subtitle": os.getenv("ARVELION_ID_CARD_SUBTITLE", "OFFICIAL COMMUNITY PROFILE").strip() or "OFFICIAL COMMUNITY PROFILE",
        "member_label": os.getenv("ARVELION_ID_MEMBER_LABEL", "MEMBER").strip() or "MEMBER",
        "sid_prefix": os.getenv("ARVELION_ID_SID_PREFIX", "ARV").strip() or "ARV",
        "panel_title": os.getenv("ARVELION_ID_PANEL_TITLE", "Arvelion ID Card").strip() or "Arvelion ID Card",
        "panel_description": (os.getenv("ARVELION_ID_PANEL_DESCRIPTION", "Buat identitas komunitas kamu melalui tombol di bawah.\n\n**Buat ID** untuk mengisi atau memperbarui data.\n**Lihat ID Saya** untuk menampilkan kartu milikmu.").strip() or "Buat identitas komunitas kamu melalui tombol di bawah.\n\n**Buat ID** untuk mengisi atau memperbarui data.\n**Lihat ID Saya** untuk menampilkan kartu milikmu.").replace("\\n", "\n"),
    }


def create_avatar(avatar_bytes: bytes | None, size: int, fallback: str) -> Image.Image:
    if avatar_bytes:
        try:
            avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
            side = min(avatar.width, avatar.height)
            left = (avatar.width - side) // 2
            top = (avatar.height - side) // 2
            avatar = avatar.crop((left, top, left + side, top + side)).resize((size, size), Image.Resampling.LANCZOS)
        except Exception:
            avatar = Image.new("RGBA", (size, size), (34, 47, 82, 255))
    else:
        avatar = Image.new("RGBA", (size, size), (34, 47, 82, 255))

    if not avatar_bytes:
        avatar_draw = ImageDraw.Draw(avatar)
        initials = "".join(part[0] for part in fallback.split()[:2] if part).upper() or "A"
        font = fit_font(initials, size - 40, size // 3, 26, True)
        box = avatar_draw.textbbox((0, 0), initials, font=font)
        avatar_draw.text(((size - (box[2] - box[0])) / 2, (size - (box[3] - box[1])) / 2 - 6), initials, font=font, fill=(242, 246, 255))

    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle((0, 0, size, size), radius=48, fill=255)
    avatar.putalpha(mask)
    return avatar


def block(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill: tuple[int, int, int, int], radius: int = 0) -> None:
    if radius > 0:
        draw.rounded_rectangle(box, radius=radius, fill=fill)
    else:
        draw.rectangle(box, fill=fill)


def render_card(data: dict[str, Any], member: discord.Member, avatar_bytes: bytes | None, config: dict[str, str]) -> io.BytesIO:
    if TEMPLATE_PATH.exists():
        image = Image.open(TEMPLATE_PATH).convert("RGBA")
    else:
        image = Image.new("RGBA", (1672, 941), (4, 11, 26, 255))
    draw = ImageDraw.Draw(image)

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    dark_fill = (5, 13, 32, 240)
    dark_fill_soft = (7, 15, 36, 230)

    block(overlay_draw, (88, 257, 465, 693), dark_fill_soft, 38)
    for box in [
        (217, 100, 706, 183),
        (1274, 96, 1533, 182),
        (761, 244, 1225, 696),
        (1316, 283, 1498, 422),
        (1310, 485, 1498, 537),
        (1310, 596, 1498, 648),
        (215, 774, 505, 848),
        (666, 768, 1114, 849),
        (1194, 766, 1545, 849),
    ]:
        block(overlay_draw, box, dark_fill, 20)

    row_cover_boxes = [
        (733, 244, 1010, 313),
        (733, 316, 1108, 390),
        (733, 394, 1108, 469),
        (733, 475, 1108, 545),
        (733, 556, 1160, 624),
        (733, 633, 1160, 698),
    ]
    for box in row_cover_boxes:
        block(overlay_draw, box, dark_fill)

    image.alpha_composite(overlay)

    title_left, title_top = 238, 89
    title = config["card_title"].strip() or "ARVELION ID CARD"
    if "ID CARD" in title.upper():
        prefix = title.upper().split("ID CARD")[0].rstrip()
        left_text = prefix if prefix else "ARVELION"
        gap = 12
        left_font = fit_font(left_text, 420, 60, 36, True)
        draw.text((title_left, title_top), left_text, font=left_font, fill=(239, 242, 248))
        left_width = int(left_font.getlength(left_text))
        draw.text((title_left + left_width + gap, title_top), "ID CARD", font=fit_font("ID CARD", 310, 58, 36, True), fill=(61, 122, 255))
    else:
        draw.text((title_left, title_top), shorten_text(fit_font(title, 600, 60, 36, True), title, 600), font=fit_font(title, 600, 60, 36, True), fill=(239, 242, 248))
    draw.text((237, 160), shorten_text(get_font(27, False), config["card_subtitle"], 640), font=get_font(27, False), fill=(135, 156, 209))
    bot_label_font = fit_font(config["bot_label"], 270, 37, 18, True)
    draw.text((1322, 105), shorten_text(bot_label_font, config["bot_label"], 240), font=bot_label_font, fill=(242, 245, 251))

    avatar = create_avatar(avatar_bytes, 309, member.display_name)
    image.alpha_composite(avatar, (95, 271))

    label_font = get_font(28, True)
    value_font = get_font(33, True)
    label_color = (147, 163, 211)
    value_color = (245, 247, 251)
    blue = (61, 122, 255)

    rows = [
        ("SID NO", data["sid"], 275),
        ("NAMA", data["name"], 352),
        ("JENIS KELAMIN", data["gender"], 431),
        ("DOMISILI", data["domicile"], 510),
        ("CITA-CITA", data["aspiration"], 590),
        ("HOBI", data["hobby"], 670),
    ]
    for label, value, y in rows:
        draw.text((523, y), label, font=label_font, fill=label_color)
        draw.text((727, y - 2), ":", font=get_font(34, True), fill=blue)
        chosen_font = fit_font(str(value), 460, 34, 19, True)
        draw.text((763, y - 2), shorten_text(chosen_font, str(value), 440), font=chosen_font, fill=value_color)

    joined_at = member.joined_at.astimezone(WIB).strftime("%d-%m-%Y") if member.joined_at else "Tidak diketahui"
    created_at = datetime.fromisoformat(data["created_at"]).astimezone(WIB).strftime("%d-%m-%Y")
    account_created = member.created_at.astimezone(WIB).strftime("%d-%m-%Y")

    draw.text((1381, 283), shorten_text(get_font(25, True), config["member_label"].upper(), 120), font=get_font(25, True), fill=blue)
    right_name_font = fit_font(member.display_name, 172, 27, 18, True)
    draw.text((1319, 354), shorten_text(right_name_font, member.display_name, 172), font=right_name_font, fill=value_color)
    right_user_font = fit_font(f"@{member.name}", 170, 21, 15, False)
    draw.text((1322, 414), shorten_text(right_user_font, f"@{member.name}", 170), font=right_user_font, fill=(169, 184, 223))
    draw.text((1370, 502), "JOIN SERVER", font=get_font(18, True), fill=blue)
    draw.text((1372, 542), joined_at, font=get_font(28, True), fill=value_color)
    draw.text((1370, 610), "ID DIBUAT", font=get_font(18, True), fill=blue)
    draw.text((1372, 650), created_at, font=get_font(28, True), fill=value_color)

    draw.text((221, 787), "AKUN DIBUAT", font=get_font(18, True), fill=blue)
    draw.text((220, 828), account_created, font=get_font(28, True), fill=value_color)
    draw.text((667, 787), "DISCORD ID", font=get_font(18, True), fill=blue)
    discord_id_font = fit_font(str(member.id), 370, 27, 18, False)
    draw.text((667, 828), shorten_text(discord_id_font, str(member.id), 370), font=discord_id_font, fill=value_color)
    community_font = fit_font(config["community_name"].upper(), 330, 23, 15, True)
    draw.text((1274, 803), shorten_text(community_font, config["community_name"].upper(), 310), font=community_font, fill=blue)

    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
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
            data, created = await self.cog.database.save_card(interaction.guild.id, interaction.user.id, values, self.cog.config["sid_prefix"])
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
