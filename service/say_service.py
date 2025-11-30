"""
service/say_service.py

All Discord API interactions and file fetching live here.
Uses discord.py for sending and aiohttp to download files from URLs.
"""
import io
import discord
import aiohttp
from typing import Optional, Tuple, List
from utils.logger import get_logger
from utils.helper import get_webhook_info, fetch_channel_global

logger = get_logger()

# Download a file from URL and return a discord.File
async def fetch_attachment_from_url(url: str, filename: Optional[str] = None, timeout: int = 30) -> Optional[discord.File]:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                if resp.status != 200:
                    logger.warning(f"fetch_attachment_from_url: HTTP {resp.status} for {url}")
                    return None
                data = await resp.read()

                if not filename:
                    disposition = resp.headers.get("Content-Disposition", "")
                    if "filename=" in disposition:
                        filename = disposition.split("filename=")[1].strip('" ')
                    else:
                        filename = url.split("/")[-1].split("?")[0] or "attachment"

                return discord.File(io.BytesIO(data), filename=filename)
    except Exception as e:
        logger.error(f"Error downloading attachment from URL {url}: {e}", exc_info=True)
        return None

# Locate a message to reply to using view.reply_to
async def find_reply_message(view, interaction: discord.Interaction) -> Tuple[Optional[discord.Message], Optional[discord.TextChannel]]:
    try:
        message_id = int(view.reply_to)
    except (ValueError, TypeError):
        await interaction.followup.send("❌ Invalid message ID!", ephemeral=True)
        return None, None

    search_channels = [view.target_channel] + [ch for ch in interaction.guild.text_channels if ch != view.target_channel]
    for channel in search_channels:
        try:
            msg = await channel.fetch_message(message_id)
            return msg, channel
        except (discord.NotFound, discord.Forbidden):
            continue

    await interaction.followup.send(f"❌ Message {view.reply_to} not found!", ephemeral=True)
    return None, None

# Prepare files for sending based on view state
async def prepare_files(view, interaction: discord.Interaction) -> Tuple[List[discord.File], Optional[str]]:
    files = []

    if getattr(view, "attachment", None):
        try:
            attached = view.attachment
            data = await attached.read()
            files.append(discord.File(io.BytesIO(data), filename=attached.filename, spoiler=view.spoiler))
        except Exception as e:
            logger.error(f"prepare_files: failed to read direct attachment: {e}", exc_info=True)
            return [], "Failed to process the attached file."

    if getattr(view, "attachment_url", None):
        fetched = await fetch_attachment_from_url(view.attachment_url, filename=getattr(view, "attachment_filename", None))
        if not fetched:
            return [], "Failed to download file from the provided URL."
        if view.spoiler:
            fetched.filename = f"SPOILER_{fetched.filename}"
        files.append(fetched)

    if getattr(view, "attachment_message_link", None):
        link = view.attachment_message_link.strip()
        try:
            parts = link.rstrip("/").split("/")
            message_id = int(parts[-1])
            channel_id = int(parts[-2])
            channel = interaction.guild.get_channel(channel_id) or await interaction.guild.fetch_channel(channel_id)
            msg = await channel.fetch_message(message_id)
            if not msg.attachments:
                return [], "That message has no attachments."
            for att in msg.attachments:
                data = await att.read()
                file_obj = discord.File(io.BytesIO(data), filename=att.filename, spoiler=view.spoiler)
                files.append(file_obj)
        except Exception as e:
            logger.error(f"prepare_files: failed to fetch attachments from message link {link}: {e}", exc_info=True)
            return [], "Failed to fetch attachments from the provided message link."

    return files, None

