"""
Image Verification Service for Circular Waste Streams.
Analyzes uploaded waste photo content (pixels, color distribution, luminance, and edge texture)
and evaluates consistency against calibrated visual signatures of supported industrial byproduct categories.

Rules:
- Content-based (never depends on filename)
- Real mathematical feature scoring (never fake or random)
- Never blocks listing submission (informational / alert only)
- Safely handles corrupted or invalid images
"""

import io
import logging
from typing import Any, Dict, Optional, Tuple
import numpy as np
from PIL import Image, UnidentifiedImageError

logger = logging.getLogger(__name__)

# Supported category reference profiles
CATEGORY_PROFILES = {
    "coconut": {
        "label": "Coconut Shells",
        "target": {
            "mean_v": 0.42,
            "std_v": 0.16,
            "dark_frac": 0.18,
            "bright_frac": 0.05,
            "mean_s": 0.50,
            "low_s_frac": 0.15,
            "high_s_frac": 0.45,
            "edge_energy": 0.08,
            "hue_weight_bins": [0, 1],  # Warm Orange / Brown hues
        },
        "weights": {
            "mean_v": 1.5,
            "dark_frac": 1.5,
            "bright_frac": 2.0,
            "mean_s": 1.5,
            "edge_energy": 1.0,
            "hue": 3.0,
        },
    },
    "rubber": {
        "label": "Scrap Rubber",
        "target": {
            "mean_v": 0.18,
            "std_v": 0.10,
            "dark_frac": 0.75,
            "bright_frac": 0.01,
            "mean_s": 0.10,
            "low_s_frac": 0.85,
            "high_s_frac": 0.02,
            "edge_energy": 0.05,
            "hue_weight_bins": [],  # Achromatic dark
        },
        "weights": {
            "mean_v": 3.0,
            "dark_frac": 3.0,
            "bright_frac": 2.0,
            "mean_s": 2.0,
            "edge_energy": 0.8,
            "hue": 0.5,
        },
    },
    "fish": {
        "label": "Fish Scales",
        "target": {
            "mean_v": 0.82,
            "std_v": 0.12,
            "dark_frac": 0.02,
            "bright_frac": 0.75,
            "mean_s": 0.08,
            "low_s_frac": 0.85,
            "high_s_frac": 0.02,
            "edge_energy": 0.07,
            "hue_weight_bins": [],  # Pale translucent silvery
        },
        "weights": {
            "mean_v": 3.0,
            "dark_frac": 2.0,
            "bright_frac": 3.0,
            "mean_s": 1.5,
            "edge_energy": 1.0,
            "hue": 0.5,
        },
    },
    "textile": {
        "label": "Textile Remnants",
        "target": {
            "mean_v": 0.50,
            "std_v": 0.20,
            "dark_frac": 0.10,
            "bright_frac": 0.20,
            "mean_s": 0.65,
            "low_s_frac": 0.10,
            "high_s_frac": 0.65,
            "edge_energy": 0.10,
            "hue_weight_bins": [0, 2, 4, 5, 6],  # Multicolored / vibrant dyes
        },
        "weights": {
            "mean_v": 1.0,
            "dark_frac": 1.0,
            "bright_frac": 1.0,
            "mean_s": 2.5,
            "edge_energy": 1.5,
            "hue": 2.0,
        },
    },
    "plastic": {
        "label": "Plastic Fragments",
        "target": {
            "mean_v": 0.60,
            "std_v": 0.22,
            "dark_frac": 0.08,
            "bright_frac": 0.35,
            "mean_s": 0.55,
            "low_s_frac": 0.20,
            "high_s_frac": 0.50,
            "edge_energy": 0.12,
            "hue_weight_bins": [2, 3, 4],  # Saturated synthetics
        },
        "weights": {
            "mean_v": 1.2,
            "dark_frac": 1.0,
            "bright_frac": 1.5,
            "mean_s": 2.0,
            "edge_energy": 1.5,
            "hue": 2.0,
        },
    },
    "paper": {
        "label": "Paper Waste",
        "target": {
            "mean_v": 0.75,
            "std_v": 0.14,
            "dark_frac": 0.05,
            "bright_frac": 0.65,
            "mean_s": 0.22,
            "low_s_frac": 0.60,
            "high_s_frac": 0.08,
            "edge_energy": 0.04,
            "hue_weight_bins": [0, 1],  # Kraft cardboard or white
        },
        "weights": {
            "mean_v": 2.5,
            "dark_frac": 2.0,
            "bright_frac": 2.0,
            "mean_s": 1.5,
            "edge_energy": 1.5,
            "hue": 1.5,
        },
    },
    "metal": {
        "label": "Metal Scrap",
        "target": {
            "mean_v": 0.45,
            "std_v": 0.28,
            "dark_frac": 0.30,
            "bright_frac": 0.25,
            "mean_s": 0.15,
            "low_s_frac": 0.70,
            "high_s_frac": 0.08,
            "edge_energy": 0.14,
            "hue_weight_bins": [],  # Metallic reflection / high contrast
        },
        "weights": {
            "mean_v": 1.5,
            "dark_frac": 1.5,
            "bright_frac": 2.0,
            "mean_s": 2.0,
            "edge_energy": 2.0,
            "hue": 0.5,
        },
    },
}


