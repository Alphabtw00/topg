"""
Discord UI components - Updated for service provider architecture
"""
import asyncio
import discord
import io
from datetime import datetime, timedelta
from urllib.parse import urlparse
from utils.logger import get_logger
from ui.embeds import create_wallet_finder_embed, create_say_embed
from typing import List, Dict, Any, Optional
from utils.formatters import safe_text
from ui.modals import (
    MessageContentModal,
    EmbedContentModal,
    EmbedImagesModal,
    WebhookConfigModal,
    ReplyConfigModal,
    AttachmentModal
)
from ui.embeds import create_say_embed
from service.say_service import (
    find_reply_message,
    send_via_webhook,
    send_via_bot,
    handle_view_timeout,
    prepare_files
)

logger = get_logger()

class TokenEmbedView(discord.ui.View):
    """Button view for token embeds"""
    __slots__ = ("address", "author_id")
    
    def __init__(self, address: str, author_id: int = None):
        super().__init__(timeout=None)
        self.address = address
        self.author_id = author_id

    @discord.ui.button(label="📋", style=discord.ButtonStyle.grey, custom_id="copy_address", row=0)
    async def copy_address(self, interaction: discord.Interaction, _: discord.ui.Button):
        """Button handler to copy address to clipboard"""
        await interaction.response.send_message(f"{self.address}", ephemeral=True)
        await asyncio.sleep(30)
        await interaction.delete_original_response()
    
    @discord.ui.button(label="❌", style=discord.ButtonStyle.red, custom_id="delete_embed", row=0)
    async def delete_embed(self, interaction: discord.Interaction, _: discord.ui.Button):
        """Delete the embed - only author or admins can use"""
        # Check permissions
        if not self._can_delete(interaction):
            await interaction.response.send_message(
                "❌ Only the message author or server admins can delete this embed.",
                ephemeral=True
            )
            return
        
        try:
            # Delete the message
            await interaction.message.delete()
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to delete messages.",
                ephemeral=True
            )
        except discord.NotFound:
            # Message already deleted
            pass
        except Exception as e:
            logger.error(f"Error deleting embed: {e}")
            await interaction.response.send_message(
                "❌ Failed to delete the embed.",
                ephemeral=True
            )
    
    def _can_delete(self, interaction: discord.Interaction) -> bool:
        """Check if user can delete the embed"""
        # Allow if user is the original message author
        if self.author_id and interaction.user.id == self.author_id:
            return True
        
        # Allow if user has administrator permission
        if interaction.user.guild_permissions.administrator:
            return True
        
        # Allow if user has manage messages permission
        if interaction.user.guild_permissions.manage_messages:
            return True
        
        return False

