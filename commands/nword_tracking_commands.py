# commands/nword_commands.py (update only the display text parts)
"""
N-word tracking commands with futuristic styling
"""
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, Literal
import repository.nword_tracking_repo as nword_db
from bot.error_handler import create_error_handler
from utils.logger import get_logger
from config import NWORD_TARGET_WORDS

logger = get_logger()

class NWordTrackingCommands(commands.Cog):
    """N-word tracking and statistics commands"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(
        name="nword-count",
        description=f"Check how many times a User has said the N-Word"
    )
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 10.0)
    async def nword_count(
        self, 
        interaction: discord.Interaction, 
        user: Optional[discord.Member] = None
    ):
        """Show user's count in this server"""
        target_user = user or interaction.user
        
        count = await nword_db.get_user_count(target_user.id, interaction.guild.id)
                
        embed = discord.Embed(
            title="<a:niglet:1454881159270895830> N-Word Counter",
            description=f"**{target_user.display_name}** has said the N-Word **{count:,}** times",
            color=0x00D9FF
        )
        embed.set_thumbnail(url=target_user.display_avatar.url)
        embed.set_footer(text=f"Server: {interaction.guild.name}")
        
        await interaction.response.send_message(embed=embed)
        self.bot.record_command_usage("nword-tracker")
    
    @app_commands.command(
        name="nword-leaderboard",
        description=f"List of Top 10 N-Word Users. (Can be used server wide or globally)"
    )
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 10.0)
    async def nword_leaderboard(
        self,
        interaction: discord.Interaction,
        scope: Literal["server", "global"] = "server"
    ):
        """Show top 10 leaderboard"""
        await interaction.response.defer()
        
        if scope == "server":
            rankings = await nword_db.get_guild_ranking(interaction.guild.id, 10)
            title = f"🏆 Top 10 - {interaction.guild.name}"
            color = 0xFF6B00
        else:
            rankings = await nword_db.get_global_ranking(10)
            title = "🌍 Global Top 10"
            color = 0xFFD700
        
        if not rankings:
            embed = discord.Embed(
                title=title,
                description="No data recorded yet!",
                color=color
            )
            return await interaction.followup.send(embed=embed)
        
        # Build leaderboard display
        description_lines = []
        medals = ["🥇", "🥈", "🥉"]
        
        for idx, (user_id, count) in enumerate(rankings, 1):
            # Try to get user object for display name
            try:
                if scope == "server":
                    user = interaction.guild.get_member(user_id)
                else:
                    user = self.bot.get_user(user_id)
                
                if user:
                    display_name = f"{user.display_name} (@{user.name})"
                else:
                    display_name = f"User {user_id}"
            except:
                display_name = f"User {user_id}"
            
            # Add medal for top 3
            medal = medals[idx - 1] if idx <= 3 else f"`#{idx:02d}`"
            
            # Create progress bar
            max_count = rankings[0][1]
            bar_length = int((count / max_count) * 20)
            bar = "█" * bar_length + "░" * (20 - bar_length)
            
            description_lines.append(
                f"{medal} **{display_name}**\n"
                f"└ `{bar}` **{count:,}** times"
            )
                
        embed = discord.Embed(
            title=title,
            description="\n\n".join(description_lines),
            color=color
        )
        
        await interaction.followup.send(embed=embed)
        self.bot.record_command_usage("nword-tracker")
    
    @app_commands.command(
        name="nword-rank",
        description=f"Check your rank for saying the N-Word. (Can be used server wide or globally)"
    )
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 10.0)
    async def nword_rank(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.Member] = None,
        scope: Literal["server", "global"] = "server"
    ):
        """Show user's rank"""
        await interaction.response.defer()
        
        target_user = user or interaction.user
        
        if scope == "server":
            rank, count = await nword_db.get_user_guild_rank(target_user.id, interaction.guild.id)
            scope_text = f"in {interaction.guild.name}"
            color = 0xFF6B00
        else:
            rank, count = await nword_db.get_user_global_rank(target_user.id)
            scope_text = "globally"
            color = 0xFFD700
                
        if rank == 0:
            embed = discord.Embed(
                title="<a:niglet:1454881159270895830> N-Word Rank",
                description=f"**{target_user.display_name}** hasn't said the N-Word yet {scope_text}!",
                color=0x808080
            )
        else:
            # Create rank badge
            if rank == 1:
                rank_display = "🥇 #1"
            elif rank == 2:
                rank_display = "🥈 #2"
            elif rank == 3:
                rank_display = "🥉 #3"
            else:
                rank_display = f"#{rank}"
            
            embed = discord.Embed(
                title="<a:niglet:1454881159270895830> N-Word Rank ",
                description=(
                    f"**{target_user.display_name}** is ranked **{rank_display}** {scope_text}\n\n"
                    f"**Total Count:** `{count:,}` times"
                ),
                color=color
            )
            embed.set_thumbnail(url=target_user.display_avatar.url)
        
        embed.set_footer(text=f"Scope: {scope.capitalize()}")
        
        await interaction.followup.send(embed=embed)
        self.bot.record_command_usage("nword-tracker")
    
    @app_commands.command(
        name="nword-total",
        description=f"Total count of N-word said across all users. (Can be used server wide or globally)"
    )
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 10.0)
    async def nword_total(
        self,
        interaction: discord.Interaction,
        scope: Literal["server", "global"] = "global"
    ):
        """Show total count"""
        await interaction.response.defer()
        
        if scope == "server":
            total = await nword_db.get_total_count(interaction.guild.id)
            scope_text = f"in {interaction.guild.name}"
            color = 0xFF6B00
        else:
            total = await nword_db.get_total_count()
            scope_text = "across all servers"
            color = 0xFFD700
                
        embed = discord.Embed(
            title="<a:niglet:1454881159270895830> N-Word Statistics ",
            description=(
                f"N-Word have been said\n"
                f"**{total:,}** times\n"
                f"{scope_text}"
            ),
            color=color
        )
        embed.set_footer(text=f"Scope: {scope.capitalize()}")
        
        await interaction.followup.send(embed=embed)
        self.bot.record_command_usage("nword-tracker")
    
    # Error handlers
    @nword_count.error
    async def nword_count_error(self, interaction, error):
        handler = create_error_handler("nword-count")
        await handler(self, interaction, error)
    
    @nword_leaderboard.error
    async def nword_leaderboard_error(self, interaction, error):
        handler = create_error_handler("nword-leaderboard")
        await handler(self, interaction, error)
    
    @nword_rank.error
    async def nword_rank_error(self, interaction, error):
        handler = create_error_handler("nword-rank")
        await handler(self, interaction, error)
    
    @nword_total.error
    async def nword_total_error(self, interaction, error):
        handler = create_error_handler("nword-total")
        await handler(self, interaction, error)