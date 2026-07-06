# Bot Discord — exotichazle

Bot Discord en Python pour le serveur d'exotichazle, avec intégration Twitch et outils de modération complets.

## Run & Operate

- `python3 -m bot.main` — lancer le bot (workflow "Discord Bot")
- Le bot se relance automatiquement via le workflow Replit

## Stack

- Python 3.11 + discord.py 2.x
- aiosqlite — base de données SQLite asynchrone (sanctions)
- aiohttp — appels API Twitch

## Où sont les fichiers

- `bot/main.py` — point d'entrée, setup du bot et commande `!help`
- `bot/config.py` — variables de configuration (lues depuis les secrets/env)
- `bot/database.py` — fonctions CRUD pour la BDD SQLite des sanctions
- `bot/cogs/moderation.py` — commandes de modération (ban, kick, timeout, warn, history, delsanction)
- `bot/cogs/twitch.py` — notification de live Twitch (polling toutes les 60s)
- `bot/cogs/planning.py` — commandes de planning de stream (owner only)
- `bot/sanctions.db` — base SQLite créée automatiquement au premier lancement

## Variables d'environnement

Secrets (configurés dans Replit Secrets) :
- `DISCORD_TOKEN` — token du bot Discord
- `TWITCH_CLIENT_ID` — Client ID de l'app Twitch
- `TWITCH_CLIENT_SECRET` — Client Secret de l'app Twitch

Env vars partagées :
- `TWITCH_USERNAME=exotichazle`
- `LIVE_CHANNEL_ID=1523496553623588935`
- `PLANNING_CHANNEL_ID=1523501712306995262`
- `MOD_ROLE_NAME=Modérateur`

## Commandes du bot

Préfixe : `!`

### Modération (rôle Modérateur requis)
| Commande | Description |
|---|---|
| `!ban @membre [raison]` | Bannit + DM + enregistre |
| `!unban <id>` | Débannit par ID utilisateur |
| `!kick @membre [raison]` | Expulse + DM + enregistre |
| `!timeout @membre <minutes> [raison]` | Timeout + DM + enregistre |
| `!untimeout @membre` | Lève un timeout |
| `!warn @membre [raison]` | Avertit + DM + enregistre |
| `!history [@membre]` | Historique des sanctions |
| `!delsanction <id>` | Supprime sanction + lève ban/timeout si applicable |

### Planning (owner only)
| Commande | Description |
|---|---|
| `!planning [# Titre] Contenu...` | Envoie un planning dans le salon dédié |
| `!clearplanning [n]` | Supprime les n derniers messages du salon planning |

## Architecture decisions

- **Polling Twitch** : vérification toutes les 60s via Helix API (pas d'EventSub, ne nécessite pas de serveur public)
- **SQLite** : stockage simple des sanctions sans dépendance externe
- **is_owner()** : les commandes planning utilisent la vérification native discord.py (propriétaire de l'application)
- **delsanction** : lève automatiquement le ban/timeout Discord en plus de désactiver la sanction en BDD

## User preferences

_À remplir au fil des sessions._

## Gotchas

- Activer **Server Members Intent** et **Message Content Intent** dans le portail développeur Discord
- Le bot doit avoir les permissions : Ban Members, Kick Members, Moderate Members, Read/Send Messages, Manage Messages
- Changer `TWITCH_CHECK_INTERVAL` dans `config.py` pour modifier la fréquence de vérification du live
