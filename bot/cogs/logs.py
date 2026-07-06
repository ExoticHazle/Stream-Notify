import discord
from discord.ext import commands
from datetime import datetime
import re
from bot.config import (
    LOG_MESSAGES_CHANNEL_ID,
    LOG_MEMBRES_CHANNEL_ID,
    IMAGES_ONLY_CHANNEL_ID,
    PROTECTED_FROM_PING_ID,
)


def is_bot_or_system(user) -> bool:
    return user.bot if user else True


PING_PATTERN = re.compile(rf"<@!?{PROTECTED_FROM_PING_ID}>")


class Logs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._webhook_cache: dict[int, discord.Webhook] = {}  # channel_id → webhook

    async def _get_webhook(self, channel: discord.TextChannel) -> discord.Webhook | None:
        """Retourne le webhook du bot pour ce salon, en crée un si besoin."""
        if channel.id in self._webhook_cache:
            return self._webhook_cache[channel.id]
        try:
            hooks = await channel.webhooks()
            wh = discord.utils.get(hooks, user=self.bot.user)
            if not wh:
                wh = await channel.create_webhook(name=self.bot.user.display_name)
            self._webhook_cache[channel.id] = wh
            return wh
        except discord.HTTPException:
            return None

    # ─── Utilitaire ──────────────────────────────────────────────────────────

    async def get_log_channel(self, guild: discord.Guild, channel_id: int):
        ch = guild.get_channel(channel_id)
        return ch

    # ─── on_message : images-only + protection ping ───────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not message.guild:
            return

        # ── 1. Salon images uniquement ────────────────────────────────────────
        if message.channel.id == IMAGES_ONLY_CHANNEL_ID:
            has_image = any(
                att.content_type and att.content_type.startswith("image/")
                for att in message.attachments
            )
            if not has_image:
                try:
                    await message.delete()
                except discord.HTTPException:
                    pass
            return  # pas besoin de vérifier le ping dans ce salon

        # ── 2. Protection anti-ping ───────────────────────────────────────────
        if not PING_PATTERN.search(message.content):
            return

        # Remplacer la mention par le nom affiché (sans ping)
        try:
            target = message.guild.get_member(PROTECTED_FROM_PING_ID) or \
                     await message.guild.fetch_member(PROTECTED_FROM_PING_ID)
            display = f"@{target.display_name}"
        except discord.HTTPException:
            display = f"@user"

        clean_content = PING_PATTERN.sub(display, message.content)

        # Récupérer les fichiers attachés avant de supprimer
        files = []
        for att in message.attachments:
            try:
                files.append(await att.to_file())
            except discord.HTTPException:
                pass

        # Supprimer le message original (le ping est envoyé ici — on doit agir vite)
        try:
            await message.delete()
        except discord.HTTPException:
            return  # Si on ne peut pas supprimer, on n'envoie pas de doublon

        # Resend via webhook en usurpant l'identité de l'auteur (nom + avatar)
        wh = await self._get_webhook(message.channel)
        if wh:
            await wh.send(
                content=clean_content or None,
                username=message.author.display_name,
                avatar_url=message.author.display_avatar.url,
                files=files,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        else:
            # Fallback : le bot renvoie le message en précisant l'auteur
            author_tag = message.author.mention
            await message.channel.send(
                f"{author_tag} : {clean_content}",
                files=files,
                allowed_mentions=discord.AllowedMentions(users=[message.author]),
            )

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