class GitHubAnalysisView(discord.ui.View):
    """Interactive view for GitHub repository analysis"""
    __slots__ = ("repo_url", "reanalyze_button", "timeout_task", "expiry_time", "cooldown_end")
   
    def __init__(self, repo_url: str):
        # The view itself doesn't time out
        super().__init__(timeout=None)
        self.repo_url = repo_url
        self.timeout_task = None
        self.cooldown_end = None
        # Set expiry time 10 minutes from now
        self.expiry_time = datetime.now() + timedelta(minutes=10)
       
        # Add repository link button
        self.add_item(discord.ui.Button(
            label="View Repository",
            url=repo_url,
            emoji="📂"
        ))
       
        # Reanalyze button with gray style
        self.reanalyze_button = discord.ui.Button(
            label="Reanalyze Repo",
            style=discord.ButtonStyle.gray,
            custom_id="reanalyze_repo",
            emoji="🔄"
        )
        self.reanalyze_button.callback = self.reanalyze_callback
        self.add_item(self.reanalyze_button)
       
        # Start timeout task for the reanalyze button (10 minutes)
        self.start_timeout_task()
   
    def start_timeout_task(self):
        """Start the timeout task for the reanalyze button"""
        async def disable_after_timeout():
            try:
                # Wait 10 minutes
                await asyncio.sleep(600)
                self.reanalyze_button.disabled = True
                self.reanalyze_button.label = "Reanalyze Repo (Expired)"
            except asyncio.CancelledError:
                pass
     
        # Create task
        self.timeout_task = asyncio.create_task(disable_after_timeout())
   
    async def reanalyze_callback(self, interaction: discord.Interaction) -> None:
        """Handle reanalyze button interactions"""
        now = datetime.now()
        
        # If we're on cooldown, show the time remaining
        if self.cooldown_end and now < self.cooldown_end:
            # Calculate remaining time
            remaining = self.cooldown_end - now
            seconds = max(1, int(remaining.total_seconds()))
            
            await interaction.response.send_message(
                f"⏱️ This button is on cooldown. Please wait {seconds} seconds before trying again.",
                ephemeral=True
            )
            return
            
        # If we're past the expiry time, disable permanently
        if now >= self.expiry_time:
            self.reanalyze_button.disabled = True
            self.reanalyze_button.label = "Reanalyze Repo (Expired)"
            await interaction.message.edit(view=self)
            
            await interaction.response.send_message(
                "⏱️ This button has expired and can no longer be used.",
                ephemeral=True
            )
            return
            
        # Handle the cache clear request
        try:
            # Clear this repo from cache to force reanalysis using service provider
            cleared = await interaction.client.services.github_analyzer.clear_from_cache(self.repo_url)
            
            # Send appropriate response
            if cleared:
                await interaction.response.send_message(
                    "✅ Repository has been cleared from memory. Next analysis will be performed from scratch.",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "ℹ️ Repository was not in cache. A fresh analysis will be performed on next check.",
                    ephemeral=True
                )
            
            # Set cooldown (60 seconds from now)
            self.cooldown_end = now + timedelta(seconds=60)
            original_label = "Reanalyze Repo"
            self.reanalyze_button.label = "Reanalyze Repo (60s cooldown)"
            await interaction.message.edit(view=self)
            
            # Reset after delay (if still within expiry window)
            await asyncio.sleep(60)
            
            # Check if we're still within the 10-minute expiry window
            if datetime.now() < self.expiry_time:
                self.cooldown_end = None
                self.reanalyze_button.label = original_label
                try:
                    await interaction.message.edit(view=self)
                except discord.NotFound:
                    # Message might have been deleted
                    pass
            else:
                # We've passed the 10-minute window, disable it
                self.reanalyze_button.disabled = True
                self.reanalyze_button.label = "Reanalyze Repo (Expired)"
                try:
                    await interaction.message.edit(view=self)
                except discord.NotFound:
                    # Message might have been deleted
                    pass
                
        except Exception as e:
            # Handle any unexpected errors
            await interaction.response.send_message(
                f"❌ An error occurred: {str(e)}",
                ephemeral=True
            )
       
    def stop(self):
        """Clean up when the view is no longer needed"""
        if self.timeout_task:
            self.timeout_task.cancel()
        super().stop()

