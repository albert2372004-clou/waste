"""
Kerala Industrial Corridor Logistics & Transportation Engine.
Manages district-to-district distance matrix, toll surcharges,
and live tracking waypoint telemetry along NH 544 & NH 66 corridors.
"""
from decimal import Decimal


KERALA_DISTRICT_DISTANCES = {
    ("kochi", "palakkad"): 142,
    ("kottayam", "palakkad"): 198,
    ("alappuzha", "palakkad"): 192,
    ("kannur", "kochi"): 265,
    ("kannur", "palakkad"): 185,
    ("kozhikode", "kochi"): 180,
    ("kozhikode", "palakkad"): 125,
    ("kochi", "thiruvananthapuram"): 205,
    ("kottayam", "thiruvananthapuram"): 150,
    ("alappuzha", "kochi"): 55,
    ("kottayam", "kochi"): 65,
}

KERALA_HIGHWAY_WAYPOINTS = [
    {"checkpoint": "Factory Gate Dispatch & Electronic Weighment", "km": 0, "status": "completed"},
    {"checkpoint": "KSPCB Transit Manifest QR Scanned", "km": 15, "status": "completed"},
    {"checkpoint": "NH 544 Aluva Interchange Checkpoint", "km": 42, "status": "completed"},
    {"checkpoint": "Paliakkara Highway Corridor Toll Plaza", "km": 88, "status": "active"},
    {"checkpoint": "Kuthiran Tunnel / Vadakkencherry Bypass", "km": 115, "status": "pending"},
    {"checkpoint": "Kanjikode Industrial Growth Centre (Destination Gate)", "km": 142, "status": "pending"},
]


def extract_district(location_str: str) -> str:
    """Normalize district name from location address string."""
    loc = (location_str or "").lower()
    for d in ["kochi", "cochin", "kottayam", "alappuzha", "palakkad", "kozhikode", "kannur", "thiruvananthapuram"]:
        if d in loc:
            if d == "cochin":
                return "kochi"
            return d
    return "kochi"


def calculate_corridor_distance(origin: str, destination: str) -> int:
    """Calculate distance in kilometers between two Kerala industrial points."""
    orig_d = extract_district(origin)
    dest_d = extract_district(destination)

    if orig_d == dest_d:
        return 35  # intra-district industrial transit

    pair = (orig_d, dest_d)
    reverse_pair = (dest_d, orig_d)

    if pair in KERALA_DISTRICT_DISTANCES:
        return KERALA_DISTRICT_DISTANCES[pair]
    elif reverse_pair in KERALA_DISTRICT_DISTANCES:
        return KERALA_DISTRICT_DISTANCES[reverse_pair]
    
    return 142  # default Kochi-Palakkad corridor standard


def calculate_transportation_breakdown(origin: str, destination: str, volume_tons: float):
    """
    Computes transparent multi-component freight quote:
    1. Base Dispatch & Factory Weighbridge Loading: ₹1,500
    2. Paliakkara / Walayar Corridor Toll & Checkpoint Clearance: ₹450
    3. Freight = Volume * Distance * ₹3.20/ton-km
    """
    distance_km = calculate_corridor_distance(origin, destination)
    base_dispatch = 1500.00
    toll_checkpoint = 450.00
    ton_km_rate = 3.20
    distance_freight = round(float(volume_tons) * distance_km * ton_km_rate, 2)
    total_freight = round(base_dispatch + toll_checkpoint + distance_freight, 2)

    return {
        "distance_km": distance_km,
        "base_dispatch": base_dispatch,
        "toll_checkpoint": toll_checkpoint,
        "ton_km_rate": ton_km_rate,
        "distance_freight": distance_freight,
        "total_freight": total_freight,
    }
