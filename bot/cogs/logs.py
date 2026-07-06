import discord
from discord.ext import commands
from datetime import datetime
from bot.config import (
    LOG_MESSAGES_CHANNEL_ID,
    LOG_MEMBRES_CHANNEL_ID,
    IMAGES_ONLY_CHANNEL_ID,
)


def is_bot_or_system(user) -> bool:
    return user.bot if user else True


class Logs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ─── Utilitaire ──────────────────────────────────────────────────────────

    async def get_log_channel(self, guild: discord.Guild, channel_id: int):
        ch = guild.get_channel(channel_id)
        return ch

    # ─── Salon images uniquement ─────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not message.guild:
            return
        if message.channel.id != IMAGES_ONLY_CHANNEL_ID:
            return

        # Vérifie qu'au moins une pièce jointe est une image
        has_image = any(
            att.content_type and att.content_type.startswith("image/")
            for att in message.attachments
        )
        if not has_image:
            try:
                await message.delete()
            except discord.HTTPException:
                pass

    # ─── Messages édités ─────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild:
            return
        if is_bot_or_system(before.author):
            return
        if before.content == after.content:
            return  # Pas de changement de texte (ex: embed chargé)

        log_ch = await self.get_log_channel(before.guild, LOG_MESSAGES_CHANNEL_ID)
        if not log_ch:
            return

        embed = discord.Embed(
            title="✏️ Message modifié",
            color=discord.Color.orange(),
            timestamp=datetime.utcnow(),
        )
        embed.set_author(
            name=str(before.author),
            icon_url=before.author.display_avatar.url,
        )
        embed.add_field(name="Salon", value=before.channel.mention, inline=True)
        embed.add_field(name="Auteur", value=before.author.mention, inline=True)
        embed.add_field(
            name="Avant",
            value=before.content[:1024] if before.content else "*vide*",
            inline=False,
        )
        embed.add_field(
            name="Après",
            value=after.content[:1024] if after.content else "*vide*",
            inline=False,
        )
        embed.add_field(
            name="Lien",
            value=f"[Voir le message]({after.jump_url})",
            inline=False,
        )
        embed.set_footer(text=f"ID utilisateur : {before.author.id}")
        await log_ch.send(embed=embed)

    # ─── Messages supprimés ───────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild:
            return
        if is_bot_or_system(message.author):
            return

        log_ch = await self.get_log_channel(message.guild, LOG_MESSAGES_CHANNEL_ID)
        if not log_ch:
            return

        embed = discord.Embed(
            title="🗑️ Message supprimé",
            color=discord.Color.red(),
            timestamp=datetime.utcnow(),
        )
        embed.set_author(
            name=str(message.author),
            icon_url=message.author.display_avatar.url,
        )
        embed.add_field(name="Salon", value=message.channel.mention, inline=True)
        embed.add_field(name="Auteur", value=message.author.mention, inline=True)
        embed.add_field(
            name="Contenu",
            value=message.content[:1024] if message.content else "*message sans texte*",
            inline=False,
        )
        if message.attachments:
            embed.add_field(
                name="Pièces jointes",
                value="\n".join(a.filename for a in message.attachments),
                inline=False,
            )
        embed.set_footer(text=f"ID utilisateur : {message.author.id}")
        await log_ch.send(embed=embed)

    # ─── Réactions ajoutées ───────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.Member | discord.User):
        # Utiliser le guild du message, pas de user (user peut être un User non-Member)
        guild = reaction.message.guild
        if not guild:
            return
        if is_bot_or_system(user):
            return

        log_ch = await self.get_log_channel(guild, LOG_MESSAGES_CHANNEL_ID)
        if not log_ch:
            return

        embed = discord.Embed(
            title="😀 Réaction ajoutée",
            color=discord.Color.teal(),
            timestamp=datetime.utcnow(),
        )
        embed.set_author(name=str(user), icon_url=user.display_avatar.url)
        embed.add_field(name="Réaction", value=str(reaction.emoji), inline=True)
        embed.add_field(name="Salon", value=reaction.message.channel.mention, inline=True)
        embed.add_field(name="Auteur du message", value=reaction.message.author.mention, inline=True)
        embed.add_field(
            name="Lien",
            value=f"[Voir le message]({reaction.message.jump_url})",
            inline=False,
        )
        embed.set_footer(text=f"ID utilisateur : {user.id}")
        await log_ch.send(embed=embed)

    # ─── Membre rejoint ───────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        log_ch = await self.get_log_channel(member.guild, LOG_MEMBRES_CHANNEL_ID)
        if not log_ch:
            return

        # Compte le nombre de membres
        member_count = member.guild.member_count

        embed = discord.Embed(
            title="✅ Nouveau membre",
            description=f"{member.mention} a rejoint le serveur !",
            color=discord.Color.green(),
            timestamp=datetime.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Compte créé le", value=member.created_at.strftime("%d/%m/%Y"), inline=True)
        embed.add_field(name="Membres total", value=str(member_count), inline=True)
        embed.set_footer(text=f"ID : {member.id}")
        await log_ch.send(embed=embed)

    # ─── Membre parti ─────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        log_ch = await self.get_log_channel(member.guild, LOG_MEMBRES_CHANNEL_ID)
        if not log_ch:
            return

        roles = [r.mention for r in member.roles if r.name != "@everyone"]
        roles_str = ", ".join(roles) if roles else "Aucun"

        embed = discord.Embed(
            title="❌ Membre parti",
            description=f"**{member}** a quitté le serveur.",
            color=discord.Color.red(),
            timestamp=datetime.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Rôles", value=roles_str[:1024], inline=False)
        embed.add_field(
            name="A rejoint le",
            value=member.joined_at.strftime("%d/%m/%Y") if member.joined_at else "Inconnu",
            inline=True,
        )
        embed.set_footer(text=f"ID : {member.id}")
        await log_ch.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Logs(bot))