class WebsiteAnalysisView(discord.ui.View):
    """Interactive view for website analysis"""
    
    def __init__(self, website_url: str, bot):
        # The view itself doesn't time out
        super().__init__(timeout=None)
        self.website_url = website_url
        self.bot = bot
        self.timeout_task = None
        self.cooldown_end = None
        # Set expiry time 10 minutes from now
        self.expiry_time = datetime.now() + timedelta(minutes=10)
        
        # Add website link button
        self.add_item(discord.ui.Button(
            label="Visit Website",
            url=website_url if website_url.startswith(('http://', 'https://')) else f"https://{website_url}",
            emoji="🌐",
            style=discord.ButtonStyle.link
        ))
        
        # Add VirusTotal button
        domain = urlparse(website_url).netloc
        virustotal_url = f"https://www.virustotal.com/gui/domain/{domain}/detection"
        self.add_item(discord.ui.Button(
            label="Check on VirusTotal",
            url=virustotal_url,
            emoji="🔍",
            style=discord.ButtonStyle.link
        ))
        
        # Reanalyze button with gray style
        self.reanalyze_button = discord.ui.Button(
            label="Reanalyze Website",
            style=discord.ButtonStyle.gray,
            custom_id="reanalyze_website",
            emoji="🔄"
        )
        self.reanalyze_button.callback = self.reanalyze_callback
        self.add_item(self.reanalyze_button)
        
        # Start timeout task for the reanalyze button (10 minutes)
        self.start_timeout_task()
    
    def start_timeout_task(self):
        """Start the timeout task for the reanalyze button"""
        async def disable_after_timeout():
            try:
                # Wait 10 minutes
                await asyncio.sleep(600)
                self.reanalyze_button.disabled = True
                self.reanalyze_button.label = "Reanalyze Website (Expired)"
            except asyncio.CancelledError:
                pass
        
        # Create task
        self.timeout_task = asyncio.create_task(disable_after_timeout())
    
    async def reanalyze_callback(self, interaction: discord.Interaction) -> None:
        """Handle reanalyze button interactions"""
        now = datetime.now()
        
        # If we're on cooldown, show the time remaining
        if self.cooldown_end and now < self.cooldown_end:
            # Calculate remaining time
            remaining = self.cooldown_end - now
            seconds = max(1, int(remaining.total_seconds()))
            
            await interaction.response.send_message(
                f"⏱️ This button is on cooldown. Please wait {seconds} seconds before trying again.",
                ephemeral=True
            )
            return
            
        # If we're past the expiry time, disable permanently
        if now >= self.expiry_time:
            self.reanalyze_button.disabled = True
            self.reanalyze_button.label = "Reanalyze Website (Expired)"
            await interaction.message.edit(view=self)
            
            await interaction.response.send_message(
                "⏱️ This button has expired and can no longer be used.",
                ephemeral=True
            )
            return
            
        # Handle the cache clear request
        try:
            # Clear this website from cache to force reanalysis
            cleared = await self.bot.services.website_analyzer.clear_from_cache(self.website_url)
            
            # Send appropriate response
            if cleared:
                await interaction.response.send_message(
                    "✅ Website has been cleared from cache. Next analysis will be performed from scratch.",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "ℹ️ Website was not in cache. A fresh analysis will be performed on next check.",
                    ephemeral=True
                )
            
            # Set cooldown (60 seconds from now)
            self.cooldown_end = now + timedelta(seconds=60)
            original_label = "Reanalyze Website"
            self.reanalyze_button.label = "Reanalyze Website (60s cooldown)"
            await interaction.message.edit(view=self)
            
            # Reset after delay (if still within expiry window)
            await asyncio.sleep(60)
            
            # Check if we're still within the 10-minute expiry window
            if datetime.now() < self.expiry_time:
                self.cooldown_end = None
                self.reanalyze_button.label = original_label
                try:
                    await interaction.message.edit(view=self)
                except discord.NotFound:
                    # Message might have been deleted
                    pass
            else:
                # We've passed the 10-minute window, disable it
                self.reanalyze_button.disabled = True
                self.reanalyze_button.label = "Reanalyze Website (Expired)"
                try:
                    await interaction.message.edit(view=self)
                except discord.NotFound:
                    # Message might have been deleted
                    pass
                
        except Exception as e:
            # Handle any unexpected errors
            await interaction.response.send_message(
                f"❌ An error occurred: {str(e)}",
                ephemeral=True
            )
    
    def stop(self):
        """Clean up when the view is no longer needed"""
        if self.timeout_task:
            self.timeout_task.cancel()
        super().stop()

