"""
Complete fixed modals.py with all naming conflicts resolved
"""
import discord
from urllib.parse import urlparse
from utils.helper import get_webhook_info, get_thread_name, fetch_channel_global
from utils.validators import is_valid_webhook_url, validate_thread_for_webhook
from utils.logger import get_logger

logger = get_logger()


class ChannelSelectModal(discord.ui.Modal, title="Select Target Channel"):
    """Modal for selecting which channel to post in"""
    
    channel_input = discord.ui.TextInput(
        label="Channel ID or #mention",
        style=discord.TextStyle.short,
        placeholder="Right-click channel > Copy Channel ID, or type #channel-name",
        required=True
    )
    
    def __init__(self, view):
        super().__init__()
        self.view = view
        # Prefill with current channel
        if view.target_channel:
            self.channel_input.default = str(view.target_channel.id)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            channel_str = self.channel_input.value.strip()
            
            # Try parsing as channel mention first
            if channel_str.startswith("<#") and channel_str.endswith(">"):
                channel_id = int(channel_str[2:-1])
            else:
                # Try as raw ID
                channel_id = int(channel_str)
            
            # Fetch the channel
            channel = interaction.guild.get_channel(channel_id)
            if not channel:
                channel = await interaction.guild.fetch_channel(channel_id)
            
            # Verify it's a text-based channel
            if not isinstance(channel, (discord.TextChannel, discord.Thread, discord.ForumChannel)):
                await interaction.response.send_message(
                    "❌ That's not a valid text channel, thread, or forum!",
                    ephemeral=True
                )
                return
            
            # Check permissions
            perms = channel.permissions_for(interaction.guild.me)
            if not perms.send_messages:
                await interaction.response.send_message(
                    f"❌ I don't have permission to send messages in {channel.mention}!",
                    ephemeral=True
                )
                return
            
            self.view.target_channel = channel
            self.view.rebuild_ui()
            await interaction.response.edit_message(
                embed=self.view.get_config_embed(),
                view=self.view
            )
            await interaction.followup.send(
                f"✅ Target channel set to {channel.mention}",
                ephemeral=True
            )
        
        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid channel ID or mention format!",
                ephemeral=True
            )
        except discord.NotFound:
            await interaction.response.send_message(
                "❌ Channel not found!",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to access that channel!",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error in ChannelSelectModal: {e}", exc_info=True)
            await interaction.response.send_message(
                f"❌ Error selecting channel: {str(e)[:200]}",
                ephemeral=True
            )

class MessageContentModal(discord.ui.Modal, title="Message Content"):
    """Modal for adding/editing message text content"""
    
    content_input = discord.ui.TextInput(
        label="Message",
        style=discord.TextStyle.paragraph,
        placeholder="Type your message here...",
        required=True,
        max_length=2000
    )
    
    def __init__(self, view):
        super().__init__()
        self.view = view
        # Prefill if content exists
        if view.message_content:
            self.content_input.default = view.message_content
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            self.view.message_content = self.content_input.value
            self.view.has_message = True
            self.view.rebuild_ui()
            await interaction.response.edit_message(
                embed=self.view.get_config_embed(),
                view=self.view
            )
        except Exception as e:
            logger.error(f"Error in MessageContentModal: {e}", exc_info=True)
            await interaction.response.send_message(
                f"❌ Error updating message: {str(e)[:200]}",
                ephemeral=True
            )

class EmbedContentModal(discord.ui.Modal, title="Embed Configuration"):
    """Modal for configuring embed content"""
    
    embed_title_input = discord.ui.TextInput(
        label="Embed Title",
        style=discord.TextStyle.short,
        placeholder="Title (optional)",
        required=False,
        max_length=256
    )
    
    embed_description_input = discord.ui.TextInput(
        label="Embed Description",
        style=discord.TextStyle.paragraph,
        placeholder="Full description",
        required=False,
        max_length=4000
    )
    
    embed_color_input = discord.ui.TextInput(
        label="Embed Color (hex)",
        style=discord.TextStyle.short,
        placeholder="e.g., FF5733 or #FF5733",
        required=False,
        max_length=7
    )
    
    embed_footer_input = discord.ui.TextInput(
        label="Footer",
        style=discord.TextStyle.short,
        placeholder="Footer text (optional)",
        required=False,
        max_length=2048
    )
    
    def __init__(self, view):
        super().__init__()
        self.view = view
        # Prefill existing values
        if view.embed_title:
            self.embed_title_input.default = view.embed_title
        if view.embed_description:
            self.embed_description_input.default = view.embed_description
        if view.embed_color:
            self.embed_color_input.default = view.embed_color
        if view.embed_footer:
            self.embed_footer_input.default = view.embed_footer
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            self.view.embed_title = self.embed_title_input.value or None
            self.view.embed_description = self.embed_description_input.value or None
            self.view.embed_color = self.embed_color_input.value or None
            self.view.embed_footer = self.embed_footer_input.value or None
            self.view.has_embed = True
            self.view.rebuild_ui()
            await interaction.response.edit_message(
                embed=self.view.get_config_embed(),
                view=self.view
            )
        except Exception as e:
            logger.error(f"Error in EmbedContentModal: {e}", exc_info=True)
            await interaction.response.send_message(
                f"❌ Error updating embed: {str(e)[:200]}",
                ephemeral=True
            )

