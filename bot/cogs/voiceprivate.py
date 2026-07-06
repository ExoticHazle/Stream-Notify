import asyncio
import discord
from discord.ext import commands
from discord import ui
from datetime import datetime
import bot.database as db
from bot.config import VOICE_CREATE_CHANNEL_ID


# ─── Utilitaires ─────────────────────────────────────────────────────────────

async def resolve_member(guild: discord.Guild, value: str) -> discord.Member | None:
    """Résout un membre depuis une mention, un ID ou un nom affiché."""
    value = value.strip()
    if value.startswith("<@") and value.endswith(">"):
        value = value[2:-1].lstrip("!")
    if value.isdigit():
        m = guild.get_member(int(value))
        if not m:
            try:
                m = await guild.fetch_member(int(value))
            except discord.HTTPException:
                pass
        return m
    return discord.utils.find(
        lambda m: m.display_name.lower() == value.lower() or m.name.lower() == value.lower(),
        guild.members,
    )


async def build_panel_embed(channel_id: int, guild: discord.Guild) -> discord.Embed:
    info = await db.get_private_voice(channel_id)
    if not info:
        return discord.Embed(title="❌ Salon introuvable", color=discord.Color.red())

    owner = guild.get_member(info["owner_id"])
    wl_ids = await db.get_voice_whitelist(channel_id)
    bl_ids = await db.get_voice_blacklist(channel_id)

    mode_labels = {
        "public":  "🌐 Public",
        "private": "🔒 Privé",
        "waiting": "⏳ Privé avec attente",
    }
    mode_desc = {
        "public":  "Tout le monde peut rejoindre.",
        "private": "Seuls le propriétaire et la whitelist peuvent rejoindre.",
        "waiting": "La whitelist rejoint directement. Les autres passent par la salle d'attente.",
    }

    embed = discord.Embed(
        title="🎙️ Panneau de contrôle — Salon privé",
        color=discord.Color.blurple(),
        timestamp=datetime.utcnow(),
    )
    embed.add_field(
        name="👑 Propriétaire",
        value=owner.mention if owner else f"<@{info['owner_id']}>",
        inline=True,
    )
    embed.add_field(
        name="📡 Mode",
        value=mode_labels.get(info["mode"], info["mode"]),
        inline=True,
    )
    wl_text = " ".join(f"<@{uid}>" for uid in wl_ids) if wl_ids else "*(vide)*"
    bl_text = " ".join(f"<@{uid}>" for uid in bl_ids) if bl_ids else "*(vide)*"
    embed.add_field(name=f"✅ Whitelist ({len(wl_ids)})", value=wl_text[:1024], inline=False)
    embed.add_field(name=f"🚫 Blacklist ({len(bl_ids)})", value=bl_text[:1024], inline=False)
    embed.set_footer(text=mode_desc.get(info["mode"], ""))
    return embed


async def refresh_panel(channel: discord.VoiceChannel, channel_id: int):
    """Édite le message du panneau de contrôle existant."""
    info = await db.get_private_voice(channel_id)
    if not info or not info.get("panel_message_id"):
        return
    try:
        msg = await channel.fetch_message(info["panel_message_id"])
        embed = await build_panel_embed(channel_id, channel.guild)
        await msg.edit(embed=embed)
    except discord.HTTPException:
        pass


# ─── Modal membre ─────────────────────────────────────────────────────────────

class MemberModal(ui.Modal):
    member_input: ui.TextInput = ui.TextInput(
        label="Mention, ID ou nom du membre",
        placeholder="@pseudo ou 123456789...",
        required=True,
    )

    def __init__(self, title: str, action: str):
        super().__init__(title=title)
        self.action = action

    async def on_submit(self, interaction: discord.Interaction):
        channel_id = interaction.channel.id
        member = await resolve_member(interaction.guild, self.member_input.value)
        if not member:
            return await interaction.response.send_message("❌ Membre introuvable.", ephemeral=True)

        if self.action == "wl_add":
            await db.add_voice_whitelist(channel_id, member.id)
            msg = f"✅ **{member.display_name}** ajouté à la whitelist."
        elif self.action == "wl_rm":
            await db.rm_voice_whitelist(channel_id, member.id)
            msg = f"❌ **{member.display_name}** retiré de la whitelist."
        elif self.action == "bl_add":
            await db.add_voice_blacklist(channel_id, member.id)
            vc = interaction.guild.get_channel(channel_id)
            if vc and member in vc.members:
                await member.move_to(None)
            msg = f"🚫 **{member.display_name}** ajouté à la blacklist."
        elif self.action == "bl_rm":
            await db.rm_voice_blacklist(channel_id, member.id)
            msg = f"🔓 **{member.display_name}** retiré de la blacklist."
        elif self.action == "set_owner":
            await db.set_voice_owner(channel_id, member.id)
            msg = f"👑 **{member.display_name}** est maintenant propriétaire du salon."
        else:
            msg = "✅ Action effectuée."

        await interaction.response.send_message(msg, ephemeral=True)
        vc = interaction.guild.get_channel(channel_id)
        if vc:
            await refresh_panel(vc, channel_id)


