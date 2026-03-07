"""
Analysis utilities
"""
from utils.logger import get_logger
from typing import Dict, Any


logger = get_logger()



# def calculate_ath_marketcap(ath_price: float, current_price: float, current_fdv: float):
#     """
#     Calculate ATH market cap based on ATH price and current FDV
    
#     Args:
#         ath_price: All-time high price
#         current_price: Current price
#         current_fdv: Current fully diluted valuation
        
#     Returns:
#         float or None: Calculated ATH market cap or None if input data is invalid
#     """
#     if not all([ath_price, current_price, current_fdv]):
#         return None
    
#     try:
#         fdv_price_ratio = current_fdv / current_price
#         return ath_price * fdv_price_ratio
#     except (ZeroDivisionError, TypeError, ValueError):
#         return None
    

def calculate_ath_marketcap(ath_price: float, current_price: float, current_fdv: float):
    """
    Calculate ATH market cap based on ATH price and current FDV
   
    Args:
        ath_price: All-time high price
        current_price: Current price
        current_fdv: Current fully diluted valuation
   
    Returns:
        float or None: Calculated ATH market cap or None if input data is invalid
    """
    if not all([ath_price, current_price, current_fdv]):
        logger.debug("[calc_ath_mcap] one or more inputs are falsy, returning None")
        return None
   
    try:
        if 0 < ath_price < 1e-6:
            ath_price *= 1e3

        # Calculate token supply
        supply = current_fdv / float(current_price)
        mcap = float(ath_price) * supply
        return mcap
        
    except (ZeroDivisionError, TypeError, ValueError) as e:
        logger.error(f"[calc_ath_mcap] error in calculation: {e}")
        return None
    
