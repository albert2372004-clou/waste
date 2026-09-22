from decimal import Decimal
from .logistics import calculate_corridor_distance


class StandardCartService:
    """
    Standard Flipkart / Amazon Style Shopping Cart.
    Allows buyers to add materials from any category, any supplier, adjust individual quantities,
    calculate itemized freight and platform fee, and execute checkout.
    """
    SESSION_KEY = "waste_standard_cart"

    def __init__(self, session):
        self.session = session
        cart = self.session.get(self.SESSION_KEY)
        if not cart:
            cart = self.session[self.SESSION_KEY] = {
                "destination_facility": "KINFRA Integrated Industrial Park, Palakkad, Kerala",
                "items": {}  # listing_id -> item data
            }
        self.cart = cart

    def set_destination(self, destination: str):
        if destination:
            self.cart["destination_facility"] = destination
            self.save()

    def add_item(self, listing, volume_tons: float):
        v = float(volume_tons)
        moq = float(listing.moq_tons)
        max_v = float(listing.volume_tons)
        v = max(moq, min(v, max_v))

        lid = str(listing.id)
        price = float(listing.price_per_ton)
        subtotal = round(v * price, 2)

        image_url = ""
        if hasattr(listing, 'primary_image') and listing.primary_image:
            try:
                image_url = listing.primary_image.url
            except Exception:
                image_url = ""

        self.cart["items"][lid] = {
            "listing_id": listing.id,
            "material_name": listing.material_name,
            "category": listing.category,
            "batch_id": listing.batch_id,
            "supplier_name": listing.supplier.company_name,
            "location": listing.location,
            "volume_tons": v,
            "moq_tons": moq,
            "max_tons": max_v,
            "price_per_ton": price,
            "subtotal": subtotal,
            "image_url": image_url,
            "purity_percent": getattr(listing, 'purity_percent', 90),
            "trust_score": getattr(listing, 'trust_score', 85),
        }
        self.save()

    def update_quantity(self, listing_id, new_volume: float):
        lid = str(listing_id)
        if lid in self.cart["items"]:
            item = self.cart["items"][lid]
            moq = item.get("moq_tons", 1.0)
            max_v = item.get("max_tons", 10000.0)
            v = max(moq, min(float(new_volume), max_v))
            item["volume_tons"] = v
            item["subtotal"] = round(v * item["price_per_ton"], 2)
            self.save()

    def remove_item(self, listing_id):
        lid = str(listing_id)
        if lid in self.cart["items"]:
            del self.cart["items"][lid]
            self.save()

    def clear(self):
        self.cart["items"] = {}
        self.save()

    def get_summary(self, destination: str = None):
        dest = destination or self.cart.get("destination_facility", "KINFRA Integrated Industrial Park, Palakkad, Kerala")
        items = list(self.cart["items"].values())

        total_tons = sum(item["volume_tons"] for item in items)
        material_cost = sum(item["subtotal"] for item in items)

        # Calculate itemized logistics
        total_freight = 0.0
        for item in items:
            dist_km = calculate_corridor_distance(item["location"], dest)
            item["distance_km"] = dist_km
            item_freight = round(item["volume_tons"] * dist_km * 3.20, 2)
            item["freight_cost"] = item_freight
            total_freight += item_freight

        platform_fee = round(material_cost * 0.015, 2) if material_cost > 0 else 0.0
        toll_fee = 450.0 if items else 0.0
        grand_total = round(material_cost + total_freight + platform_fee + toll_fee, 2)

        return {
            "items": items,
            "items_count": len(items),
            "total_tons": round(total_tons, 2),
            "destination_facility": dest,
            "material_cost": round(material_cost, 2),
            "freight_cost": round(total_freight, 2),
            "platform_fee": platform_fee,
            "toll_fee": toll_fee,
            "grand_total": grand_total,
        }

    def save(self):
        self.session.modified = True