class EmbedImagesModal(discord.ui.Modal, title="Embed Images"):
    """Modal for adding images to embeds"""
    
    image_url_input = discord.ui.TextInput(
        label="Main Image URL",
        style=discord.TextStyle.short,
        placeholder="https://example.com/image.png",
        required=False
    )
    
    thumbnail_url_input = discord.ui.TextInput(
        label="Thumbnail URL",
        style=discord.TextStyle.short,
        placeholder="https://example.com/thumb.png",
        required=False
    )
    
    author_name_input = discord.ui.TextInput(
        label="Author Name",
        style=discord.TextStyle.short,
        placeholder="Author (optional)",
        required=False
    )
    
    author_icon_input = discord.ui.TextInput(
        label="Author Icon URL",
        style=discord.TextStyle.short,
        placeholder="https://example.com/icon.png",
        required=False
    )
    
    def __init__(self, view):
        super().__init__()
        self.view = view
        # Prefill existing values
        if view.embed_image:
            self.image_url_input.default = view.embed_image
        if view.embed_thumbnail:
            self.thumbnail_url_input.default = view.embed_thumbnail
        if view.embed_author:
            self.author_name_input.default = view.embed_author
        if view.embed_author_icon:
            self.author_icon_input.default = view.embed_author_icon
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            self.view.embed_image = self.image_url_input.value or None
            self.view.embed_thumbnail = self.thumbnail_url_input.value or None
            self.view.embed_author = self.author_name_input.value or None
            self.view.embed_author_icon = self.author_icon_input.value or None
            self.view.rebuild_ui()
            await interaction.response.edit_message(
                embed=self.view.get_config_embed(),
                view=self.view
            )
        except Exception as e:
            logger.error(f"Error in EmbedImagesModal: {e}", exc_info=True)
            await interaction.response.send_message(
                f"❌ Error updating images: {str(e)[:200]}",
                ephemeral=True
            )

class AttachmentModal(discord.ui.Modal, title="Add Attachment"):
    """
    Modal for adding attachments via URL or message link.
    Note: Discord doesn't allow file uploads in modals, so we use URLs.
    """
    
    file_url_input = discord.ui.TextInput(
        label="File URL",
        style=discord.TextStyle.short,
        placeholder="https://example.com/image.png",
        required=False
    )
    
    message_link_input = discord.ui.TextInput(
        label="Or Discord Message Link (with attachment)",
        style=discord.TextStyle.paragraph,
        placeholder="https://discord.com/channels/guild_id/channel_id/message_id",
        required=False
    )
    
    filename_input = discord.ui.TextInput(
        label="Custom Filename (optional)",
        style=discord.TextStyle.short,
        placeholder="my-file.png",
        required=False
    )
    
    def __init__(self, view):
        super().__init__()
        self.view = view
        # Prefill existing values
        if view.attachment_url:
            self.file_url_input.default = view.attachment_url
        if view.attachment_message_link:
            self.message_link_input.default = view.attachment_message_link
        if view.attachment_filename:
            self.filename_input.default = view.attachment_filename
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            url = self.file_url_input.value.strip() or None
            msg_link = self.message_link_input.value.strip() or None
            filename = self.filename_input.value.strip() or None
            
            # Clear if both empty
            if not url and not msg_link:
                self.view.attachment_url = None
                self.view.attachment_message_link = None
                self.view.attachment_filename = None
                self.view.has_attachment = False
                self.view.rebuild_ui()
                await interaction.response.edit_message(
                    embed=self.view.get_config_embed(),
                    view=self.view
                )
                return
            
            # Prefer message link if both provided
            if msg_link:
                # Validate message link format
                if not ("discord.com/channels/" in msg_link or "discordapp.com/channels/" in msg_link):
                    await interaction.response.send_message(
                        "❌ Invalid message link format. Use: https://discord.com/channels/guild/channel/message",
                        ephemeral=True
                    )
                    return
                
                self.view.attachment_message_link = msg_link
                self.view.attachment_url = None
                self.view.attachment_filename = None
                self.view.has_attachment = True
                
                msg = "✅ Message link saved. Attachments will be fetched from that message."
                if url:
                    msg += "\n(File URL was ignored since you provided a message link)"
                
                self.view.rebuild_ui()
                await interaction.response.edit_message(
                    embed=self.view.get_config_embed(),
                    view=self.view
                )
                await interaction.followup.send(msg, ephemeral=True)
            
            elif url:
                # Validate URL format
                if not url.startswith(("http://", "https://")):
                    await interaction.response.send_message(
                        "❌ Invalid URL. Must start with http:// or https://",
                        ephemeral=True
                    )
                    return
                
                self.view.attachment_url = url
                self.view.attachment_message_link = None
                self.view.attachment_filename = filename
                self.view.has_attachment = True
                self.view.rebuild_ui()
                await interaction.response.edit_message(
                    embed=self.view.get_config_embed(),
                    view=self.view
                )
        
        except Exception as e:
            logger.error(f"Error in AttachmentModal: {e}", exc_info=True)
            try:
                await interaction.response.send_message(
                    f"❌ Error updating attachment: {str(e)[:200]}",
                    ephemeral=True
                )
            except:
                await interaction.followup.send(
                    f"❌ Error updating attachment: {str(e)[:200]}",
                    ephemeral=True
                )

