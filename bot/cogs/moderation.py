import discord
from discord.ext import commands
from datetime import timedelta, datetime
import bot.database as db
from bot.config import MOD_ROLE_NAME, LOG_SANCTIONS_CHANNEL_ID, LOG_MESSAGES_CHANNEL_ID


async def send_sanction_log(guild: discord.Guild, sanction_type: str, member, moderator, reason: str, sanction_id: int, duration: int = None, lifted: bool = False):
    """Envoie un log dans le salon des sanctions."""
    log_ch = guild.get_channel(LOG_SANCTIONS_CHANNEL_ID)
    if not log_ch:
        return
    colors = {
        "ban": discord.Color.red(), "kick": discord.Color.orange(),
        "timeout": discord.Color.gold(), "warn": discord.Color.yellow(),
        "unban": discord.Color.green(), "untimeout": discord.Color.green(),
        "delsanction": discord.Color.green(),
    }
    labels = {
        "ban": "🔨 Bannissement", "kick": "👢 Expulsion", "timeout": "⏱️ Timeout",
        "warn": "⚠️ Avertissement", "unban": "✅ Déban", "untimeout": "✅ Timeout levé",
        "delsanction": "🗑️ Sanction supprimée",
    }
    embed = discord.Embed(
        title=labels.get(sanction_type, sanction_type),
        color=colors.get(sanction_type, discord.Color.greyple()),
        timestamp=datetime.utcnow(),
    )
    if hasattr(member, "mention"):
        embed.add_field(name="Membre", value=f"{member.mention} (`{member}`)", inline=True)
    else:
        embed.add_field(name="Membre", value=str(member), inline=True)
    embed.add_field(name="Modérateur", value=moderator.mention, inline=True)
    embed.add_field(name="Raison", value=reason or "Aucune", inline=False)
    if duration:
        embed.add_field(name="Durée", value=f"{duration} minute(s)", inline=True)
    embed.add_field(name="ID Sanction", value=f"#{sanction_id}", inline=True)
    if hasattr(member, "display_avatar"):
        embed.set_thumbnail(url=member.display_avatar.url)
    await log_ch.send(embed=embed)


def has_mod_role():
    async def predicate(ctx):
        role = discord.utils.get(ctx.guild.roles, name=MOD_ROLE_NAME)
        if role and role in ctx.author.roles:
            return True
        if await ctx.bot.is_owner(ctx.author):
            return True
        raise commands.MissingRole(MOD_ROLE_NAME)
    return commands.check(predicate)


SANCTION_COLORS = {
    "ban": discord.Color.red(),
    "kick": discord.Color.orange(),
    "timeout": discord.Color.gold(),
    "warn": discord.Color.yellow(),
}

TYPE_LABELS = {
    "ban": "🔨 Bannissement",
    "kick": "👢 Expulsion (Kick)",
    "timeout": "⏱️ Timeout",
    "warn": "⚠️ Avertissement",
}


async def send_sanction_dm(member: discord.Member, sanction_type: str, reason: str, guild_name: str, sanction_id: int, duration: int = None):
    """Envoie un DM à la personne sanctionnée."""
    try:
        embed = discord.Embed(
            title=f"{TYPE_LABELS.get(sanction_type, sanction_type)} sur **{guild_name}**",
            color=SANCTION_COLORS.get(sanction_type, discord.Color.greyple()),
        )
        embed.add_field(name="Raison", value=reason or "Aucune raison fournie", inline=False)
        if duration and sanction_type == "timeout":
            embed.add_field(name="Durée", value=f"{duration} minute(s)", inline=False)
        embed.add_field(name="Référence sanction", value=f"#{sanction_id}", inline=False)
        embed.set_footer(text=f"Serveur : {guild_name}")
        await member.send(embed=embed)
    except discord.Forbidden:
        pass  # DMs désactivés par l'utilisateur


