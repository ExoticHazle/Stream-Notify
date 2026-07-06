import discord
from discord.ext import commands
from datetime import datetime
from bot.config import PLANNING_CHANNEL_ID


class Planning(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="planning", aliases=["schedule", "calendrier"])
    @commands.is_owner()
    async def planning(self, ctx, *, contenu: str = None):
        """
        [OWNER ONLY] Crée et envoie un planning de stream dans le salon dédié.

        Utilisation :
          !planning Lundi 20h - Minecraft
                    Mercredi 21h - Fortnite
                    Vendredi 20h30 - Valorant

        Ou avec un titre personnalisé (première ligne = titre si elle commence par #) :
          !planning # Planning semaine du 7 juillet
                    Lundi 20h - Minecraft
                    Vendredi 21h - GTA RP
        """
        if not contenu:
            return await ctx.send(
                "❌ Tu dois fournir le contenu du planning.\n"
                "**Exemple :**\n"
                "```\n"
                "!planning Lundi 20h - Minecraft\n"
                "Mercredi 21h - Fortnite\n"
                "Vendredi 20h30 - Valorant\n"
                "```\n"
                "Tu peux aussi mettre un titre en première ligne en commençant par `#` :\n"
                "```\n"
                "!planning # Planning semaine du 7 juillet\n"
                "Lundi 20h - Minecraft\n"
                "```"
            )

        lignes = contenu.strip().split("\n")
        titre = f"📅 Planning de Stream — {PLANNING_CHANNEL_ID}"
        entries = lignes

        # Détection d'un titre personnalisé (ligne commençant par #)
        if lignes[0].startswith("#"):
            titre_brut = lignes[0].lstrip("#").strip()
            titre = f"📅 {titre_brut}"
            entries = lignes[1:]

        canal = self.bot.get_channel(PLANNING_CHANNEL_ID)
        if not canal:
            return await ctx.send(
                f"❌ Impossible de trouver le salon de planning (ID: {PLANNING_CHANNEL_ID})."
            )

        embed = discord.Embed(
            title=titre,
            color=0x9146FF,
            timestamp=datetime.utcnow(),
        )

        # Formatage des entrées du planning
        planning_text = ""
        for ligne in entries:
            ligne = ligne.strip()
            if not ligne:
                continue
            # Séparateur " - " entre jour/heure et activité
            if " - " in ligne:
                parts = ligne.split(" - ", 1)
                planning_text += f"🕐 **{parts[0].strip()}** — {parts[1].strip()}\n"
            else:
                planning_text += f"• {ligne}\n"

        if not planning_text:
            return await ctx.send("❌ Le planning est vide après traitement. Vérifie le format.")

        embed.description = planning_text
        embed.set_footer(
            text=f"Planning posté par {ctx.author.display_name}",
            icon_url=ctx.author.display_avatar.url,
        )

        # Supprimer le message de commande pour garder le salon propre
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass

        await canal.send(embed=embed)
        await ctx.author.send(f"✅ Ton planning a bien été posté dans <#{PLANNING_CHANNEL_ID}> !")

    @planning.error
    async def planning_error(self, ctx, error):
        if isinstance(error, commands.NotOwner):
            await ctx.send("❌ Cette commande est réservée au propriétaire du bot.")
        else:
            await ctx.send(f"❌ Erreur : {error}")

    @commands.command(name="clearplanning", aliases=["deleteplanning"])
    @commands.is_owner()
    async def clearplanning(self, ctx, nombre: int = 10):
        """[OWNER ONLY] Supprime les X derniers messages du salon planning (défaut: 10)."""
        canal = self.bot.get_channel(PLANNING_CHANNEL_ID)
        if not canal:
            return await ctx.send("❌ Salon de planning introuvable.")

        deleted = await canal.purge(limit=nombre, check=lambda m: m.author == self.bot.user)
        await ctx.send(f"✅ {len(deleted)} message(s) supprimé(s) du planning.", delete_after=5)
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass

    @clearplanning.error
    async def clearplanning_error(self, ctx, error):
        if isinstance(error, commands.NotOwner):
            await ctx.send("❌ Cette commande est réservée au propriétaire du bot.")


async def setup(bot):
    await bot.add_cog(Planning(bot))
