import discord
from discord.ext import commands
from discord import ui
import io
from datetime import datetime
import aiosqlite
import bot.database as db
from bot.config import (
    TICKET_DISCORD_ROLE_ID,
    TICKET_TWITCH_ROLE_ID,
    TICKET_PANEL_CHANNEL_ID,
    TICKET_CATEGORY_ID,
    LOG_TICKETS_CHANNEL_ID,
    MOD_ROLE_NAME,
)

# ─── Helpers ────────────────────────────────────────────────────────────────

TICKET_TYPES = {
    "discord": {
        "label": "Discord",
        "emoji": "💬",
        "color": discord.Color.blurple(),
        "role_id": TICKET_DISCORD_ROLE_ID,
        "description": "Problème ou question concernant le serveur Discord",
    },
    "twitch": {
        "label": "Twitch",
        "emoji": "🟣",
        "color": discord.Color.purple(),
        "role_id": TICKET_TWITCH_ROLE_ID,
        "description": "Problème ou question concernant le Twitch",
    },
}


async def get_ticket_count(guild_id: int) -> int:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM tickets WHERE guild_id = ?", (guild_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


async def save_ticket(channel_id, user_id, user_name, guild_id, ticket_type):
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute(
            """INSERT INTO tickets (channel_id, user_id, user_name, guild_id, type, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'open', datetime('now'))""",
            (channel_id, user_id, user_name, guild_id, ticket_type),
        )
        await conn.commit()


async def close_ticket_db(channel_id: int):
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute(
            "UPDATE tickets SET status='closed', closed_at=datetime('now') WHERE channel_id=?",
            (channel_id,),
        )
        await conn.commit()


async def get_ticket_info(channel_id: int):
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM tickets WHERE channel_id=?", (channel_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def generate_transcript(channel: discord.TextChannel) -> io.BytesIO:
    """Génère un fichier texte avec tous les messages du salon ticket."""
    lines = [
        f"=== TRANSCRIPT — #{channel.name} ===",
        f"Généré le : {datetime.utcnow().strftime('%d/%m/%Y à %H:%M')} UTC",
        "=" * 50,
        "",
    ]
    async for msg in channel.history(limit=None, oldest_first=True):
        timestamp = msg.created_at.strftime("%d/%m/%Y %H:%M")
        content = msg.content or "[message sans texte]"
        lines.append(f"[{timestamp}] {msg.author} : {content}")
        for attachment in msg.attachments:
            lines.append(f"  📎 Pièce jointe : {attachment.url}")
        for embed in msg.embeds:
            if embed.title:
                lines.append(f"  📋 Embed : {embed.title}")
    lines += ["", "=" * 50, "Fin du transcript."]
    content = "\n".join(lines)
    return io.BytesIO(content.encode("utf-8"))


# ─── Views persistantes ──────────────────────────────────────────────────────

class TicketPanelView(ui.View):
    """Bouton affiché dans le salon panel — persistent."""

    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(
        label="🎫 Créer un ticket",
        style=discord.ButtonStyle.primary,
        custom_id="persistent:ticket_create",
    )
    async def create_ticket(self, interaction: discord.Interaction, button: ui.Button):
        # Vérifier si l'utilisateur a déjà un ticket ouvert
        async with aiosqlite.connect(db.DB_PATH) as conn:
            cursor = await conn.execute(
                "SELECT channel_id FROM tickets WHERE user_id=? AND guild_id=? AND status='open'",
                (interaction.user.id, interaction.guild.id),
            )
            existing = await cursor.fetchone()

        if existing:
            ch = interaction.guild.get_channel(existing[0])
            if ch:
                return await interaction.response.send_message(
                    f"❌ Tu as déjà un ticket ouvert : {ch.mention}",
                    ephemeral=True,
                )

        await interaction.response.send_message(
            "Quel type de ticket souhaites-tu ouvrir ?",
            view=TicketTypeView(),
            ephemeral=True,
        )


