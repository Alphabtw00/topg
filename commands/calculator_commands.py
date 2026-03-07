"""
Trading Calculator Commands - Position sizing, liquidation, funding, and risk calculations
"""
import discord
from discord import app_commands
from discord.ext import commands
from bot.error_handler import create_error_handler
from utils.logger import get_logger
from ui.embeds import (
    create_pos_calc_capital_embed,
    create_pos_calc_loss_embed,
    create_liquidation_calc_embed,
    create_funding_calc_embed
)
from utils.formatters import safe_text

logger = get_logger()


class CalculatorCommands(commands.Cog):
    """Trading calculation commands for risk management"""
   
    def __init__(self, bot):
        self.bot = bot
   
    @app_commands.command(
        name="pos-calc-capital-based",
        description="Calculate position size based on % of capital you're willing to risk"
    )
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 3)
    @app_commands.describe(
        entry="Entry price (e.g., 50000)",
        stop_loss="Stop loss price (e.g., 49000)",
        capital="Your total trading capital (e.g., 10000)",
        risk_percent="% of capital willing to risk (e.g., 2 for 2%)"
    )
    async def pos_calc_capital(
        self,
        interaction: discord.Interaction,
        entry: float,
        stop_loss: float,
        capital: float,
        risk_percent: float
    ):
        """Calculate position size based on capital percentage risk"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Validation
            if capital <= 0:
                return await interaction.followup.send(
                    "❌ Capital must be greater than 0!",
                    ephemeral=True
                )
            
            if risk_percent <= 0 or risk_percent > 100:
                return await interaction.followup.send(
                    "❌ Risk percentage must be between 0 and 100!",
                    ephemeral=True
                )
            
            if entry <= 0 or stop_loss <= 0:
                return await interaction.followup.send(
                    "❌ Entry and stop loss must be greater than 0!",
                    ephemeral=True
                )
            
            # Create embed using separated logic
            embed = create_pos_calc_capital_embed(
                entry, stop_loss, capital, risk_percent,
                interaction.user.name, interaction.user.display_avatar.url
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
            # Record usage
            self.bot.record_command_usage("pos_calc_capital")
            logger.info(f"Position calc (capital-based) used by {safe_text(interaction.user.display_name)} ({safe_text(interaction.user.name)}) in {safe_text(interaction.guild.name)} (ID: {interaction.guild.id})")
            
        except Exception as e:
            logger.error(f"Position calc capital error: {str(e)}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred during calculation. Please check your inputs and try again.",
                ephemeral=True
            )
    
    @app_commands.command(
        name="pos-calc-loss-based",
        description="Calculate position size based on max $ loss you're willing to risk"
    )
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 3)
    @app_commands.describe(
        entry="Entry price (e.g., 50000)",
        stop_loss="Stop loss price (e.g., 49000)",
        max_loss="Maximum $ you're willing to lose (e.g., 200)"
    )
    async def pos_calc_loss(
        self,
        interaction: discord.Interaction,
        entry: float,
        stop_loss: float,
        max_loss: float
    ):
        """Calculate position size based on maximum dollar loss"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Validation
            if max_loss <= 0:
                return await interaction.followup.send(
                    "❌ Max loss must be greater than 0!",
                    ephemeral=True
                )
            
            if entry <= 0 or stop_loss <= 0:
                return await interaction.followup.send(
                    "❌ Entry and stop loss must be greater than 0!",
                    ephemeral=True
                )
            
            # Create embed using separated logic
            embed = create_pos_calc_loss_embed(
                entry, stop_loss, max_loss,
                interaction.user.name, interaction.user.display_avatar.url
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
            # Record usage
            self.bot.record_command_usage("pos_calc_loss")
            logger.info(f"Position calc (loss-based) used by {safe_text(interaction.user.display_name)} ({safe_text(interaction.user.name)}) in {safe_text(interaction.guild.name)} (ID: {interaction.guild.id})")
            
        except Exception as e:
            logger.error(f"Position calc loss error: {str(e)}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred during calculation. Please check your inputs and try again.",
                ephemeral=True
            )
    
    @app_commands.command(
        name="liquidation-calc",
        description="Calculate your liquidation price and safety margin"
    )
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 3)
    @app_commands.describe(
        entry="Entry price (e.g., 50000)",
        leverage="Leverage used (e.g., 10 for 10x)",
        position_type="Long or Short position"
    )
    @app_commands.choices(position_type=[
        app_commands.Choice(name="🟢 LONG", value="long"),
        app_commands.Choice(name="🔴 SHORT", value="short")
    ])
    async def liquidation_calc(
        self,
        interaction: discord.Interaction,
        entry: float,
        leverage: float,
        position_type: app_commands.Choice[str]
    ):
        """Calculate liquidation price and risk metrics"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Validation
            if entry <= 0:
                return await interaction.followup.send(
                    "❌ Entry price must be greater than 0!",
                    ephemeral=True
                )
            
            if leverage <= 0 or leverage > 125:
                return await interaction.followup.send(
                    "❌ Leverage must be between 1 and 125!",
                    ephemeral=True
                )
            
            is_long = position_type.value == "long"
            
            # Create embed using separated logic
            embed = create_liquidation_calc_embed(
                entry, leverage, is_long,
                interaction.user.name, interaction.user.display_avatar.url
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
            # Record usage
            self.bot.record_command_usage("liquidation_calc")
            logger.info(f"Liquidation calc used by {safe_text(interaction.user.display_name)} ({safe_text(interaction.user.name)}) in {safe_text(interaction.guild.name)} (ID: {interaction.guild.id})")
            
        except Exception as e:
            logger.error(f"Liquidation calc error: {str(e)}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred during calculation. Please check your inputs and try again.",
                ephemeral=True
            )
    
    @app_commands.command(
        name="funding-calc",
        description="Calculate funding fees for holding a perpetual position"
    )
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 3)
    @app_commands.describe(
        position_size="Position size in USD (e.g., 10000)",
        funding_rate="Funding rate in % (e.g., 0.01 for 0.01%)",
        hours="Hours you plan to hold (8 hours = 1 funding period)"
    )
    async def funding_calc(
        self,
        interaction: discord.Interaction,
        position_size: float,
        funding_rate: float,
        hours: float
    ):
        """Calculate funding fees for perpetual positions"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Validation
            if position_size <= 0:
                return await interaction.followup.send(
                    "❌ Position size must be greater than 0!",
                    ephemeral=True
                )
            
            if hours <= 0:
                return await interaction.followup.send(
                    "❌ Hours must be greater than 0!",
                    ephemeral=True
                )
            
            # Create embed using separated logic
            embed = create_funding_calc_embed(
                position_size, funding_rate, hours,
                interaction.user.name, interaction.user.display_avatar.url
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
            # Record usage
            self.bot.record_command_usage("funding_calc")
            logger.info(f"Funding calc used by {safe_text(interaction.user.display_name)} ({safe_text(interaction.user.name)}) in {safe_text(interaction.guild.name)} (ID: {interaction.guild.id})")
            
        except Exception as e:
            logger.error(f"Funding calc error: {str(e)}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred during calculation. Please check your inputs and try again.",
                ephemeral=True
            )
    
    # Error handlers for all commands
    @pos_calc_capital.error
    async def pos_calc_capital_error(self, interaction, error):
        error_handler = create_error_handler("pos_calc_capital")
        await error_handler(self, interaction, error)
    
    @pos_calc_loss.error
    async def pos_calc_loss_error(self, interaction, error):
        error_handler = create_error_handler("pos_calc_loss")
        await error_handler(self, interaction, error)
    
    @liquidation_calc.error
    async def liquidation_calc_error(self, interaction, error):
        error_handler = create_error_handler("liquidation_calc")
        await error_handler(self, interaction, error)
    
    @funding_calc.error
    async def funding_calc_error(self, interaction, error):
        error_handler = create_error_handler("funding_calc")
        await error_handler(self, interaction, error)


async def setup(bot):
    """Setup function to add the cog to the bot"""
    await bot.add_cog(CalculatorCommands(bot))