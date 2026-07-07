import asyncio
import discord
from discord.ext import commands
from discord import ui
from datetime import datetime
import bot.database as db
from bot.config import VOICE_CREATE_CHANNEL_ID


# ─── Utilitaires ─────────────────────────────────────────────────────────────

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
    info = await db.get_private_voice(channel_id)
    if not info or not info.get("panel_message_id"):
        return
    try:
        msg = await channel.fetch_message(info["panel_message_id"])
        embed = await build_panel_embed(channel_id, channel.guild)
        await msg.edit(embed=embed)
    except discord.HTTPException:
        pass


async def get_or_create_waiting_channel(
    guild: discord.Guild, private_channel: discord.VoiceChannel, cog: "VoicePrivate"
) -> discord.VoiceChannel | None:
    """Retourne le salon d'attente existant ou en crée un nouveau."""
    ch_id = private_channel.id
    # Vérifier dans le cache cog
    wait_id = cog._waiting_channels.get(ch_id)
    if wait_id:
        wc = guild.get_channel(wait_id)
        if wc:
            return wc

    # Chercher dans la catégorie
    wait_name = f"⏳ {private_channel.name}"
    wc = discord.utils.get(guild.voice_channels, name=wait_name, category=private_channel.category)
    if not wc:
        try:
            wc = await guild.create_voice_channel(
                name=wait_name, category=private_channel.category, reason="Salle d'attente"
            )
        except discord.HTTPException:
            return None

    cog._waiting_channels[ch_id] = wc.id
    return wc


async def delete_waiting_channel(
    guild: discord.Guild, channel_id: int, cog: "VoicePrivate"
):
    """Supprime la salle d'attente et déconnecte ses membres."""
    wait_id = cog._waiting_channels.pop(channel_id, None)
    if wait_id:
        wc = guild.get_channel(wait_id)
        if wc:
            for m in list(wc.members):
                try:
                    await m.move_to(None)
                except discord.HTTPException:
                    pass
            try:
                await wc.delete(reason="Mode attente désactivé")
            except discord.HTTPException:
                pass


# ─── Vues de sélection (éphémères, non persistantes) ─────────────────────────

class AddWhitelistView(ui.View):
    """Sélection de membres/rôles à ajouter à la whitelist."""

    def __init__(self, channel_id: int):
        super().__init__(timeout=120)
        self.channel_id = channel_id

    @ui.select(
        cls=ui.MentionableSelect,
        placeholder="Rôles et membres de la whitelist",
        min_values=0,
        max_values=25,
        row=0,
    )
    async def select(self, interaction: discord.Interaction, select: ui.MentionableSelect):
        added = 0
        for item in select.values:
            if isinstance(item, discord.Member):
                await db.add_voice_whitelist(self.channel_id, item.id)
                added += 1
            elif isinstance(item, discord.Role):
                for m in item.members:
                    if not m.bot:
                        await db.add_voice_whitelist(self.channel_id, m.id)
                        added += 1

        await interaction.response.send_message(
            f"✅ {added} membre(s) ajouté(s) à la whitelist.", ephemeral=True
        )
        vc = interaction.guild.get_channel(self.channel_id)
        if vc:
            await refresh_panel(vc, self.channel_id)

    @ui.button(label="Tout le salon", style=discord.ButtonStyle.primary, row=1)
    async def all_members(self, interaction: discord.Interaction, button: ui.Button):
        count = 0
        for m in interaction.guild.members:
            if not m.bot:
                await db.add_voice_whitelist(self.channel_id, m.id)
                count += 1
        await interaction.response.send_message(
            f"✅ {count} membre(s) du salon ajouté(s) à la whitelist.", ephemeral=True
        )
        vc = interaction.guild.get_channel(self.channel_id)
        if vc:
            await refresh_panel(vc, self.channel_id)

    @ui.button(label="Remettre à zéro", style=discord.ButtonStyle.danger, row=1)
    async def reset(self, interaction: discord.Interaction, button: ui.Button):
        await db.clear_voice_whitelist(self.channel_id)
        await interaction.response.send_message("🗑️ Whitelist remise à zéro.", ephemeral=True)
        vc = interaction.guild.get_channel(self.channel_id)
        if vc:
            await refresh_panel(vc, self.channel_id)


