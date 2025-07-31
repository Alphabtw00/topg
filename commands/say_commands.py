"""
Admin say command - Admins can send messages through the bot with reply and image support
"""
import discord
from discord import app_commands
from discord.ext import commands
import io
from bot.error_handler import create_error_handler
from utils.logger import get_logger

logger = get_logger()

class SayCommands(commands.Cog):
    """Admin command to send messages through the bot"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="say", description="Send a message through the bot")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.cooldown(1, 3)
    @app_commands.describe(
        message="The message to send (optional)",
        channel="Channel to send the message in (optional, defaults to current channel)",
        image="Image attachment to include (optional)",
        spoiler="Send as spoiler (optional, default: False)",
        reply_to="Message ID to reply to"
    )
    async def say_slash(
        self, 
        interaction: discord.Interaction, 
        message: str = None,
        channel: discord.TextChannel = None,
        image: discord.Attachment = None,
        spoiler: bool = False,
        reply_to: str = None
    ):
        """Send a message through the bot - Admin only"""
        
        # Check if at least one of message or image is provided
        if not message and not image:
            await interaction.response.send_message(
                "❌ You must provide either a message or an image.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            target_channel = None
            reply_message = None
            
            # Handle reply_to parameter (takes precedence)
            if reply_to:
                try:
                    # Try to convert to int
                    message_id = int(reply_to)
                    
                    # First try to find the message in the current channel
                    try:
                        reply_message = await interaction.channel.fetch_message(message_id)
                        target_channel = interaction.channel
                    except discord.NotFound:
                        # If not found in current channel, try the specified channel
                        if channel:
                            try:
                                reply_message = await channel.fetch_message(message_id)
                                target_channel = channel
                            except discord.NotFound:
                                pass
                        
                        # If still not found, search through all text channels in the guild
                        if not reply_message:
                            for guild_channel in interaction.guild.text_channels:
                                try:
                                    reply_message = await guild_channel.fetch_message(message_id)
                                    target_channel = guild_channel
                                    break
                                except (discord.NotFound, discord.Forbidden):
                                    continue
                    
                    if not reply_message:
                        await interaction.followup.send(
                            f"❌ Could not find message with ID `{reply_to}` in any accessible channel.",
                            ephemeral=True
                        )
                        return
                        
                except ValueError:
                    await interaction.followup.send(
                        "❌ Invalid message ID. Please provide a valid numeric message ID.",
                        ephemeral=True
                    )
                    return
            else:
                # Use specified channel or current channel if no reply
                target_channel = channel or interaction.channel
            
            # Check permissions
            if not target_channel.permissions_for(interaction.guild.me).send_messages:
                await interaction.followup.send(
                    f"❌ I don't have permission to send messages in {target_channel.mention}.",
                    ephemeral=True
                )
                return
            
            # Prepare message content and files
            message_content = ""
            files = []
            
            # Handle message content
            if message:
                message_content = message
                # Apply spoiler to text if requested and no image
                if spoiler and not image:
                    message_content = f"||{message_content}||"
            
            # Handle image attachment if provided
            if image:
                try:
                    # Read the attachment data
                    file_data = await image.read()
                    
                    # Create Discord file object with spoiler if requested
                    discord_file = discord.File(
                        io.BytesIO(file_data), 
                        filename=image.filename, 
                        spoiler=spoiler
                    )
                    files.append(discord_file)
                    
                except Exception as e:
                    logger.error(f"Error processing image attachment: {e}")
                    await interaction.followup.send(
                        "❌ Failed to process the image attachment.",
                        ephemeral=True
                    )
                    return
            
            # Send the message
            if reply_message:
                sent_message = await reply_message.reply(
                    content=message_content if message_content else None,
                    files=files if files else None
                )
                action_description = f"Reply sent to message in {target_channel.mention}"
            else:
                sent_message = await target_channel.send(
                    content=message_content if message_content else None,
                    files=files if files else None
                )
                action_description = f"Message sent in {target_channel.mention}"
            
            # Send ephemeral confirmation
            await interaction.followup.send(
                f"✅ {action_description}",
                ephemeral=True
            )
            
            # Log the command usage
            self.bot.record_command_usage("say")
            reply_info = f" | Reply to: {reply_message.id}" if reply_message else ""
            image_info = f" | Image: {image.filename}" if image else ""
            logger.info(f"Say command used by {interaction.user} | Channel: {target_channel.id} | Message ID: {sent_message.id}{reply_info}{image_info}")
            
        except discord.Forbidden:
            await interaction.followup.send(
                f"❌ I don't have permission to send messages in {target_channel.mention}.",
                ephemeral=True
            )
        except discord.HTTPException as e:
            logger.error(f"HTTP error sending message: {e}")
            await interaction.followup.send(
                "❌ Failed to send message. The message might be too long or contain invalid content.",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Say command error: {e}")
            await interaction.followup.send(
                "❌ An error occurred while sending the message. Please check the logs.",
                ephemeral=True
            )
    
    # Register error handler
    @say_slash.error
    async def say_error(self, interaction, error):
        await create_error_handler("say")(self, interaction, error)