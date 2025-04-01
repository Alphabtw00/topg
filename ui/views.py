"""
Discord UI components - Updated for service provider architecture
"""
import asyncio
import discord
from datetime import datetime, timedelta
from utils.logger import get_logger

logger = get_logger()

class CopyAddressView(discord.ui.View):
    """Button view for copying crypto addresses"""
    __slots__ = ("address",)
    
    def __init__(self, address: str):
        super().__init__(timeout=None)
        self.address = address

    @discord.ui.button(label="📋", style=discord.ButtonStyle.grey, custom_id="copy_address", row=0)
    async def copy_address(self, interaction: discord.Interaction, _: discord.ui.Button):
        """Button handler to copy address to clipboard"""
        await interaction.response.send_message(self.address, ephemeral=True)
        await asyncio.sleep(30)
        await interaction.delete_original_response()


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