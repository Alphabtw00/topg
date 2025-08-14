import discord
import asyncio

# Bot token and server ID
DISCORD_TOKEN = "MTM0MDcyMjE4NjEwMDQwODM0MA.GKXdNa.XYdQw16EP-u5Pew2sP9IpQDaTKRIBR-HJBZXww"
SERVER_ID = 1374780009608253541

# Create bot instance with necessary intents
intents = discord.Intents.default()
intents.guilds = True
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f'Bot connected as {client.user}')
    
    # Get the guild (server) by ID
    guild = client.get_guild(SERVER_ID)
    
    if guild is None:
        print(f"Could not find server with ID {SERVER_ID} or bot is not in that server")
        await client.close()
        return
    
    print(f"\n=== ROLES IN '{guild.name}' ===")
    print(f"Total roles: {len(guild.roles)}\n")
    
    # Sort roles by position (highest first)
    sorted_roles = sorted(guild.roles, key=lambda r: r.position, reverse=True)
    
    for role in sorted_roles:
        # Get additional info about the role
        member_count = len(role.members)
        color_hex = str(role.color) if role.color != discord.Color.default() else "No color"
        
        print(f"📋 Role: {role.name}")
        print(f"   ID: {role.id}")
        print(f"   Position: {role.position}")
        print(f"   Members: {member_count}")
        print(f"   Color: {color_hex}")
        print(f"   Mentionable: {role.mentionable}")
        print(f"   Managed: {role.managed}")
        print("-" * 50)
    
    # Close the bot after printing
    await client.close()

# Run the bot
async def main():
    try:
        await client.start(DISCORD_TOKEN)
    except discord.LoginFailure:
        print("Invalid token provided")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(main())