def calculate_trust_score(code_review: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate trust score based on code review with improved balancing.
    
    Args:
        code_review: Code review data
        
    Returns:
        Dictionary with trust score and details
    """
    # Count issues
    red_flags = code_review.get("redFlags", [])
    larp_indicators = code_review.get("larpIndicators", [])
    
    # Classify red flags by severity
    severe_flags = []
    moderate_flags = []
    minor_flags = []
    
    severe_keywords = ["vulnerability", "security", "exploit", "critical", "breach", "unsafe"]
    moderate_keywords = ["warning", "concern", "issue", "problem", "limitation"]
    
    for flag in red_flags:
        flag_lower = flag.lower()
        if any(keyword in flag_lower for keyword in severe_keywords):
            severe_flags.append(flag)
        elif any(keyword in flag_lower for keyword in moderate_keywords):
            moderate_flags.append(flag)
        else:
            minor_flags.append(flag)
    
    # Check for misrepresentation concerns
    misrepresentation_count = sum(
        1 for check in code_review.get("misrepresentationChecks", [])
        if any(term in check.lower() for term in ["suspicious", "concern", "issue", "problem"])
    )
    
    # AI-specific factors
    ai_analysis = code_review.get("aiAnalysis", {})
    
    misleading_level = ai_analysis.get("misleadingLevel", "None")
    ai_misleading_penalty = {
        "None": 0,
        "Low": 7,
        "Medium": 15,
        "High": 25
    }.get(misleading_level, 0)
    
    ai_concerns_penalty = min(15, len(ai_analysis.get("concerns", [])) * 5)
    
    # Start with base trust score
    trust_score = 100
    
    # Apply penalties for issues with reduced severity
    penalties = {
        "severe_flags": len(severe_flags) * 15,  # -15 points per severe flag
        "moderate_flags": len(moderate_flags) * 10,  # -10 points per moderate flag
        "minor_flags": len(minor_flags) * 5,    # -5 points per minor flag
        "larp_indicators": min(30, len(larp_indicators) * 7),  # -7 points per LARP indicator, max 30
        "misrepresentation": min(30, misrepresentation_count * 15),  # -15 points per misrepresentation, max 30
        "ai_misleading": ai_misleading_penalty,
        "ai_concerns": ai_concerns_penalty
    }
    
    # Add positive factors
    positive_factors = {}
    
    # Look for positive indicators in repo review
    if ai_analysis.get("implementationQuality") in ["Good", "Excellent"]:
        positive_factors["good_ai_implementation"] = 10
    
    # Check investment ranking
    investment = code_review.get("investmentRanking", {})
    if investment.get("rating") in ["High", "Strong Buy", "Buy"]:
        confidence = investment.get("confidence", 0)
        # Only boost if confidence is high
        if confidence >= 70:
            positive_factors["positive_investment"] = 15
    
    # Apply all penalties
    for penalty_name, penalty_value in penalties.items():
        trust_score -= penalty_value
    
    # Apply positive factors
    for factor_name, factor_value in positive_factors.items():
        trust_score += factor_value
    
    # Cap the total penalty - ensure even repos with issues don't go below 30
    trust_score = max(15, trust_score)
    
    # Ensure range 0-100
    trust_score = min(100, trust_score)
    
    return {
        "score": trust_score,
        "penalties": penalties,
        "positive_factors": positive_factors,
        "red_flags_count": len(red_flags),
        "severe_flags_count": len(severe_flags),
        "moderate_flags_count": len(moderate_flags),
        "minor_flags_count": len(minor_flags),
        "larp_indicators_count": len(larp_indicators),
        "misleading_level": misleading_level
    }

def calculate_final_legitimacy_score(technical_score: int, trust_score: int, repo_info: Dict = None) -> int:
    """
    Calculate final legitimacy score with adaptive weighting.
    
    Args:
        technical_score: Technical score (0-100)
        trust_score: Trust score (0-100)
        repo_info: Repository information (optional)
        
    Returns:
        Final legitimacy score (0-100)
    """
    # Default weights
    tech_weight = 0.6
    trust_weight = 0.4
    
    # Adjust weights based on technical score
    if technical_score >= 85:
        # For excellent technical repos, reduce trust impact
        tech_weight = 0.7
        trust_weight = 0.3
    elif technical_score <= 50:
        # For poor technical repos, increase trust impact
        tech_weight = 0.5
        trust_weight = 0.5
    
    # Additional adjustment for ML/AI projects
    if repo_info and repo_info.get("description"):
        description = repo_info.get("description", "").lower()
        if any(term in description for term in ["ml", "ai", "machine learning", "artificial intelligence", "neural", "model"]):
            # Further reduce trust impact for ML/AI projects which often have inherent limitations
            tech_weight += 0.05
            trust_weight -= 0.05
    
    return round((technical_score * tech_weight) + (trust_score * trust_weight))

def calculate_verdict(scores: Dict[str, Any], trust_result: Dict[str, Any], 
                    code_review: Dict[str, Any], repo_info: Dict = None) -> Dict[str, Any]:
    """
    Calculate verdict with transparent weighting of factors and popularity recognition.
    
    Args:
        scores: Technical scores data
        trust_result: Trust calculation result
        code_review: Code review data
        repo_info: Repository information (optional)
        
    Returns:
        Verdict information
    """
    # Get core scores
    technical_score = scores.get("technicalScore", 0)
    trust_score = trust_result.get("score", 0)
    
    # Get additional metrics that influence the verdict
    ranking = code_review.get("investmentRanking", {})
    rating = ranking.get("rating", "Unknown")
    confidence = ranking.get("confidence", 0)
    
    # First, convert investment rating to a numeric value
    rating_value = {
        "Strong Buy": 95,
        "Buy": 85,
        "High": 85, 
        "Medium-High": 75,
        "Medium": 70,
        "Hold": 65, 
        "Low": 50,
        "Sell": 50,
        "Strong Sell": 40
    }.get(rating, 60)  # Default is positive
    
    # Apply confidence adjustment to rating value
    # Low confidence reduces the impact of the rating
    adjusted_rating = rating_value * (confidence / 100) if confidence > 0 else rating_value * 0.5
    
    # Calculate popularity boost for starred repos
    popularity_boost = 0
    if repo_info:
        stars = repo_info.get("stargazers_count", 0)
        if stars > 5000:
            popularity_boost = 10
        elif stars > 1000:
            popularity_boost = 7
        elif stars > 500:
            popularity_boost = 5
        elif stars > 100:
            popularity_boost = 3
    
    # Clear weighting of factors for transparency
    weights = {
        "technical": 0.5,    # Technical quality is most important
        "trust": 0.3,        # Trust factors matter but less than technical merit
        "rating": 0.2        # Investment rating has some influence
    }
    
    # Calculate composite score with adjustments
    base_boost = 5  # Base positive boost
    
    # Higher boost for highly technical projects
    if technical_score >= 85:
        base_boost += 2
    
    composite_score = (
        (technical_score * weights["technical"]) + 
        (trust_score * weights["trust"]) + 
        (adjusted_rating * weights["rating"]) +
        base_boost +
        popularity_boost
    )
    
    # Ensure score is within bounds
    composite_score = max(0, min(100, composite_score))
    
    # Adjust threshold for excellent technical implementations
    recommend_threshold = 80  # Default threshold
    if technical_score >= 85:
        recommend_threshold = 75  # Lower threshold for excellent projects
    
    # Determine verdict based on composite score with adjusted thresholds
    if composite_score >= recommend_threshold:
        return {
            "color": 0x00FF00,  # Green
            "verdict": "INVESTMENT RECOMMENDED",
            "emoji": "✅",
            "investment_advice": "Appears to be a solid project with good technical foundation. 📝 NFA-DYOR",
            "score": composite_score,
            "factors": {
                "technical_score": technical_score,
                "trust_score": trust_score,
                "rating_value": rating_value,
                "adjusted_rating": adjusted_rating,
                "popularity_boost": popularity_boost,
                "weights": weights
            }
        }
    elif composite_score >= 55:
        return {
            "color": 0xFFD700,  # Gold
            "verdict": "POTENTIALLY VIABLE",
            "emoji": "⚠️",
            "investment_advice": "Shows promise but exercise caution and conduct additional research. 📝 NFA-DYOR",
            "score": composite_score,
            "factors": {
                "technical_score": technical_score,
                "trust_score": trust_score,
                "rating_value": rating_value,
                "adjusted_rating": adjusted_rating,
                "popularity_boost": popularity_boost,
                "weights": weights
            }
        }
    elif composite_score >= 40:
        return {
            "color": 0xFF8C00,  # Dark Orange
            "verdict": "HIGH RISK INVESTMENT",
            "emoji": "⚠️",
            "investment_advice": "Significant concerns detected - thorough investigation recommended. 📝 NFA-DYOR",
            "score": composite_score,
            "factors": {
                "technical_score": technical_score,
                "trust_score": trust_score,
                "rating_value": rating_value,
                "adjusted_rating": adjusted_rating,
                "popularity_boost": popularity_boost,
                "weights": weights
            }
        }
    else:
        return {
            "color": 0xFF0000,  # Red
            "verdict": "NOT RECOMMENDED",
            "emoji": "🚨",
            "investment_advice": "Multiple critical issues found - investment not advised. 📝 NFA-DYOR",
            "score": composite_score,
            "factors": {
                "technical_score": technical_score,
                "trust_score": trust_score,
                "rating_value": rating_value,
                "adjusted_rating": adjusted_rating,
                "popularity_boost": popularity_boost,
                "weights": weights
            }
        }