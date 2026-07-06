import os

# Discord
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
PREFIX = "<<"
MOD_ROLE_NAME = os.environ.get("MOD_ROLE_NAME", "Modérateur")

# Channels
LIVE_CHANNEL_ID = int(os.environ.get("LIVE_CHANNEL_ID", "1523496553623588935"))
PLANNING_CHANNEL_ID = int(os.environ.get("PLANNING_CHANNEL_ID", "1523501712306995262"))

# Twitch
TWITCH_CLIENT_ID = os.environ.get("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.environ.get("TWITCH_CLIENT_SECRET")
TWITCH_USERNAME = os.environ.get("TWITCH_USERNAME", "exotichazle")
TWITCH_CHECK_INTERVAL = 60  # secondes entre chaque vérification
