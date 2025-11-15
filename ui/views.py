"""
Discord UI components - Updated for service provider architecture
"""
import asyncio
import discord
from datetime import datetime, timedelta
from urllib.parse import urlparse
from utils.logger import get_logger
from ui.embeds import create_wallet_finder_embed
from typing import List, Dict, Any, Optional


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
  