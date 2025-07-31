# commands/bundle_checker.py
"""
Bundle distribution analysis command
"""
import discord
from discord import app_commands
from discord.ext import commands
from bot.error_handler import create_error_handler
from ui.embeds import create_bundle_embed
from utils.logger import get_logger

logger = get_logger()

class BundleCheckerCommands(commands.Cog):
    """Bundle analysis command"""
   
    def __init__(self, bot):
        self.bot = bot
   
    @app_commands.command(name="bundle-check", description="Analyze token bundle distribution (pumpfun only)")
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 5)  # 5 seconds cooldown
    async def check_bundle(self, interaction: discord.Interaction, contract_address: str):
        """
        Analyze token bundle distribution for a contract address.
       
        Args:
            interaction: Discord interaction
            contract_address: Token contract address
        """
        # Defer response to allow time for API call
        await interaction.response.defer(thinking=True)
       
        try:
            # Get bundle analysis using TrenchBot service
            bundle_data = await self.bot.services.trenchbot.get_bundle_analysis(contract_address)
            
            if not bundle_data:
                return await interaction.followup.send(
                    "❌ Failed to fetch bundle data. Please ensure that the contract address is valid and the token is a pumpfun.",
                    ephemeral=True
                )
            
            # Create embed with bundle analysis
            embed = create_bundle_embed(bundle_data, contract_address)
           
            # Send the response
            await interaction.followup.send(embed=embed)
           
            # Record command usage metrics
            self.bot.record_command_usage("bundle-check")
            logger.info(f"Bundle check called by {interaction.user} for {contract_address}")
               
        except Exception as e:
            logger.error(f"Bundle analysis error for {contract_address}: {str(e)}", exc_info=True)
            await interaction.followup.send(
                "❌ Failed to analyze bundle distribution. The service may be experiencing issues.",
                ephemeral=True
            )
   
    # Register error handler
    @check_bundle.error
    async def bundle_error(self, interaction, error):
        error_handler = create_error_handler("bundle-check")
        await error_handler(self, interaction, error)