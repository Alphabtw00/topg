import discord
import asyncio

# Your bot token
TOKEN = "MTM0MDcyMjE4NjEwMDQwODM0MA.GKXdNa.XYdQw16EP-u5Pew2sP9IpQDaTKRIBR-HJBZXww"

async def check_who_added_bot():
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)
    
    @client.event
    async def on_ready():
        print(f'Logged in as {client.user}')
        print(f'Checking {len(client.guilds)} servers...\n')
        
        for guild in client.guilds:
            print(f"Server: {guild.name} (ID: {guild.id})")
            
            try:
                # Check audit logs for bot additions
                found = False
                async for entry in guild.audit_logs(action=discord.AuditLogAction.bot_add, limit=20):
                    if entry.target.id == client.user.id:
                        user = entry.user
                        print(f"  Added by: {user.name} (Display: {user.display_name}) | ID: {user.id}")
                        print(f"  Date: {entry.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                        found = True
                        break
                
                if not found:
                    print("  Added by: Unknown (not found in audit logs)")
                    
            except discord.Forbidden:
                print("  Added by: Unknown (no audit log permissions)")
            except Exception as e:
                print(f"  Error: {e}")
            
            print("-" * 50)
        
        await client.close()
    
    await client.start(TOKEN)

# Run the script
if __name__ == "__main__":
    asyncio.run(check_who_added_bot())