"""
Complete fixed modals.py with all naming conflicts resolved
"""
import discord
from urllib.parse import urlparse
from utils.helper import get_webhook_info, get_thread_name
from utils.validators import is_valid_webhook_url
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
    """Modal for configuring webhook settings - supports multiple webhook URLs"""
    
    webhook_urls_input = discord.ui.TextInput(
        label="Webhook URL(s) - one per line (OPTIONAL)",
        style=discord.TextStyle.paragraph,
        placeholder="https://discord.com/api/webhooks/...\nhttps://discord.com/api/webhooks/...\n\nLeave empty to auto-create temporary webhook",
        required=False
    )
    
    thread_id_input = discord.ui.TextInput(
        label="Thread ID (OPTIONAL)",
        style=discord.TextStyle.short,
        placeholder="For forum posts or when using custom webhook URLs with threads (right-click thread > Copy ID)",
        required=False
    )
    
    webhook_name_input = discord.ui.TextInput(
        label="Display Name (OPTIONAL)",
        style=discord.TextStyle.short,
        placeholder="Custom webhook display name (if not using custom URL)",
        required=False,
        max_length=80
    )
    
    webhook_avatar_input = discord.ui.TextInput(
        label="Avatar URL (OPTIONAL)",
        style=discord.TextStyle.short,
        placeholder="https://example.com/avatar.png (if not using custom URL)",
        required=False
    )
    
    def __init__(self, view):
        super().__init__()
        self.view = view
        # Prefill existing values
        if view.webhook_urls:
            self.webhook_urls_input.default = "\n".join(view.webhook_urls)
        if view.thread_id:
            self.thread_id_input.default = view.thread_id
        if view.webhook_name:
            self.webhook_name_input.default = view.webhook_name
        if view.webhook_avatar:
            self.webhook_avatar_input.default = view.webhook_avatar
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            
            urls_text = self.webhook_urls_input.value.strip()
            
            if urls_text:
                urls = [url.strip() for url in urls_text.split("\n") if url.strip()]
                
                invalid_urls = []
                valid_urls = []
                webhook_channel_names = []
                
                for url in urls:
                    if is_valid_webhook_url(url):
                        valid_urls.append(url)
                        
                        # Use helper method to get webhook info
                        webhook_info = await get_webhook_info(url, self.view.bot)
                        if webhook_info:
                            webhook_channel_names.append(f"#{webhook_info['channel_name']}")
                        else:
                            webhook_channel_names.append("Unknown channel")
                    else:
                        invalid_urls.append(url)
                
                if invalid_urls:
                    await interaction.response.send_message(
                        f"❌ {len(invalid_urls)} invalid webhook URL(s) found:\n" + 
                        "\n".join([f"• {url[:50]}..." if len(url) > 50 else f"• {url}" for url in invalid_urls[:3]]),
                        ephemeral=True
                    )
                    return
                
                self.view.webhook_urls = valid_urls
                self.view.webhook_channel_names = webhook_channel_names
                
                success_msg = f"✅ {len(valid_urls)} webhook URL(s) configured!\n"
                if webhook_channel_names:
                    success_msg += f"**Channels:** {', '.join(webhook_channel_names)}\n\n"
                success_msg += "📝 **Note:** When using custom webhook URLs:\n"
                success_msg += "• Name/avatar settings will be ignored (use webhook's defaults)\n"
                success_msg += "• You can specify a thread ID to post in specific threads\n"
                success_msg += "• Message will be sent to all configured webhooks"
            else:
                self.view.webhook_urls = []
                self.view.webhook_channel_names = []
                success_msg = "✅ Webhooks cleared. A temporary webhook will be created when sending.\n\n"
                success_msg += "You can now use the name and avatar settings."
            
            # Handle thread ID - use helper method
            thread_id_str = self.thread_id_input.value.strip()
            if thread_id_str:
                thread_name = await get_thread_name(thread_id_str, interaction)
                self.view.thread_name = thread_name
            else:
                self.view.thread_name = None
            
            self.view.thread_id = thread_id_str or None
            self.view.webhook_name = self.webhook_name_input.value.strip() or None
            self.view.webhook_avatar = self.webhook_avatar_input.value.strip() or None
            self.view.rebuild_ui()
            
            await interaction.response.edit_message(
                embed=self.view.get_config_embed(),
                view=self.view
            )
            await interaction.followup.send(success_msg, ephemeral=True)
        
        except Exception as e:
            logger.error(f"Error in WebhookConfigModal: {e}", exc_info=True)
            await interaction.response.send_message(
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