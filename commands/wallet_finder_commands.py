"""
Wallet finder commands for finding wallets based on average market cap
"""
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
from utils.validators import validate_solana_address
from utils.helper import parse_market_cap_value, parse_buy_amount_value
import service.wallet_finder_service as wallet_finder_service
from utils.logger import get_logger
from utils.formatters import safe_text
from bot.error_handler import create_error_handler
from utils.formatters import safe_text


logger = get_logger()

class WalletFinderCommands(commands.Cog):
    """Wallet finder commands for finding wallets by average market cap"""
    
    def __init__(self, bot):
        self.bot = bot
        
    
    @app_commands.command(
        name="wallet-finder", 
        description="Find wallets based on average market cap entry and optional buy amount filter"
    )
    @app_commands.describe(
        contract_address="Token contract address",
        market_cap="Target market cap (e.g., 50k, 2.5m, 1b)",
        cutoff="Optional cutoff range (e.g., 5k, 500k) - creates range around target MC",
        buy_amount="Optional buy amount filter (e.g., 2 sol, $150, 1.5 solana, 300 usd) - filters by buy size"
    )
    @app_commands.checks.cooldown(1, 15) #15 second cooldown
    async def wallet_finder_command(
        self,
        interaction: discord.Interaction,
        contract_address: str,
        market_cap: str,
        cutoff: Optional[str] = None,
        buy_amount: Optional[str] = None
    ):
        """Find wallets based on average market cap entry and optional buy amount"""
        await interaction.response.defer(thinking=True)
        
        try:
            # Validate contract address
            if not validate_solana_address(contract_address):
                await interaction.followup.send("❌ Invalid Solana contract address.", ephemeral=True)
                return
            
            # Parse market cap values
            try:
                target_mc = parse_market_cap_value(market_cap)
                cutoff_value = parse_market_cap_value(cutoff) if cutoff else None
                buy_amount_filter = parse_buy_amount_value(buy_amount) if buy_amount else None
            except ValueError as e:
                await interaction.followup.send(f"❌ Invalid format: {str(e)}", ephemeral=True)
                return
            
            # Process wallet finder request
            embed, view = await wallet_finder_service.find_wallets_by_average_mc(
                self.bot,
                contract_address,
                target_mc,
                cutoff_value,
                buy_amount_filter,
                market_cap,
                cutoff,
                buy_amount
            )
            
            if embed:
                if view:
                    await interaction.followup.send(embed=embed, view=view)
                else:
                    await interaction.followup.send(embed=embed)
                logger.info(f"Wallet finder executed by {safe_text(interaction.user.display_name)} ({safe_text(interaction.user.name)}) in {safe_text(interaction.guild.name)} (ID: {interaction.guild.id}) for {safe_text(contract_address)} at {safe_text(market_cap)} MC")
                # Record command usage
                self.bot.record_command_usage("wallet-finder")
            else:
                await interaction.followup.send("❌ No wallet data found or error occurred.", ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error in wallet finder command: {e}")
            await interaction.followup.send("❌ An error occurred while finding wallets.", ephemeral=True)

    @wallet_finder_command.error
    async def wallet_finder_command_error(self, interaction, error):
        """Handle errors in wallet finder command"""
        error_handler = create_error_handler("wallet_finder_commands")
        await error_handler(self, interaction, error)