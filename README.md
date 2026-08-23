# ShawarmaMusic

> A private Discord music bot with YouTube playback, queue controls, and owner-only server recovery commands.

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![discord.py](https://img.shields.io/badge/discord.py-2.x-5865F2?logo=discord&logoColor=white)](https://discordpy.readthedocs.io/)
[![License](https://img.shields.io/badge/license-private-lightgrey)](#license)

## Overview

ShawarmaMusic is a Discord music bot built with Python and `discord.py`. It supports slash commands for music playback and a small set of private, owner-only prefix commands for restoring the bot owner's access to a server.

The bot is started by `main.py`, which calls `run_bot()` from `shawarma.py`.

## Features

- Play YouTube videos, searches, and playlists.
- Queue, skip, pause, resume, shuffle, loop, and change volume.
- Jump to a timestamp in the current track.
- Display queue and now-playing progress.
- Automatically disconnect after two minutes alone in a voice channel.
- Owner-only DM commands for assigning manageable roles, removing bans, and removing timeouts.
- Console logging for owner-only recovery actions.

## Project Structure

```text
.
|-- main.py       # Application entry point
|-- shawarma.py   # Bot setup, commands, music system, and events
|-- .env          # Local secrets; never commit this file
|-- .gitignore
`-- README.md
```

## Requirements

- Python 3.10 or newer.
- A Discord application and bot account.
- FFmpeg installed and available on your system `PATH`.
- A bot token stored locally in `.env`.
- YouTube access through `yt-dlp`.

## Installation

Create a virtual environment and install the Python packages:

```bash
python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# Windows Command Prompt
.venv\Scripts\activate.bat

pip install -U discord.py yt-dlp python-dotenv PyNaCl
```

Install FFmpeg and verify that this command works:

```bash
ffmpeg -version
```

## Configuration

Create a local `.env` file in the project root:

```env
discord_token=YOUR_NEW_BOT_TOKEN
my_id=YOUR_DISCORD_USER_ID
```

- `discord_token` is the bot token from the Discord Developer Portal.
- `my_id` is the Discord user ID allowed to use the private recovery commands.

Never commit `.env`, publish the token, or paste it into a public issue or chat. If a token is exposed, regenerate it immediately in the Developer Portal.

## Discord Bot Setup

In the Developer Portal, enable these privileged intents under **Bot**:

- Message Content Intent
- Server Members Intent is recommended for reliable member lookups
- Presence Intent is not required by the current code

Invite the bot with the permissions it needs:

- View Channels
- Send Messages
- Read Message History
- Manage Messages, so it can delete the public `s!admin` message when used in a server
- Connect and Speak, for music playback
- Manage Roles, for `s!admin`
- Ban Members, for `s!unban`
- Moderate Members, for `s!untime`

The bot's highest role must be above every role it should assign. Discord never allows a bot to manage roles above its own highest role, managed integration roles, or the `@everyone` role.

## Running the Bot

```bash
python main.py
```

A successful startup prints the bot login and slash-command sync status in the Python console.

## Slash Commands

Slash commands are available in servers where the bot is installed.

| Command | Description |
| --- | --- |
| `/play query` | Play a YouTube link, playlist, or search result. |
| `/queue query` | Add a YouTube link, playlist, or search result to the queue. |
| `/queue_list` | Show up to the first 10 queued tracks. |
| `/skip` | Skip the current track. |
| `/pause` | Pause playback. |
| `/resume` | Resume playback. |
| `/stop` | Stop playback and disconnect. |
| `/jump_to timestamp` | Jump to `mm:ss` or `hh:mm:ss`. |
| `/clear` | Empty the queue. |
| `/nowplaying` | Show the current track and progress. |
| `/shuffle` | Randomize the queue order. |
| `/loop mode` | Set `one`, `all`, or `off` loop mode. |
| `/volume percent` | Set volume from `0` to `200`. |
| `/nukeslash` | Delete this server's slash commands. Use carefully. |
| `/help` | Show the slash-command list. |

### Playback Notes

- `/play` and `/queue` accept either a YouTube URL or a search phrase.
- `/queue_list` currently displays queued entries as playlist items.
- The bot uses a default volume of 25% for new playback.
- When the bot is alone in voice for two minutes and is not playing, it disconnects.

## Private Prefix Commands

These commands use the `s!` prefix and work only in a direct message with the bot. They also work only when the sender's ID exactly matches `my_id` in `.env`. Other users and server-channel messages are ignored.

Replace `SERVER_ID` with the numeric ID of the target Discord server.

| Command | Description |
| --- | --- |
| `s!admin SERVER_ID` | Assign every non-managed role the bot can manage to you. |
| `s!unban SERVER_ID` | Remove your ban from the selected server. |
| `s!untime SERVER_ID` | Remove your timeout from the selected server. |
| `s!help` | Show discord.py's automatically generated prefix-command help. |

Examples:

```text
s!admin 123456789012345678
s!unban 123456789012345678
s!untime 123456789012345678
```

If `SERVER_ID` is omitted, the bot sends a usage message in the DM and logs the event in the Python console.

These commands do not make moderation changes invisible. Discord server owners and administrators may still see role, ban, or timeout changes in audit logs and other Discord surfaces.

## Getting a Server ID

Enable **Developer Mode** in Discord, then right-click the server icon and choose **Copy Server ID**.

## Troubleshooting

### Slash commands do not appear

- Confirm the bot started successfully.
- Restart the bot to run the global slash-command sync.
- Confirm the bot was invited with the `applications.commands` scope.
- Check the console for sync errors.

### `s!` commands do nothing

- Confirm Message Content Intent is enabled in the Developer Portal.
- Confirm the command is being sent in a DM for `admin`, `unban`, or `untime`.
- Confirm `my_id` exactly matches your Discord user ID.
- Confirm the prefix is exactly `s!`.

### Roles are not assigned

- Confirm the bot has Manage Roles.
- Move the bot's highest role above the roles it should assign.
- Managed roles and roles above the bot cannot be assigned.
- You must currently be a member of the selected server.

### Unban fails

- The bot must still be in the selected server.
- The bot needs Ban Members.
- Use the numeric server ID, not the server name or invite link.
- Discord will report that you are not banned if no ban exists for your account.

### Timeout removal fails

- The bot must still be in the selected server.
- The bot needs Moderate Members.
- You must currently be a member of the selected server.
- Discord role hierarchy and moderation permissions still apply.

## Security Checklist

- Keep `.env` out of Git with the included `.gitignore`.
- Regenerate any token that has ever been exposed.
- Do not store tokens, cookies, or downloaded media in the repository.
- Review the owner ID in `my_id` before running the bot.
- Treat `/nukeslash` as a destructive administrative command.

## License

This repository is intended for private use. Add a license here before distributing the project publicly.
