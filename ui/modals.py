"""
Complete fixed modals.py with all naming conflicts resolved
"""
import discord
from urllib.parse import urlparse
from utils.logger import get_logger

logger = get_logger()


def is_valid_webhook_url(url: str) -> bool:
    """Validate Discord webhook URL format"""
    if not url:
        return False
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https"):
            return False
        return "/api/webhooks/" in p.path and ("discord" in p.netloc or "discordapp" in p.netloc)
    except Exception:
        return False


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
        label="Webhook URL(s) - one per line",
        style=discord.TextStyle.paragraph,
        placeholder="https://discord.com/api/webhooks/...\nhttps://discord.com/api/webhooks/...",
        required=False
    )
    
    webhook_name_input = discord.ui.TextInput(
        label="Webhook Name",
        style=discord.TextStyle.short,
        placeholder="Display name for the webhook",
        required=False,
        max_length=80
    )
    
    webhook_avatar_input = discord.ui.TextInput(
        label="Webhook Avatar URL",
        style=discord.TextStyle.short,
        placeholder="https://example.com/avatar.png",
        required=False
    )
    
    def __init__(self, view):
        super().__init__()
        self.view = view
        # Prefill existing values
        if view.webhook_urls:
            self.webhook_urls_input.default = "\n".join(view.webhook_urls)
        if view.webhook_name:
            self.webhook_name_input.default = view.webhook_name
        if view.webhook_avatar:
            self.webhook_avatar_input.default = view.webhook_avatar
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Parse webhook URLs (one per line)
            urls_text = self.webhook_urls_input.value.strip()
            
            if urls_text:
                urls = [url.strip() for url in urls_text.split("\n") if url.strip()]
                
                # Validate all URLs
                invalid_urls = []
                valid_urls = []
                
                for url in urls:
                    if is_valid_webhook_url(url):
                        valid_urls.append(url)
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
                
                # Show success message with count
                success_msg = f"✅ {len(valid_urls)} webhook URL(s) configured!"
                if len(valid_urls) > 1:
                    success_msg += "\n\nYour message will be sent to all webhooks."
            else:
                # Clear webhooks
                self.view.webhook_urls = []
                success_msg = "✅ Webhooks cleared. A temporary webhook will be created when sending."
            
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