class TicketTypeView(ui.View):
    """Sélection Discord / Twitch — non persistante (éphémère)."""

    def __init__(self):
        super().__init__(timeout=60)

    async def _open(self, interaction: discord.Interaction, ticket_type: str):
        await interaction.response.defer(ephemeral=True)
        info = TICKET_TYPES[ticket_type]
        guild = interaction.guild
        user = interaction.user

        # Revalidation au moment de la création (protection contre les clics simultanés)
        async with aiosqlite.connect(db.DB_PATH) as conn:
            cursor = await conn.execute(
                "SELECT channel_id FROM tickets WHERE user_id=? AND guild_id=? AND status='open'",
                (user.id, guild.id),
            )
            existing = await cursor.fetchone()
        if existing:
            ch = guild.get_channel(existing[0])
            msg = f"❌ Tu as déjà un ticket ouvert : {ch.mention}" if ch else "❌ Tu as déjà un ticket ouvert."
            return await interaction.followup.send(msg, ephemeral=True)

        # Permissions du salon
        mod_role = discord.utils.get(guild.roles, name=MOD_ROLE_NAME)
        ping_role = guild.get_role(info["role_id"])
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, manage_channels=True,
                attach_files=True, embed_links=True, read_message_history=True,
            ),
            user: discord.PermissionOverwrite(
                view_channel=True, send_messages=True,
                attach_files=True, read_message_history=True,
            ),
        }
        if mod_role:
            overwrites[mod_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True,
                attach_files=True, read_message_history=True, manage_messages=True,
            )

        # Chercher/créer la catégorie Tickets
        category = guild.get_channel(TICKET_CATEGORY_ID)

        ticket_num = await get_ticket_count(guild.id) + 1
        channel_name = f"ticket-{user.name.lower().replace(' ', '-')}-{ticket_num:04d}"
        channel = await guild.create_text_channel(
            channel_name, overwrites=overwrites, category=category,
            reason=f"Ticket {ticket_type} ouvert par {user}",
        )

        await save_ticket(channel.id, user.id, str(user), guild.id, ticket_type)

        # Message de bienvenue
        embed = discord.Embed(
            title=f"{info['emoji']} Ticket {info['label']} #{ticket_num:04d}",
            description=(
                f"Bonjour {user.mention} !\n\n"
                f"Ton ticket **{info['label']}** a bien été créé.\n"
                "Décris ton problème ou ta question, l'équipe te répondra rapidement.\n\n"
                "Clique sur **🔒 Fermer le ticket** quand ton problème est résolu."
            ),
            color=info["color"],
            timestamp=datetime.utcnow(),
        )
        embed.set_footer(text=f"Ticket #{ticket_num:04d} — {user}")

        ping_mention = ping_role.mention if ping_role else ""
        await channel.send(
            content=f"{user.mention} {ping_mention}",
            embed=embed,
            view=TicketCloseView(),
        )

        # Log ouverture
        await send_ticket_log(
            guild, "open", user, channel, ticket_type, ticket_num
        )

        await interaction.followup.send(
            f"✅ Ton ticket a été créé : {channel.mention}", ephemeral=True
        )

    @ui.button(label="💬 Discord", style=discord.ButtonStyle.blurple)
    async def discord_btn(self, interaction: discord.Interaction, button: ui.Button):
        await self._open(interaction, "discord")

    @ui.button(label="🟣 Twitch", style=discord.ButtonStyle.secondary)
    async def twitch_btn(self, interaction: discord.Interaction, button: ui.Button):
        await self._open(interaction, "twitch")


