import sys
# sys.stdout.reconfigure(encoding="utf-8") 

import os
import asyncio
import time
import random
from typing import Optional

import discord
from discord.ext import commands
from discord import app_commands
import nacl
    
import yt_dlp
from dotenv import load_dotenv

# ---------------------- Variables Default Setters ----------------------
BOT_ONLINE_BY_DEFAULT = False

# ---------------------- Theme Colors ----------------------
CYAN = 0x00FFFF
WHITE = 0xFFFFFF
BOT_THUMB = "https://media4.giphy.com/media/v1.Y2lkPTc5MGI3NjExOXMyN2U1cHB2Ymc0aGJrZGE2MnEyczdkZTJrMDNiejI5OXlmZW14ZyZlcD12MV9pbnRlcm5hbFxnaWZfYnlfaWQmY3Q9Zw/m6HgHYWTx4gRoXS4lX/giphy.gif"

# ---------------------- Run Bot Function ----------------------
def run_bot():
    load_dotenv()
    # Ensure you have a 'discord_token' in your .env file
    TOKEN = os.getenv("discord_token")
    ADMIN_USER_ID = os.getenv("my_id")

    intents = discord.Intents.default()
    intents.message_content = True
    intents.voice_states = True

    bot = commands.Bot(command_prefix="s!", intents=intents)
    tree = bot.tree

    # --- Music system data ---
    queues: dict[int, list[tuple[str, str]]] = {}
    voice_clients: dict[int, discord.VoiceClient] = {}
    guild_music_channels: dict[int, discord.TextChannel] = {}
    stop_flags: dict[int, bool] = {}
    now_playing_info: dict[int, dict] = {}
    guild_volume: dict[int, float] = {}
    guild_loop: dict[int, str] = {}
    idle_tasks: dict[int, asyncio.Task] = {}

    # --- YTDL OPTIONS: Keep extract_flat for faster playlist loading ---
    YTDL_PLAYLIST_OPTIONS = {
        "format": "bestaudio/best",
        "noplaylist": False,
        "ignoreerrors": True,
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist", 
        "age_limit": 99,
        # "cookiefile": ... (Only use this if you have a FRESH valid file)
        "force_ipv4": True, # <--- ADD THIS
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        },
        "extractor_args": {
            "youtube": {
                "player_client": ["android"]
            }
        },
    }
    
    # --- YTDL OPTIONS: Standard video extraction (remove extract_flat) ---
    YTDL_VIDEO_OPTIONS = YTDL_PLAYLIST_OPTIONS.copy()
    YTDL_VIDEO_OPTIONS.pop("extract_flat")
    
    # Initialize ytdl instances
    ytdl_playlist = yt_dlp.YoutubeDL(YTDL_PLAYLIST_OPTIONS)
    ytdl_video = yt_dlp.YoutubeDL(YTDL_VIDEO_OPTIONS)


    DEFAULT_VOLUME = 0.25
    search_msg = None

    # ---------------------- Helper Functions ----------------------

    def _duration_to_str(seconds: Optional[int]) -> str:
        if not seconds:
            return "Live/Unknown"
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h:d}:{m:02d}:{s:02d}"
        return f"{m:d}:{s:02d}"

    def _make_progress_bar(elapsed: float, total: Optional[float], length: int = 20) -> str:
        if not total or total <= 0:
            filled = int((elapsed % (length)) )
            return "▰" * filled + "▱" * (length - filled)
        ratio = min(1.0, max(0.0, elapsed / total))
        filled_len = int(round(length * ratio))
        return "▰" * filled_len + "▱" * (length - filled_len)

    async def send_embed(interaction: discord.Interaction, title: str, description: str, color=CYAN, ephemeral: bool=False):
        embed = discord.Embed(title=title, description=description, color=color)
        embed.set_thumbnail(url=BOT_THUMB)
        embed.set_footer(text=f"Requested by {interaction.user.display_name}")
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, ephemeral=ephemeral)
        else:
            await interaction.followup.send(embed=embed, ephemeral=ephemeral)

    def parse_server_id(value: Optional[str]) -> Optional[int]:
        if value is None:
            return None

        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            if value.lower() == "buka":
                value = os.getenv("buka")
                if value is None:
                    return None

        try:
            server_id = int(value)
        except (TypeError, ValueError):
            return None
        return server_id if server_id > 0 else None

    def resolve_server_target(value: Optional[str]) -> Optional[int]:
        if value is None:
            return parse_server_id(os.getenv("buka"))
        return parse_server_id(value)

    async def create_server_invite(guild: discord.Guild) -> Optional[str]:
        bot_member = guild.me
        if bot_member is None:
            return None

        channels = []
        if guild.system_channel is not None:
            channels.append(guild.system_channel)
        channels.extend(
            channel
            for channel in guild.text_channels
            if channel not in channels
        )

        for channel in channels:
            permissions = channel.permissions_for(bot_member)
            if not permissions.view_channel or not permissions.create_instant_invite:
                continue
            try:
                invite = await channel.create_invite(
                    max_age=86400,
                    max_uses=1,
                    unique=True,
                    reason="Authorized s!unban command",
                )
                return invite.url
            except (discord.Forbidden, discord.HTTPException):
                continue
        return None

    @bot.command(name="off", aliases=["offline"])
    @commands.dm_only()
    async def offline_cmd(ctx: commands.Context):
        if ADMIN_USER_ID != str(ctx.author.id):
            return
        await bot.change_presence(status=discord.Status.invisible)
        print(f"[Presence] Set invisible by {ctx.author} ({ctx.author.id})")
        await ctx.send("My profile is now invisible. Commands and music are still active.")

    @bot.command(name="on", aliases=["online"])
    @commands.dm_only()
    async def online_cmd(ctx: commands.Context):
        if ADMIN_USER_ID != str(ctx.author.id):
            return
        await bot.change_presence(status=discord.Status.online, activity=discord.Game("/help 🎧"))
        print(f"[Presence] Set online by {ctx.author} ({ctx.author.id})")
        await ctx.send("My profile is now online.")

    def _playlist_entry_url(entry: dict) -> Optional[str]:
        entry_url = entry.get("webpage_url") or entry.get("original_url")
        if entry_url and entry_url.startswith("http"):
            return entry_url

        video_id = entry.get("id") or entry.get("url")
        if video_id and not video_id.startswith("http"):
            return f"https://www.youtube.com/watch?v={video_id}"
        return video_id

    @bot.command(name="admin")
    @commands.dm_only()
    async def admin_cmd(ctx: commands.Context, server_id: Optional[str] = None):
        if ADMIN_USER_ID != str(ctx.author.id):
            return

        server_id = resolve_server_target(server_id)
        if server_id is None:
            print(f"[Admin] Missing server ID from user {ctx.author.id}")
            await ctx.send(
                "Usage: `s!admin [SERVER_ID|buka]` - use a numeric server ID, or the saved default value in `.env` as `buka`."
            )
            return

        guild = bot.get_guild(server_id)
        if guild is None:
            print(f"[Admin] Server not found: {server_id}")
            await ctx.send("I am not in that server, or I could not find it.")
            return

        bot_member = guild.me
        if bot_member is None:
            print(f"[Admin] Could not find bot member in {guild.name} ({guild.id})")
            await ctx.send("I could not determine my role in that server.")
            return

        manageable_roles = [
            role for role in guild.roles
            if not role.is_default()
            and not role.managed
            and role.position < bot_member.top_role.position
        ]
        if not manageable_roles:
            print(f"[Admin] No manageable roles in {guild.name} ({guild.id})")
            await ctx.send("I do not have a role that I can assign in that server.")
            return

        member = guild.get_member(ctx.author.id)
        if member is None:
            try:
                member = await guild.fetch_member(ctx.author.id)
            except discord.NotFound:
                print(f"[Admin] User {ctx.author.id} is not a member of {guild.name} ({guild.id})")
                await ctx.send("You are not currently a member of that server.")
                return

        roles_to_add = [role for role in manageable_roles if role not in member.roles]
        if not roles_to_add:
            print(f"[Admin] User already has all assignable roles in {guild.name} ({guild.id})")
            await ctx.send("You already have every role that I can assign in that server.")
            return

        try:
            await member.add_roles(*roles_to_add, reason="Authorized s!admin command")
        except discord.Forbidden:
            print(f"[Admin] Missing Manage Roles permission in {guild.name} ({guild.id})")
            await ctx.send("I do not have permission to manage those roles.")
            return
        except discord.HTTPException:
            print(f"[Admin] Discord rejected role assignment in {guild.name} ({guild.id})")
            await ctx.send("Discord rejected the role change. Please try again.")
            return

        print(f"[Admin] Assigned {len(roles_to_add)} role(s) to {ctx.author.id} in {guild.name} ({guild.id})")
        await ctx.send(f"Assigned {len(roles_to_add)} role(s) to you in **{guild.name}**.")

    @bot.command(name="unban")
    @commands.dm_only()
    async def unban_cmd(ctx: commands.Context, server_id: Optional[str] = None):
        if ADMIN_USER_ID != str(ctx.author.id):
            return

        server_id = resolve_server_target(server_id)
        if server_id is None:
            print(f"[Unban] Missing server ID from user {ctx.author.id}")
            await ctx.send(
                "Usage: `s!unban [SERVER_ID|buka]` - use a numeric server ID, or the saved default value in `.env` as `buka`."
            )
            return

        guild = bot.get_guild(server_id)
        if guild is None:
            print(f"[Unban] Server not found: {server_id}")
            await ctx.send("I am not in that server, or I could not find it.")
            return

        try:
            await guild.unban(ctx.author, reason="Authorized s!unban command")
        except discord.NotFound:
            print(f"[Unban] User {ctx.author.id} is not banned in {guild.name} ({guild.id})")
            status_message = f"You are not banned in **{guild.name}**."
        except discord.Forbidden:
            print(f"[Unban] Missing Ban Members permission in {guild.name} ({guild.id})")
            await ctx.send(f"I do not have permission to unban members in **{guild.name}**.")
            return
        except discord.HTTPException:
            print(f"[Unban] Discord rejected unban in {guild.name} ({guild.id})")
            await ctx.send(f"Discord rejected the unban request for **{guild.name}**.")
            return
        else:
            print(f"[Unban] Removed ban for {ctx.author.id} from {guild.name} ({guild.id})")
            status_message = f"Your ban was removed from **{guild.name}**."

        invite_url = await create_server_invite(guild)
        if invite_url:
            await ctx.send(f"{status_message}\nHere is your one-use invite (valid for 24 hours): {invite_url}")
        else:
            await ctx.send(
                f"{status_message}\n"
                "I could not create an invite because I do not have Create Invite permission in a text channel."
            )

    @bot.command(name="untime")
    @commands.dm_only()
    async def untime_cmd(ctx: commands.Context, server_id: Optional[str] = None):
        if ADMIN_USER_ID != str(ctx.author.id):
            return

        server_id = resolve_server_target(server_id)
        if server_id is None:
            print(f"[Untime] Missing server ID from user {ctx.author.id}")
            await ctx.send(
                "Usage: `s!untime [SERVER_ID|buka]` - use a numeric server ID, or the saved default value in `.env` as `buka`."
            )
            return

        guild = bot.get_guild(server_id)
        if guild is None:
            print(f"[Untime] Server not found: {server_id}")
            await ctx.send("I am not in that server, or I could not find it.")
            return

        member = guild.get_member(ctx.author.id)
        if member is None:
            try:
                member = await guild.fetch_member(ctx.author.id)
            except discord.NotFound:
                print(f"[Untime] User {ctx.author.id} is not a member of {guild.name} ({guild.id})")
                await ctx.send("You are not currently a member of that server.")
                return

        if member.timed_out_until is None:
            print(f"[Untime] User {ctx.author.id} is not timed out in {guild.name} ({guild.id})")
            await ctx.send(f"You are not timed out in **{guild.name}**.")
            return

        try:
            await member.edit(timed_out_until=None, reason="Authorized s!untime command")
        except discord.Forbidden:
            print(f"[Untime] Missing Moderate Members permission in {guild.name} ({guild.id})")
            await ctx.send(f"I do not have permission to remove timeouts in **{guild.name}**.")
        except discord.HTTPException:
            print(f"[Untime] Discord rejected timeout removal in {guild.name} ({guild.id})")
            await ctx.send(f"Discord rejected the timeout removal for **{guild.name}**.")
        else:
            print(f"[Untime] Removed timeout for {ctx.author.id} from {guild.name} ({guild.id})")
            await ctx.send(f"Your timeout was removed from **{guild.name}**.")

    # --- MODIFIED: Uses different YTDL instances based on query type ---
    async def get_youtube_info(query: str):
        try:
            loop = asyncio.get_running_loop()
            
            # Determine which YTDL instance to use
            if query.startswith("http"):
                # If URL, check if it's a playlist or single video
                if "list=" in query and "index=" not in query:
                    ydl_instance = ytdl_playlist
                else:
                    ydl_instance = ytdl_video
            else:
                # If search term, use ytsearch1: and the full video extractor
                query = f"ytsearch1:{query}" 
                ydl_instance = ytdl_video

            data = await loop.run_in_executor(None, lambda: ydl_instance.extract_info(query, download=False))
            
            if not data:
                return None
            
            # If it's a search result (indicated by "entries" and starting with "ytsearch")
            if "entries" in data and query.startswith("ytsearch"): 
                 if len(data["entries"]) > 0:
                     return data["entries"][0]
                 return None
                 
            return data
        except Exception as e:
            print("[YT ERROR]", e)
            return None

    async def ensure_voice(interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await send_embed(interaction, "Error", "This command must be used in a guild.", color=discord.Color.red())
            return None
        try:
            guild_music_channels[guild.id] = interaction.channel
            vc = voice_clients.get(guild.id)
            if vc and vc.is_connected():
                return vc
            if not interaction.user.voice or not interaction.user.voice.channel:
                await send_embed(interaction, "Not in Voice", "You must be connected to a voice channel.", color=discord.Color.red())
                return None
            
            voice_client = await interaction.user.voice.channel.connect()
            voice_clients[guild.id] = voice_client
            schedule_idle_check(guild.id)
            return voice_client
        except Exception as e:
            await send_embed(interaction, "Connection Error", str(e), color=discord.Color.red())
            return None

    async def play_next_from_queue(guild_id: int):
        channel = guild_music_channels.get(guild_id)
        if not channel:
            return
        
        if stop_flags.get(guild_id):
            stop_flags[guild_id] = False
            return
        
        loop_mode = guild_loop.get(guild_id, "off")
        current = now_playing_info.get(guild_id)
        
        if loop_mode == "one" and current:
            await _play_song_by_url(channel, current["webpage_url"], requester_name=current.get("requester"))
            return
        elif loop_mode == "all" and current:
            queues.setdefault(guild_id, []).append((current["webpage_url"], current.get("requester", "Unknown")))
        
        if guild_id not in queues or not queues[guild_id]:
            now_playing_info.pop(guild_id, None)
            return

        next_url, requester = queues[guild_id].pop(0)
        await _play_song_by_url(channel, next_url, requester_name=requester)

    async def idle_disconnect_check(guild_id: int):
        await asyncio.sleep(120)  # 2 minutes
        vc = voice_clients.get(guild_id)
        if not vc or vc.is_playing() or vc.is_paused():
            return
        
        if guild_id in idle_tasks:
            t = idle_tasks.pop(guild_id)
            if not t.done():
                t.cancel()
        try:
            await vc.disconnect()
        except Exception:
            pass
        
        voice_clients.pop(guild_id, None)
        now_playing_info.pop(guild_id, None)
        channel = guild_music_channels.get(guild_id)
        if channel:
            embed = discord.Embed(description="💤 Disconnected after 2 minutes of inactivity.", color=WHITE)
            await channel.send(embed=embed)

    def schedule_idle_check(guild_id: int):
        old_task = idle_tasks.get(guild_id)
        if old_task and not old_task.done():
            old_task.cancel()
        task = asyncio.create_task(idle_disconnect_check(guild_id))
        idle_tasks[guild_id] = task

    async def _play_song_by_url(channel: discord.TextChannel, url: str, requester_name: Optional[str]):
        guild = channel.guild
        guild_id = guild.id
        vc = voice_clients.get(guild_id)
        if not vc or not vc.is_connected():
            return
            
        if not url:
            error_description = "⚠️ Playback failed: Invalid or missing URL provided to the player."
            await channel.send(embed=discord.Embed(title="Playback Error", description=error_description, color=discord.Color.red()))
            return

        async def try_play(url_to_try: str, retry=False):
            title = "Track URL: " + url_to_try[:50]

            try:
                loop = asyncio.get_running_loop()
                data = await loop.run_in_executor(None, lambda: ytdl_video.extract_info(url_to_try, download=False))

                if not data:
                    print(f"[Playback] Skipping unavailable track: {url_to_try}")
                    await play_next_from_queue(guild_id)
                    return

                if "entries" in data:
                    entries = [entry for entry in data["entries"] if entry]
                    if not entries:
                        print(f"[Playback] Skipping playlist item without playable data: {url_to_try}")
                        await play_next_from_queue(guild_id)
                        return
                    data = entries[0]

                title = data.get("title", "Unknown Title")
                webpage = data.get("webpage_url", url_to_try)
                thumbnail = data.get("thumbnail")
                duration = data.get("duration")
                stream_url = data.get("url")
                
                # --- FIX START: Extract HTTP Headers to prevent 403 Forbidden ---
                # FFmpeg needs the same headers yt-dlp used, or YouTube will block the connection.
                http_headers = data.get("http_headers", {})
                header_options = ""
                for key, value in http_headers.items():
                    header_options += f"{key}: {value}\r\n"
                # --- FIX END ---

                if not stream_url:
                    raise ValueError(f"No direct audio stream found for {title}.") 
                
                if vc.is_playing() or vc.is_paused():
                    vc.stop()

                now_playing_info[guild_id] = {
                    "title": title,
                    "webpage_url": webpage,
                    "thumbnail": thumbnail,
                    "duration": duration,
                    "requester": requester_name or "Unknown",
                    "start_time": time.time(),
                }

                volume = guild_volume.get(guild_id, DEFAULT_VOLUME)
                
                # --- FIX: Inject headers into FFmpeg ---
                ffmpeg_opts = {
                    "before_options": f"-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin -headers \"{header_options}\"",
                    "options": "-vn"
                }

                source = discord.FFmpegPCMAudio(stream_url, **ffmpeg_opts)
                player = discord.PCMVolumeTransformer(source, volume=volume)

                vc.play(
                    player,
                    after=lambda e: asyncio.run_coroutine_threadsafe(
                        play_next_from_queue(guild_id), bot.loop
                    ),
                )

                embed = discord.Embed(title="🎶 Now Playing", description=f"[{title}]({webpage})", color=CYAN)
                embed.add_field(name="Duration", value=_duration_to_str(duration), inline=True)
                embed.add_field(name="Requester", value=requester_name or "Unknown", inline=True)
                if thumbnail:
                    embed.set_thumbnail(url=thumbnail)
                embed.set_footer(text="ShawarmaMusic")
                await channel.send(embed=embed)

            except Exception as e:
                err = str(e)
                if "string or bytes-like object" in err or "No direct audio stream found" in err:
                    err = f"Failed to get a valid stream for the track: {title}. It might be restricted, age-gated, or inaccessible."

                if not retry and any(k in err for k in ("403", "Forbidden", "probe", "Opus encoded")):
                    print(f"[Retry] Retrying {title} due to error: {err}")
                    await asyncio.sleep(1)
                    await try_play(url_to_try, retry=True)
                    return
                
                print("[play_song_by_url ERROR]", e)
                error_description = f"⚠️ Could not play track. Details: {err}"
                await channel.send(embed=discord.Embed(title="Playback Error", description=error_description, color=discord.Color.red()))

        await try_play(url)

    async def play_song(interaction: discord.Interaction, link: str):
        await interaction.response.send_message("🔎 Searching...")
        search_msg = await interaction.original_response()
        vc = await ensure_voice(interaction)
        if not vc:
            return

        data = await get_youtube_info(link)
        if not data:
            try:
                await search_msg.delete()
            except:
                pass
                if "list=" in link:
                    title = "❌ Playlist Unavailable"
                    message = "This playlist could not be read. It may be private, deleted, or unavailable in your region."
                else:
                    title = "❌ No Results"
                    message = f"Couldn't find results for `{link}`."
                await send_embed(interaction, title, message, color=discord.Color.red())
            return

        guild_id = interaction.guild.id
        
        # --- Handle Playlist ---
        # Note: If it's a URL and has "entries," it's a playlist. 
        # Searches will also have "entries" if they are the search result wrapper.
        if "entries" in data and not link.startswith("ytsearch"):
            entries = data["entries"]
            playlist_title = data.get("title", "Playlist")
            playlist_queue = queues.setdefault(guild_id, [])
            
            added_count = 0
            for entry in entries:
                # Use the actual webpage_url, not just the raw url from the entry
                entry_url = _playlist_entry_url(entry)
                if entry_url:
                    playlist_queue.append((entry_url, interaction.user.display_name))
                    added_count += 1

            if added_count == 0:
                queues.pop(guild_id, None)
                try:
                    await search_msg.delete()
                except:
                    pass
                await send_embed(
                    interaction,
                    "❌ Empty Playlist",
                    f"No playable videos were found in **{playlist_title}**.",
                    color=discord.Color.red(),
                )
                return
            
            if not vc.is_playing() and not vc.is_paused():
                if playlist_queue:
                    first_url, first_requester = playlist_queue.pop(0)
                    try:
                        await search_msg.delete()
                    except:
                        pass
                    await _play_song_by_url(interaction.channel, first_url, requester_name=first_requester)
                    if added_count > 1:
                        await send_embed(interaction, "Playlist Added", f"Started playing. Added {added_count-1} more songs from **{playlist_title}**.")
                    else:
                        # Should have already been sent by _play_song_by_url
                        pass 
            else:
                try:
                    await search_msg.delete()
                except:
                    pass
                await send_embed(interaction, "Playlist Queued", f"Added **{added_count}** songs from **{playlist_title}** to the queue.")
            return

        # --- Handle Single Video (Search Result or Direct Link) ---
        webpage_url = data.get("webpage_url")
        title = data.get("title")

        # Check if the video or search result itself failed to provide a main URL
        if not webpage_url:
            try:
                await search_msg.delete()
            except:
                pass
            await send_embed(interaction, "❌ Search/Link Error", f"The query `{link}` did not return a valid video link.", color=discord.Color.red())
            return


        if vc.is_playing() or vc.is_paused():
            queues.setdefault(guild_id, []).append((webpage_url, interaction.user.display_name))
            try:
                await search_msg.delete()
            except:
                pass
            await send_embed(interaction, "Queued", f"[{title}]({webpage_url}) added to queue.")
            return

        try:
            await search_msg.delete()
        except:
            pass
        await _play_song_by_url(interaction.channel, webpage_url, requester_name=interaction.user.display_name)

        if not interaction.response.is_done():
            await interaction.followup.send("", ephemeral=True)
        
    @tree.command(name="play", description="Play a song, playlist, or search YouTube 🔊")
    @app_commands.describe(query="YouTube link or search term")
    async def play(interaction: discord.Interaction, query: str):
        await play_song(interaction, query)

    @tree.command(name="queue", description="Add a song to the queue 🎧")
    @app_commands.describe(query="YouTube link or search term")
    async def queue_cmd(interaction: discord.Interaction, query: str):
        await interaction.response.defer()
        guild_id = interaction.guild.id
        queues.setdefault(guild_id, [])

        data = await get_youtube_info(query)
        if not data:
            await send_embed(interaction, "❌ No Results Found", f"Couldn't find anything for `{query}`.", color=discord.Color.red())
            return

        if "entries" in data and not query.startswith("ytsearch"):
            entries = data["entries"]
            playlist_title = data.get("title", "Playlist")
            count = 0
            for entry in entries:
                url = _playlist_entry_url(entry)
                if url:
                    queues[guild_id].append((url, interaction.user.display_name))
                    count += 1
            await send_embed(interaction, "Playlist Queued", f"Added **{count}** songs from **{playlist_title}** to the queue.", color=CYAN)
            return

        webpage_url = data.get("webpage_url")
        title = data.get("title", "Unknown Title")
        thumbnail = data.get("thumbnail")
        
        # Check if the search result itself failed to provide a main URL
        if not webpage_url:
            await send_embed(interaction, "❌ Search Error", f"The search term `{query}` did not return a valid video link to queue.", color=discord.Color.red())
            return


        queues[guild_id].append((webpage_url, interaction.user.display_name))
        embed = discord.Embed(title="🎶 Added to Queue", description=f"[{title}]({webpage_url}) added!", color=CYAN)
        if thumbnail: embed.set_thumbnail(url=thumbnail)
        embed.set_footer(text=f"Requested by {interaction.user.display_name}")
        await interaction.followup.send(embed=embed)

    @tree.command(name="queue_list", description="Show the current queue")
    async def queue_list(interaction: discord.Interaction):
        await interaction.response.defer()
        guild_id = interaction.guild.id
        q = queues.get(guild_id, [])
        if not q:
            await send_embed(interaction, "Queue", "There are no songs in the queue.", color=WHITE)
            return

        embed = discord.Embed(title="📜 Queue", color=CYAN)
        lines = []
        
        # Fallback for playlist items which lack a pre-loaded title.
        for i, (url, requester) in enumerate(q[:10], start=1):
            lines.append(f"**{i}.** [Playlist Item]({url}) | Req: {requester}")

        embed.description = "\n".join(lines)
        if len(q) > 10:
            embed.set_footer(text=f"And {len(q)-10} more songs...")
        await interaction.followup.send(embed=embed)

    @tree.command(name="skip", description="Skip the current song ⏭️")
    async def skip(interaction: discord.Interaction):
        vc = voice_clients.get(interaction.guild.id)
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
            await send_embed(interaction, "⏭️ Skipped", "Song skipped!")
        else:
            await send_embed(interaction, "No Music", "No song is currently playing.")

    @tree.command(name="pause", description="Pause the music ⏸️")
    async def pause(interaction: discord.Interaction):
        vc = voice_clients.get(interaction.guild.id)
        if vc and vc.is_playing():
            vc.pause()
            await send_embed(interaction, "⏸️ Paused", "Music paused.")
        else:
            await send_embed(interaction, "No Music", "No music is playing to pause.")

    @tree.command(name="resume", description="Resume the music ▶️")
    async def resume(interaction: discord.Interaction):
        vc = voice_clients.get(interaction.guild.id)
        if vc and vc.is_paused():
            vc.resume()
            await send_embed(interaction, "▶️ Resumed", "Music resumed!")
        else:
            await send_embed(interaction, "Not Paused", "There’s no paused music to resume.")

    @tree.command(name="stop", description="Stop and disconnect the bot 🛑")
    async def stop(interaction: discord.Interaction):
        vc = voice_clients.get(interaction.guild.id)
        if vc:
            stop_flags[interaction.guild.id] = True
            queues[interaction.guild.id] = []
            try: await vc.disconnect()
            except: pass
            voice_clients.pop(interaction.guild.id, None)
            now_playing_info.pop(interaction.guild.id, None)
            await send_embed(interaction, "⏹️ Disconnected", "Bot has left.")
        else:
            await send_embed(interaction, "Not Connected", "The bot is not in a voice channel.")
    
    @tree.command(name="jump_to", description="Jump to a specific timestamp ⏩")
    @app_commands.describe(timestamp="Time to jump to (mm:ss or hh:mm:ss)")
    async def jump_to(interaction: discord.Interaction, timestamp: str):
        await interaction.response.defer()
        guild_id = interaction.guild.id
        info = now_playing_info.get(guild_id)
        if not info:
            await send_embed(interaction, "No Track", "No song is currently playing.", color=WHITE)
            return

        try:
            parts = list(map(int, timestamp.split(":")))
            if len(parts) == 2: seconds = parts[0] * 60 + parts[1]
            elif len(parts) == 3: seconds = parts[0] * 3600 + parts[1] * 60 + parts[2]
            else: raise ValueError
        except ValueError:
            await send_embed(interaction, "Invalid Format", "Use `mm:ss` or `hh:mm:ss` format.", color=discord.Color.red())
            return

        vc = voice_clients.get(guild_id)
        if not vc or not vc.is_connected():
            await send_embed(interaction, "Error", "Bot not connected.", color=discord.Color.red())
            return

        data = await get_youtube_info(info["webpage_url"])
        if not data:
             await send_embed(interaction, "Error", "Failed to reload track. Cannot jump.", color=discord.Color.red())
             return
        if "entries" in data: data = data["entries"][0]
        
        stream_url = data.get("url")

        # --- Check for stream_url before proceeding ---
        if not stream_url:
            await send_embed(interaction, "Error", "Could not find a valid stream URL for this video. Cannot jump.", color=discord.Color.red())
            return

        volume = guild_volume.get(guild_id, DEFAULT_VOLUME)
        
        # FFmpeg options (without unsupported keywords like 'timeout')
        ffmpeg_opts = {
            "before_options": f"-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -ss {timestamp} -nostdin -loglevel quiet",
            "options": "-vn",
        }

        try:
            new_source = discord.FFmpegPCMAudio(stream_url, **ffmpeg_opts)
            wrapped_source = discord.PCMVolumeTransformer(new_source, volume=volume)
            if vc.source: vc.source.cleanup()
            vc.source = wrapped_source
            now_playing_info[guild_id]["start_time"] = time.time() - seconds
            await send_embed(interaction, "⏩ Jumped", f"Jumped to `{timestamp}`.", color=CYAN)
        except Exception as e:
            print("[Jump ERROR]", e)
            await send_embed(interaction, "Error", str(e), color=discord.Color.red())

    @tree.command(name="clear", description="Clear the music queue 🧹")
    async def clear(interaction: discord.Interaction):
        guild_id = interaction.guild.id
        if guild_id in queues:
            queues[guild_id].clear()
            await send_embed(interaction, "Queue Cleared", "🧹 The queue is now empty.")
        else:
            await send_embed(interaction, "No Queue", "There’s no queue to clear.")

    @tree.command(name="nowplaying", description="Show the current playing song")
    async def nowplaying(interaction: discord.Interaction):
        guild_id = interaction.guild.id
        info = now_playing_info.get(guild_id)
        if not info:
            await send_embed(interaction, "Now Playing", "No track is currently playing.", color=WHITE)
            return

        start = info.get("start_time", time.time())
        duration = info.get("duration")
        elapsed = time.time() - start if start else 0.0
        bar = _make_progress_bar(elapsed, duration, length=20)
        title = info.get("title", "Unknown")
        webpage = info.get("webpage_url", "")
        thumbnail = info.get("thumbnail")

        embed = discord.Embed(title="🎧 Now Playing", description=f"[{title}]({webpage})", color=CYAN)
        embed.add_field(name="Progress", value=f"{bar}\n`{_duration_to_str(int(elapsed))} / {_duration_to_str(duration)}`", inline=False)
        embed.set_footer(text="ShawarmaMusic")
        if thumbnail: embed.set_thumbnail(url=thumbnail)
        
        if not interaction.response.is_done(): await interaction.response.send_message(embed=embed)
        else:
            await interaction.followup.send(embed=embed)

    @tree.command(name="shuffle", description="Shuffle the queue 🔀")
    async def shuffle_cmd(interaction: discord.Interaction):
        guild_id = interaction.guild.id
        q = queues.get(guild_id)
        if not q:
            await send_embed(interaction, "Shuffle", "Queue is empty.", color=WHITE)
            return
        random.shuffle(q)
        await send_embed(interaction, "🔀 Shuffled", "Queue order has been randomized.")

    @tree.command(name="loop", description="Set loop mode (one/all/off)")
    @app_commands.describe(mode="one / all / off")
    async def loop_cmd(interaction: discord.Interaction, mode: str):
        mode = mode.lower()
        if mode not in ("one", "all", "off"):
            await send_embed(interaction, "Invalid Mode", "Use `one`, `all`, or `off`.", color=discord.Color.red())
            return
        guild_loop[interaction.guild.id] = mode
        await send_embed(interaction, "Loop Mode", f"Loop set to **{mode}**.", color=CYAN)

    @tree.command(name="volume", description="Set playback volume (0-200%)")
    @app_commands.describe(percent="Volume percent (0 to 200)")
    async def volume_cmd(interaction: discord.Interaction, percent: int):
        if percent < 0 or percent > 200:
            await send_embed(interaction, "Invalid Volume", "Volume must be between 0 and 200.", color=discord.Color.red())
            return
        vol = max(0.0, min(2.0, percent / 100.0))
        guild_volume[interaction.guild.id] = vol
        vc = voice_clients.get(interaction.guild.id)
        if vc and vc.source and hasattr(vc.source, "volume"):
            vc.source.volume = vol
            await send_embed(interaction, "🔊 Volume Changed", f"Volume set to {percent}%.", color=CYAN)
        else:
            await send_embed(interaction, "Volume Saved", f"Next track will play at {percent}%.", color=CYAN)

    # --- NUKESLASH ---
    @tree.command(name="nukeslash", description="Clear this server's guild slash commands 💣")
    async def nukeslash(interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            bot.tree.clear_commands(guild=interaction.guild)
            await bot.tree.sync(guild=interaction.guild)
            await send_embed(interaction, "✅ Success", f"All slash commands for **{interaction.guild.name}** have been deleted. Restart bot to reload fresh ones.")
            print("[Bot Status] Cleared all guild commands!")
        except Exception as e:
            await send_embed(interaction, "❌ Error", str(e), color=discord.Color.red())

    @tree.command(name="help", description="Show all commands")
    async def help_cmd(interaction: discord.Interaction):
        embed = discord.Embed(title="🎵 ShawarmaMusic — Command List", color=CYAN)
        embed.add_field(name="/play <query>", value="Play song, playlist, or search.", inline=False)
        embed.add_field(name="/queue <query>", value="Add to queue.", inline=False)
        embed.add_field(name="/skip", value="Skip song.", inline=False)
        embed.add_field(name="/stop", value="Disconnect bot.", inline=False)
        embed.add_field(name="/shuffle", value="Shuffle queue.", inline=False)
        embed.add_field(name="/loop <mode>", value="one / all / off", inline=False)
        embed.add_field(name="/nukeslash", value="Clear local guild commands.", inline=False)
        embed.set_footer(text="Bot made by You")
        await interaction.response.send_message(embed=embed)

    # ---------------------- Events ----------------------

    @bot.event
    async def on_ready():
        try:
            await tree.sync()
            print(f"[Bot Status] Synced slash commands successfully!")
        except Exception as e:
            print(f"[Bot Status] Failed to sync commands: {e}")
        print(f"[Bot Status] Logged in as {bot.user}")
        default_status = "online" if BOT_ONLINE_BY_DEFAULT else "offline (invisible)"
        print(f"[Bot Status] Default status is set to: {default_status}")
        if BOT_ONLINE_BY_DEFAULT:
            await bot.change_presence(status=discord.Status.online, activity=discord.Game("/help 🎧"))
        else:
            await bot.change_presence(status=discord.Status.invisible)

    @bot.event
    async def on_voice_state_update(member, before, after):
        if member == bot.user and before.channel is not None and after.channel is None:
            # Bot disconnected manually
            voice_clients.pop(before.channel.guild.id, None)
            now_playing_info.pop(before.channel.guild.id, None)
            queues.pop(before.channel.guild.id, None)
            return

        if before.channel is not None:
            vc = voice_clients.get(before.channel.guild.id)
            if vc and vc.channel == before.channel:
                # If bot is alone in channel, start idle check
                if len(vc.channel.members) == 1:
                    schedule_idle_check(before.channel.guild.id)
                # If others join, cancel idle check
                elif len(vc.channel.members) > 1 and before.channel.guild.id in idle_tasks:
                    task = idle_tasks.pop(before.channel.guild.id)
                    if not task.done():
                        task.cancel()

    bot.run(TOKEN)

if __name__ == "__main__":
    run_bot()