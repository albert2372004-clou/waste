"""
Consistency Checking Engine for Material Listings.
Checks whether Category + Material Name + Image appear consistent.
Example: 'Category: Plastic' with Material Name 'Tyre Rubber' or Image 'rubber.jpg'
will trigger a friendly warning to prevent misleading listings.
"""

CATEGORY_KEYWORDS = {
    "rubber": ["rubber", "tyre", "tire", "latex", "crumb", "vulcanized", "tread"],
    "textile": ["textile", "cotton", "fabric", "cloth", "yarn", "fiber", "denim", "selvage", "knitted"],
    "coconut": ["coconut", "shell", "coir", "pith", "charcoal", "copra", "husk"],
    "plastic": ["plastic", "pet", "hdpe", "pp", "polymer", "flake", "regrind", "pvc", "ldpe"],
    "fish": ["fish", "scale", "marine", "collagen", "seafood", "organic"],
}


def check_material_consistency(category: str, material_name: str, image_filename: str = "") -> dict:
    """
    Evaluates consistency across Category, Material Name, and Image file.
    Returns dict:
      {
        'is_consistent': bool,
        'name_conflict': str,
        'image_conflict': str,
        'warning_message': str,
        'confidence': str
      }
    """
    category = (category or "").lower().strip()
    mat_name = (material_name or "").lower().strip()
    img_name = (image_filename or "").lower().strip()

    name_conflicts = []
    image_conflicts = []

    for other_cat, keywords in CATEGORY_KEYWORDS.items():
        if other_cat != category:
            for kw in keywords:
                if kw in mat_name.split() or f" {kw} " in f" {mat_name} ":
                    name_conflicts.append(other_cat)
                    break
            for kw in keywords:
                if kw in img_name.lower():
                    image_conflicts.append(other_cat)
                    break

    name_conflict_str = ", ".join([c.capitalize() for c in set(name_conflicts)])
    image_conflict_str = ", ".join([c.capitalize() for c in set(image_conflicts)])

    is_consistent = not (bool(name_conflicts) or bool(image_conflicts))
    msg_parts = []
    if name_conflict_str:
        msg_parts.append(f"Material name references '{name_conflict_str}' while category is '{category.capitalize()}'")
    if image_conflict_str:
        msg_parts.append(f"Image filename references '{image_conflict_str}' while category is '{category.capitalize()}'")

    return {
        "is_consistent": is_consistent,
        "name_conflict": name_conflict_str,
        "image_conflict": image_conflict_str,
        "warning_message": " & ".join(msg_parts),
        "confidence": "High (Strict Keyword Alignment)" if is_consistent else "Conflict Detected"
    }
