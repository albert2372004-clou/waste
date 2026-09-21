def calculate_carbon_savings(volume_tons: float, category_code: str = 'rubber') -> dict:
    """
    Calculates estimated carbon reduction (CO₂e) achieved by diverting
    and reusing industrial byproduct streams instead of virgin feedstock.
    
    Factors (kg CO₂e avoided per ton):
    - Rubber: ~1,690 kg CO₂e / ton (1.69 t CO₂e / ton)
    - Textile: ~2,100 kg CO₂e / ton (2.10 t CO₂e / ton)
    - Coconut: ~1,450 kg CO₂e / ton (1.45 t CO₂e / ton)
    - Plastic: ~1,850 kg CO₂e / ton (1.85 t CO₂e / ton)
    - Fish: ~1,150 kg CO₂e / ton (1.15 t CO₂e / ton)
    """
    factors = {
        'rubber': 1.69,
        'textile': 2.10,
        'coconut': 1.45,
        'plastic': 1.85,
        'fish': 1.15,
    }
    factor = factors.get(category_code.lower(), 1.65)
    total_co2e_tons = round(float(volume_tons) * factor, 2)
    return {
        'co2e_tons': total_co2e_tons,
        'factor': factor,
        'label': f"{total_co2e_tons} t CO₂e Diverted",
        'disclaimer': "ESTIMATE: Based on lifecycle greenhouse gas avoidance factors."
    }
