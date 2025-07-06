"""
Wallet finder service for finding wallets based on average market cap
"""
import asyncio
from typing import Optional, List, Dict, Any, Tuple
from utils.logger import get_logger
from utils.formatters import safe_text
from utils.helper import calculate_mc_range, get_auto_tolerance, get_buy_amount_tolerance
from ui.embeds import create_wallet_finder_embed
from ui.views import WalletFinderView

logger = get_logger()

# BitQuery query for getting all token buyers
WALLET_BUYERS_QUERY = """
query GetAllBuyers($contractAddress: String!) {
  Solana {
    DEXTradeByTokens(
      where: {
        Trade: {
          Currency: {MintAddress: {is: $contractAddress}}, 
          Side: {Type: {is: buy}}
        }, 
        Transaction: {Result: {Success: true}}
      }
      orderBy: {descendingByField: "total_buy_usd"}
    ) {
      Trade {
        Account {
          Owner
        }
      }
      total_buy_usd: sum(
        of: Trade_Side_AmountInUSD
        if: {Trade: {Side: {Type: {is: buy}}}}
      )
      total_buy_sol: sum(
        of: Trade_Side_Amount
        if: {Trade: {Side: {Type: {is: buy}}}}
      )
      total_tokens_bought: sum(
        of: Trade_Amount
        if: {Trade: {Side: {Type: {is: buy}}}}
      )
      buy_count: count(if: {Trade: {Side: {Type: {is: buy}}}})
    }
    TokenSupplyUpdates(
      where: {
        TokenSupplyUpdate: {
          Currency: {MintAddress: {is: $contractAddress}}
        }
      }
      orderBy: {descending: Block_Time}
      limit: {count: 1}
    ) {
      TokenSupplyUpdate {
        Currency {
          Symbol
          Name
          MintAddress
          Uri
        }
        PostBalance
        PreBalance
      }
    }
  }
}
"""

class WalletFinderService:
    """Service for finding wallets based on average market cap"""
    
    def __init__(self):
        pass

class WalletFinderService:
    """Service for finding wallets based on average market cap"""
    
    def __init__(self):
        pass

