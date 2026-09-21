from decimal import Decimal


def calculate_match_score(listing, target_category: str = None, min_purity: int = 80, target_price: float = None) -> dict:
    """
    Rule-Based Matching Engine.
    Evaluates compatibility between a buyer's target requirement and an available waste stream.
    
    Factors:
    1. Category Match: 35 points (Must match)
    2. Purity Compatibility: up to 25 points
    3. Price Competitive Score: up to 20 points
    4. Supplier Trust & Reliability Score: up to 10 points
    5. Certificate & Permit Verification: 10 points
    """
    total_score = 0

    # 1. Category Match (35 pts)
    if not target_category or listing.category.lower() == target_category.lower():
        total_score += 35
    else:
        # Mismatched category fails
        return {
            "score_percent": 0,
            "label": "0% Match",
            "eligible": False,
            "reason": "Material category mismatch"
        }

    # 2. Purity Score (up to 25 pts)
    purity = listing.purity_percent
    if purity >= min_purity:
        total_score += 25
    else:
        purity_deficit = min_purity - purity
        score_component = max(0, 25 - (purity_deficit * 2))
        total_score += score_component

    # 3. Price Competitiveness (up to 20 pts)
    if target_price and target_price > 0:
        price_ratio = float(listing.price_per_ton) / float(target_price)
        if price_ratio <= 1.0:
            total_score += 20
        elif price_ratio <= 1.2:
            total_score += 12
        else:
            total_score += 5
    else:
        total_score += 18  # default baseline

    # 4. Supplier Trust Score (up to 10 pts)
    trust = getattr(listing, 'trust_score', 80)
    total_score += int((trust / 100) * 10)

    # 5. Permit Verification (10 pts)
    if listing.permit_verified:
        total_score += 10
    else:
        total_score += 2

    final_percent = min(99, max(45, int(total_score)))
    return {
        "score_percent": final_percent,
        "label": f"{final_percent}% Match",
        "eligible": final_percent >= 70,
        "algorithm": "Rule-Based Match Score",
    }