class RemoveWhitelistView(ui.View):
    """Sélection parmi les membres actuellement dans la whitelist pour les retirer."""

    def __init__(self, channel_id: int, options: list[discord.SelectOption]):
        super().__init__(timeout=120)
        self.channel_id = channel_id

        select = ui.Select(
            placeholder="Choisir les membres à retirer de la whitelist…",
            options=options,
            min_values=0,
            max_values=len(options),
            row=0,
        )
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction):
        select: ui.Select = self.children[0]
        for uid_str in select.values:
            await db.rm_voice_whitelist(self.channel_id, int(uid_str))
        await interaction.response.send_message(
            f"❌ {len(select.values)} membre(s) retiré(s) de la whitelist.", ephemeral=True
        )
        vc = interaction.guild.get_channel(self.channel_id)
        if vc:
            await refresh_panel(vc, self.channel_id)


class AddBlacklistView(ui.View):
    """Sélection d'utilisateurs à ajouter à la blacklist."""

    def __init__(self, channel_id: int, private_channel: discord.VoiceChannel):
        super().__init__(timeout=120)
        self.channel_id = channel_id
        self.private_channel = private_channel

    @ui.select(
        cls=ui.UserSelect,
        placeholder="Sélectionne des membres à blacklister…",
        min_values=0,
        max_values=25,
        row=0,
    )
    async def select(self, interaction: discord.Interaction, select: ui.UserSelect):
        count = 0
        for member in select.values:
            if not member.bot:
                await db.add_voice_blacklist(self.channel_id, member.id)
                # Expulse immédiatement si présent
                if member in self.private_channel.members:
                    try:
                        await member.move_to(None)
                    except discord.HTTPException:
                        pass
                count += 1
        await interaction.response.send_message(
            f"🚫 {count} membre(s) ajouté(s) à la blacklist.", ephemeral=True
        )
        vc = interaction.guild.get_channel(self.channel_id)
        if vc:
            await refresh_panel(vc, self.channel_id)


class RemoveBlacklistView(ui.View):
    """Sélection parmi les membres blacklistés pour les retirer."""

    def __init__(self, channel_id: int, options: list[discord.SelectOption]):
        super().__init__(timeout=120)
        self.channel_id = channel_id

        select = ui.Select(
            placeholder="Choisir les membres à retirer de la blacklist…",
            options=options,
            min_values=0,
            max_values=len(options),
            row=0,
        )
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction):
        select: ui.Select = self.children[0]
        for uid_str in select.values:
            await db.rm_voice_blacklist(self.channel_id, int(uid_str))
        await interaction.response.send_message(
            f"🔓 {len(select.values)} membre(s) retiré(s) de la blacklist.", ephemeral=True
        )
        vc = interaction.guild.get_channel(self.channel_id)
        if vc:
            await refresh_panel(vc, self.channel_id)


class ChangeOwnerView(ui.View):
    """Sélection du nouveau propriétaire du salon."""

    def __init__(self, channel_id: int):
        super().__init__(timeout=120)
        self.channel_id = channel_id

    @ui.select(
        cls=ui.UserSelect,
        placeholder="Sélectionne le nouveau propriétaire…",
        min_values=1,
        max_values=1,
        row=0,
    )
    async def select(self, interaction: discord.Interaction, select: ui.UserSelect):
        new_owner: discord.Member = select.values[0]
        if new_owner.bot:
            return await interaction.response.send_message(
                "❌ Tu ne peux pas donner la propriété à un bot.", ephemeral=True
            )
        await db.set_voice_owner(self.channel_id, new_owner.id)
        await interaction.response.send_message(
            f"👑 **{new_owner.display_name}** est maintenant propriétaire du salon.", ephemeral=True
        )
        vc = interaction.guild.get_channel(self.channel_id)
        if vc:
            await refresh_panel(vc, self.channel_id)


