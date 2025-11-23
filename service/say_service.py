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

logger = get_logger()


async def fetch_attachment_from_url(url: str, filename: Optional[str] = None, timeout: int = 30) -> Optional[discord.File]:
    """
    Download a file from `url` and return a discord.File (or None on failure).
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                if resp.status != 200:
                    logger.warning(f"fetch_attachment_from_url: HTTP {resp.status} for {url}")
                    return None
                data = await resp.read()

                # determine filename
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


async def find_reply_message(view, interaction: discord.Interaction) -> Tuple[Optional[discord.Message], Optional[discord.TextChannel]]:
    """
    Locate a message to reply to using view.reply_to (expects message ID string).
    Returns (message, channel) or (None, None) and replies ephemerally on failure.
    """
    try:
        message_id = int(view.reply_to)
    except (ValueError, TypeError):
        await interaction.followup.send("❌ Invalid message ID!", ephemeral=True)
        return None, None

    # search in configured channel first, then all text channels
    search_channels = [view.target_channel] + [ch for ch in interaction.guild.text_channels if ch != view.target_channel]
    for channel in search_channels:
        try:
            msg = await channel.fetch_message(message_id)
            return msg, channel
        except (discord.NotFound, discord.Forbidden):
            continue

    await interaction.followup.send(f"❌ Message {view.reply_to} not found!", ephemeral=True)
    return None, None


async def prepare_files(view, interaction: discord.Interaction) -> Tuple[List[discord.File], Optional[str]]:
    """
    Produce a list of discord.File objects for sending based on view state.
    Returns (files_list, error_message_or_None).
    Supports:
      - direct initial attachment (not used in this design but kept for compatibility)
      - attachment_url (downloaded)
      - attachment_message_link/message_id -> fetch attachments from that message
    """
    files = []

    # 1) direct attached Attachment object (if set)
    if getattr(view, "attachment", None):
        try:
            attached = view.attachment  # discord.Attachment
            data = await attached.read()
            files.append(discord.File(io.BytesIO(data), filename=attached.filename, spoiler=view.spoiler))
        except Exception as e:
            logger.error(f"prepare_files: failed to read direct attachment: {e}", exc_info=True)
            return [], "Failed to process the attached file."

    # 2) attachment_url
    if getattr(view, "attachment_url", None):
        fetched = await fetch_attachment_from_url(view.attachment_url, filename=getattr(view, "attachment_filename", None))
        if not fetched:
            return [], "Failed to download file from the provided URL."
        # apply spoiler by renaming (discord.File has no built-in 'spoiler' flag in creation in older versions)
        if view.spoiler:
            # prepend SPOILER_ to filename (Discord treats filename starting with SPOILER_ as spoiler)
            fetched.filename = f"SPOILER_{fetched.filename}"
        files.append(fetched)

    # 3) attachment_message_link or message id: try parse and fetch attachments
    if getattr(view, "attachment_message_link", None):
        link = view.attachment_message_link.strip()
        try:
            # parse link format: https://discord.com/channels/<guild>/<channel>/<message>
            parts = link.rstrip("/").split("/")
            message_id = int(parts[-1])
            channel_id = int(parts[-2])
            # fetch channel and message
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


async def send_via_webhook(view, interaction: discord.Interaction, content, embed, files):
    """
    Send the message via webhook. Uses provided webhook URL if present,
    otherwise creates a temporary webhook in the target channel and deletes it.
    """
    webhook = None
    created = False
    try:
        if getattr(view, "webhook_url", None):
            # from_url uses an aiohttp session; reuse bot's http session
            webhook = discord.Webhook.from_url(view.webhook_url, session=view.bot.http._HTTPClient__session)
        else:
            webhook = await view.target_channel.create_webhook(name=view.webhook_name or "Say Webhook", reason=f"Say command by {interaction.user}")
            created = True

        # send - discord.Webhook.send returns a WebhookMessage when wait=True
        sent = await webhook.send(content=content, embed=embed, files=files, username=view.webhook_name or interaction.guild.me.display_name, avatar_url=view.webhook_avatar, wait=True)

        if created:
            try:
                await webhook.delete()
            except Exception:
                logger.debug("send_via_webhook: failed to delete temp webhook (non-fatal)")

        return sent
    except Exception as e:
        logger.error(f"Webhook send failed: {e}", exc_info=True)
        await interaction.followup.send(f"❌ Webhook error: {str(e)[:200]}", ephemeral=True)
        return None


async def send_via_bot(view, reply_message, content, embed, files):
    """
    Send via bot account (reply if reply_message present).
    """
    if reply_message:
        return await reply_message.reply(content=content, embed=embed, files=files)
    return await view.target_channel.send(content=content, embed=embed, files=files)


async def handle_view_timeout(view):
    """
    Gracefully mark a view as timed out.
    """
    try:
        for item in view.children:
            item.disabled = True
        await view.interaction.edit_original_response(embed=discord.Embed(title="⏱️ Configuration Timed Out", color=discord.Color.orange()), view=view)
    except Exception:
        pass
