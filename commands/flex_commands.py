# commands/pnl_flex.py
"""
PnL Flex command - Generate trading PnL cards
"""
import discord
from discord import app_commands
from discord.ext import commands
from bot.error_handler import create_error_handler
from service.flex_service import generate_pnl_card, calculate_pnl
from utils.logger import get_logger
from utils.formatters import safe_text


logger = get_logger()


class FlexCommands(commands.Cog):
    """PnL Flex card generator command"""
   
    def __init__(self, bot):
        self.bot = bot
   
    @app_commands.command(name="flex", description="Generate a PnL flex card")
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 10)
    @app_commands.describe(
        side="Trade side (BUY or SELL)",
        symbol="Trading pair symbol (e.g., BTCUSDT)",
        entry_price="Entry price",
        mark_price="Current/exit price",
        leverage="Leverage used (e.g., 120)"
    )
    async def flex(
        self, 
        interaction: discord.Interaction, 
        side: str,
        symbol: str,
        entry_price: float,
        mark_price: float,
        leverage: int
    ):
        """
        Generate a PnL flex card with trading details.
       
        Args:
            interaction: Discord interaction
            side: Trade side (BUY/SELL)
            symbol: Trading pair
            entry_price: Entry price
            mark_price: Mark/exit price
            leverage: Leverage multiplier
        """
        await interaction.response.defer()
       
        try:
            # Validate side
            side = side.upper()
            if side not in ["BUY", "SELL"]:
                return await interaction.followup.send(
                    "❌ Invalid side. Please use 'BUY' or 'SELL'.",
                    ephemeral=True
                )
            
            # Validate prices
            if entry_price <= 0 or mark_price <= 0:
                return await interaction.followup.send(
                    "❌ Prices must be positive numbers.",
                    ephemeral=True
                )
            
            # Validate leverage
            if leverage <= 0:
                return await interaction.followup.send(
                    "❌ Leverage must be a positive number.",
                    ephemeral=True
                )
            
            # Generate the PnL card using service function
            image_buffer = await generate_pnl_card(
                side=side,
                symbol=symbol.upper(),
                entry_price=entry_price,
                mark_price=mark_price,
                leverage=leverage,
                username=interaction.user.name
            )
            
            if not image_buffer:
                return await interaction.followup.send(
                    "❌ Failed to generate PnL card. Please try again.",
                    ephemeral=True
                )
            
            # Create Discord file from buffer
            file = discord.File(fp=image_buffer, filename=f"pnl_flex_{side.lower()}.png")
            
            # Calculate PnL for display
            pnl_percentage = calculate_pnl(entry_price, mark_price, leverage, side)
            
            # Send the image
            await interaction.followup.send(file=file)
           
            # Record command usage metrics
            self.bot.record_command_usage("flex")
            logger.info(f"Flex command used by {safe_text(interaction.user.display_name)} ({safe_text(interaction.user.name)}) in {safe_text(interaction.guild.name)} (ID: {interaction.guild.id}) - {side} {symbol} {leverage}X | PnL: {pnl_percentage:.2f}%")

               
        except ValueError as e:
            logger.warning(f"Invalid input for flex command: {str(e)}")
            await interaction.followup.send(
                f"❌ Invalid input: {str(e)}",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"PnL flex error: {str(e)}", exc_info=True)
            await interaction.followup.send(
                "❌ Failed to generate PnL card. Please try again later.",
                ephemeral=True
            )
   
    @flex.error
    async def flex_error(self, interaction, error):
        error_handler = create_error_handler("flex")
        await error_handler(self, interaction, error)