class WalletFinderView(discord.ui.View):
    """Pagination view for wallet finder results"""
    
    def __init__(
        self,
        token_info: Dict,
        all_holders: List[Dict],
        target_mc: float,
        cutoff_value: Optional[float],
        buy_amount_filter: Optional[Dict[str, Any]],
        market_cap_input: str,
        cutoff_input: Optional[str],
        buy_amount_input: Optional[str]
    ):
        super().__init__(timeout=300)  # 5 minutes timeout
        self.token_info = token_info
        self.all_holders = all_holders
        self.target_mc = target_mc
        self.cutoff_value = cutoff_value
        self.buy_amount_filter = buy_amount_filter
        self.market_cap_input = market_cap_input
        self.cutoff_input = cutoff_input
        self.buy_amount_input = buy_amount_input
        
        self.current_page = 1
        self.total_pages = max(1, (len(all_holders) + 9) // 10)
        
        # Update button states
        self.update_buttons()
    
    def update_buttons(self):
        """Update button states based on current page"""
        # Previous page button
        self.previous_page.disabled = self.current_page <= 1
        
        # Next page button
        self.next_page.disabled = self.current_page >= self.total_pages
        
        # Update page info button
        self.page_info.label = f"Page {self.current_page}/{self.total_pages}"
    
    async def update_embed(self, interaction: discord.Interaction):
        """Update the embed with current page data"""
        start_idx = (self.current_page - 1) * 10
        end_idx = start_idx + 10
        page_holders = self.all_holders[start_idx:end_idx]
        
        embed = await create_wallet_finder_embed(
            self.token_info,
            page_holders,
            self.target_mc,
            self.cutoff_value,
            self.buy_amount_filter,
            self.market_cap_input,
            self.cutoff_input,
            self.buy_amount_input,
            page=self.current_page,
            total_pages=self.total_pages
        )
        
        self.update_buttons()
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="◀", style=discord.ButtonStyle.primary, custom_id="previous_page")
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to previous page"""
        if self.current_page > 1:
            self.current_page -= 1
            await self.update_embed(interaction)
    
    @discord.ui.button(label="Page 1/1", style=discord.ButtonStyle.secondary, custom_id="page_info", disabled=True)
    async def page_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Display current page info (disabled button)"""
        pass
    
    @discord.ui.button(label="▶", style=discord.ButtonStyle.primary, custom_id="next_page")
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to next page"""
        if self.current_page < self.total_pages:
            self.current_page += 1
            await self.update_embed(interaction)
    
    async def on_timeout(self):
        """Disable all buttons when view times out"""
        for item in self.children:
            item.disabled = True

class ExplainView(discord.ui.View):
    """Interactive view for navigating between topics"""
    
    def __init__(self, topics: dict, current_topic: str):
        super().__init__(timeout=300)  # 5 minute timeout
        self.topics = topics
        self.current_topic = current_topic
        
        # Add select menu for topics
        self.add_item(TopicSelect(topics, current_topic))
        
        # Add quick navigation buttons
        self.add_item(AllTopicsButton())

class TopicSelect(discord.ui.Select):
    """Dropdown menu for selecting topics"""
    
    def __init__(self, topics: dict, current_topic: str):
        self.topics = topics
        self.current_topic = current_topic
        
        options = []
        for key, data in topics.items():
            options.append(
                discord.SelectOption(
                    label=data["title"][:100],
                    value=key,
                    emoji=data["emoji"],
                    description=f"Learn about {key}",
                    default=(key == current_topic)
                )
            )
        
        super().__init__(
            placeholder="📚 Choose another topic to learn...",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle topic selection"""
        selected = self.values[0]
        data = self.topics[selected]
        
        # Create new embed
        embed = discord.Embed(
            title=data["title"],
            description=data["description"],
            color=data["color"],
            timestamp=discord.utils.utcnow()
        )
        
        if data.get("image"):
            embed.set_image(url=data["image"])
        
        embed.set_footer(
            text=f"📚 Trading Education • Requested by {interaction.user.name}",
            icon_url=interaction.user.display_avatar.url
        )
        
        embed.set_author(
            name="Trading Academy",
            icon_url=interaction.guild.icon.url if interaction.guild and interaction.guild.icon else None
        )
        
        # Update view with new current topic
        view = ExplainView(self.topics, selected)
        await interaction.response.edit_message(embed=embed, view=view)

