from decimal import Decimal
from marketplace.models import MaterialCategory

# Default fallback standard rates (₹ per ton) if category is not configured in DB
DEFAULT_STANDARD_RATES = {
    "rubber": Decimal("20000.00"),
    "textile": Decimal("15000.00"),
    "coconut": Decimal("12000.00"),
    "plastic": Decimal("25000.00"),
    "fish": Decimal("8500.00"),
}


def get_standard_rate(category_code: str) -> Decimal:
    """Retrieves standard rate per ton configured in DB, or uses fallback."""
    cat = MaterialCategory.objects.filter(code=category_code).first()
    if cat:
        return cat.standard_price_per_ton
    return DEFAULT_STANDARD_RATES.get(category_code, Decimal("18000.00"))


def calculate_recommended_rate(category_code: str, purity_percent: int, volume_tons: float) -> Decimal:
    """
    Automatic Price Recommendation Engine:
    Recommended Rate = Base Standard Rate × (Purity / 100) × Volume Adjustment Factor
    """
    base_rate = get_standard_rate(category_code)
    purity_factor = Decimal(purity_percent) / Decimal(100)

    # Volume adjustment factor:
    # Large reliable bulk volumes (> 200t) receive slight premium due to reduced freight overhead
    # Small volumes (< 50t) receive slight discount
    v = float(volume_tons)
    if v >= 200:
        vol_factor = Decimal("1.04")
    elif v >= 100:
        vol_factor = Decimal("1.00")
    elif v >= 50:
        vol_factor = Decimal("0.98")
    else:
        vol_factor = Decimal("0.95")

    recommended = base_rate * purity_factor * vol_factor
    return round(recommended, 2)