class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ─── BAN ────────────────────────────────────────────────────────────────

    @commands.command(name="ban")
    @has_mod_role()
    @commands.bot_has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason: str = "Aucune raison fournie"):
        """Bannit un membre du serveur."""
        if member == ctx.author:
            return await ctx.send("❌ Tu ne peux pas te bannir toi-même.")
        if member.top_role >= ctx.author.top_role and not await self.bot.is_owner(ctx.author):
            return await ctx.send("❌ Tu ne peux pas bannir quelqu'un avec un rôle supérieur ou égal au tien.")

        await member.ban(reason=reason)
        sanction_id = await db.add_sanction(
            member.id, str(member), ctx.guild.id,
            ctx.author.id, str(ctx.author), "ban", reason
        )
        await send_sanction_dm(member, "ban", reason, ctx.guild.name, sanction_id)
        await send_sanction_log(ctx.guild, "ban", member, ctx.author, reason, sanction_id)

        embed = discord.Embed(
            title="🔨 Membre banni",
            color=discord.Color.red(),
            description=f"**{member}** a été banni."
        )
        embed.add_field(name="Raison", value=reason, inline=False)
        embed.add_field(name="Modérateur", value=ctx.author.mention, inline=True)
        embed.add_field(name="ID Sanction", value=f"#{sanction_id}", inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(name="unban")
    @has_mod_role()
    @commands.bot_has_permissions(ban_members=True)
    async def unban(self, ctx, user_id: int, *, reason: str = "Aucune raison fournie"):
        """Débannit un utilisateur par son ID."""
        try:
            user = await self.bot.fetch_user(user_id)
            await ctx.guild.unban(user, reason=reason)
            await send_sanction_log(ctx.guild, "unban", user, ctx.author, reason, 0)
            embed = discord.Embed(
                title="✅ Membre débanni",
                color=discord.Color.green(),
                description=f"**{user}** a été débanni."
            )
            embed.add_field(name="Raison", value=reason)
            await ctx.send(embed=embed)
        except discord.NotFound:
            await ctx.send("❌ Cet utilisateur n'est pas banni ou n'existe pas.")

    # ─── KICK ───────────────────────────────────────────────────────────────

    @commands.command(name="kick")
    @has_mod_role()
    @commands.bot_has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: str = "Aucune raison fournie"):
        """Expulse un membre du serveur."""
        if member == ctx.author:
            return await ctx.send("❌ Tu ne peux pas te kick toi-même.")
        if member.top_role >= ctx.author.top_role and not await self.bot.is_owner(ctx.author):
            return await ctx.send("❌ Tu ne peux pas kick quelqu'un avec un rôle supérieur ou égal au tien.")

        await member.kick(reason=reason)
        sanction_id = await db.add_sanction(
            member.id, str(member), ctx.guild.id,
            ctx.author.id, str(ctx.author), "kick", reason
        )
        await send_sanction_dm(member, "kick", reason, ctx.guild.name, sanction_id)
        await send_sanction_log(ctx.guild, "kick", member, ctx.author, reason, sanction_id)

        embed = discord.Embed(
            title="👢 Membre expulsé",
            color=discord.Color.orange(),
            description=f"**{member}** a été expulsé."
        )
        embed.add_field(name="Raison", value=reason, inline=False)
        embed.add_field(name="Modérateur", value=ctx.author.mention, inline=True)
        embed.add_field(name="ID Sanction", value=f"#{sanction_id}", inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    # ─── TIMEOUT ────────────────────────────────────────────────────────────

    @commands.command(name="timeout", aliases=["mute", "to"])
    @has_mod_role()
    @commands.bot_has_permissions(moderate_members=True)
    async def timeout(self, ctx, member: discord.Member, duration: int, *, reason: str = "Aucune raison fournie"):
        """Met un membre en timeout. Durée en minutes (max 40320 = 28 jours)."""
        if member == ctx.author:
            return await ctx.send("❌ Tu ne peux pas te mettre en timeout toi-même.")
        if member.top_role >= ctx.author.top_role and not await self.bot.is_owner(ctx.author):
            return await ctx.send("❌ Tu ne peux pas timeout quelqu'un avec un rôle supérieur ou égal au tien.")
        if duration < 1 or duration > 40320:
            return await ctx.send("❌ La durée doit être entre 1 et 40320 minutes (28 jours).")

        until = discord.utils.utcnow() + timedelta(minutes=duration)
        await member.timeout(until, reason=reason)
        sanction_id = await db.add_sanction(
            member.id, str(member), ctx.guild.id,
            ctx.author.id, str(ctx.author), "timeout", reason, duration
        )
        await send_sanction_dm(member, "timeout", reason, ctx.guild.name, sanction_id, duration)
        await send_sanction_log(ctx.guild, "timeout", member, ctx.author, reason, sanction_id, duration)

        embed = discord.Embed(
            title="⏱️ Membre en timeout",
            color=discord.Color.gold(),
            description=f"**{member}** a été mis en timeout."
        )
        embed.add_field(name="Durée", value=f"{duration} minute(s)", inline=True)
        embed.add_field(name="Raison", value=reason, inline=False)
        embed.add_field(name="Modérateur", value=ctx.author.mention, inline=True)
        embed.add_field(name="ID Sanction", value=f"#{sanction_id}", inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(name="untimeout", aliases=["unmute", "unto"])
    @has_mod_role()
    @commands.bot_has_permissions(moderate_members=True)
    async def untimeout(self, ctx, member: discord.Member, *, reason: str = "Levée manuelle"):
        """Retire le timeout d'un membre."""
        await member.timeout(None, reason=reason)
        await send_sanction_log(ctx.guild, "untimeout", member, ctx.author, reason, 0)
        await ctx.send(f"✅ Le timeout de **{member}** a été levé.")

    # ─── WARN ───────────────────────────────────────────────────────────────

    @commands.command(name="warn", aliases=["avertir"])
    @has_mod_role()
    async def warn(self, ctx, member: discord.Member, *, reason: str = "Aucune raison fournie"):
        """Avertit un membre."""
        if member == ctx.author:
            return await ctx.send("❌ Tu ne peux pas t'avertir toi-même.")

        sanction_id = await db.add_sanction(
            member.id, str(member), ctx.guild.id,
            ctx.author.id, str(ctx.author), "warn", reason
        )
        await send_sanction_dm(member, "warn", reason, ctx.guild.name, sanction_id)
        await send_sanction_log(ctx.guild, "warn", member, ctx.author, reason, sanction_id)

        embed = discord.Embed(
            title="⚠️ Avertissement",
            color=discord.Color.yellow(),
            description=f"**{member}** a reçu un avertissement."
        )
        embed.add_field(name="Raison", value=reason, inline=False)
        embed.add_field(name="Modérateur", value=ctx.author.mention, inline=True)
        embed.add_field(name="ID Sanction", value=f"#{sanction_id}", inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    # ─── PURGE ──────────────────────────────────────────────────────────────

    @commands.command(name="purge", aliases=["clear", "nettoyer"])
    @has_mod_role()
    @commands.bot_has_permissions(manage_messages=True)
    async def purge(self, ctx, amount: int, member: discord.Member = None):
        """Supprime des messages dans le salon. Filtre optionnel par membre.
        Usage : <<purge <nombre> [@membre]"""
        if amount < 1 or amount > 1000:
            return await ctx.send(
                "❌ Le nombre de messages doit être compris entre **1** et **1000**.",
                delete_after=5,
            )

        await ctx.message.delete()

        if member:
            # Compte les suppressions pour respecter la limite demandée
            count = 0
            scan_limit = min(amount * 10, 2000)

            def member_check(msg):
                nonlocal count
                if msg.author == member and not msg.pinned and count < amount:
                    count += 1
                    return True
                return False

            deleted = await ctx.channel.purge(
                limit=scan_limit,
                check=member_check,
                bulk=True,
                reason=f"Purge par {ctx.author} — messages de {member}",
            )
        else:
            deleted = await ctx.channel.purge(
                limit=amount,
                check=lambda m: not m.pinned,
                bulk=True,
                reason=f"Purge par {ctx.author}",
            )

        n = len(deleted)

        # ── Confirmation éphémère ──────────────────────────────────────────
        if member:
            msg = f"✅ **{n}** message(s) de **{member}** supprimé(s) dans {ctx.channel.mention}."
        else:
            msg = f"✅ **{n}** message(s) supprimé(s) dans {ctx.channel.mention}."
        await ctx.send(msg, delete_after=6)

        # ── Log dans le salon messages ─────────────────────────────────────
        log_ch = ctx.guild.get_channel(LOG_MESSAGES_CHANNEL_ID)
        if log_ch:
            embed = discord.Embed(
                title="🗑️ Purge de messages",
                color=discord.Color.red(),
                timestamp=datetime.utcnow(),
            )
            embed.add_field(name="Salon", value=ctx.channel.mention, inline=True)
            embed.add_field(name="Modérateur", value=ctx.author.mention, inline=True)
            embed.add_field(name="Messages supprimés", value=str(n), inline=True)
            if member:
                embed.add_field(name="Filtré sur", value=f"{member.mention} (`{member}`)", inline=True)
            await log_ch.send(embed=embed)

    # ─── HISTORIQUE ─────────────────────────────────────────────────────────

    @commands.command(name="history", aliases=["historique", "sanctions"])
    @has_mod_role()
    async def history(self, ctx, member: discord.Member = None):
        """Affiche l'historique des sanctions. Utilise @membre pour filtrer."""
        sanctions = await db.get_sanctions(ctx.guild.id, member.id if member else None)

        if not sanctions:
            target = f"de **{member}**" if member else "du serveur"
            return await ctx.send(f"📭 Aucune sanction trouvée {target}.")

        title = f"📋 Sanctions de {member}" if member else "📋 Historique des sanctions"
        embed = discord.Embed(title=title, color=discord.Color.blurple())

        shown = sanctions[:10]
        for s in shown:
            status = "✅ Active" if s["active"] else "❌ Levée"
            dur = f" | {s['duration']}min" if s["duration"] else ""
            label = TYPE_LABELS.get(s["type"], s["type"])
            value = (
                f"**Membre:** {s['user_name']}\n"
                f"**Raison:** {s['reason'] or 'Aucune'}\n"
                f"**Modérateur:** {s['moderator_name']}\n"
                f"**Date:** {s['created_at'][:16]}{dur}\n"
                f"**Statut:** {status}"
            )
            embed.add_field(name=f"#{s['id']} — {label}", value=value, inline=False)

        if len(sanctions) > 10:
            embed.set_footer(text=f"Affichage des 10 dernières sur {len(sanctions)} sanctions.")
        await ctx.send(embed=embed)

    # ─── SUPPRIMER SANCTION ─────────────────────────────────────────────────

    @commands.command(name="delsanction", aliases=["removesanction", "supprimersanction"])
    @has_mod_role()
    async def delsanction(self, ctx, sanction_id: int):
        """Supprime une sanction par son ID. Lève automatiquement le ban/timeout associé."""
        sanction = await db.get_sanction_by_id(sanction_id, ctx.guild.id)

        if not sanction:
            return await ctx.send(f"❌ Aucune sanction #{sanction_id} trouvée sur ce serveur.")

        if not sanction["active"]:
            return await ctx.send(f"⚠️ La sanction #{sanction_id} est déjà inactive.")

        label = TYPE_LABELS.get(sanction["type"], sanction["type"])
        lifted_msg = ""
        reversal_ok = True

        # Tenter de lever la sanction Discord AVANT de désactiver en BDD
        if sanction["type"] == "ban":
            try:
                user = await self.bot.fetch_user(sanction["user_id"])
                await ctx.guild.unban(user, reason=f"Sanction #{sanction_id} supprimée par {ctx.author}")
                lifted_msg = "\n✅ **Le bannissement a été levé automatiquement.**"
            except discord.NotFound:
                lifted_msg = "\n⚠️ L'utilisateur n'était plus banni (déjà levé)."
            except discord.HTTPException as e:
                lifted_msg = f"\n⚠️ Impossible de lever le ban : {e}"
                reversal_ok = False

        elif sanction["type"] == "timeout":
            try:
                # Essayer d'abord depuis le cache, sinon fetch
                member = ctx.guild.get_member(sanction["user_id"])
                if member is None:
                    try:
                        member = await ctx.guild.fetch_member(sanction["user_id"])
                    except discord.NotFound:
                        member = None

                if member is not None and member.is_timed_out():
                    await member.timeout(None, reason=f"Sanction #{sanction_id} supprimée par {ctx.author}")
                    lifted_msg = "\n✅ **Le timeout a été levé automatiquement.**"
                elif member is None:
                    lifted_msg = "\n⚠️ Membre introuvable sur le serveur (peut avoir quitté)."
                else:
                    lifted_msg = "\n⚠️ Le timeout était déjà expiré."
            except discord.HTTPException as e:
                lifted_msg = f"\n⚠️ Impossible de lever le timeout : {e}"
                reversal_ok = False

        # Désactiver en BDD seulement si la levée a réussi (ou si c'était déjà levé)
        if reversal_ok:
            await db.deactivate_sanction(sanction_id, ctx.guild.id)
            await send_sanction_log(ctx.guild, "delsanction", sanction["user_name"], ctx.author, sanction["reason"] or "Aucune", sanction_id)
        else:
            lifted_msg += "\n❌ **La sanction reste active en base de données** car la levée Discord a échoué."

        embed = discord.Embed(
            title=f"🗑️ Sanction #{sanction_id} supprimée",
            color=discord.Color.green(),
            description=(
                f"**Type :** {label}\n"
                f"**Membre :** {sanction['user_name']}\n"
                f"**Raison originale :** {sanction['reason'] or 'Aucune'}\n"
                f"**Supprimée par :** {ctx.author.mention}"
                + lifted_msg
            ),
        )
        await ctx.send(embed=embed)

    # ─── GESTION DES ERREURS ────────────────────────────────────────────────

    @ban.error
    @kick.error
    @timeout.error
    @warn.error
    @purge.error
    @history.error
    @delsanction.error
    async def mod_error(self, ctx, error):
        if isinstance(error, commands.MissingRole):
            await ctx.send(f"❌ Tu n'as pas la permission d'utiliser cette commande.")
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("❌ Membre introuvable. Mentionne un membre valide.")
        elif isinstance(error, commands.BadArgument):
            await ctx.send(f"❌ Argument invalide : {error}")
        elif isinstance(error, commands.BotMissingPermissions):
            await ctx.send(f"❌ Je n'ai pas les permissions nécessaires : {error.missing_permissions}")
        else:
            await ctx.send(f"❌ Une erreur est survenue : {error}")


async def setup(bot):
    await bot.add_cog(Moderation(bot))
