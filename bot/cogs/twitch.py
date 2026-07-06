import asyncio
import aiohttp
import discord
from discord.ext import commands, tasks
from bot.config import (
    TWITCH_CLIENT_ID,
    TWITCH_CLIENT_SECRET,
    TWITCH_USERNAME,
    LIVE_CHANNEL_ID,
    TWITCH_CHECK_INTERVAL,
)


class TwitchNotifier(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.is_live = False
        self.access_token = None
        self.check_live.start()

    def cog_unload(self):
        self.check_live.cancel()

    async def get_access_token(self) -> str | None:
        """Récupère un token d'accès Twitch via Client Credentials."""
        if not TWITCH_CLIENT_ID or not TWITCH_CLIENT_SECRET:
            return None
        url = "https://id.twitch.tv/oauth2/token"
        params = {
            "client_id": TWITCH_CLIENT_ID,
            "client_secret": TWITCH_CLIENT_SECRET,
            "grant_type": "client_credentials",
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("access_token")
        except Exception as e:
            print(f"[Twitch] Erreur lors de l'obtention du token : {e}")
        return None

    async def fetch_stream_data(self) -> dict | None:
        """Vérifie si le streamer est en live. Retourne les données du stream ou None."""
        if not self.access_token:
            self.access_token = await self.get_access_token()
        if not self.access_token:
            print("[Twitch] Impossible d'obtenir un access token.")
            return None

        url = "https://api.twitch.tv/helix/streams"
        params = {"user_login": TWITCH_USERNAME}

        async def _do_request(token: str):
            headers = {
                "Client-ID": TWITCH_CLIENT_ID,
                "Authorization": f"Bearer {token}",
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params) as resp:
                    return resp.status, await resp.json()

        try:
            status, data = await _do_request(self.access_token)

            if status == 401:
                # Token expiré : renouveler et réessayer dans le même cycle
                print("[Twitch] Token expiré, renouvellement en cours…")
                self.access_token = await self.get_access_token()
                if not self.access_token:
                    return None
                status, data = await _do_request(self.access_token)

            if status == 200:
                streams = data.get("data", [])
                return streams[0] if streams else None

            print(f"[Twitch] Réponse inattendue de l'API : HTTP {status}")
        except Exception as e:
            print(f"[Twitch] Erreur lors de la vérification du stream : {e}")
        return None

    async def fetch_user_data(self) -> dict | None:
        """Récupère les informations du compte Twitch (avatar, etc.)."""
        if not self.access_token:
            return None
        url = "https://api.twitch.tv/helix/users"
        headers = {
            "Client-ID": TWITCH_CLIENT_ID,
            "Authorization": f"Bearer {self.access_token}",
        }
        params = {"login": TWITCH_USERNAME}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        users = data.get("data", [])
                        return users[0] if users else None
        except Exception:
            return None

    @tasks.loop(seconds=TWITCH_CHECK_INTERVAL)
    async def check_live(self):
        """Boucle qui vérifie toutes les X secondes si le streamer est en live."""
        await self.bot.wait_until_ready()
        try:
            stream = await self.fetch_stream_data()

            # Si fetch a échoué (erreur réseau, token invalide…), on ne change pas l'état
            if stream is None and not self.is_live:
                return

            currently_live = stream is not None

            if currently_live and not self.is_live:
                # Passage de offline → live : envoyer la notification
                self.is_live = True
                await self.send_live_notification(stream)
            elif not currently_live and self.is_live:
                # Passage de live → offline
                self.is_live = False
                print(f"[Twitch] {TWITCH_USERNAME} n'est plus en live.")
        except Exception as e:
            print(f"[Twitch] Erreur inattendue dans la boucle de vérification : {e}")

    @check_live.before_loop
    async def before_check_live(self):
        await self.bot.wait_until_ready()

    async def send_live_notification(self, stream: dict):
        """Envoie la notification de live dans le salon dédié."""
        channel = self.bot.get_channel(LIVE_CHANNEL_ID)
        if not channel:
            print(f"[Twitch] Salon de notification introuvable (ID: {LIVE_CHANNEL_ID})")
            return

        user_data = await self.fetch_user_data()
        avatar_url = user_data.get("profile_image_url") if user_data else None
        offline_image = user_data.get("offline_image_url") if user_data else None

        game = stream.get("game_name", "Jeu inconnu")
        title = stream.get("title", "Sans titre")
        viewer_count = stream.get("viewer_count", 0)
        stream_url = f"https://www.twitch.tv/{TWITCH_USERNAME}"

        # Miniature du stream
        thumbnail = stream.get("thumbnail_url", "").replace("{width}", "1280").replace("{height}", "720")

        embed = discord.Embed(
            title=f"🔴 {TWITCH_USERNAME} est en LIVE !",
            url=stream_url,
            description=f"**{title}**",
            color=0x9146FF,  # Couleur Twitch
        )
        embed.add_field(name="🎮 Jeu", value=game, inline=True)
        embed.add_field(name="👥 Spectateurs", value=str(viewer_count), inline=True)
        embed.add_field(name="🔗 Lien", value=f"[Regarder le live]({stream_url})", inline=False)

        if thumbnail:
            embed.set_image(url=thumbnail + f"?t={stream.get('started_at', '')}")
        if avatar_url:
            embed.set_thumbnail(url=avatar_url)

        embed.set_footer(text="Twitch • Notification automatique")

        await channel.send(
            content=f"@everyone 🔴 **{TWITCH_USERNAME}** vient de lancer un live !",
            embed=embed,
        )
        print(f"[Twitch] Notification de live envoyée pour {TWITCH_USERNAME}.")


async def setup(bot):
    await bot.add_cog(TwitchNotifier(bot))