async def find_wallets_by_average_mc(
    bot, 
    contract_address: str, 
    target_mc: float, 
    cutoff_value: Optional[float],
    buy_amount_filter: Optional[Dict[str, Any]],
    market_cap_input: str,
    cutoff_input: Optional[str],
    buy_amount_input: Optional[str]
) -> Tuple[Optional[Any], Optional[Any]]:
    """
    Find wallets based on average market cap entry and optional buy amount
    
    Args:
        bot: Discord bot instance
        contract_address: Token contract address
        target_mc: Target market cap value
        cutoff_value: Optional cutoff value for range
        buy_amount_filter: Optional buy amount filter dict with 'amount', 'currency', 'original'
        market_cap_input: Original market cap input string
        cutoff_input: Original cutoff input string
        buy_amount_input: Original buy amount input string
        
    Returns:
        Tuple of (Discord embed or None, View or None)
    """
    try:
        # Get token data from BitQuery - [USING ORIGINAL QUERY LOGIC]
        variables = {"contractAddress": contract_address}
        data = await bot.services.bitquery.execute_query(WALLET_BUYERS_QUERY, variables)
        
        if not data or not data.get("Solana"):
            logger.error(f"No data returned from BitQuery for {safe_text(contract_address)}")
            return None, None
        
        solana_data = data["Solana"]
        buyers_data = solana_data.get("DEXTradeByTokens", [])
        supply_data = solana_data.get("TokenSupplyUpdates", [])
        
        if not buyers_data or not supply_data:
            logger.error(f"Missing buyers or supply data for {safe_text(contract_address)}")
            return None, None
        
        # Get token supply and info
        token_supply = float(supply_data[0]["TokenSupplyUpdate"]["PreBalance"])
        token_info = supply_data[0]["TokenSupplyUpdate"]["Currency"]
        
        # Calculate average market cap for each holder
        holders_with_mc = []
        
        for buyer in buyers_data:
            try:
                total_usd = float(buyer["total_buy_usd"])
                total_sol = float(buyer["total_buy_sol"])
                total_tokens = float(buyer["total_tokens_bought"])
                
                if total_tokens > 0:
                    # Calculate average entry price and market cap
                    avg_entry_price = total_usd / total_tokens
                    avg_entry_mc = avg_entry_price * token_supply
                    
                    holders_with_mc.append({
                        "wallet": buyer["Trade"]["Account"]["Owner"],
                        "avg_mc": avg_entry_mc,
                        "total_usd": total_usd,
                        "total_sol": total_sol,
                        "buy_count": int(buyer["buy_count"])
                    })
            except (ValueError, ZeroDivisionError):
                continue
        
        if not holders_with_mc:
            logger.error(f"No valid holders found for {contract_address}")
            return None, None
        
        # Filter by market cap first
        if cutoff_value is not None:
            # User provided cutoff - use exact range
            min_mc, max_mc = calculate_mc_range(target_mc, cutoff_value)
            mc_filtered_holders = [
                holder for holder in holders_with_mc
                if min_mc <= holder["avg_mc"] <= max_mc
            ]
        else:
            # No cutoff - use auto tolerance
            tolerance = get_auto_tolerance(target_mc)
            min_mc = target_mc - tolerance
            max_mc = target_mc + tolerance
            
            mc_filtered_holders = [
                holder for holder in holders_with_mc
                if min_mc <= holder["avg_mc"] <= max_mc
            ]
        
        # Filter by buy amount if provided
        if buy_amount_filter:
            buy_amount_filtered = []
            currency = buy_amount_filter["currency"]
            target_amount = buy_amount_filter["amount"]
            
            # Get tolerance for buy amount
            tolerance = get_buy_amount_tolerance(target_amount, currency)
            min_amount = max(0, target_amount - tolerance)
            max_amount = target_amount + tolerance
            
            for holder in mc_filtered_holders:
                holder_amount = holder["total_sol"] if currency == "SOL" else holder["total_usd"]
                
                # Only include if buy amount is within tolerance and not too small
                if holder_amount >= min_amount and holder_amount <= max_amount:
                    buy_amount_filtered.append(holder)
            
            matching_holders = buy_amount_filtered
        else:
            matching_holders = mc_filtered_holders
        
        if not matching_holders:
            logger.info(f"No wallets found matching criteria for {contract_address}")
            return None, None
        
        # Sort by market cap closeness first, then by buy amount closeness if filter provided
        def sort_key(holder):
            mc_diff = abs(holder["avg_mc"] - target_mc)
            
            if buy_amount_filter:
                currency = buy_amount_filter["currency"]
                target_amount = buy_amount_filter["amount"]
                holder_amount = holder["total_sol"] if currency == "SOL" else holder["total_usd"]
                amount_diff = abs(holder_amount - target_amount)
                # Normalize both differences and combine (market cap priority)
                return (mc_diff / target_mc, amount_diff / target_amount)
            else:
                return mc_diff
        
        matching_holders.sort(key=sort_key)
        
        # Create embed and view for pagination
        embed = await create_wallet_finder_embed(
            token_info,
            matching_holders[:10],  # First 10 for initial display
            target_mc,
            cutoff_value,
            buy_amount_filter,
            market_cap_input,
            cutoff_input,
            buy_amount_input,
            page=1,
            total_pages=max(1, (len(matching_holders) + 9) // 10)
        )
        
        # Create view for pagination if more than 10 results
        view = None
        if len(matching_holders) > 10:
            view = WalletFinderView(
                token_info,
                matching_holders,
                target_mc,
                cutoff_value,
                buy_amount_filter,
                market_cap_input,
                cutoff_input,
                buy_amount_input
            )
        
        return embed, view
        
    except Exception as e:
        logger.error(f"Error in wallet finder service: {e}")
        return None, None