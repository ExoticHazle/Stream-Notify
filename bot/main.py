import asyncio
import os
import sys
import discord
from discord.ext import commands
from bot.config import DISCORD_TOKEN, PREFIX
from bot import database
from bot.cogs.tickets import TicketPanelView, TicketCloseView
from bot.cogs.voiceprivate import VoiceControlPanel
from bot.web import start_web

start_web()

COGS = [
    "bot.cogs.moderation",
    "bot.cogs.twitch",
    "bot.cogs.planning",
    "bot.cogs.tickets",
    "bot.cogs.logs",
    "bot.cogs.voiceprivate",
]


class DiscordBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        intents.reactions = True
        super().__init__(
            command_prefix=PREFIX,
            intents=intents,
            case_insensitive=True,
            help_command=None,
        )

    async def setup_hook(self):
        """Chargement des cogs, BDD et vues persistantes."""
        await database.init_db()

        # Enregistrer les vues persistantes AVANT de charger les cogs
        self.add_view(TicketPanelView())
        self.add_view(TicketCloseView())
        self.add_view(VoiceControlPanel())

        for cog in COGS:
            try:
                await self.load_extension(cog)
                print(f"[Bot] ✅ Cog chargé : {cog}")
            except Exception as e:
                print(f"[Bot] ❌ Erreur chargement {cog} : {e}")

    async def on_ready(self):
        print(f"[Bot] Connecté en tant que {self.user} (ID: {self.user.id})")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="le serveur 👀",
            )
        )

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.NoPrivateMessage):
            await ctx.send("❌ Cette commande ne peut pas être utilisée en message privé.")
        elif isinstance(error, commands.CheckFailure):
            await ctx.send("❌ Tu n'as pas la permission d'utiliser cette commande.")


async def main():
    if not DISCORD_TOKEN:
        print("[Bot] ❌ DISCORD_TOKEN manquant. Configure tes secrets.")
        sys.exit(1)

    bot = DiscordBot()

    @bot.command(name="help", aliases=["aide"])
    async def help_cmd(ctx):
        embed = discord.Embed(title="📖 Commandes du bot", color=0x9146FF)
        embed.add_field(
            name="🔨 Modération",
            value=(
                f"`{PREFIX}ban @membre [raison]` — Bannir\n"
                f"`{PREFIX}unban <id>` — Débannir\n"
                f"`{PREFIX}kick @membre [raison]` — Expulser\n"
                f"`{PREFIX}timeout @membre <min> [raison]` — Timeout\n"
                f"`{PREFIX}untimeout @membre` — Lever un timeout\n"
                f"`{PREFIX}warn @membre [raison]` — Avertir\n"
            ),
            inline=False,
        )
        embed.add_field(
            name="📋 Historique (modérateurs)",
            value=(
                f"`{PREFIX}history [@membre]` — Voir les sanctions\n"
                f"`{PREFIX}delsanction <id>` — Supprimer + lever ban/timeout\n"
            ),
            inline=False,
        )
        embed.add_field(
            name="🎫 Tickets",
            value=(
                f"`{PREFIX}panelticket` — Poster le panel de tickets *(owner)*\n"
                "Les tickets se créent via le bouton dans le salon dédié.\n"
            ),
            inline=False,
        )
        embed.add_field(
            name="📅 Planning (propriétaire)",
            value=(
                f"`{PREFIX}planning <contenu>` — Envoyer un planning\n"
                f"`{PREFIX}clearplanning [n]` — Nettoyer le salon planning\n"
            ),
            inline=False,
        )
        embed.set_footer(text=f"Préfixe : {PREFIX} | Bot — exotichazle")
        await ctx.send(embed=embed)

    async with bot:
        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