class BatchCartService:
    """
    Manages session-based multi-supplier material pooling and quantity aggregation.
    Allows buyers to combine surplus batches from multiple factories to fulfill large orders.
    Enforces category isolation, target destination routing, and exact-quantity capping
    so total collected never exceeds the buyer's required target.
    """
    SESSION_KEY = "waste_batch_cart"

    def __init__(self, session):
        self.session = session
        cart = self.session.get(self.SESSION_KEY)
        if not cart:
            cart = self.session[self.SESSION_KEY] = {
                "target_volume_tons": 500.0,
                "target_material": "Scrap Rubber",
                "target_category": "rubber",
                "target_destination": "KINFRA Integrated Industrial Park, Palakkad, Kerala",
                "items": {}  # listing_id -> {listing_id, title, supplier, volume_tons, price, subtotal}
            }
        self.cart = cart

    def set_target(self, target_volume: float, target_material: str = None, target_category: str = None, target_destination: str = None):
        new_target = max(1.0, float(target_volume))
        self.cart["target_volume_tons"] = new_target
        if target_material:
            self.cart["target_material"] = target_material
        if target_category:
            self.cart["target_category"] = target_category
        if target_destination:
            self.cart["target_destination"] = target_destination

        # Excess Detection on Target Volume Reduction:
        # If the new target volume is less than currently collected volume,
        # trim the excess from the last allocated supplier(s) so required target is not exceeded.
        current_total = sum(item["volume_tons"] for item in self.cart["items"].values())
        if current_total > new_target:
            excess = current_total - new_target
            for lid in reversed(list(self.cart["items"].keys())):
                if excess <= 0:
                    break
                item = self.cart["items"][lid]
                if item["volume_tons"] > excess:
                    item["volume_tons"] = round(item["volume_tons"] - excess, 2)
                    item["subtotal"] = round(item["volume_tons"] * item["price_per_ton"], 2)
                    excess = 0
                else:
                    excess -= item["volume_tons"]
                    del self.cart["items"][lid]

        self.save()

    def add_listing(self, listing, volume_tons: float, cap_to_target: bool = True):
        v = float(volume_tons)
        lid = str(listing.id)
        price = float(listing.price_per_ton)

        # Enforce Single-Category Aggregation Invariant
        if self.cart["items"]:
            first_item = next(iter(self.cart["items"].values()))
            existing_cat = first_item.get("category")
            if existing_cat and existing_cat != listing.category:
                raise ValueError(
                    f"Category Isolation Conflict: Your active Batch Cart is aggregating '{existing_cat.capitalize()}'. "
                    f"You cannot combine '{listing.category.capitalize()}' in the same consolidated logistics batch."
                )

        target = float(self.cart.get("target_volume_tons", 500.0))
        # Other items in pool excluding this listing
        current_other = sum(it["volume_tons"] for k, it in self.cart["items"].items() if k != lid)
        remaining_needed = max(0.0, target - current_other)

        # Excess Detection & Capping:
        # When added quantity would exceed required target, detect excess and trim from this supplier
        # so total allocated NEVER exceeds what the buyer required.
        if cap_to_target and remaining_needed > 0 and v > remaining_needed:
            v = remaining_needed

        v = round(v, 2)

        if v <= 0:
            return

        subtotal = round(v * price, 2)

        self.cart["target_category"] = listing.category
        if not self.cart.get("target_material") or self.cart.get("target_material") == "Scrap Rubber":
            self.cart["target_material"] = listing.get_category_display()

        self.cart["items"][lid] = {
            "listing_id": listing.id,
            "material_name": listing.material_name,
            "category": listing.category,
            "batch_id": listing.batch_id,
            "supplier_name": listing.supplier.company_name,
            "volume_tons": v,
            "price_per_ton": price,
            "subtotal": subtotal,
            "trust_score": getattr(listing, 'trust_score', 85),
            "purity_percent": getattr(listing, 'purity_percent', 90),
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

    def get_summary(self, destination: str = None):
        items = list(self.cart["items"].values())
        collected_tons = sum(item["volume_tons"] for item in items)
        target_tons = float(self.cart.get("target_volume_tons", 500.0))
        target_material = self.cart.get("target_material", "Scrap Rubber")
        target_category = self.cart.get("target_category", "rubber")
        target_dest = destination or self.cart.get("target_destination", "KINFRA Integrated Industrial Park, Palakkad, Kerala")

        material_cost = sum(item["subtotal"] for item in items)

        # Dynamic corridor freight computation based on target destination
        freight_cost = 0.0
        for item in items:
            dist_km = calculate_corridor_distance(item["location"], target_dest)
            item["distance_km"] = dist_km
            item_freight = round(item["volume_tons"] * dist_km * 3.10, 2)
            item["freight_cost"] = item_freight
            freight_cost += item_freight
            if collected_tons > 0:
                item["share_percent"] = round((item["volume_tons"] / collected_tons) * 100, 1)
            else:
                item["share_percent"] = 0

        platform_fee = round(material_cost * 0.015, 2) if material_cost > 0 else 0.0
        toll_fee = 450.0 if items else 0.0
        total_procurement_cost = round(material_cost + freight_cost + platform_fee + toll_fee, 2)

        progress_pct = min(100, int((collected_tons / target_tons) * 100)) if target_tons > 0 else 0
        remaining_tons = max(0.0, target_tons - collected_tons)

        return {
            "items": items,
            "items_count": len(items),
            "target_tons": target_tons,
            "target_material": target_material,
            "target_category": target_category,
            "target_destination": target_dest,
            "collected_tons": round(collected_tons, 2),
            "remaining_tons": round(remaining_tons, 2),
            "progress_pct": progress_pct,
            "is_fully_filled": collected_tons >= target_tons,
            "material_cost": round(material_cost, 2),
            "freight_cost": round(freight_cost, 2),
            "platform_fee": platform_fee,
            "toll_fee": toll_fee,
            "total_cost": total_procurement_cost,
        }

    def save(self):
        self.session.modified = True
