# commands/explain_trading.py
"""
Trading Education Command - Explain complex trading concepts
"""
import discord
from discord import app_commands
from discord.ext import commands
from bot.error_handler import create_error_handler
from utils.logger import get_logger
from ui.views import ExplainView
from utils.formatters import safe_text


logger = get_logger()


class ExplainCommands(commands.Cog):
    """Educational commands for trading concepts"""
   
    def __init__(self, bot):
        self.bot = bot
        
        # Topic data with explanations and image URLs
        self.topics = {
            "propfirms": {
                "title": "🏢 Proprietary Trading Firms (Prop Firms)",
                "emoji": "🏢",
                "description": (
                    "## What is a Prop Firm?\n"
                    "A **Proprietary Trading Firm** provides traders with **capital** to trade in exchange for a share of profits.\n\n"
                    
                    "## 💰 How It Works\n"
                    "**1. Evaluation Phase** → Pass a challenge with specific profit targets and risk rules\n"
                    "**2. Funded Account** → Get access to real capital (usually $10K - $200K+)\n"
                    "**3. Profit Split** → Keep 70-90% of your profits, firm takes the rest\n\n"
                    
                    "## ✅ Benefits\n"
                    "• Trade with **large capital** without risking your own money\n"
                    "• **Low entry cost** compared to trading your own capital\n"
                    "• Learn **discipline** through strict risk management rules\n\n"
                    
                    "## ⚠️ Key Rules (Usually)\n"
                    "• **Daily Loss Limit** → Max 5% loss per day\n"
                    "• **Max Drawdown** → Total account can't drop more than 10%\n"
                    "• **Profit Target** → Hit 8-10% profit to pass evaluation\n"
                    "• **No gambling** → Must follow risk management\n\n"
                    
                    "## 🎯 Popular Firms\n"
                    "`FTMO` • `The5ers` • `MyForexFunds` • `Topstep` • `Funded Next`\n\n"
                    
                    "## ⚡ Pro Tip\n"
                    "*Treat the evaluation like real money. Prop firms look for consistent, disciplined traders, not gamblers!*"
                ),
                "color": 0x00D9FF,
                "image": "https://liquidity-provider.com/app/uploads/2024/03/prop-trading-firm-workflow-800x433.png"
            },
            
            "leverage": {
                "title": "⚡ Leverage in Trading",
                "emoji": "⚡",
                "description": (
                    "## What is Leverage?\n"
                    "Leverage lets you **control a large position** with a **small amount of capital**. "
                    "It's like a multiplier for your trades.\n\n"
                    
                    "## 🔢 The Math\n"
                    "**Without Leverage:** $100 → 10% gain = $10 profit *(10% return)*\n"
                    "**With 10x Leverage:** $100 → 10% gain = $100 profit *(100% return)*\n"
                    "**With 100x Leverage:** $100 → 10% gain = $1,000 profit *(1000% return)*\n\n"
                    
                    "## ⚠️ The Double-Edged Sword\n"
                    "Leverage **amplifies BOTH gains AND losses**:\n"
                    "• **50x Leverage** → 2% price move = 100% of your capital (*liquidation*)\n"
                    "• **100x Leverage** → 1% price move = 100% of your capital (*liquidation*)\n\n"
                    
                    "## 📊 Leverage Examples\n"
                    "**Scenario:** BTC at $50,000, you have $1,000\n\n"
                    "**10x Leverage:**\n"
                    "→ Control $10,000 worth of BTC\n"
                    "→ 5% BTC gain = $500 profit (50% return)\n"
                    "→ 5% BTC loss = $500 loss (50% loss)\n\n"
                    
                    "**100x Leverage:**\n"
                    "→ Control $100,000 worth of BTC\n"
                    "→ 1% BTC gain = $1,000 profit (100% return)\n"
                    "→ 1% BTC loss = **LIQUIDATED** (100% loss)\n\n"
                    
                    "## 🎯 Recommended Leverage\n"
                    "• **Beginners:** 1-5x leverage max\n"
                    "• **Intermediate:** 5-20x leverage\n"
                    "• **Advanced:** 20-50x leverage\n"
                    "• **Degens:** 50-125x leverage (*not recommended*)\n\n"
                    
                    "## ⚡ Pro Tip\n"
                    "*High leverage = high risk. Most successful traders use lower leverage (5-20x) with proper risk management!*"
                ),
                "color": 0xFFD700,
                "image": "https://d33vw3iu5hs0zi.cloudfront.net/media/Image4_Exness_Insights_trading_with_and_without_leverage_3x_c2b25255fa.png"
            },
            
            "funding": {
                "title": "💸 Funding Rates Explained",
                "emoji": "💸",
                "description": (
                    "## What is Funding?\n"
                    "A **periodic payment** between traders to keep perpetual futures prices anchored to spot prices.\n\n"
                    
                    "## 🔄 How It Works\n"
                    "**Positive Funding (e.g., +0.01%):**\n"
                    "→ **Longs pay shorts** every 8 hours\n"
                    "→ Means: More people are bullish (buying)\n\n"
                    
                    "**Negative Funding (e.g., -0.01%):**\n"
                    "→ **Shorts pay longs** every 8 hours\n"
                    "→ Means: More people are bearish (selling)\n\n"
                    
                    "## 💰 Real Example\n"
                    "You have a **$10,000 long position** on BTC\n"
                    "Funding rate: **+0.05%**\n\n"
                    "**Every 8 hours you pay:**\n"
                    "$10,000 × 0.05% = **$5 payment**\n"
                    "**Daily cost:** $5 × 3 = **$15/day**\n\n"
                    
                    "## 📊 What Rates Mean\n"
                    "**+0.01% to +0.05%** → Normal bullish sentiment\n"
                    "**+0.05% to +0.10%** → High demand for longs\n"
                    "**+0.10% or higher** → Overleveraged longs (*risk of squeeze*)\n\n"
                    
                    "**-0.01% to -0.05%** → Normal bearish sentiment\n"
                    "**-0.05% to -0.10%** → High demand for shorts\n"
                    "**-0.10% or lower** → Overleveraged shorts (*risk of squeeze*)\n\n"
                    
                    "## 🎯 Trading Strategy\n"
                    "• **Extremely high positive funding** → Consider shorting (long squeeze likely)\n"
                    "• **Extremely negative funding** → Consider longing (short squeeze likely)\n"
                    "• **Neutral funding** → Market is balanced\n\n"
                    
                    "## ⚡ Pro Tip\n"
                    "*Funding rates reset every 8 hours (00:00, 08:00, 16:00 UTC). Check rates before entering positions to avoid surprises!*"
                ),
                "color": 0x00FF88,
                "image": "https://fsr-develop.com/wp-content/uploads/2024/09/image-1857.png"
            },
            
            "liquidation": {
                "title": "💀 Liquidation (Getting Rekt)",
                "emoji": "💀",
                "description": (
                    "## What is Liquidation?\n"
                    "When the exchange **force-closes your position** because you don't have enough margin to keep it open.\n\n"
                    
                    "## ⚠️ How It Happens\n"
                    "**1. You open a leveraged position**\n"
                    "**2. Price moves against you**\n"
                    "**3. Your margin runs out**\n"
                    "**4. Exchange closes your position = You lose everything**\n\n"
                    
                    "## 💀 Real Example\n"
                    "**Your trade:**\n"
                    "• Balance: $1,000\n"
                    "• BTC Price: $50,000\n"
                    "• Position: LONG with 50x leverage\n"
                    "• Position Size: $50,000 worth of BTC\n\n"
                    
                    "**Liquidation Price:** ~$49,000 (2% drop)\n\n"
                    
                    "**What happens:**\n"
                    "→ BTC drops to $49,000 (-2%)\n"
                    "→ Your $1,000 is gone\n"
                    "→ Position auto-closed\n"
                    "→ **Account balance: $0** 💀\n\n"
                    
                    "## 🛡️ How to Avoid Liquidation\n"
                    "**1. Lower Leverage** → More room for price movement\n"
                    "**2. Proper Stop Loss** → Exit before liquidation\n"
                    "**3. Position Sizing** → Don't use full margin\n"
                    "**4. Add Margin** → Top up if price moves against you\n\n"
                    
                    "## 📊 Leverage vs Liquidation Distance\n"
                    "**5x leverage** → Liquidation at ~20% price move\n"
                    "**10x leverage** → Liquidation at ~10% price move\n"
                    "**25x leverage** → Liquidation at ~4% price move\n"
                    "**50x leverage** → Liquidation at ~2% price move\n"
                    "**100x leverage** → Liquidation at ~1% price move\n\n"
                    
                    "## ⚡ Pro Tip\n"
                    "*Never use 100% of your margin! Keep 30-50% as buffer. Better to survive than to get liquidated!*"
                ),
                "color": 0xFF0000,
                "image": "https://www.investopedia.com/thmb/ohQ8xHtdhpNc1SERuZg-r8rPMlM=/1500x0/filters:no_upscale():max_bytes(150000):strip_icc()/Liquidation-4193561-Final-699e67d885c243c39cac2985b16d51cb.jpg"
            },
            
            "stoploss": {
                "title": "🛑 Stop Loss - Your Best Friend",
                "emoji": "🛑",
                "description": (
                    "## What is a Stop Loss?\n"
                    "An **automatic order** that closes your position when price hits a certain level to **limit your losses**.\n\n"
                    
                    "## 🎯 Why You NEED It\n"
                    "• **Protects your capital** from total loss\n"
                    "• **Removes emotions** from trading\n"
                    "• **Prevents revenge trading**\n"
                    "• **Keeps you in the game** long-term\n\n"
                    
                    "## 📊 How to Set Stop Loss\n"
                    "**Rule of Thumb:** Risk only **1-2% of your account** per trade\n\n"
                    
                    "**Example:**\n"
                    "• Account: $10,000\n"
                    "• Risk per trade: 2% = $200\n"
                    "• Entry: BTC at $50,000\n"
                    "• Stop Loss: $49,500 (1% below entry)\n"
                    "• Leverage: 10x\n\n"
                    
                    "If stopped out → You lose $200 (2% of account)\n\n"
                    
                    "## 🔧 Types of Stop Loss\n"
                    "**Market Stop Loss** ✅\n"
                    "→ Guarantees execution\n"
                    "→ May have slippage in volatile markets\n\n"
                    
                    "**Limit Stop Loss**\n"
                    "→ Executes at exact price\n"
                    "→ May not fill if price gaps\n\n"
                    
                    "**Trailing Stop Loss** 🔥\n"
                    "→ Follows price as it moves in your favor\n"
                    "→ Locks in profits automatically\n\n"
                    
                    "## 📐 Where to Place Stop Loss\n"
                    "**Support/Resistance Levels**\n"
                    "→ Below support for longs\n"
                    "→ Above resistance for shorts\n\n"
                    
                    "**Recent Swing Points**\n"
                    "→ Below last low for longs\n"
                    "→ Above last high for shorts\n\n"
                    
                    "**ATR-Based** (Advanced)\n"
                    "→ 1.5-2x Average True Range\n"
                    "→ Adapts to volatility\n\n"
                    
                    "## ⚡ Pro Tip\n"
                    "*\"Plan your trade, trade your plan.\" Set your stop loss BEFORE entering. Never trade without one!*"
                ),
                "color": 0xFF4444,
                "image": "https://tradelocker.com/wp-content/uploads/2023/10/stop-limit-order.jpg"
            },
            
            "rr": {
                "title": "📊 Risk-Reward Ratio",
                "emoji": "📊",
                "description": (
                    "## What is Risk-Reward Ratio?\n"
                    "The relationship between **how much you risk** vs **how much you can gain** on a trade.\n\n"
                    
                    "## 🧮 The Formula\n"
                    "**Risk-Reward Ratio = Potential Profit / Potential Loss**\n\n"
                    
                    "## 💰 Real Example\n"
                    "**Trade Setup:**\n"
                    "• Entry: $50,000\n"
                    "• Stop Loss: $49,000 (risk = $1,000)\n"
                    "• Take Profit: $53,000 (profit = $3,000)\n\n"
                    
                    "**Risk-Reward:** $3,000 / $1,000 = **3:1 (or 1:3)** ✅\n\n"
                    
                    "## 📈 Why It Matters\n"
                    "**With 1:3 RR ratio:**\n"
                    "→ Win 3 trades = +$9,000\n"
                    "→ Lose 7 trades = -$7,000\n"
                    "→ **Net profit: +$2,000** (30% win rate profitable!)\n\n"
                    
                    "**With 1:1 RR ratio:**\n"
                    "→ Win 3 trades = +$3,000\n"
                    "→ Lose 7 trades = -$7,000\n"
                    "→ **Net loss: -$4,000** (need 50%+ win rate)\n\n"
                    
                    "## 🎯 Recommended Ratios\n"
                    "**Minimum:** 1:2 RR (risk $1 to make $2)\n"
                    "**Good:** 1:3 RR (risk $1 to make $3)\n"
                    "**Excellent:** 1:4+ RR (risk $1 to make $4+)\n\n"
                    
                    "## 🔥 Win Rate vs RR\n"
                    "**1:1 RR** → Need 55%+ win rate to profit\n"
                    "**1:2 RR** → Need 40%+ win rate to profit\n"
                    "**1:3 RR** → Need 30%+ win rate to profit\n"
                    "**1:5 RR** → Need 20%+ win rate to profit\n\n"
                    
                    "## ⚡ Pro Tip\n"
                    "*Never take a trade with less than 1:2 risk-reward. Better opportunities are always around the corner!*"
                ),
                "color": 0x9B59B6,
                "image": "https://s3.tradingview.com/q/qQl1tL48_big.png"
            },
            
            "margin": {
                "title": "💼 Margin Trading Explained",
                "emoji": "💼",
                "description": (
                    "## What is Margin?\n"
                    "The **collateral** you put up to open a leveraged position. It's your \"skin in the game.\"\n\n"
                    
                    "## 💰 Types of Margin\n"
                    "**Initial Margin** → Amount needed to open position\n"
                    "**Maintenance Margin** → Minimum to keep position open\n\n"
                    
                    "## 🔢 The Math\n"
                    "**Example with 10x leverage:**\n"
                    "• You want to control: $10,000 of BTC\n"
                    "• Required margin: $10,000 ÷ 10 = **$1,000**\n"
                    "• You only need $1,000 to control $10,000!\n\n"
                    
                    "## 📊 Cross vs Isolated Margin\n"
                    "**Cross Margin** 🔄\n"
                    "→ Uses **entire account balance**\n"
                    "→ One position can affect others\n"
                    "→ Lower liquidation risk\n"
                    "→ Risk: Lose entire account on one bad trade\n\n"
                    
                    "**Isolated Margin** 🎯\n"
                    "→ Uses **only assigned margin**\n"
                    "→ Positions are separate\n"
                    "→ Loss limited to position margin\n"
                    "→ Better for beginners\n\n"
                    
                    "## ⚠️ Margin Call\n"
                    "When your margin drops below maintenance level:\n"
                    "**1. Warning issued**\n"
                    "**2. Add more margin (top up)**\n"
                    "**3. Or close position**\n"
                    "**4. Or get liquidated** 💀\n\n"
                    
                    "## 🛡️ Margin Management\n"
                    "• Never use **100% of available margin**\n"
                    "• Keep **30-50% as buffer**\n"
                    "• Monitor **margin ratio** regularly\n"
                    "• Use **isolated margin** for risky trades\n\n"
                    
                    "## 📐 Available vs Used Margin\n"
                    "**Account Balance:** $10,000\n"
                    "**Used Margin:** $3,000 (positions)\n"
                    "**Available Margin:** $7,000 (can use)\n"
                    "**Margin Usage:** 30% ✅ (safe)\n\n"
                    
                    "## ⚡ Pro Tip\n"
                    "*Use isolated margin when learning. Cross margin is for advanced traders who understand the risks!*"
                ),
                "color": 0x3498DB,
                "image": "https://piggibacks.com/wp-content/uploads/elementor/thumbs/Margin-Trading-e1628076541611-pb49d8ujnh60riskfufedod8s5kt812afmdcsyo0b8.jpg"
            },
            
            "orderbook": {
                "title": "📖 Order Book Reading",
                "emoji": "📖",
                "description": (
                    "## What is an Order Book?\n"
                    "A **live list** of all buy and sell orders at different price levels. Shows market depth and liquidity.\n\n"
                    
                    "## 📊 Order Book Structure\n"
                    "```\n"
                    "SELL ORDERS (Asks) 🔴\n"
                    "50,100 | 2.5 BTC  ← Someone selling 2.5 BTC at $50,100\n"
                    "50,050 | 5.0 BTC\n"
                    "50,000 | 10.0 BTC ← Resistance\n"
                    "────────────────\n"
                    "49,950 | 12.0 BTC ← Support\n"
                    "49,900 | 4.0 BTC\n"
                    "49,850 | 3.0 BTC  ← Someone buying 3 BTC at $49,850\n"
                    "BUY ORDERS (Bids) 🟢\n"
                    "```\n\n"
                    
                    "## 🔍 Key Concepts\n"
                    "**Bid** 🟢 → Buy orders (people wanting to buy)\n"
                    "**Ask** 🔴 → Sell orders (people wanting to sell)\n"
                    "**Spread** → Difference between best bid and ask\n"
                    "**Depth** → Total volume at each price level\n\n"
                    
                    "## 🎯 What to Look For\n"
                    "**Large Walls** 🧱\n"
                    "→ Big orders that act as support/resistance\n"
                    "→ Example: 100 BTC buy order at $49,000\n\n"
                    
                    "**Spoofing** 👻\n"
                    "→ Fake walls that get pulled before execution\n"
                    "→ Used to manipulate price perception\n\n"
                    
                    "**Imbalance** ⚖️\n"
                    "→ More bids than asks = Bullish pressure\n"
                    "→ More asks than bids = Bearish pressure\n\n"
                    
                    "## 📈 Trading Strategies\n"
                    "**Buy Wall at $49,000** 🟢\n"
                    "→ Strong support\n"
                    "→ Consider buying above it\n"
                    "→ Stop loss below the wall\n\n"
                    
                    "**Sell Wall at $51,000** 🔴\n"
                    "→ Strong resistance\n"
                    "→ Consider shorting below it\n"
                    "→ Take profit before wall\n\n"
                    
                    "**Wall Removed** 🚨\n"
                    "→ Path of least resistance\n"
                    "→ Price may move quickly\n\n"
                    
                    "## ⚡ Pro Tip\n"
                    "*Don't trade based solely on order book. Combine with price action, volume, and indicators for best results!*"
                ),
                "color": 0xE67E22,
                "image": "https://d2nzipe0469gd2.cloudfront.net/uploads/34cf73fb-d93b-45db-b462-a6170c5e51b7.png"
            }
        }
   
    @app_commands.command(name="explain", description="Learn about trading concepts")
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 5)
    @app_commands.describe(topic="Choose a trading concept to learn about")
    @app_commands.choices(topic=[
        app_commands.Choice(name="🏢 Prop Firms", value="propfirms"),
        app_commands.Choice(name="⚡ Leverage", value="leverage"),
        app_commands.Choice(name="💸 Funding Rates", value="funding"),
        app_commands.Choice(name="💀 Liquidation", value="liquidation"),
        app_commands.Choice(name="🛑 Stop Loss", value="stoploss"),
        app_commands.Choice(name="📊 Risk-Reward Ratio", value="rr"),
        app_commands.Choice(name="💼 Margin Trading", value="margin"),
        app_commands.Choice(name="📖 Order Book", value="orderbook")
    ])
    async def explain(
        self, 
        interaction: discord.Interaction,
        topic: app_commands.Choice[str]
    ):
        """
        Explain trading concepts with rich embeds and visuals.
       
        Args:
            interaction: Discord interaction
            topic: Trading concept to learn about
        """
        await interaction.response.defer(ephemeral=True)
        
        try:
            topic_key = topic.value
            
            if topic_key not in self.topics:
                available = "\n".join([f"• `{key}` - {data['title']}" for key, data in self.topics.items()])
                
                embed = discord.Embed(
                    title="❓ Topic Not Found",
                    description=(
                        f"**Available Topics:**\n{available}\n\n"
                        f"*Use `/explain <topic>` to learn more!*"
                    ),
                    color=0xFF6B6B
                )
                embed.set_footer(text="💡 Tip: Topics are case-insensitive")
                
                return await interaction.followup.send(embed=embed, ephemeral=True)
            
            # Get topic data
            data = self.topics[topic_key]
            
            # Create rich embed
            embed = discord.Embed(
                title=data["title"],
                description=data["description"],
                color=data["color"],
                timestamp=discord.utils.utcnow()
            )
            
            # Add image if available
            if data.get("image"):
                embed.set_image(url=data["image"])
            
            # Add footer with branding
            embed.set_footer(
                text=f"📚 Trading Education • Requested by {interaction.user.name}",
                icon_url=interaction.user.display_avatar.url
            )
            
            # Add author section
            embed.set_author(
                name="Trading Academy",
                icon_url=interaction.guild.icon.url if interaction.guild and interaction.guild.icon else None
            )
            
            # Send with view for more topics
            view = ExplainView(self.topics, topic_key)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            
            # Record usage
            self.bot.record_command_usage("explain")
            logger.info(f"Explain command used by {safe_text(interaction.user.display_name)} ({safe_text(interaction.user.name)}) in {safe_text(interaction.guild.name)} (ID: {interaction.guild.id}) - Topic: {topic_key}")
            
        except Exception as e:
            logger.error(f"Explain command error: {str(e)}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while fetching the explanation. Please try again.",
                ephemeral=True
            )
   
    @explain.error
    async def explain_error(self, interaction, error):
        error_handler = create_error_handler("explain")
        await error_handler(self, interaction, error)