class TicketCloseView(ui.View):
    """Bouton Fermer le ticket — persistent."""

    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(
        label="🔒 Fermer le ticket",
        style=discord.ButtonStyle.danger,
        custom_id="persistent:ticket_close",
    )
    async def close_btn(self, interaction: discord.Interaction, button: ui.Button):
        ticket = await get_ticket_info(interaction.channel.id)
        if not ticket:
            return await interaction.response.send_message(
                "❌ Ce salon n'est pas un ticket.", ephemeral=True
            )
        if ticket["status"] == "closed":
            return await interaction.response.send_message(
                "⚠️ Ce ticket est déjà fermé.", ephemeral=True
            )

        # Vérifier permission : propriétaire du ticket ou mod
        mod_role = discord.utils.get(interaction.guild.roles, name=MOD_ROLE_NAME)
        is_owner = interaction.user.id == ticket["user_id"]
        is_mod = mod_role and mod_role in interaction.user.roles
        is_owner_bot = await interaction.client.is_owner(interaction.user)

        if not (is_owner or is_mod or is_owner_bot):
            return await interaction.response.send_message(
                "❌ Seul le créateur du ticket ou un modérateur peut le fermer.",
                ephemeral=True,
            )

        await close_ticket_db(interaction.channel.id)

        # Renommer le salon en closed-(username)-####
        safe_name = (
            ticket["user_name"]
            .split("#")[0]          # retirer le discriminant #1234 si présent
            .lower()
            .replace(" ", "-")
        )
        # Garder seulement les caractères autorisés par Discord dans les noms de salon
        safe_name = "".join(c for c in safe_name if c.isalnum() or c == "-") or "user"
        new_channel_name = f"closed-{safe_name}-{ticket['id']:04d}"
        try:
            await interaction.channel.edit(name=new_channel_name)
        except discord.HTTPException:
            pass  # Pas bloquant si le renommage échoue

        # Retirer les permissions d'écriture du créateur
        ticket_user = interaction.guild.get_member(ticket["user_id"])
        if ticket_user:
            try:
                await interaction.channel.set_permissions(
                    ticket_user,
                    send_messages=False,
                    view_channel=True,
                    read_message_history=True,
                )
            except discord.HTTPException:
                pass

        # Log fermeture
        await send_ticket_log(
            interaction.guild, "close", interaction.user,
            interaction.channel, ticket["type"], ticket["id"],
        )

        embed = discord.Embed(
            title="🔒 Ticket fermé",
            description=(
                f"Ticket fermé par {interaction.user.mention}.\n\n"
                "Choisis une action ci-dessous :"
            ),
            color=discord.Color.dark_grey(),
            timestamp=datetime.utcnow(),
        )
        await interaction.response.send_message(
            embed=embed, view=TicketActionView()
        )


class TicketActionView(ui.View):
    """Actions après fermeture : Transcript ou Suppression."""

    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(
    label="📄 Transcript + Supprimer",
    style=discord.ButtonStyle.primary,
    custom_id="persistent:ticket_transcript"
)
    async def transcript_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        channel = interaction.channel
        ticket = await get_ticket_info(channel.id)

        transcript = await generate_transcript(channel)
        log_ch = interaction.guild.get_channel(LOG_TICKETS_CHANNEL_ID)

        if log_ch:
            user_mention = f"<@{ticket['user_id']}>" if ticket else "?"
            t_type = ticket["type"] if ticket else "?"
            embed = discord.Embed(
                title="📄 Transcript de ticket",
                description=(
                    f"**Salon :** #{channel.name}\n"
                    f"**Type :** {t_type.title()}\n"
                    f"**Créé par :** {user_mention}\n"
                    f"**Fermé par :** {interaction.user.mention}"
                ),
                color=discord.Color.blurple(),
                timestamp=datetime.utcnow(),
            )
            await log_ch.send(
                embed=embed,
                file=discord.File(transcript, filename=f"transcript-{channel.name}.txt"),
            )

        await interaction.followup.send("✅ Transcript envoyé dans les logs. Suppression dans 5 secondes…")
        import asyncio
        await asyncio.sleep(5)
        try:
            await channel.delete(reason="Ticket clôturé avec transcript")
        except discord.HTTPException:
            pass

    @ui.button(
    label="🗑️ Supprimer sans transcript",
    style=discord.ButtonStyle.danger,
    custom_id="persistent:ticket_delete"
)
    async def delete_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("🗑️ Suppression dans 5 secondes…")
        import asyncio
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason="Ticket clôturé sans transcript")
        except discord.HTTPException:
            pass

    @ui.button(
    label="↩️ Réouvrir",
    style=discord.ButtonStyle.secondary,
    custom_id="persistent:ticket_reopen"
)
    async def reopen_btn(self, interaction: discord.Interaction, button: ui.Button):
        mod_role = discord.utils.get(interaction.guild.roles, name=MOD_ROLE_NAME)
        is_mod = mod_role and mod_role in interaction.user.roles
        is_owner_bot = await interaction.client.is_owner(interaction.user)
        if not (is_mod or is_owner_bot):
            return await interaction.response.send_message(
                "❌ Seul un modérateur peut réouvrir un ticket.", ephemeral=True
            )

        ticket = await get_ticket_info(interaction.channel.id)
        if ticket:
            async with aiosqlite.connect(db.DB_PATH) as conn:
                await conn.execute(
                    "UPDATE tickets SET status='open', closed_at=NULL WHERE channel_id=?",
                    (interaction.channel.id,),
                )
                await conn.commit()

            ticket_user = interaction.guild.get_member(ticket["user_id"])
            if ticket_user:
                try:
                    await interaction.channel.set_permissions(
                        ticket_user,
                        send_messages=True,
                        view_channel=True,
                        read_message_history=True,
                    )
                except discord.HTTPException:
                    pass

        await interaction.response.send_message(
            f"✅ Ticket réouvert par {interaction.user.mention}.",
            view=TicketCloseView(),
        )
        self.stop()


