import { Client, Collection, Events, GatewayIntentBits, Partials } from "discord.js";
import { readdirSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath, pathToFileURL } from "url";
import { createServer } from "http";
import type { Command } from "./types.js";

const __dirname = dirname(fileURLToPath(import.meta.url));

// Évite que les erreurs non gérées fassent crasher le bot
process.on("unhandledRejection", (err) => {
  console.error("[UnhandledRejection]", err);
});
process.on("uncaughtException", (err) => {
  console.error("[UncaughtException]", err);
});

const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMembers,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.GuildMessageReactions,
    GatewayIntentBits.MessageContent,
    GatewayIntentBits.DirectMessages,
  ],
  partials: [Partials.Channel, Partials.Message, Partials.Reaction],
});

const commands = new Collection<string, Command>();

async function loadCommands() {
  const commandsPath = join(__dirname, "commands");
  const commandFiles = readdirSync(commandsPath).filter((f) => f.endsWith(".js"));

  for (const file of commandFiles) {
    const filePath = pathToFileURL(join(commandsPath, file)).href;
    const mod = await import(filePath);
    const command = mod.default as unknown;
    if (
      command !== null &&
      typeof command === "object" &&
      "data" in command &&
      "execute" in command
    ) {
      const cmd = command as Command;
      commands.set(cmd.data.name, cmd);
      console.log(`[CMD] Loaded: ${cmd.data.name}`);
    }
  }
}

async function loadEvents() {
  const eventsPath = join(__dirname, "events");
  const eventFiles = readdirSync(eventsPath).filter((f) => f.endsWith(".js"));

  for (const file of eventFiles) {
    const filePath = pathToFileURL(join(eventsPath, file)).href;
    const mod = await import(filePath);
    const event = mod.default as { name: string; once: boolean; execute: (...args: unknown[]) => void };
    if (event.once) {
      client.once(event.name, (...args) => event.execute(...args, commands));
    } else {
      client.on(event.name, (...args) => event.execute(...args, commands));
    }
    console.log(`[EVT] Loaded: ${event.name}`);
  }
}

await loadCommands();
await loadEvents();

const token = process.env.DISCORD_BOT_TOKEN;
if (!token) {
  console.error("DISCORD_BOT_TOKEN is not set.");
  process.exit(1);
}

await client.login(token);

// Serveur HTTP minimal pour Render (Web Service)
const PORT = process.env.PORT ?? 3000;
createServer((_, res) => {
  res.writeHead(200, { "Content-Type": "text/plain" });
  res.end("OK");
}).listen(PORT, () => {
  console.log(`[HTTP] Health check server listening on port ${PORT}`);
});