class WebhookConfigModal(discord.ui.Modal, title="Webhook Configuration"):
    # Modal for configuring webhook settings - supports multiple webhook URLs

    webhook_urls_input = discord.ui.TextInput(
        label="Webhook URL(s) - one per line (OPTIONAL)",
        style=discord.TextStyle.paragraph,
        placeholder="One URL per line. Leave empty to auto-create a temporary webhook.",
        required=False
    )

    thread_id_input = discord.ui.TextInput(
        label="Thread ID (OPTIONAL)",
        style=discord.TextStyle.short,
        placeholder="Thread ID for forum or webhook threads. Right-click thread > Copy ID.",
        required=False
    )

    webhook_name_input = discord.ui.TextInput(
        label="Display Name (OPTIONAL)",
        style=discord.TextStyle.short,
        placeholder="Custom webhook display name (no effect on custom URLs).",
        required=False,
        max_length=80
    )

    webhook_avatar_input = discord.ui.TextInput(
        label="Avatar URL (OPTIONAL)",
        style=discord.TextStyle.short,
        placeholder="https://example.com/avatar.png",
        required=False
    )

    def __init__(self, view):
        super().__init__()
        self.view = view

        # Prefill webhook URLs
        try:
            urls = getattr(view, "webhook_urls", None)
            if urls:
                urls = [str(u) for u in urls if u]
                if urls:
                    self.webhook_urls_input.default = "\n".join(urls)
        except Exception as e:
            logger.error(f"WebhookConfigModal: error pre-filling webhook_urls: {e}", exc_info=True)

        # Prefill thread ID
        try:
            if getattr(view, "thread_id", None):
                self.thread_id_input.default = str(view.thread_id)
        except Exception as e:
            logger.error(f"WebhookConfigModal: error pre-filling thread_id: {e}", exc_info=True)

        # Prefill name
        try:
            if getattr(view, "webhook_name", None):
                self.webhook_name_input.default = str(view.webhook_name)
        except Exception as e:
            logger.error(f"WebhookConfigModal: error pre-filling webhook_name: {e}", exc_info=True)

        # Prefill avatar
        try:
            if getattr(view, "webhook_avatar", None):
                self.webhook_avatar_input.default = str(view.webhook_avatar)
        except Exception as e:
            logger.error(f"WebhookConfigModal: error pre-filling webhook_avatar: {e}", exc_info=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            bot = self.view.bot
            raw_urls = (self.webhook_urls_input.value or "").strip()
            thread_raw = (self.thread_id_input.value or "").strip()
            valid_urls = []
            invalid_urls = []
            channel_names = []
            webhook_meta = {}
            base_webhook_info = None

            # Parse and validate webhook URLs
            if raw_urls:
                urls = [u.strip() for u in raw_urls.split("\n") if u.strip()]
                for url in urls:
                    if is_valid_webhook_url(url):
                        info = await get_webhook_info(url, bot)
                        if info:
                            valid_urls.append(url)
                            webhook_meta[url] = info
                            if info["bot_in_guild"]:
                                chan_label = f"#{info['channel_name']}"
                            else:
                                chan_label = "Unknown (bot not in webhook server)"
                            channel_names.append(chan_label)
                        else:
                            invalid_urls.append(url)
                    else:
                        invalid_urls.append(url)

                if invalid_urls:
                    text = "❌ Invalid webhook URL(s):\n" + "\n".join(f"• {u}" for u in invalid_urls[:5])
                    return await interaction.response.send_message(text, ephemeral=True)

                self.view.webhook_urls = valid_urls
                self.view.webhook_channel_names = channel_names
                self.view.webhook_meta = webhook_meta

                if valid_urls:
                    base_webhook_info = webhook_meta[valid_urls[0]]

                    if base_webhook_info["bot_in_guild"]:
                        try:
                            chan = await fetch_channel_global(bot, base_webhook_info["channel_id"])
                            if chan:
                                self.view.target_channel = chan
                        except Exception as e:
                            logger.error(f"Failed to auto-set target channel from webhook: {e}", exc_info=True)
            else:
                self.view.webhook_urls = []
                self.view.webhook_channel_names = []
                self.view.webhook_meta = {}

                self.view.target_channel = self.view.original_target_channel
                self.view.thread_id = None
                self.view.thread_name = None

            # Thread ID handling
            self.view.thread_id = thread_raw if thread_raw else None
            self.view.thread_name = None
            thread_warning = None

            if thread_raw:
                if base_webhook_info and base_webhook_info.get("bot_in_guild"):
                    validate_result = await validate_thread_for_webhook(thread_raw, base_webhook_info, bot)
                    if validate_result["display_name"]:
                        self.view.thread_name = validate_result["display_name"]
                    if not validate_result["ok"]:
                        thread_warning = validate_result["warning"]
                    elif validate_result["warning"]:
                        thread_warning = validate_result["warning"]
                else:
                    name = await get_thread_name(thread_raw, bot)
                    if name:
                        self.view.thread_name = name
                    else:
                        self.view.thread_name = None
                        thread_warning = "⚠️ Bot is not in the webhook's server, cannot resolve thread name."

            # Name and avatar settings
            self.view.webhook_name = (self.webhook_name_input.value or "").strip() or None
            self.view.webhook_avatar = (self.webhook_avatar_input.value or "").strip() or None

            # Rebuild main UI
            self.view.rebuild_ui()
            await interaction.response.edit_message(
                embed=self.view.get_config_embed(),
                view=self.view
            )

            # Ephemeral summary
            lines = []
            if self.view.webhook_urls:
                lines.append(f"✅ {len(self.view.webhook_urls)} webhook URL(s) configured.")
                if channel_names:
                    lines.append(f"Channels: {', '.join(channel_names)}")
                lines.append("Note: If the bot is not in a webhook's server, channel names may show as unknown.")
            else:
                lines.append("✅ Webhooks cleared. A temporary webhook will be created in the target channel when sending.")

            if self.view.thread_id:
                if self.view.thread_name:
                    lines.append(f"🧵 Thread: {self.view.thread_name}")
                else:
                    lines.append(f"🧵 Thread ID: {self.view.thread_id}")

            if thread_warning:
                lines.append("")
                lines.append(thread_warning)

            await interaction.followup.send("\n".join(lines), ephemeral=True)

        except Exception as e:
            logger.error(f"WebhookConfigModal error: {e}", exc_info=True)
            try:
                await interaction.response.send_message(
                    f"❌ Error updating webhook config: {str(e)[:200]}",
                    ephemeral=True
                )
            except:
                await interaction.followup.send(
                    f"❌ Error updating webhook config: {str(e)[:200]}",
                    ephemeral=True
                )


class ReplyConfigModal(discord.ui.Modal, title="Reply Configuration"):
    """Modal for setting message to reply to"""
    
    message_id_input = discord.ui.TextInput(
        label="Message ID to Reply To",
        style=discord.TextStyle.short,
        placeholder="Right-click message > Copy Message ID",
        required=True
    )
    
    def __init__(self, view):
        super().__init__()
        self.view = view
        # Prefill existing value
        if view.reply_to:
            self.message_id_input.default = view.reply_to
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            msg_id = self.message_id_input.value.strip()
            
            # Validate message ID is numeric
            try:
                int(msg_id)
            except ValueError:
                await interaction.response.send_message(
                    "❌ Invalid message ID. Must be a numeric ID.",
                    ephemeral=True
                )
                return
            
            self.view.reply_to = msg_id
            self.view.rebuild_ui()
            await interaction.response.edit_message(
                embed=self.view.get_config_embed(),
                view=self.view
            )
        
        except Exception as e:
            logger.error(f"Error in ReplyConfigModal: {e}", exc_info=True)
            await interaction.response.send_message(
                f"❌ Error setting reply: {str(e)[:200]}",
                ephemeral=True
            )