# ─── Helper log ─────────────────────────────────────────────────────────────

async def send_ticket_log(guild, action, actor, channel, ticket_type, ticket_id):
    log_ch = guild.get_channel(LOG_TICKETS_CHANNEL_ID)
    if not log_ch:
        return

    info = TICKET_TYPES.get(ticket_type, {})
    emoji = info.get("emoji", "🎫")
    color = discord.Color.green() if action == "open" else discord.Color.red()
    action_label = "ouvert" if action == "open" else "fermé"

    embed = discord.Embed(
        title=f"{emoji} Ticket #{ticket_id:04d} {action_label}",
        color=color,
        timestamp=datetime.utcnow(),
    )
    embed.add_field(name="Salon", value=channel.mention, inline=True)
    embed.add_field(name="Type", value=ticket_type.title(), inline=True)
    embed.add_field(name="Par", value=actor.mention, inline=True)
    embed.set_thumbnail(url=actor.display_avatar.url)
    await log_ch.send(embed=embed)


# ─── Cog ────────────────────────────────────────────────────────────────────

class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="panelticket", aliases=["setupticket", "ticket"])
    @commands.is_owner()
    async def panel_ticket(self, ctx):
        """[OWNER ONLY] Poste le panel de création de tickets."""
        channel = self.bot.get_channel(TICKET_PANEL_CHANNEL_ID)
        if not channel:
            return await ctx.send(f"❌ Salon panel introuvable (ID: {TICKET_PANEL_CHANNEL_ID})")

        embed = discord.Embed(
            title="🎫 Support — Créer un ticket",
            description=(
                "Tu as besoin d'aide ou tu as un problème ?\n\n"
                "💬 **Discord** — Questions ou problèmes liés au serveur Discord\n"
                "🟣 **Twitch** — Questions ou problèmes liés au Twitch\n\n"
                "Clique sur le bouton ci-dessous pour ouvrir un ticket.\n"
                "*Un seul ticket à la fois par membre.*"
            ),
            color=0x9146FF,
        )
        embed.set_footer(text="Système de tickets — exotichazle")
        await channel.send(embed=embed, view=TicketPanelView())

        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass
        await ctx.send("✅ Panel de tickets posté !", delete_after=5)

    @panel_ticket.error
    async def panel_error(self, ctx, error):
        if isinstance(error, commands.NotOwner):
            await ctx.send("❌ Réservé au propriétaire du bot.")


async def setup(bot):
    await bot.add_cog(Tickets(bot))