# ─── Panneau de contrôle (persistant) ────────────────────────────────────────

class VoiceControlPanel(ui.View):
    """Vue persistante — un seul enregistrement suffit pour tous les salons.
    On lit interaction.channel.id pour savoir de quel salon il s'agit."""

    def __init__(self):
        super().__init__(timeout=None)

    async def _check_owner(self, interaction: discord.Interaction) -> bool:
        info = await db.get_private_voice(interaction.channel.id)
        if not info:
            await interaction.response.send_message(
                "❌ Ce panneau n'est plus actif.", ephemeral=True
            )
            return False
        is_owner = interaction.user.id == info["owner_id"]
        is_bot_owner = await interaction.client.is_owner(interaction.user)
        if not (is_owner or is_bot_owner):
            await interaction.response.send_message(
                "❌ Seul le propriétaire peut modifier ces paramètres.", ephemeral=True
            )
            return False
        return True

    # ── Modes ──────────────────────────────────────────────────────────────────

    @ui.button(label="🌐 Public", style=discord.ButtonStyle.secondary,
               custom_id="vpc:mode:public", row=0)
    async def mode_public(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._check_owner(interaction):
            return
        await db.set_voice_mode(interaction.channel.id, "public")
        await interaction.response.send_message("🌐 Mode **Public** activé.", ephemeral=True)
        await refresh_panel(interaction.channel, interaction.channel.id)

    @ui.button(label="🔒 Privé", style=discord.ButtonStyle.secondary,
               custom_id="vpc:mode:private", row=0)
    async def mode_private(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._check_owner(interaction):
            return
        await db.set_voice_mode(interaction.channel.id, "private")
        await interaction.response.send_message("🔒 Mode **Privé** activé.", ephemeral=True)
        await refresh_panel(interaction.channel, interaction.channel.id)

    @ui.button(label="⏳ Avec attente", style=discord.ButtonStyle.secondary,
               custom_id="vpc:mode:waiting", row=0)
    async def mode_waiting(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._check_owner(interaction):
            return
        await db.set_voice_mode(interaction.channel.id, "waiting")
        await interaction.response.send_message("⏳ Mode **Privé avec attente** activé.", ephemeral=True)
        await refresh_panel(interaction.channel, interaction.channel.id)

    # ── Whitelist / Blacklist ──────────────────────────────────────────────────

    @ui.button(label="✅ Add whitelist", style=discord.ButtonStyle.success,
               custom_id="vpc:wl:add", row=1)
    async def wl_add(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._check_owner(interaction):
            return
        await interaction.response.send_modal(MemberModal("✅ Ajouter à la whitelist", "wl_add"))

    @ui.button(label="❌ Retirer whitelist", style=discord.ButtonStyle.danger,
               custom_id="vpc:wl:rm", row=1)
    async def wl_rm(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._check_owner(interaction):
            return
        await interaction.response.send_modal(MemberModal("❌ Retirer de la whitelist", "wl_rm"))

    @ui.button(label="🚫 Add blacklist", style=discord.ButtonStyle.danger,
               custom_id="vpc:bl:add", row=1)
    async def bl_add(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._check_owner(interaction):
            return
        await interaction.response.send_modal(MemberModal("🚫 Ajouter à la blacklist", "bl_add"))

    @ui.button(label="🔓 Retirer blacklist", style=discord.ButtonStyle.secondary,
               custom_id="vpc:bl:rm", row=1)
    async def bl_rm(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._check_owner(interaction):
            return
        await interaction.response.send_modal(MemberModal("🔓 Retirer de la blacklist", "bl_rm"))

    # ── Owner & Sauvegarde ─────────────────────────────────────────────────────

    @ui.button(label="👑 Changer owner", style=discord.ButtonStyle.primary,
               custom_id="vpc:owner", row=2)
    async def set_owner(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._check_owner(interaction):
            return
        await interaction.response.send_modal(MemberModal("👑 Changer le propriétaire", "set_owner"))

    @ui.button(label="💾 Sauvegarder WL", style=discord.ButtonStyle.secondary,
               custom_id="vpc:save_wl", row=2)
    async def save_wl(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._check_owner(interaction):
            return
        info = await db.get_private_voice(interaction.channel.id)
        wl = await db.get_voice_whitelist(interaction.channel.id)
        await db.save_voice_whitelist(info["owner_id"], interaction.guild.id, wl)
        await interaction.response.send_message(
            f"💾 Whitelist sauvegardée ({len(wl)} membre(s)).", ephemeral=True
        )

    @ui.button(label="📂 Charger WL", style=discord.ButtonStyle.secondary,
               custom_id="vpc:load_wl", row=2)
    async def load_wl(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._check_owner(interaction):
            return
        info = await db.get_private_voice(interaction.channel.id)
        saved = await db.load_voice_whitelist(info["owner_id"], interaction.guild.id)
        if not saved:
            return await interaction.response.send_message(
                "📂 Aucune whitelist sauvegardée.", ephemeral=True
            )
        await db.clear_voice_whitelist(interaction.channel.id)
        for uid in saved:
            await db.add_voice_whitelist(interaction.channel.id, uid)
        await interaction.response.send_message(
            f"📂 Whitelist chargée ({len(saved)} membre(s)).", ephemeral=True
        )
        await refresh_panel(interaction.channel, interaction.channel.id)


# ─── Vue d'approbation (salle d'attente) — non persistante ───────────────────

class WaitingApprovalView(ui.View):
    def __init__(self, channel_id: int, waiting_member: discord.Member,
                 waiting_channel: discord.VoiceChannel):
        super().__init__(timeout=300)
        self.channel_id = channel_id
        self.waiting_member = waiting_member
        self.waiting_channel = waiting_channel
        self.handled = False

    async def _only_owner(self, interaction: discord.Interaction) -> bool:
        info = await db.get_private_voice(self.channel_id)
        if not info or interaction.user.id != info["owner_id"]:
            await interaction.response.send_message(
                "❌ Seul le propriétaire peut accepter ou refuser.", ephemeral=True
            )
            return False
        return True

    @ui.button(label="✅ Accepter", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: ui.Button):
        if self.handled:
            return await interaction.response.send_message("⚠️ Déjà traité.", ephemeral=True)
        if not await self._only_owner(interaction):
            return

        self.handled = True
        self.stop()

        target = interaction.guild.get_channel(self.channel_id)
        if not target:
            return await interaction.response.send_message(
                "❌ Le salon vocal n'existe plus.", ephemeral=True
            )

        in_waiting = self.waiting_member in self.waiting_channel.members
        if in_waiting:
            await self.waiting_member.move_to(target)
            await interaction.response.send_message(
                f"✅ **{self.waiting_member.display_name}** a été déplacé dans ton salon.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"⚠️ **{self.waiting_member.display_name}** a quitté la salle d'attente.",
                ephemeral=True,
            )

        try:
            await interaction.message.delete()
        except discord.HTTPException:
            pass
        await self._try_delete_waiting()

    @ui.button(label="❌ Refuser", style=discord.ButtonStyle.danger)
    async def deny(self, interaction: discord.Interaction, button: ui.Button):
        if self.handled:
            return await interaction.response.send_message("⚠️ Déjà traité.", ephemeral=True)
        if not await self._only_owner(interaction):
            return

        self.handled = True
        self.stop()

        if self.waiting_member in self.waiting_channel.members:
            await self.waiting_member.move_to(None)

        await interaction.response.send_message(
            f"❌ **{self.waiting_member.display_name}** a été refusé.", ephemeral=True
        )
        try:
            await interaction.message.delete()
        except discord.HTTPException:
            pass
        await self._try_delete_waiting()

    async def on_timeout(self):
        if not self.handled:
            if self.waiting_member in self.waiting_channel.members:
                await self.waiting_member.move_to(None)
            await self._try_delete_waiting()

    async def _try_delete_waiting(self):
        if len(self.waiting_channel.members) == 0:
            try:
                await self.waiting_channel.delete(reason="Salle d'attente vide")
            except discord.HTTPException:
                pass


# ─── Cog ─────────────────────────────────────────────────────────────────────

class VoicePrivate(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        # ── Création ──────────────────────────────────────────────────────────
        if after.channel and after.channel.id == VOICE_CREATE_CHANNEL_ID:
            await self._create_channel(member, after.channel)
            return

        # ── Quelqu'un rejoint un salon géré ───────────────────────────────────
        if after.channel and after.channel.id != VOICE_CREATE_CHANNEL_ID:
            info = await db.get_private_voice(after.channel.id)
            if info:
                await self._handle_join(member, after.channel, info)

        # ── Quelqu'un quitte un salon géré ────────────────────────────────────
        if before.channel and before.channel.id != VOICE_CREATE_CHANNEL_ID:
            info = await db.get_private_voice(before.channel.id)
            if info:
                await self._handle_leave(before.channel)

    # ── Création du salon ──────────────────────────────────────────────────────

    async def _create_channel(self, member: discord.Member, lobby: discord.VoiceChannel):
        guild = member.guild
        category = lobby.category

        safe = "".join(c for c in member.display_name if c.isalnum() or c in " -_").strip() or "user"
        name = f"🔒 {safe}"

        try:
            channel = await guild.create_voice_channel(name=name, category=category)
            await member.move_to(channel)
        except discord.HTTPException:
            return

        await db.create_private_voice(channel.id, member.id, guild.id)

        embed = await build_panel_embed(channel.id, guild)
        msg = await channel.send(embed=embed, view=VoiceControlPanel())
        await db.set_voice_panel_message(channel.id, msg.id)

    # ── Arrivée dans un salon géré ─────────────────────────────────────────────

    async def _handle_join(self, member: discord.Member, channel: discord.VoiceChannel, info: dict):
        if member.id == info["owner_id"]:
            return  # Toujours autorisé

        if await db.is_in_voice_blacklist(channel.id, member.id):
            try:
                await member.move_to(None)
                await member.send(f"🚫 Tu es dans la blacklist du salon **{channel.name}**.")
            except discord.HTTPException:
                pass
            return

        if await db.is_in_voice_whitelist(channel.id, member.id):
            return  # Toujours autorisé

        mode = info["mode"]

        if mode == "public":
            return

        elif mode == "private":
            try:
                await member.move_to(None)
                await member.send(f"🔒 Le salon **{channel.name}** est privé.")
            except discord.HTTPException:
                pass

        elif mode == "waiting":
            await self._send_to_waiting(member, channel, info)

    # ── Salle d'attente ────────────────────────────────────────────────────────

    async def _send_to_waiting(
        self, member: discord.Member, channel: discord.VoiceChannel, info: dict
    ):
        guild = member.guild
        category = channel.category
        wait_name = f"⏳ {channel.name}"

        wait_ch = discord.utils.get(guild.voice_channels, name=wait_name, category=category)
        if not wait_ch:
            try:
                wait_ch = await guild.create_voice_channel(
                    name=wait_name, category=category, reason="Salle d'attente"
                )
            except discord.HTTPException:
                return

        try:
            await member.move_to(wait_ch)
        except discord.HTTPException:
            return

        owner = guild.get_member(info["owner_id"])
        embed = discord.Embed(
            title="⏳ Demande d'accès",
            description=f"{member.mention} veut rejoindre ton salon vocal.",
            color=discord.Color.orange(),
            timestamp=datetime.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        await channel.send(
            content=owner.mention if owner else "",
            embed=embed,
            view=WaitingApprovalView(channel.id, member, wait_ch),
        )

    # ── Départ / nettoyage ─────────────────────────────────────────────────────

    async def _handle_leave(self, channel: discord.VoiceChannel):
        channel_id = channel.id
        await asyncio.sleep(1)  # Laisser Discord mettre à jour la liste des membres

        channel = channel.guild.get_channel(channel_id)
        if channel is None or len(channel.members) == 0:
            if channel:
                # Supprimer la salle d'attente associée si elle existe
                wait_name = f"⏳ {channel.name}"
                wait_ch = discord.utils.get(
                    channel.guild.voice_channels, name=wait_name, category=channel.category
                )
                if wait_ch:
                    try:
                        await wait_ch.delete(reason="Salon privé supprimé")
                    except discord.HTTPException:
                        pass
                try:
                    await channel.delete(reason="Salon privé vide")
                except discord.HTTPException:
                    pass

            await db.delete_private_voice(channel_id)


async def setup(bot):
    await bot.add_cog(VoicePrivate(bot))
