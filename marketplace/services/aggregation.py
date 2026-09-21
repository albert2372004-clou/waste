from decimal import Decimal


class BatchCartService:
    """
    Manages session-based multi-supplier material pooling and quantity aggregation.
    Allows buyers to combine surplus batches from multiple factories to fulfill large orders.
    """
    SESSION_KEY = "waste_batch_cart"

    def __init__(self, session):
        self.session = session
        cart = self.session.get(self.SESSION_KEY)
        if not cart:
            cart = self.session[self.SESSION_KEY] = {
                "target_volume_tons": 500.0,
                "target_material": "Scrap Rubber",
                "items": {}  # listing_id -> {listing_id, title, supplier, volume_tons, price, subtotal}
            }
        self.cart = cart

    def set_target(self, target_volume: float, target_material: str = "Scrap Rubber"):
        self.cart["target_volume_tons"] = max(1.0, float(target_volume))
        if target_material:
            self.cart["target_material"] = target_material
        self.save()

    def add_listing(self, listing, volume_tons: float):
        v = float(volume_tons)
        lid = str(listing.id)
        price = float(listing.price_per_ton)
        subtotal = round(v * price, 2)
        
        self.cart["items"][lid] = {
            "listing_id": listing.id,
            "material_name": listing.material_name,
            "category": listing.category,
            "batch_id": listing.batch_id,
            "supplier_name": listing.supplier.company_name,
            "volume_tons": v,
            "price_per_ton": price,
            "subtotal": subtotal,
            "trust_score": listing.trust_score,
            "location": listing.location,
        }
        self.save()

    def remove_listing(self, listing_id):
        lid = str(listing_id)
        if lid in self.cart["items"]:
            del self.cart["items"][lid]
            self.save()

    def clear(self):
        self.cart["items"] = {}
        self.save()

    def get_summary(self):
        items = list(self.cart["items"].values())
        collected_tons = sum(item["volume_tons"] for item in items)
        target_tons = float(self.cart.get("target_volume_tons", 500.0))
        target_material = self.cart.get("target_material", "Scrap Rubber")
        
        material_cost = sum(item["subtotal"] for item in items)
        # Average freight placeholder: 165 km * ₹3.10 / ton
        freight_cost = round(collected_tons * 165 * 3.10, 2)
        platform_fee = round(material_cost * 0.015, 2) if material_cost > 0 else 0.0
        total_procurement_cost = round(material_cost + freight_cost + platform_fee, 2)

        progress_pct = min(100, int((collected_tons / target_tons) * 100)) if target_tons > 0 else 0
        remaining_tons = max(0.0, target_tons - collected_tons)

        return {
            "items": items,
            "items_count": len(items),
            "target_tons": target_tons,
            "target_material": target_material,
            "collected_tons": round(collected_tons, 2),
            "remaining_tons": round(remaining_tons, 2),
            "progress_pct": progress_pct,
            "is_fully_filled": collected_tons >= target_tons,
            "material_cost": round(material_cost, 2),
            "freight_cost": freight_cost,
            "platform_fee": platform_fee,
            "total_cost": total_procurement_cost,
        }

    def save(self):
        self.session.modified = True
