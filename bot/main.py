import asyncio
import os
import sys
import discord
from discord.ext import commands
from bot.config import DISCORD_TOKEN, PREFIX
from bot import database


COGS = [
    "bot.cogs.moderation",
    "bot.cogs.twitch",
    "bot.cogs.planning",
]


class DiscordBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(
            command_prefix=PREFIX,
            intents=intents,
            case_insensitive=True,
            help_command=None,
        )

    async def setup_hook(self):
        """Chargement des cogs et initialisation de la BDD."""
        await database.init_db()
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
        """Gestion globale des erreurs de commande."""
        if isinstance(error, commands.CommandNotFound):
            return  # Ignorer les commandes inconnues silencieusement
        if isinstance(error, commands.NoPrivateMessage):
            await ctx.send("❌ Cette commande ne peut pas être utilisée en message privé.")
        elif isinstance(error, commands.CheckFailure):
            await ctx.send("❌ Tu n'as pas la permission d'utiliser cette commande.")
        else:
            # Laisser les cogs gérer leurs propres erreurs
            pass


async def main():
    if not DISCORD_TOKEN:
        print("[Bot] ❌ DISCORD_TOKEN manquant. Configure tes secrets.")
        sys.exit(1)

    bot = DiscordBot()

    # Commande d'aide personnalisée
    @bot.command(name="help", aliases=["aide"])
    async def help_cmd(ctx):
        embed = discord.Embed(
            title="📖 Commandes du bot",
            color=0x9146FF,
        )

        embed.add_field(
            name="🔨 Modération",
            value=(
                f"`{PREFIX}ban @membre [raison]` — Bannir un membre\n"
                f"`{PREFIX}unban <id>` — Débannir un utilisateur\n"
                f"`{PREFIX}kick @membre [raison]` — Expulser un membre\n"
                f"`{PREFIX}timeout @membre <minutes> [raison]` — Mettre en timeout\n"
                f"`{PREFIX}untimeout @membre` — Lever un timeout\n"
                f"`{PREFIX}warn @membre [raison]` — Avertir un membre\n"
            ),
            inline=False,
        )
        embed.add_field(
            name="📋 Historique (modérateurs)",
            value=(
                f"`{PREFIX}history [@membre]` — Voir les sanctions\n"
                f"`{PREFIX}delsanction <id>` — Supprimer une sanction (lève ban/timeout)\n"
            ),
            inline=False,
        )
        embed.add_field(
            name="📅 Planning (propriétaire)",
            value=(
                f"`{PREFIX}planning <contenu>` — Envoyer un planning dans le salon dédié\n"
                f"`{PREFIX}clearplanning [nombre]` — Supprimer des messages du planning\n"
                "\n**Format planning :**\n"
                "```\n"
                "!planning # Titre optionnel\n"
                "Lundi 20h - Minecraft\n"
                "Vendredi 21h - Fortnite\n"
                "```"
            ),
            inline=False,
        )
        embed.set_footer(text=f"Préfixe : {PREFIX} | Bot développé pour exotichazle")
        await ctx.send(embed=embed)

    async with bot:
        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
