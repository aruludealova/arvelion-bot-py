import os
from pathlib import Path

import discord
from discord.ext import commands


def load_env_file() -> None:
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_env_file()


class ArvelionBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        intents.members = True
        super().__init__(command_prefix=commands.when_mentioned_or("arv!"), intents=intents)

    async def setup_hook(self) -> None:
        systems_path = Path(__file__).resolve().parent / "systems"
        for file_path in sorted(systems_path.glob("*.py")):
            if file_path.name == "__init__.py" or file_path.name.startswith("_"):
                continue
            await self.load_extension(f"systems.{file_path.stem}")

        guild_id = os.getenv("GUILD_ID", "").strip()
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_ready(self) -> None:
        print(f"Arvelion Bot siap sebagai {self.user} ({self.user.id})")


bot = ArvelionBot()
token = os.getenv("DISCORD_TOKEN", "").strip()
if not token:
    raise RuntimeError("DISCORD_TOKEN belum diisi")
bot.run(token, log_handler=None)
