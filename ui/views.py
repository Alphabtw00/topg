"""
Discord UI components
"""
import asyncio
import discord
from api.github_analyzer import clear_repo_from_cache
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
    __slots__ = ("repo_url",)
    
    def __init__(self, repo_url: str):
        super().__init__(timeout=None)
        self.repo_url = repo_url
        
        # Add buttons
        self.add_item(discord.ui.Button(
            label="View Repository", 
            url=repo_url
        ))
        
        self.add_item(discord.ui.Button(
            label="Reanalyze", 
            style=discord.ButtonStyle.gray, 
            custom_id="reanalyze_repo"
        ))
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Handle button interactions"""
        if interaction.data.get("custom_id") == "reanalyze_repo":
            # Clear this repo from cache to force reanalysis
            clear_repo_from_cache(self.repo_url)
            await interaction.response.send_message(
                "Repository will be reanalyzed on next check.", 
                ephemeral=True
            )
        return True