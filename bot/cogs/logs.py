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

    async def get_log_channel(self, guild: discord.Guild, channel_id: int):
        return guild.get_channel(channel_id)

    # ─── Salon images uniquement ──────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not message.guild:
            return
        if message.channel.id != IMAGES_ONLY_CHANNEL_ID:
            return

        has_image = any(
            att.content_type and att.content_type.startswith("image/")
            for att in message.attachments
        )
        if not has_image:
            try:
                await message.delete()
            except discord.HTTPException:
                pass

    # ─── Messages édités ──────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild:
            return
        if is_bot_or_system(before.author):
            return
        if before.content == after.content:
            return

        log_ch = await self.get_log_channel(before.guild, LOG_MESSAGES_CHANNEL_ID)
        if not log_ch:
            return

        embed = discord.Embed(
            title="✏️ Message modifié",
            color=discord.Color.orange(),
            timestamp=datetime.utcnow(),
        )
        embed.set_author(name=str(before.author), icon_url=before.author.display_avatar.url)
        embed.add_field(name="Salon", value=before.channel.mention, inline=True)
        embed.add_field(name="Auteur", value=before.author.mention, inline=True)
        embed.add_field(name="Avant", value=before.content[:1024] or "*(vide)*", inline=False)
        embed.add_field(name="Après", value=after.content[:1024] or "*(vide)*", inline=False)
        embed.add_field(name="Lien", value=f"[Aller au message]({after.jump_url})", inline=False)
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
        embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
        embed.add_field(name="Salon", value=message.channel.mention, inline=True)
        embed.add_field(name="Auteur", value=message.author.mention, inline=True)
        embed.add_field(name="Contenu", value=message.content[:1024] or "*(vide)*", inline=False)
        if message.attachments:
            embed.add_field(
                name="Pièces jointes",
                value="\n".join(a.filename for a in message.attachments),
                inline=False,
            )
        await log_ch.send(embed=embed)

    # ─── Réactions ajoutées ───────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.Member | discord.User):
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
            color=discord.Color.green(),
            timestamp=datetime.utcnow(),
        )
        embed.add_field(name="Réaction", value=str(reaction.emoji), inline=True)
        embed.add_field(name="Salon", value=reaction.message.channel.mention, inline=True)
        embed.add_field(name="Par", value=user.mention, inline=True)
        embed.add_field(
            name="Message",
            value=f"[Voir]({reaction.message.jump_url})",
            inline=False,
        )
        await log_ch.send(embed=embed)

    # ─── Membre rejoint ───────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        log_ch = await self.get_log_channel(member.guild, LOG_MEMBRES_CHANNEL_ID)
        if not log_ch:
            return

        embed = discord.Embed(
            title="✅ Membre rejoint",
            color=discord.Color.green(),
            timestamp=datetime.utcnow(),
        )
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        embed.add_field(name="Membre", value=member.mention, inline=True)
        embed.add_field(name="ID", value=str(member.id), inline=True)
        created = discord.utils.format_dt(member.created_at, style="R")
        embed.add_field(name="Compte créé", value=created, inline=False)
        await log_ch.send(embed=embed)

    # ─── Membre quitte ────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        log_ch = await self.get_log_channel(member.guild, LOG_MEMBRES_CHANNEL_ID)
        if not log_ch:
            return

        roles = [r.mention for r in member.roles if r.name != "@everyone"]
        embed = discord.Embed(
            title="❌ Membre parti",
            color=discord.Color.red(),
            timestamp=datetime.utcnow(),
        )
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        embed.add_field(name="Membre", value=str(member), inline=True)
        embed.add_field(name="ID", value=str(member.id), inline=True)
        embed.add_field(
            name=f"Rôles ({len(roles)})",
            value=" ".join(roles)[:1024] if roles else "*(aucun)*",
            inline=False,
        )
        await log_ch.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Logs(bot))