# ─── Panneau de contrôle (persistant) ────────────────────────────────────────

class VoiceControlPanel(ui.View):
    """Vue persistante — un seul enregistrement suffit pour tous les salons.
    interaction.channel.id identifie le salon vocal concerné."""

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

    def _get_cog(self, interaction: discord.Interaction) -> "VoicePrivate | None":
        return interaction.client.get_cog("VoicePrivate")

    # ── Modes ──────────────────────────────────────────────────────────────────

    @ui.button(label="🌐 Public", style=discord.ButtonStyle.secondary,
               custom_id="vpc:mode:public", row=0)
    async def mode_public(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._check_owner(interaction):
            return
        ch_id = interaction.channel.id
        cog = self._get_cog(interaction)
        if cog:
            await delete_waiting_channel(interaction.guild, ch_id, cog)
        await db.set_voice_mode(ch_id, "public")
        await interaction.response.send_message("🌐 Mode **Public** activé.", ephemeral=True)
        await refresh_panel(interaction.channel, ch_id)

    @ui.button(label="🔒 Privé", style=discord.ButtonStyle.secondary,
               custom_id="vpc:mode:private", row=0)
    async def mode_private(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._check_owner(interaction):
            return
        ch_id = interaction.channel.id
        cog = self._get_cog(interaction)
        if cog:
            await delete_waiting_channel(interaction.guild, ch_id, cog)
        await db.set_voice_mode(ch_id, "private")
        await interaction.response.send_message("🔒 Mode **Privé** activé.", ephemeral=True)
        await refresh_panel(interaction.channel, ch_id)

    @ui.button(label="⏳ Avec attente", style=discord.ButtonStyle.secondary,
               custom_id="vpc:mode:waiting", row=0)
    async def mode_waiting(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._check_owner(interaction):
            return
        ch_id = interaction.channel.id
        await db.set_voice_mode(ch_id, "waiting")

        # Créer la salle d'attente immédiatement
        cog = self._get_cog(interaction)
        vc = interaction.guild.get_channel(ch_id)
        if cog and vc:
            await get_or_create_waiting_channel(interaction.guild, vc, cog)

        await interaction.response.send_message(
            "⏳ Mode **Privé avec attente** activé. La salle d'attente a été créée.", ephemeral=True
        )
        await refresh_panel(interaction.channel, ch_id)

    # ── Whitelist ──────────────────────────────────────────────────────────────

    @ui.button(label="✅ Add whitelist", style=discord.ButtonStyle.success,
               custom_id="vpc:wl:add", row=1)
    async def wl_add(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._check_owner(interaction):
            return
        await interaction.response.send_message(
            "Sélectionne les membres ou rôles à ajouter à la whitelist :",
            view=AddWhitelistView(interaction.channel.id),
            ephemeral=True,
        )

    @ui.button(label="❌ Retirer whitelist", style=discord.ButtonStyle.danger,
               custom_id="vpc:wl:rm", row=1)
    async def wl_rm(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._check_owner(interaction):
            return
        ch_id = interaction.channel.id
        wl_ids = await db.get_voice_whitelist(ch_id)
        if not wl_ids:
            return await interaction.response.send_message(
                "ℹ️ La whitelist est déjà vide.", ephemeral=True
            )
        options = []
        for uid in wl_ids[:25]:
            m = interaction.guild.get_member(uid)
            label = m.display_name if m else f"User {uid}"
            options.append(discord.SelectOption(label=label, value=str(uid),
                                                emoji="✅" if m else None))
        await interaction.response.send_message(
            "Sélectionne les membres à retirer de la whitelist :",
            view=RemoveWhitelistView(ch_id, options),
            ephemeral=True,
        )

    # ── Blacklist ──────────────────────────────────────────────────────────────

    @ui.button(label="🚫 Add blacklist", style=discord.ButtonStyle.danger,
               custom_id="vpc:bl:add", row=1)
    async def bl_add(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._check_owner(interaction):
            return
        vc = interaction.guild.get_channel(interaction.channel.id)
        await interaction.response.send_message(
            "Sélectionne les membres à ajouter à la blacklist :",
            view=AddBlacklistView(interaction.channel.id, vc),
            ephemeral=True,
        )

    @ui.button(label="🔓 Retirer blacklist", style=discord.ButtonStyle.secondary,
               custom_id="vpc:bl:rm", row=1)
    async def bl_rm(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._check_owner(interaction):
            return
        ch_id = interaction.channel.id
        bl_ids = await db.get_voice_blacklist(ch_id)
        if not bl_ids:
            return await interaction.response.send_message(
                "ℹ️ La blacklist est déjà vide.", ephemeral=True
            )
        options = []
        for uid in bl_ids[:25]:
            m = interaction.guild.get_member(uid)
            label = m.display_name if m else f"User {uid}"
            options.append(discord.SelectOption(label=label, value=str(uid),
                                                emoji="🚫" if m else None))
        await interaction.response.send_message(
            "Sélectionne les membres à retirer de la blacklist :",
            view=RemoveBlacklistView(ch_id, options),
            ephemeral=True,
        )

    # ── Owner & Sauvegarde ─────────────────────────────────────────────────────

    @ui.button(label="👑 Changer owner", style=discord.ButtonStyle.primary,
               custom_id="vpc:owner", row=2)
    async def set_owner(self, interaction: discord.Interaction, button: ui.Button):
        if not await self._check_owner(interaction):
            return
        await interaction.response.send_message(
            "Sélectionne le nouveau propriétaire du salon :",
            view=ChangeOwnerView(interaction.channel.id),
            ephemeral=True,
        )

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

        # Marquer l'utilisateur comme "en cours de déplacement" via le cog
        cog: VoicePrivate | None = interaction.client.get_cog("VoicePrivate")
        if cog:
            cog._being_accepted.add(self.waiting_member.id)

        in_waiting = self.waiting_member in self.waiting_channel.members
        if in_waiting:
            try:
                await self.waiting_member.move_to(target)
            except discord.HTTPException:
                pass
            await interaction.response.send_message(
                f"✅ **{self.waiting_member.display_name}** a été déplacé dans ton salon.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"⚠️ **{self.waiting_member.display_name}** a quitté la salle d'attente.",
                ephemeral=True,
            )

        # Retirer le marqueur après un court délai
        if cog:
            asyncio.get_event_loop().call_later(
                3, cog._being_accepted.discard, self.waiting_member.id
            )

        try:
            await interaction.message.delete()
        except discord.HTTPException:
            pass

    @ui.button(label="❌ Refuser", style=discord.ButtonStyle.danger)
    async def deny(self, interaction: discord.Interaction, button: ui.Button):
        if self.handled:
            return await interaction.response.send_message("⚠️ Déjà traité.", ephemeral=True)
        if not await self._only_owner(interaction):
            return

        self.handled = True
        self.stop()

        if self.waiting_member in self.waiting_channel.members:
            try:
                await self.waiting_member.move_to(None)
            except discord.HTTPException:
                pass

        await interaction.response.send_message(
            f"❌ **{self.waiting_member.display_name}** a été refusé.", ephemeral=True
        )
        try:
            await interaction.message.delete()
        except discord.HTTPException:
            pass

    async def on_timeout(self):
        if not self.handled:
            if self.waiting_member in self.waiting_channel.members:
                try:
                    await self.waiting_member.move_to(None)
                except discord.HTTPException:
                    pass


# ─── Cog ─────────────────────────────────────────────────────────────────────

class VoicePrivate(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # private_channel_id → waiting_channel_id
        self._waiting_channels: dict[int, int] = {}
        # user IDs en cours de déplacement depuis salle d'attente (pour éviter boucle)
        self._being_accepted: set[int] = set()

    @commands.Cog.listener()
    async def on_ready(self):
        """Au démarrage : supprimer les canaux 🔒 orphelins (aucune entrée DB + vides).
        Les canaux ⏳ (salle d'attente) ne sont PAS dans private_voice — on les ignore."""
        for guild in self.bot.guilds:
            for channel in list(guild.voice_channels):
                # Seuls les canaux privés principaux (🔒) sont concernés
                if not channel.name.startswith("🔒 "):
                    continue
                # Ne pas toucher aux canaux occupés (membres actifs)
                if len(channel.members) > 0:
                    continue
                info = await db.get_private_voice(channel.id)
                if info:
                    # Entrée DB valide → récupérer le cache des salles d'attente si elles existent
                    wait_name = f"⏳ {channel.name}"
                    wc = discord.utils.get(
                        guild.voice_channels, name=wait_name, category=channel.category
                    )
                    if wc:
                        self._waiting_channels[channel.id] = wc.id
                    continue
                # Canal 🔒 vide sans entrée DB → orphelin confirmé
                try:
                    await channel.delete(reason="Nettoyage démarrage : canal privé orphelin vide")
                except discord.HTTPException:
                    pass

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
                from_id = before.channel.id if before.channel else None
                await self._handle_join(member, after.channel, info, from_id)

        # ── Quelqu'un quitte un salon géré ────────────────────────────────────
        if before.channel and before.channel.id != VOICE_CREATE_CHANNEL_ID:
            info = await db.get_private_voice(before.channel.id)
            if info:
                await self._handle_leave(before.channel)

    # ── Création du salon ──────────────────────────────────────────────────────

    async def _create_channel(self, member: discord.Member, lobby: discord.VoiceChannel):
        guild = member.guild
        safe = "".join(c for c in member.display_name if c.isalnum() or c in " -_").strip() or "user"
        name = f"🔒 {safe}"

        try:
            channel = await guild.create_voice_channel(name=name, category=lobby.category)
        except discord.HTTPException:
            return

        # Enregistrer en DB AVANT de déplacer le membre pour éviter la race condition
        # (on_voice_state_update se déclenche dès que le membre rejoint le salon)
        await db.create_private_voice(channel.id, member.id, guild.id)

        try:
            await member.move_to(channel)
        except discord.HTTPException:
            await db.delete_private_voice(channel.id)
            await channel.delete(reason="Déplacement impossible")
            return

        embed = await build_panel_embed(channel.id, guild)
        msg = await channel.send(embed=embed, view=VoiceControlPanel())
        await db.set_voice_panel_message(channel.id, msg.id)

    # ── Arrivée dans un salon géré ─────────────────────────────────────────────

    async def _handle_join(
        self, member: discord.Member, channel: discord.VoiceChannel,
        info: dict, from_channel_id: int | None
    ):
        if member.id == info["owner_id"]:
            return

        # Vient de la salle d'attente de CE salon → déjà accepté, on laisse passer
        wait_ch_id = self._waiting_channels.get(channel.id)
        if from_channel_id and wait_ch_id and from_channel_id == wait_ch_id:
            return

        # Marqué comme "en cours d'acceptation" (sécurité supplémentaire)
        if member.id in self._being_accepted:
            return

        # Blacklist → déconnexion immédiate
        if await db.is_in_voice_blacklist(channel.id, member.id):
            try:
                await member.move_to(None)
                await member.send(f"🚫 Tu es dans la blacklist du salon **{channel.name}**.")
            except discord.HTTPException:
                pass
            return

        # Whitelist → toujours autorisé
        if await db.is_in_voice_whitelist(channel.id, member.id):
            return

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
        wait_ch = await get_or_create_waiting_channel(guild, channel, self)
        if not wait_ch:
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
        await asyncio.sleep(1)

        channel = channel.guild.get_channel(channel_id)
        if channel is None or len(channel.members) == 0:
            if channel:
                await delete_waiting_channel(channel.guild, channel_id, self)
                try:
                    await channel.delete(reason="Salon privé vide")
                except discord.HTTPException:
                    pass
            self._waiting_channels.pop(channel_id, None)
            await db.delete_private_voice(channel_id)


async def setup(bot):
    await bot.add_cog(VoicePrivate(bot))