# Internal helper to send via a temporary webhook in a local channel
async def _send_via_temp_webhook(view, interaction: discord.Interaction, content, embed, files):
    webhook = None
    created = False
    sent = None

    try:
        is_forum = isinstance(view.target_channel, discord.ForumChannel)

        if is_forum:
            if not view.thread_id:
                logger.error("Forum channel selected but no thread_id provided")
                return None

            try:
                thread = await view.target_channel.guild.fetch_channel(int(view.thread_id))
                if not isinstance(thread, discord.Thread) or thread.parent_id != view.target_channel.id:
                    logger.error(f"Invalid thread ID {view.thread_id} or thread does not belong to forum {view.target_channel.id}")
                    return None

                webhook = await view.target_channel.create_webhook(
                    name=view.webhook_name or "Say Webhook",
                    reason=f"Say command by {interaction.user}"
                )
                created = True

                sent = await webhook.send(
                    content=content,
                    embed=embed,
                    files=files,
                    username=view.webhook_name or interaction.guild.me.display_name,
                    avatar_url=view.webhook_avatar,
                    thread=thread,
                    wait=True
                )
            except Exception as e:
                logger.error(f"Failed to send via temp webhook in forum: {e}", exc_info=True)
                return None
        else:
            if isinstance(view.target_channel, discord.Thread):
                parent = view.target_channel.parent
                webhook = await parent.create_webhook(
                    name=view.webhook_name or "Say Webhook",
                    reason=f"Say command by {interaction.user}"
                )
                created = True

                sent = await webhook.send(
                    content=content,
                    embed=embed,
                    files=files,
                    username=view.webhook_name or interaction.guild.me.display_name,
                    avatar_url=view.webhook_avatar,
                    thread=view.target_channel,
                    wait=True
                )
            else:
                webhook = await view.target_channel.create_webhook(
                    name=view.webhook_name or "Say Webhook",
                    reason=f"Say command by {interaction.user}"
                )
                created = True

                sent = await webhook.send(
                    content=content,
                    embed=embed,
                    files=files,
                    username=view.webhook_name or interaction.guild.me.display_name,
                    avatar_url=view.webhook_avatar,
                    wait=True
                )

        if created and webhook:
            try:
                await webhook.delete()
            except Exception:
                logger.debug("send_via_webhook: failed to delete temp webhook (non-fatal)")

        return sent
    except Exception as e:
        logger.error(f"Temp webhook send failed: {e}", exc_info=True)
        return None

# Send the message via webhook (custom URL or temporary)
async def send_via_webhook(view, interaction: discord.Interaction, content, embed, files):
    try:
        if getattr(view, "webhook_url", None):
            webhook = discord.Webhook.from_url(view.webhook_url, session=view.bot.http._HTTPClient__session)

            info = None
            meta = getattr(view, "webhook_meta", {}) or {}
            if view.webhook_url in meta:
                info = meta[view.webhook_url]
            else:
                info = await get_webhook_info(view.webhook_url, view.bot)

            thread_obj = None
            thread_id_int = None

            if view.thread_id:
                try:
                    thread_id_int = int(view.thread_id)
                except ValueError:
                    thread_id_int = None

                if info and info.get("bot_in_guild"):
                    try:
                        thread_obj = await fetch_channel_global(view.bot, thread_id_int)
                        if not isinstance(thread_obj, discord.Thread):
                            logger.error(f"Thread ID {view.thread_id} is not a valid thread")
                            thread_obj = None
                    except Exception as e:
                        logger.error(f"Failed to fetch thread {view.thread_id}: {e}", exc_info=True)
                        thread_obj = None

            if thread_obj is not None:
                sent = await webhook.send(
                    content=content,
                    embed=embed,
                    files=files,
                    thread=thread_obj,
                    wait=True
                )
                return sent

            if thread_id_int is not None:
                try:
                    sent = await webhook.send(
                        content=content,
                        embed=embed,
                        files=files,
                        wait=True,
                        thread_id=thread_id_int
                    )
                    return sent
                except TypeError:
                    logger.error("Webhook.send does not support thread_id parameter in this discord.py version.", exc_info=True)
                except Exception as e:
                    logger.error(f"Failed to send to thread_id {thread_id_int} via webhook: {e}", exc_info=True)
                    return None

            try:
                sent = await webhook.send(
                    content=content,
                    embed=embed,
                    files=files,
                    wait=True
                )
                return sent
            except Exception as e:
                logger.error(f"Webhook send failed: {e}", exc_info=True)
                return None
        else:
            return await _send_via_temp_webhook(view, interaction, content, embed, files)
    except Exception as e:
        logger.error(f"send_via_webhook: unexpected failure: {e}", exc_info=True)
        return None

# Send via bot account (reply if reply_message present)
async def send_via_bot(view, reply_message, content, embed, files):
    if reply_message:
        return await reply_message.reply(content=content, embed=embed, files=files)
    return await view.target_channel.send(content=content, embed=embed, files=files)

# Gracefully mark a view as timed out
async def handle_view_timeout(view):
    try:
        for item in view.children:
            item.disabled = True
        await view.interaction.edit_original_response(
            embed=discord.Embed(title="⏱️ Configuration Timed Out", color=discord.Color.orange()),
            view=view
        )
    except Exception:
        pass
