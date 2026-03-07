"""
Kalshi prediction market analysis commands
"""
import discord
import io
from discord import app_commands
from discord.ext import commands
from datetime import datetime
from bot.error_handler import create_error_handler
from utils.logger import get_logger
from utils.validators import extract_event_ticker
from utils.helper import generate_candlestick_excel, populate_excel_data
from ui.embeds import create_kalshi_market_embed
from utils.formatters import safe_text


logger = get_logger()

class KalshiCommands(commands.Cog):
    """Kalshi market analysis commands"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="kalshi-event", description="Analyze Kalshi prediction market event")
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 10)
    async def check_kalshi_event(self, interaction: discord.Interaction, event_input: str):
        """
        Analyze Kalshi event markets with price data.
        
        Args:
            interaction: Discord interaction
            event_input: Event URL or event ticker
        """
        await interaction.response.defer(thinking=True)
        
        try:
            # Extract event ticker and original URL if provided
            event_ticker = extract_event_ticker(event_input)
            original_url = event_input if "kalshi.com" in event_input.lower() else None
            
            if not event_ticker:
                return await interaction.followup.send(
                    "❌ Invalid input. Please provide a valid Kalshi event URL or event ticker.",
                    ephemeral=True
                )
            
            # Get event data with markets
            event_data = await self.bot.services.kalshi.get_event_data(event_ticker)
            
            if not event_data:
                return await interaction.followup.send(
                    f"❌ Failed to fetch event data for `{event_ticker}`. Please check the ticker and try again.",
                    ephemeral=True
                )
            
            event = event_data.get("event", {})
            markets = event.get("markets", [])
            
            if not markets:
                return await interaction.followup.send(
                    f"❌ No markets found for event `{event_ticker}`.",
                    ephemeral=True
                )
            
            # Get event details for header
            title = event.get("title", "Unknown Event")
            status = event.get("status", "unknown")
            series_ticker = event.get("series_ticker", "")
            
            # Create header message
            status_emoji = "✅ Finalized" if status == "finalized" else "🔄 Active"
            header_message = f"**[{title}]({original_url})** • {status_emoji}" if original_url else f"**{title}** • {status_emoji}"
            
            # Create embed
            embed = await create_kalshi_market_embed(
                event, 
                markets, 
                series_ticker,
                self.bot.services.kalshi.get_market_candlesticks
            )
            
            # Generate Excel file
            wb_data = generate_candlestick_excel(markets, series_ticker, None)
            if wb_data:
                wb, start_row, _ = wb_data
                excel_bytes = await populate_excel_data(
                    wb,
                    start_row,
                    markets,
                    series_ticker,
                    self.bot.services.kalshi.get_market_candlesticks
                )
                
                if excel_bytes:
                    filename = f"kalshi_{event_ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                    file = discord.File(io.BytesIO(excel_bytes), filename=filename)
                    
                    await interaction.followup.send(
                        content=header_message,
                        embed=embed,
                        file=file
                    )
                else:
                    await interaction.followup.send(
                        content=header_message,
                        embed=embed
                    )
            else:
                await interaction.followup.send(
                    content=header_message,
                    embed=embed
                )
            
            # Record metrics
            self.bot.record_command_usage("kalshi-event")
            logger.info(f"Kalshi event check called by {safe_text(interaction.user.display_name)} ({safe_text(interaction.user.name)}) in {safe_text(interaction.guild.name)} (ID: {interaction.guild.id}) for {event_ticker} - {title}")
            
        except Exception as e:
            logger.error(f"Kalshi event analysis error for {event_input}: {str(e)}", exc_info=True)
            await interaction.followup.send(
                "❌ Failed to analyze Kalshi event. The service may be experiencing issues.",
                ephemeral=True
            )
    
    @check_kalshi_event.error
    async def kalshi_error(self, interaction, error):
        error_handler = create_error_handler("kalshi-event")
        await error_handler(self, interaction, error)

async def setup(bot):
    await bot.add_cog(KalshiCommands(bot))