class AllTopicsButton(discord.ui.Button):
    """Button to show all available topics"""
    
    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label="📋 All Topics",
            emoji="📋"
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Show all available topics"""
        view = self.view
        if not isinstance(view, ExplainView):
            return
        
        topics_list = []
        for key, data in view.topics.items():
            topics_list.append(f"{data['emoji']} **{data['title']}**\n└ Use `/explain {key}`")
        
        embed = discord.Embed(
            title="📚 All Trading Topics",
            description="\n\n".join(topics_list),
            color=0x5865F2,
            timestamp=discord.utils.utcnow()
        )
        
        embed.set_footer(
            text=f"💡 Select a topic from the dropdown above • {interaction.user.name}",
            icon_url=interaction.user.display_avatar.url
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

class SayConfigView(discord.ui.View):
    """Interactive view for configuring the say command with progressive disclosure"""
    
    def __init__(self, interaction: discord.Interaction):
        super().__init__(timeout=300)
        self.interaction = interaction
        self.bot = interaction.client
        
        # Stage: method -> configure -> ready
        self.stage = "method"
        
        # configuration
        self.send_method = None         # "bot" or "webhook"
        self.target_channel = interaction.channel
        
        # content flags
        self.has_message = False
        self.has_embed = False
        self.has_attachment = False
        
        # attachments
        self.attachment = None
        self.attachment_url = None
        self.attachment_message_link = None
        self.attachment_filename = None
        
        # misc
        self.spoiler = False
        self.reply_to = None
        
        # message content
        self.message_content = None
        
        # embed content
        self.embed_title = None
        self.embed_description = None
        self.embed_color = None
        self.embed_footer = None
        self.embed_image = None
        self.embed_thumbnail = None
        self.embed_author = None
        self.embed_author_icon = None
        
        # webhook settings
        self.webhook_urls = []  # list of webhook URLs
        self.webhook_name = None
        self.webhook_avatar = None
        
        self.rebuild_ui()
    
    # UI builder
    def rebuild_ui(self):
        self.clear_items()
        if self.stage == "method":
            self._add_method_buttons()
        elif self.stage == "configure":
            self._add_config_buttons()
        elif self.stage == "ready":
            self._add_final_buttons()
    
    def _add_method_buttons(self):
        bot_btn = discord.ui.Button(
            label="Send as Bot", 
            style=discord.ButtonStyle.primary, 
            emoji="🤖",
            row=0
        )
        bot_btn.callback = self._choose_bot
        self.add_item(bot_btn)
        
        webhook_btn = discord.ui.Button(
            label="Send as Webhook", 
            style=discord.ButtonStyle.primary, 
            emoji="🔗",
            row=0
        )
        webhook_btn.callback = self._choose_webhook
        self.add_item(webhook_btn)
        
        cancel_btn = discord.ui.Button(
            label="Cancel", 
            style=discord.ButtonStyle.danger, 
            emoji="✖️",
            row=1
        )
        cancel_btn.callback = self._cancel
        self.add_item(cancel_btn)
    
    def _add_config_buttons(self):
        # Row 0: Content type buttons
        msg_btn = discord.ui.Button(
            label="Message" if not self.has_message else "✓ Message",
            style=discord.ButtonStyle.success if self.has_message else discord.ButtonStyle.secondary,
            emoji="💬",
            row=0
        )
        msg_btn.callback = self._edit_message
        self.add_item(msg_btn)
        
        embed_btn = discord.ui.Button(
            label="Embed" if not self.has_embed else "✓ Embed",
            style=discord.ButtonStyle.success if self.has_embed else discord.ButtonStyle.secondary,
            emoji="📋",
            row=0
        )
        embed_btn.callback = self._edit_embed
        self.add_item(embed_btn)
        
        attach_btn = discord.ui.Button(
            label="Attachment" if not self.has_attachment else "✓ Attachment",
            style=discord.ButtonStyle.success if self.has_attachment else discord.ButtonStyle.secondary,
            emoji="📎",
            row=0
        )
        attach_btn.callback = self._add_attachment
        self.add_item(attach_btn)
        
        # Row 1: Additional options (only show if embed exists)
        if self.has_embed:
            images_btn = discord.ui.Button(
                label="Embed Images",
                style=discord.ButtonStyle.secondary,
                emoji="🖼️",
                row=1
            )
            images_btn.callback = self._edit_images
            self.add_item(images_btn)
        
        # Row 2: Reply, Webhook, Spoiler
        if self.send_method == "bot":
            reply_btn = discord.ui.Button(
                label="Reply To" if not self.reply_to else "✓ Reply Set",
                style=discord.ButtonStyle.success if self.reply_to else discord.ButtonStyle.secondary,
                emoji="↩️",
                row=2
            )
            reply_btn.callback = self._set_reply
            self.add_item(reply_btn)
        
        if self.send_method == "webhook":
            webhook_btn = discord.ui.Button(
                label=f"Webhooks ({len(self.webhook_urls)})" if self.webhook_urls else "Webhook Config",
                style=discord.ButtonStyle.success if self.webhook_urls else discord.ButtonStyle.secondary,
                emoji="⚙️",
                row=2
            )
            webhook_btn.callback = self._config_webhook
            self.add_item(webhook_btn)
        
        spoiler_btn = discord.ui.Button(
            label=f"Spoiler: {'ON' if self.spoiler else 'OFF'}",
            style=discord.ButtonStyle.success if self.spoiler else discord.ButtonStyle.secondary,
            emoji="🤫",
            row=2
        )
        spoiler_btn.callback = self._toggle_spoiler
        self.add_item(spoiler_btn)
        
        # Row 3: Navigation
        if self._is_ready_to_send():
            preview_btn = discord.ui.Button(
                label="Preview & Send",
                style=discord.ButtonStyle.primary,
                emoji="👁️",
                row=3
            )
            preview_btn.callback = self._go_to_ready
            self.add_item(preview_btn)
        
        back_btn = discord.ui.Button(
            label="Back",
            style=discord.ButtonStyle.secondary,
            emoji="⬅️",
            row=3
        )
        back_btn.callback = self._back_to_method
        self.add_item(back_btn)
        
        cancel_btn = discord.ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.danger,
            emoji="✖️",
            row=3
        )
        cancel_btn.callback = self._cancel
        self.add_item(cancel_btn)
    
    def _add_final_buttons(self):
        send_btn = discord.ui.Button(
            label="Send Message",
            style=discord.ButtonStyle.success,
            emoji="✉️",
            row=0
        )
        send_btn.callback = self._send_message
        self.add_item(send_btn)
        
        back_btn = discord.ui.Button(
            label="Back to Edit",
            style=discord.ButtonStyle.secondary,
            emoji="⬅️",
            row=0
        )
        back_btn.callback = self._back_to_configure
        self.add_item(back_btn)
        
        cancel_btn = discord.ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.danger,
            emoji="✖️",
            row=0
        )
        cancel_btn.callback = self._cancel
        self.add_item(cancel_btn)
    
    # helpers
    def _has_embed_content(self):
        return any([
            self.embed_title, 
            self.embed_description, 
            self.embed_color, 
            self.embed_footer, 
            self.embed_image, 
            self.embed_thumbnail, 
            self.embed_author
        ])
    
    def _is_ready_to_send(self):
        return self.has_message or self.has_embed or self.has_attachment
    
    def get_config_embed(self):
        # stage-specific embed
        if self.stage == "method":
            embed = discord.Embed(
                title="📨 Say Command — Step 1/2",
                description=(
                    "Choose how to send your message:\n\n"
                    "🤖 **Bot** — Send as the bot (can reply to messages)\n"
                    "🔗 **Webhook** — Send with custom name & avatar"
                ),
                color=discord.Color.blue()
            )
            embed.set_footer(text="Select a send method to continue")
            return embed
        
        if self.stage == "configure":
            embed = discord.Embed(
                title="📨 Say Command — Step 2/2 (Configure)",
                description=f"**Send Method:** {self.send_method.upper()}\n**Target:** {self.target_channel.mention}",
                color=discord.Color.blue()
            )
            
            # Build preview
            preview_lines = []
            
            if self.has_message and self.message_content:
                content_preview = self.message_content
                if len(content_preview) > 100:
                    content_preview = content_preview[:97] + "..."
                preview_lines.append(f"💬 **Message:** {content_preview}")
            
            if self.has_embed:
                embed_preview = []
                if self.embed_title:
                    embed_preview.append(f"Title: {self.embed_title}")
                if self.embed_description:
                    desc = self.embed_description[:50] + "..." if len(self.embed_description) > 50 else self.embed_description
                    embed_preview.append(f"Description: {desc}")
                if self.embed_color:
                    embed_preview.append(f"Color: {self.embed_color}")
                if embed_preview:
                    preview_lines.append(f"📋 **Embed:** {', '.join(embed_preview)}")
            
            if self.has_attachment:
                if self.attachment:
                    preview_lines.append(f"📎 **File:** {self.attachment.filename}")
                elif self.attachment_url:
                    preview_lines.append(f"📎 **File URL:** {self.attachment_filename or 'from URL'}")
                elif self.attachment_message_link:
                    preview_lines.append(f"📎 **File:** from message")
            
            if self.reply_to:
                preview_lines.append(f"↩️ **Replying to:** Message ID {self.reply_to}")
            
            if self.spoiler:
                preview_lines.append("🤫 **Spoiler:** Enabled")
            
            if preview_lines:
                embed.add_field(
                    name="Current Configuration",
                    value="\n".join(preview_lines),
                    inline=False
                )
            else:
                embed.add_field(
                    name="Current Configuration",
                    value="*No content added yet. Click the buttons above to add content.*",
                    inline=False
                )
            
            embed.set_footer(text="Add content using the buttons above. Click 'Preview & Send' when ready.")
            return embed
        
        # ready stage
        embed = discord.Embed(
            title="📨 Say Command — Final Review",
            description=f"**Send Method:** {self.send_method.upper()}\n**Target:** {self.target_channel.mention}",
            color=discord.Color.green()
        )
        
        # Full preview
        if self.has_message and self.message_content:
            embed.add_field(
                name="💬 Message Content",
                value=self.message_content if len(self.message_content) <= 1024 else self.message_content[:1021] + "...",
                inline=False
            )
        
        if self.has_embed:
            embed_info = []
            if self.embed_title:
                embed_info.append(f"**Title:** {self.embed_title}")
            if self.embed_description:
                desc = self.embed_description[:100] + "..." if len(self.embed_description) > 100 else self.embed_description
                embed_info.append(f"**Description:** {desc}")
            if self.embed_color:
                embed_info.append(f"**Color:** {self.embed_color}")
            if self.embed_footer:
                embed_info.append(f"**Footer:** {self.embed_footer}")
            if self.embed_image:
                embed_info.append(f"**Image:** Set")
            if self.embed_thumbnail:
                embed_info.append(f"**Thumbnail:** Set")
            if self.embed_author:
                embed_info.append(f"**Author:** {self.embed_author}")
            
            embed.add_field(
                name="📋 Embed Configuration",
                value="\n".join(embed_info) if embed_info else "*Embed configured*",
                inline=False
            )
        
        if self.has_attachment:
            if self.attachment:
                embed.add_field(name="📎 Attachment", value=self.attachment.filename, inline=False)
            elif self.attachment_url:
                embed.add_field(name="📎 Attachment", value=f"URL: {self.attachment_filename or 'from URL'}", inline=False)
            elif self.attachment_message_link:
                embed.add_field(name="📎 Attachment", value="From message link", inline=False)
        
        extra_info = []
        if self.reply_to:
            extra_info.append(f"↩️ Replying to message ID: {self.reply_to}")
        if self.spoiler:
            extra_info.append("🤫 Spoiler enabled")
        if self.webhook_name:
            extra_info.append(f"🔗 Webhook name: {self.webhook_name}")
        if self.webhook_urls:
            extra_info.append(f"🔗 Webhook URLs: {len(self.webhook_urls)} configured")
        
        if extra_info:
            embed.add_field(name="Additional Settings", value="\n".join(extra_info), inline=False)
        
        embed.set_footer(text="Review your message and click 'Send Message' to send it!")
        return embed
    
    # ==================== callbacks (async handlers) ====================
    
    async def _choose_bot(self, interaction: discord.Interaction):
        self.send_method = "bot"
        self.stage = "configure"
        self.rebuild_ui()
        await interaction.response.edit_message(embed=self.get_config_embed(), view=self)
    
    async def _choose_webhook(self, interaction: discord.Interaction):
        self.send_method = "webhook"
        self.stage = "configure"
        self.rebuild_ui()
        await interaction.response.edit_message(embed=self.get_config_embed(), view=self)
    
    async def _edit_message(self, interaction: discord.Interaction):
        modal = MessageContentModal(self)
        await interaction.response.send_modal(modal)
    
    async def _edit_embed(self, interaction: discord.Interaction):
        modal = EmbedContentModal(self)
        await interaction.response.send_modal(modal)
    
    async def _edit_images(self, interaction: discord.Interaction):
        modal = EmbedImagesModal(self)
        await interaction.response.send_modal(modal)
    
    async def _add_attachment(self, interaction: discord.Interaction):
        modal = AttachmentModal(self)
        await interaction.response.send_modal(modal)
    
    async def _set_reply(self, interaction: discord.Interaction):
        modal = ReplyConfigModal(self)
        await interaction.response.send_modal(modal)
    
    async def _config_webhook(self, interaction: discord.Interaction):
        modal = WebhookConfigModal(self)
        await interaction.response.send_modal(modal)
    
    async def _toggle_spoiler(self, interaction: discord.Interaction):
        self.spoiler = not self.spoiler
        self.rebuild_ui()
        await interaction.response.edit_message(embed=self.get_config_embed(), view=self)
    
    async def _go_to_ready(self, interaction: discord.Interaction):
        self.stage = "ready"
        self.rebuild_ui()
        await interaction.response.edit_message(embed=self.get_config_embed(), view=self)
    
    async def _back_to_method(self, interaction: discord.Interaction):
        self.stage = "method"
        self.rebuild_ui()
        await interaction.response.edit_message(embed=self.get_config_embed(), view=self)
    
    async def _back_to_configure(self, interaction: discord.Interaction):
        self.stage = "configure"
        self.rebuild_ui()
        await interaction.response.edit_message(embed=self.get_config_embed(), view=self)
    
    async def _send_message(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            # find reply message if applicable
            reply_message = None
            if self.reply_to:
                reply_message, found_channel = await find_reply_message(self, interaction)
                if not reply_message:
                    return
                self.target_channel = found_channel
            
            # prepare embed
            embed_obj = None
            if self.has_embed and self._has_embed_content():
                embed_obj = create_say_embed(
                    title=self.embed_title,
                    description=self.embed_description,
                    color=self.embed_color,
                    footer=self.embed_footer,
                    thumbnail=self.embed_thumbnail,
                    image=self.embed_image,
                    author=self.embed_author,
                    author_icon=self.embed_author_icon
                )
            
            # prepare files
            files, file_error = await prepare_files(self, interaction)
            if file_error:
                await interaction.followup.send(f"❌ {file_error}", ephemeral=True)
                return
            
            content = self.message_content if self.has_message else None
            if content and self.spoiler and not files:
                content = f"||{content}||"
            
            # send via webhook(s) or bot
            sent_count = 0
            if self.send_method == "webhook":
                if self.webhook_urls:
                    # Send to multiple webhooks
                    for webhook_url in self.webhook_urls:
                        # Need to prepare files again for each webhook
                        files_copy, _ = await prepare_files(self, interaction)
                        
                        # Temporarily set single webhook_url for send function
                        original_urls = self.webhook_urls
                        self.webhook_url = webhook_url
                        
                        sent = await send_via_webhook(self, interaction, content, embed_obj, files_copy)
                        
                        # Restore webhook_urls list
                        self.webhook_urls = original_urls
                        delattr(self, 'webhook_url')
                        
                        if sent:
                            sent_count += 1
                    
                    if sent_count > 0:
                        await interaction.followup.send(
                            f"✅ Message sent successfully to {sent_count} webhook(s)!",
                            ephemeral=True
                        )
                    else:
                        await interaction.followup.send(
                            f"❌ Failed to send to any webhooks.",
                            ephemeral=True
                        )
                        return
                else:
                    # No webhook URLs, create temp webhook
                    self.webhook_url = None  # Signal to create temp
                    sent = await send_via_webhook(self, interaction, content, embed_obj, files)
                    delattr(self, 'webhook_url')
                    
                    if sent:
                        sent_count = 1
                        await interaction.followup.send(
                            f"✅ Message sent successfully in {self.target_channel.mention}!",
                            ephemeral=True
                        )
            else:
                # Bot send
                sent = await send_via_bot(self, reply_message, content, embed_obj, files)
                if sent:
                    sent_count = 1
                    await interaction.followup.send(
                        f"✅ Message sent successfully in {self.target_channel.mention}!",
                        ephemeral=True
                    )
            
            if sent_count > 0:
                # Record usage if bot has this method
                if hasattr(self.bot, 'record_command_usage'):
                    self.bot.record_command_usage("say")
                
                logger.info(
                    f"Say command used by {safe_text(interaction.user.display_name)} "
                    f"in {safe_text(interaction.guild.name)} | "
                    f"method={self.send_method} webhooks={sent_count if self.send_method == 'webhook' else 0}"
                )
                
                # Disable all buttons
                for item in self.children:
                    item.disabled = True
                
                success_embed = discord.Embed(
                    title="✅ Message Sent Successfully",
                    description=f"Your message was sent to {sent_count} destination(s)",
                    color=discord.Color.green()
                )
                await interaction.edit_original_response(embed=success_embed, view=self)
                self.stop()
        
        except Exception as e:
            logger.error(f"Send error in say command: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ An error occurred while sending: {str(e)[:200]}",
                ephemeral=True
            )
    
    async def _cancel(self, interaction: discord.Interaction):
        for item in self.children:
            item.disabled = True
        
        cancel_embed = discord.Embed(
            title="❌ Cancelled",
            description="Say command cancelled.",
            color=discord.Color.red()
        )
        await interaction.response.edit_message(embed=cancel_embed, view=self)
        self.stop()
    
    async def on_timeout(self):
        await handle_view_timeout(self)