def _rgb_to_hsv(arr: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Fast vectorized RGB -> HSV conversion for float32 array in [0..1]."""
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    maxc = np.maximum(np.maximum(r, g), b)
    minc = np.minimum(np.minimum(r, g), b)
    v = maxc
    deltac = maxc - minc

    s = np.zeros_like(v)
    mask = maxc > 1e-5
    s[mask] = deltac[mask] / maxc[mask]

    h = np.zeros_like(v)
    rc = np.zeros_like(r)
    gc = np.zeros_like(g)
    bc = np.zeros_like(b)

    mask_delta = deltac > 1e-5
    rc[mask_delta] = (maxc[mask_delta] - r[mask_delta]) / deltac[mask_delta]
    gc[mask_delta] = (maxc[mask_delta] - g[mask_delta]) / deltac[mask_delta]
    bc[mask_delta] = (maxc[mask_delta] - b[mask_delta]) / deltac[mask_delta]

    mask_r = (r == maxc) & mask_delta
    mask_g = (g == maxc) & (~mask_r) & mask_delta
    mask_b = (b == maxc) & (~mask_r) & (~mask_g) & mask_delta

    h[mask_r] = (bc[mask_r] - gc[mask_r]) % 6.0
    h[mask_g] = 2.0 + rc[mask_g] - bc[mask_g]
    h[mask_b] = 4.0 + gc[mask_b] - rc[mask_b]
    h = (h / 6.0) % 1.0
    return h, s, v


def extract_visual_features(pil_img: Image.Image) -> Dict[str, Any]:
    """
    Extracts normalized color, luminance, and edge texture metrics from a PIL Image.
    """
    img_resized = pil_img.convert("RGB").resize((128, 128))
    arr = np.asarray(img_resized, dtype=np.float32) / 255.0

    h, s, v = _rgb_to_hsv(arr)

    # Edge and texture roughness via finite gradient differences
    gray = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
    dx = np.abs(gray[:, 1:] - gray[:, :-1])
    dy = np.abs(gray[1:, :] - gray[:-1, :])
    edge_energy = float((np.mean(dx) + np.mean(dy)) / 2.0)

    mean_v = float(np.mean(v))
    std_v = float(np.std(v))
    dark_frac = float(np.mean(v < 0.25))
    bright_frac = float(np.mean(v > 0.70))

    mean_s = float(np.mean(s))
    low_s_frac = float(np.mean(s < 0.20))
    high_s_frac = float(np.mean(s > 0.50))

    # Hue histogram (8 bins)
    color_mask = (s > 0.15) & (v > 0.15)
    hue_bins = np.zeros(8, dtype=np.float32)
    if np.sum(color_mask) > 10:
        h_colored = h[color_mask]
        hist, _ = np.histogram(h_colored, bins=8, range=(0.0, 1.0))
        hue_bins = (hist / np.sum(hist)).astype(np.float32)

    return {
        "mean_v": mean_v,
        "std_v": std_v,
        "dark_frac": dark_frac,
        "bright_frac": bright_frac,
        "mean_s": mean_s,
        "low_s_frac": low_s_frac,
        "high_s_frac": high_s_frac,
        "edge_energy": edge_energy,
        "hue_bins": hue_bins,
    }


def compute_category_similarity(features: Dict[str, Any], cat_key: str) -> float:
    """
    Computes mathematical similarity score (0.0% to 100.0%) for a given category.
    """
    if cat_key not in CATEGORY_PROFILES:
        return 50.0

    prof = CATEGORY_PROFILES[cat_key]
    tgt = prof["target"]
    w = prof["weights"]

    dist_v = abs(features["mean_v"] - tgt["mean_v"])
    dist_dark = abs(features["dark_frac"] - tgt["dark_frac"])
    dist_bright = abs(features["bright_frac"] - tgt["bright_frac"])
    dist_s = abs(features["mean_s"] - tgt["mean_s"])
    dist_edge = abs(features["edge_energy"] - tgt["edge_energy"])

    hue_bins = tgt.get("hue_weight_bins", [])
    if hue_bins:
        matching_hue_frac = sum([features["hue_bins"][b] for b in hue_bins if b < len(features["hue_bins"])])
        hue_dist = 1.0 - matching_hue_frac
    else:
        # Achromatic profile: penalize high saturation
        hue_dist = features["high_s_frac"]

    weighted_dist = (
        dist_v * w["mean_v"]
        + dist_dark * w["dark_frac"]
        + dist_bright * w["bright_frac"]
        + dist_s * w["mean_s"]
        + dist_edge * w["edge_energy"]
        + hue_dist * w["hue"]
    )
    total_weight = sum(w.values())
    norm_dist = weighted_dist / total_weight

    # Scale to percentage 0..100
    score = max(5.0, min(96.0, 96.0 * (1.0 - 1.4 * norm_dist)))
    return round(score, 1)


def verify_waste_image(image_input: Any, selected_category: str) -> Dict[str, Any]:
    """
    Verifies uploaded waste image content against selected category.
    Returns:
      {
        "status": "Likely Match" | "Manual Review" | "Possible Mismatch",
        "score": float (0.0 to 100.0),
        "detected_category": str,
        "is_likely_match": bool,
        "is_mismatch": bool,
        "message": str
      }
    """
    if not image_input:
        return {
            "status": "Manual Review",
            "score": 0.0,
            "detected_category": "No Image Provided",
            "is_likely_match": False,
            "is_mismatch": False,
            "message": "No image was uploaded. Requires manual review.",
        }

    pil_img = None
    try:
        # Safely reset file pointer if needed
        if hasattr(image_input, "seek"):
            try:
                image_input.seek(0)
            except Exception:
                pass

        if isinstance(image_input, Image.Image):
            pil_img = image_input
        elif hasattr(image_input, "read"):
            data = image_input.read()
            if hasattr(image_input, "seek"):
                try:
                    image_input.seek(0)
                except Exception:
                    pass
            if not data:
                raise ValueError("Uploaded file is empty.")
            pil_img = Image.open(io.BytesIO(data))
        elif isinstance(image_input, (str, bytes)):
            pil_img = Image.open(image_input)
        else:
            raise TypeError("Unsupported image input type.")

        pil_img.verify()
        # After verify(), re-open as Image.open() moves pointer
        if hasattr(image_input, "seek"):
            try:
                image_input.seek(0)
            except Exception:
                pass

        if hasattr(image_input, "read"):
            data = image_input.read()
            if hasattr(image_input, "seek"):
                try:
                    image_input.seek(0)
                except Exception:
                    pass
            pil_img = Image.open(io.BytesIO(data))
        elif isinstance(image_input, (str, bytes)):
            pil_img = Image.open(image_input)

    except Exception as e:
        logger.warning(f"Image verification failed to open image: {e}")
        return {
            "status": "Manual Review",
            "score": 0.0,
            "detected_category": "Unknown / Corrupted File",
            "is_likely_match": False,
            "is_mismatch": False,
            "message": f"Could not analyze image content ({str(e)}). Manual verification required.",
        }

    # Extract features
    try:
        features = extract_visual_features(pil_img)
    except Exception as e:
        logger.warning(f"Feature extraction failed: {e}")
        return {
            "status": "Manual Review",
            "score": 0.0,
            "detected_category": "Unknown",
            "is_likely_match": False,
            "is_mismatch": False,
            "message": "Feature extraction failed. Manual verification required.",
        }

    # Compute scores for all supported categories
    category_scores = {}
    for cat_key in CATEGORY_PROFILES:
        category_scores[cat_key] = compute_category_similarity(features, cat_key)

    # Clean selected category key
    clean_cat = (selected_category or "").lower().strip()
    target_score = category_scores.get(clean_cat)

    # Identify best matching category
    best_cat_key = max(category_scores, key=category_scores.get)
    best_cat_label = CATEGORY_PROFILES[best_cat_key]["label"]

    if target_score is None:
        # Category not recognized in profiles
        return {
            "status": "Manual Review",
            "score": 50.0,
            "detected_category": best_cat_label,
            "is_likely_match": False,
            "is_mismatch": False,
            "message": f"Category '{selected_category}' not calibrated. Detected closest: {best_cat_label}.",
        }

    # Determine status according to thresholds
    # ≥80% -> "Likely Match"
    # 50–79% -> "Manual Review"
    # <50% -> "Possible Mismatch"
    if target_score >= 80.0:
        status = "Likely Match"
        message = f"Likely Match ({target_score:.0f}%): Visual features correspond to {CATEGORY_PROFILES.get(clean_cat, {}).get('label', clean_cat)}."
    elif target_score >= 50.0:
        status = "Manual Review"
        message = f"Manual Verification Required ({target_score:.0f}%): Borderline match with {CATEGORY_PROFILES.get(clean_cat, {}).get('label', clean_cat)}. Closest match: {best_cat_label} ({category_scores[best_cat_key]:.0f}%)."
    else:
        status = "Possible Mismatch"
        message = f"⚠ Possible Mismatch ({target_score:.0f}%): Visual appearance differs from selected {CATEGORY_PROFILES.get(clean_cat, {}).get('label', clean_cat)}. Detected profile: {best_cat_label} ({category_scores[best_cat_key]:.0f}%)."

    return {
        "status": status,
        "score": target_score,
        "detected_category": best_cat_label,
        "is_likely_match": (status == "Likely Match"),
        "is_mismatch": (status == "Possible Mismatch"),
        "message": message,
        "category_scores": category_scores,
    }


def process_multi_image_verification(primary_file: Any, additional_files: list, category: str) -> Dict[str, Any]:
    """
    Evaluates multi-angle batch photos (primary + additional angles):
    1. If some images match and others do not (e.g. image 1 matches, images 2 & 3 do not):
       Includes ONLY the verified matching images, and automatically removes / filters out the mismatched ones.
    2. If NONE of the images match (not 1st, 2nd, or 3rd):
       Automatically applies official industrial category symbols, omits mismatched photos from gallery,
       and sets use_category_symbol = True.
    """
    candidates = []
    if primary_file:
        candidates.append({"file": primary_file, "role": "Primary Image"})
    for idx, f in enumerate(additional_files or []):
        if f:
            candidates.append({"file": f, "role": f"Angle {idx + 1}"})

    if not candidates:
        return {
            "verified_primary": None,
            "verified_gallery": [],
            "matched_count": 0,
            "mismatched_count": 0,
            "use_category_symbol": True,
            "status": "Manual Review",
            "score": 0.0,
            "detected_category": "No Image Provided",
            "alert_type": "info",
            "message": "No photos uploaded. Category symbol will be displayed.",
        }

    for item in candidates:
        item["result"] = verify_waste_image(item["file"], category)
        item["is_match"] = not item["result"]["is_mismatch"]  # score >= 50%

    matching = [c for c in candidates if c["is_match"]]
    mismatched = [c for c in candidates if not c["is_match"]]

    # Case 1: At least one image is a verified match
    if matching:
        verified_primary = matching[0]["file"]
        verified_gallery = [m["file"] for m in matching[1:]]
        best_score = max(m["result"]["score"] for m in matching)
        overall_status = "Likely Match" if best_score >= 80.0 else "Manual Review"
        detected_cat = matching[0]["result"]["detected_category"]
        mismatched_count = len(mismatched)

        if mismatched_count > 0:
            msg = (
                f"{len(matching)} authentic image(s) verified and included. "
                f"{mismatched_count} mismatched image(s) were automatically filtered out."
            )
            alert_type = "warning"
        else:
            msg = f"All {len(matching)} uploaded photo(s) verified successfully ({best_score:.0f}%)."
            alert_type = "success"

        return {
            "verified_primary": verified_primary,
            "verified_gallery": verified_gallery,
            "matched_count": len(matching),
            "mismatched_count": mismatched_count,
            "use_category_symbol": False,
            "status": overall_status,
            "score": best_score,
            "detected_category": detected_cat,
            "alert_type": alert_type,
            "message": msg,
        }

    # Case 2: NONE of the images match (not 1st, 2nd, or 3rd)
    # Automatically applies official industrial category symbols!
    mismatched_count = len(mismatched)
    best_mismatch_score = max(c["result"]["score"] for c in mismatched) if mismatched else 0.0
    detected_cat = mismatched[0]["result"]["detected_category"] if mismatched else "Unknown"

    msg = (
        f"⚠ Visual Alert: None of the {mismatched_count} uploaded photo(s) matched selected category "
        f"'{category.capitalize()}' (Detected: {detected_cat}). "
        f"The official industrial stream symbol has been automatically applied to your listing. "
        f"Listing was submitted successfully for administrative review."
    )

    return {
        "verified_primary": candidates[0]["file"],  # preserved for admin audit
        "verified_gallery": [],  # discard all mismatched gallery images
        "matched_count": 0,
        "mismatched_count": mismatched_count,
        "use_category_symbol": True,
        "status": "Possible Mismatch",
        "score": best_mismatch_score,
        "detected_category": detected_cat,
        "alert_type": "warning",
        "message": msg,
    }
