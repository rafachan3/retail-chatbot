"""Embedding-only recommendation backend.

This module now provides ONLY the embedding-based recommendation logic.
Legacy TF-IDF code was removed after design decision to rely exclusively on
semantic sentence embeddings for:
  * Single item recommendations (with optional wardrobe match context)
  * Multi-item outfit recommendations (top_k per requested item)

Main entrypoints:
  - get_embedding_recommender(base_dir) -> EmbeddingRecommender singleton

The EmbeddingRecommender performs:
  1. Label-space matching for style and product_type_name via cosine similarity on
      normalized SentenceTransformer embeddings of unique catalog labels.
  2. Row filtering to matched style + product_type (single-item) or style subset +
      per-item candidate selection (outfit).
  3. Construction of per-row descriptive text (select semantic columns) and ranking
      by cosine similarity to the user (or per-item) description.
  4. Optional augmentation of single-item description with wardrobe context when
      the user wants the new item to match existing wardrobe items.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
from pathlib import Path
import re
import threading
import logging
import numpy as np
try:
    from sentence_transformers import SentenceTransformer  # type: ignore
except Exception:  # pragma: no cover - optional dependency environment guard
    SentenceTransformer = None  # type: ignore


STYLE_COLUMN = "style"  # style column in cleaned CSV


#############################
# Item type normalization (shared inner logic)
#############################
_ITEM_TYPE_CLEAN = re.compile(r"[^a-z0-9]+")

def _normalize_item_type_text(text: str) -> str:
    t = text.lower().strip()
    t = t.replace("-", " ")
    t = _ITEM_TYPE_CLEAN.sub(" ", t)
    parts = [p for p in t.split() if p]
    if not parts:
        return ""
    # Singularize naive (remove trailing 's') for last token if >3 chars
    norm_parts = []
    for p in parts:
        if len(p) > 3 and p.endswith("s"):
            p = p[:-1]
        norm_parts.append(p)
    return "_".join(norm_parts)


def _load_catalog(csv_path: Path) -> pd.DataFrame:
    if not csv_path.exists():
        raise FileNotFoundError(f"Catalog file not found: {csv_path}")
    df = pd.read_csv(csv_path)
    if "article_id" not in df.columns:
        raise ValueError("Expected 'article_id' column in catalog CSV.")
    return df
if __name__ == "__main__":  # simple manual smoke test for embedding path
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    rec = None
    try:
        rec = None
        base = Path(__file__).parent
        emb = None
        from sentence_transformers import SentenceTransformer  # type: ignore
        emb = SentenceTransformer
        emb_rec = None
        # Build singleton
        from pathlib import Path as _P
        emb_rec = None
    except Exception as e:
        logging.error("Embedding smoke test failed init: %s", e)

# ------------------ Embedding (SentenceTransformer) Based Recommender ------------------

EMBED_MODEL_NAME = "all-MiniLM-L6-v2"

class EmbeddingRecommender:
    """Embedding-based product recommender using semantic similarity.
    
    This recommender uses SentenceTransformer embeddings to:
    1. Match user style preferences to catalog styles via cosine similarity
    2. Match user item type requests to catalog product types
    3. Filter products based on matched style and product type
    4. Rank products by semantic similarity to user descriptions
    5. Apply color and style bonuses for better personalization
    
    Attributes:
        df: Product catalog dataframe
        model: SentenceTransformer model for encoding text
        text_cols: Columns used for building product descriptions
        unique_styles: All available styles in the catalog
        unique_item_types: All available product types in the catalog
        style_embs: Pre-computed embeddings for styles
        item_type_embs: Pre-computed embeddings for item types
    """

    def __init__(self, df: pd.DataFrame, model: Any, text_cols: List[str]):
        self.df = df
        self.model = model
        self.text_cols = text_cols
        # Precompute unique style + product_type embeddings
        self.unique_styles = sorted([s for s in df[STYLE_COLUMN].dropna().unique()]) if STYLE_COLUMN in df.columns else []
        self.unique_item_types = sorted([s for s in df["product_type_name"].dropna().unique()]) if "product_type_name" in df.columns else []
        self.style_embs = self.model.encode(self.unique_styles, normalize_embeddings=True) if self.unique_styles else None
        self.item_type_embs = self.model.encode(self.unique_item_types, normalize_embeddings=True) if self.unique_item_types else None

    @classmethod
    def from_catalog(cls, base_dir: Path) -> "EmbeddingRecommender":
        """Create an EmbeddingRecommender from the product catalog.
        
        Args:
            base_dir: Directory containing the articles_expanded_cleaned.csv file
            
        Returns:
            Initialized EmbeddingRecommender instance
            
        Raises:
            RuntimeError: If sentence-transformers is not installed
            FileNotFoundError: If catalog file is not found
        """
        df = _load_catalog(base_dir / "articles_expanded_cleaned.csv")
        if SentenceTransformer is None:
            raise RuntimeError("sentence-transformers not installed; run pip install sentence-transformers")
        model = SentenceTransformer(EMBED_MODEL_NAME)
        # Choose description columns subset (reuse some from TF-IDF but exclude style)
        text_cols = [c for c in ["prod_name", "detail_desc", "product_group_name", "graphical_appearance_name", "colour_group_name", "perceived_colour_value_name"] if c in df.columns]
        return cls(df, model, text_cols)

    def _encode(self, text: str):
        return self.model.encode([text], normalize_embeddings=True)[0]

    def _match_value(self, query: str, catalog_values: List[str], catalog_embs) -> Tuple[str, float]:
        if not query or not catalog_values or catalog_embs is None:
            return "", 0.0
        q_emb = self._encode(query)
        # Safe similarity computation (guard against stray NaN/Inf from backend/device)
        catalog_embs = np.nan_to_num(catalog_embs, copy=False)
        q_emb = np.nan_to_num(q_emb, copy=False)
        with np.errstate(over='ignore', invalid='ignore', divide='ignore'):
            sims = (catalog_embs * q_emb).sum(axis=1)
        if not np.all(np.isfinite(sims)):
            sims = np.nan_to_num(sims, nan=-1.0, posinf=1.0, neginf=-1.0)
        idx = int(np.argmax(sims))
        return catalog_values[idx], float(sims[idx])

    def _build_row_text(self, row: pd.Series) -> str:
        parts = []
        for c in self.text_cols:
            val = str(row.get(c, ""))
            if val and val.lower() != "nan":
                parts.append(val)
        return " | ".join(parts)
    
    def _build_color_emphasized_text(self, row: pd.Series) -> str:
        """Build product description with emphasized color information."""
        color_parts = []
        other_parts = []
        
        for c in self.text_cols:
            val = str(row.get(c, ""))
            if val and val.lower() != "nan":
                # Emphasize color-related columns by including them multiple times
                if "colour" in c.lower() or "color" in c.lower():
                    color_parts.extend([val, val, val])  # Triple weight for color
                else:
                    other_parts.append(val)
        
        # Put color information first and repeat it for emphasis
        all_parts = color_parts + other_parts
        return " | ".join(all_parts)
    
    def _extract_color_terms(self, text: str) -> str:
        """Extract color-related terms from user input using comprehensive color vocabulary."""
        import re
        
        # Comprehensive color terms from domain vocabulary (from backend-user-preferences.py)
        color_terms = {
            # Basic colors
            "black", "white", "gray", "grey", "silver", "charcoal", "graphite", "slate",
            "navy", "blue", "light", "dark", "midnight", "indigo", "cyan", "teal", "aqua", "turquoise",
            "green", "olive", "khaki", "lime", "forest", "emerald", "mint",
            "brown", "tan", "beige", "camel", "chocolate", "mocha", "sand", "taupe",
            "red", "maroon", "burgundy", "wine", "crimson",
            "pink", "blush", "rose", "magenta", "fuchsia",
            "purple", "violet", "lavender", "lilac",
            "orange", "rust", "terracotta", "coral", "peach", "apricot",
            "yellow", "mustard", "gold", "golden", "cream", "ivory", "ecru", "offwhite", "off-white"
        }
        
        text_lower = text.lower()
        found_colors = []
        
        # Check for color terms in the text
        for color in color_terms:
            if color in text_lower:
                found_colors.append(color)
        
        # Also look for color modifiers/descriptors that enhance color matching
        color_descriptors = ["bright", "pale", "deep", "vibrant", "muted", "pastel", "neon", "metallic"]
        for descriptor in color_descriptors:
            if descriptor in text_lower:
                found_colors.append(descriptor)
        
        return " ".join(found_colors)
    
    def _calculate_color_bonus(self, user_desc: str, product_row: pd.Series) -> float:
        """Calculate color matching bonus score."""
        user_colors = self._extract_color_terms(user_desc)
        if not user_colors:
            return 0.0
        
        # Get product color information
        product_colors = []
        for col in ["colour_group_name", "perceived_colour_value_name"]:
            if col in product_row.index:
                val = str(product_row.get(col, ""))
                if val and val.lower() != "nan":
                    product_colors.append(val.lower())
        
        if not product_colors:
            return 0.0
        
        # Simple color matching - check if any user color appears in product colors
        user_color_list = user_colors.lower().split()
        product_color_text = " ".join(product_colors)
        
        matches = sum(1 for color in user_color_list if color in product_color_text)
        
        # Return bonus score (0.0 to 0.3 range)
        return min(0.3, matches * 0.15)

    def recommend_from_preferences(self, prefs: Dict[str, Any], top_k: int = 3) -> List[Dict[str, Any]]:
        # Extract cleaned fields
        style_q = (prefs.get("clean_debug", {}).get("style_clean") or prefs.get("style") or "").strip()
        item_type_q = (prefs.get("clean_debug", {}).get("single_item_type_clean") or prefs.get("single_item_type") or "").strip()
        desc_map = prefs.get("clean_debug", {}).get("descriptions_clean") or prefs.get("descriptions") or {}
        if isinstance(desc_map, dict):
            user_desc = " ".join(desc_map.values())
        else:
            user_desc = str(desc_map)
        # Wardrobe matching context (single-item flow with match_existing True)
        if prefs.get("mode") == "item" and prefs.get("match_existing") and not prefs.get("outfit_items_list"):
            wardrobe_text = (
                prefs.get("clean_debug", {}).get("wardrobe_items_to_match_clean")
                or prefs.get("wardrobe_items_to_match_clean")
                or prefs.get("wardrobe_items_to_match")
                or ""
            )
            if wardrobe_text:
                # Append with a separator to keep semantic distinction
                user_desc = (user_desc + " | match: " + wardrobe_text).strip()

        matched_style, style_sim = self._match_value(style_q, self.unique_styles, self.style_embs)
        matched_item_type, item_sim = self._match_value(item_type_q, self.unique_item_types, self.item_type_embs)
        logging.info("[embed] Matched style '%s' (%.3f) item_type '%s' (%.3f) from queries style='%s' item_type='%s'", matched_style, style_sim, matched_item_type, item_sim, style_q, item_type_q)

        # Check if user has strong color preferences
        user_colors = self._extract_color_terms(user_desc)
        has_strong_color_preference = bool(user_colors.strip())
        
        filt_df = self.df
        
        # Apply item type filtering first (this is usually more important)
        if matched_item_type:
            filt_df = filt_df[filt_df["product_type_name"] == matched_item_type]
        
        # Smart style filtering: relax when user has strong color preferences
        if matched_style:
            style_filtered_df = filt_df[filt_df[STYLE_COLUMN] == matched_style]
            
            if has_strong_color_preference and len(style_filtered_df) < top_k * 3:
                # If we have few results with exact style match and user specified colors,
                # expand to include other styles but weight the original style higher
                logging.info("[embed] Relaxing style filter due to strong color preference and limited style matches (%d items)", len(style_filtered_df))
                # Keep the style-filtered items but expand the pool
                expanded_df = filt_df  # All items of the right type
                filt_df = expanded_df
            else:
                filt_df = style_filtered_df
        
        if filt_df.empty:
            logging.info("[embed] No rows after filtering; returning empty list.")
            return []

        # Build / encode product texts with color emphasis
        texts = filt_df.apply(self._build_color_emphasized_text, axis=1).tolist()
        prod_embs = self.model.encode(texts, normalize_embeddings=True)
        user_desc = user_desc.strip()
        if not user_desc:
            subset = filt_df.head(top_k)
            base: List[Dict[str, Any]] = []
            for _, r in subset.iterrows():
                base.append({
                    "article_id": int(r.article_id),  # type: ignore[arg-type]
                    "product_type_name": r.product_type_name,
                    "prod_name": r.get("prod_name", ""),
                    "style": r.get(STYLE_COLUMN, ""),
                    "score": None,
                    "style_match_score": style_sim,
                    "item_type_match_score": item_sim,
                    "desc_similarity": None,
                    "color_bonus": 0.0,
                    "style_bonus": 0.0,
                    "requested_item_type": item_type_q,  # Track which user item this was recommended for
                })
            return base
        q_emb = self._encode(user_desc)
        prod_embs = np.nan_to_num(prod_embs, copy=False)
        q_emb = np.nan_to_num(q_emb, copy=False)
        with np.errstate(over='ignore', invalid='ignore', divide='ignore'):
            sims = (prod_embs * q_emb).sum(axis=1)
        if not np.all(np.isfinite(sims)):
            sims = np.nan_to_num(sims, nan=-1.0, posinf=1.0, neginf=-1.0)
        
        # Apply color bonus to similarity scores
        color_bonuses = np.array([self._calculate_color_bonus(user_desc, filt_df.iloc[i]) for i in range(len(filt_df))])
        
        # Add style bonus for items that match the original style when we've expanded the search
        style_bonuses = np.zeros(len(filt_df))
        if has_strong_color_preference and matched_style:
            # Give bonus to items that match the original style preference
            for i, (_, row) in enumerate(filt_df.iterrows()):
                if row.get(STYLE_COLUMN) == matched_style:
                    style_bonuses[i] = 0.1  # Small bonus to maintain style preference
        
        enhanced_sims = sims + color_bonuses + style_bonuses
        
        order = np.argsort(-enhanced_sims)[: top_k * 3]
        results: List[Dict[str, Any]] = []
        for i in order:
            row = filt_df.iloc[i]
            base_sim = float(sims[i])
            color_bonus = float(color_bonuses[i])
            style_bonus = float(style_bonuses[i]) if 'style_bonuses' in locals() else 0.0
            final_score = float(enhanced_sims[i])
            results.append({
                "article_id": int(row.article_id),  # type: ignore[arg-type]
                "product_type_name": row.product_type_name,
                "prod_name": row.get("prod_name", ""),
                "style": row.get(STYLE_COLUMN, ""),
                "score": final_score,
                "style_match_score": style_sim,
                "item_type_match_score": item_sim,
                "desc_similarity": base_sim,
                "color_bonus": color_bonus,  # New field to track color matching
                "style_bonus": style_bonus,  # New field to track style preference bonus
                "requested_item_type": item_type_q,  # Track which user item this was recommended for
            })
            if len(results) >= top_k:
                break
        return results

    # ------------------------------------------------------------------
    # Outfit (multi-item) flow
    # ------------------------------------------------------------------
    def recommend_outfit_from_preferences(self, prefs: Dict[str, Any], top_k: int = 3) -> List[Dict[str, Any]]:
        """Per-item outfit recommendations returning flattened list matching single-item format.

        Flow: style match -> style subset -> per-item product_type candidates (exact norm, substring, embed fallback) ->
        per-item description ranking.
        """
        style_q = (prefs.get("clean_debug", {}).get("style_clean") or prefs.get("style") or "").strip()
        matched_style, style_sim = self._match_value(style_q, self.unique_styles, self.style_embs)
        items_list = (
            prefs.get("clean_debug", {}).get("outfit_items_list_clean")
            or prefs.get("outfit_items_list_clean")
            or prefs.get("outfit_items_list")
            or []
        )
        if not items_list:
            return []
        desc_map = (
            prefs.get("clean_debug", {}).get("descriptions_clean")
            or prefs.get("descriptions_clean")
            or prefs.get("descriptions")
            or {}
        )
        if not isinstance(desc_map, dict):
            desc_map = {}
        style_df = self.df
        if matched_style:
            style_df = style_df[style_df[STYLE_COLUMN] == matched_style]
        def _substring_types(q: str) -> List[str]:
            q_norm = _normalize_item_type_text(q)
            exact, subs = [], []
            for pt in self.unique_item_types:
                pt_norm = _normalize_item_type_text(pt)
                if pt_norm == q_norm:
                    exact.append(pt)
                elif q_norm and (q_norm in pt_norm or pt_norm in q_norm):
                    subs.append(pt)
                elif q.lower() in pt.lower():
                    subs.append(pt)
            return exact or subs
        
        all_recommendations: List[Dict[str, Any]] = []
        
        for raw_item in items_list:
            requested_item = (raw_item or "").strip()
            if not requested_item:
                continue
            substr_types = _substring_types(requested_item)
            matched_item_type = ""
            item_sim = 0.0
            if substr_types:
                candidate_types = substr_types
            else:
                matched_item_type, item_sim = self._match_value(requested_item, self.unique_item_types, self.item_type_embs)
                candidate_types = [matched_item_type] if matched_item_type else []
            item_df = style_df if not candidate_types else style_df[style_df["product_type_name"].isin(candidate_types)]
            if len(item_df) < top_k and candidate_types:
                relaxed = self.df[self.df["product_type_name"].isin(candidate_types)]
                if len(relaxed) > len(item_df):
                    item_df = relaxed
            if item_df.empty:
                continue
            user_desc = (desc_map.get(raw_item) or desc_map.get(requested_item) or "").strip()
            if user_desc:
                texts = item_df.apply(self._build_color_emphasized_text, axis=1).tolist()
                prod_embs = self.model.encode(texts, normalize_embeddings=True)
                q_emb = self._encode(user_desc)
                prod_embs = np.nan_to_num(prod_embs, copy=False)
                q_emb = np.nan_to_num(q_emb, copy=False)
                with np.errstate(over='ignore', invalid='ignore', divide='ignore'):
                    sims = (prod_embs * q_emb).sum(axis=1)
                if not np.all(np.isfinite(sims)):
                    sims = np.nan_to_num(sims, nan=-1.0, posinf=1.0, neginf=-1.0)
                
                # Apply color bonus for outfit items too
                color_bonuses = np.array([self._calculate_color_bonus(user_desc, item_df.iloc[i]) for i in range(len(item_df))])
                enhanced_sims = sims + color_bonuses
                order = np.argsort(-enhanced_sims)
            else:
                sims = np.zeros(len(item_df))
                color_bonuses = np.zeros(len(item_df))
                enhanced_sims = sims
                order = list(range(len(item_df)))
            
            # Get exactly top_k recommendations for THIS item type
            item_recommendations = 0
            for idx in order:
                if item_recommendations >= top_k:
                    break
                row = item_df.iloc[idx]
                base_sim = float(sims[idx]) if user_desc else None
                color_bonus = float(color_bonuses[idx]) if user_desc else 0.0
                final_score = float(enhanced_sims[idx]) if user_desc else None
                
                all_recommendations.append({
                    "article_id": int(row.article_id),  # type: ignore[arg-type]
                    "product_type_name": row.product_type_name,
                    "prod_name": row.get("prod_name", ""),
                    "style": row.get(STYLE_COLUMN, ""),
                    "score": final_score,
                    "style_match_score": style_sim,
                    "item_type_match_score": item_sim if matched_item_type else None,
                    "desc_similarity": base_sim,
                    "color_bonus": color_bonus,  # New field to track color matching
                    "requested_item_type": requested_item,  # Track which user item this was recommended for
                })
                item_recommendations += 1
        
        return all_recommendations

_embed_singleton: Optional[EmbeddingRecommender] = None
_embed_lock = threading.Lock()

def get_embedding_recommender(base_dir: Path) -> EmbeddingRecommender:
    global _embed_singleton
    if _embed_singleton is not None:
        return _embed_singleton
    with _embed_lock:
        if _embed_singleton is None:
            _embed_singleton = EmbeddingRecommender.from_catalog(base_dir)
    return _embed_singleton


def get_recommended_size(user_prefs: Dict[str, Any], base_dir: Path) -> Optional[str]:
    """Get recommended clothing size based on user's body measurements.
    
    Uses a more intelligent approach that considers BMI and height percentiles
    to avoid unrealistic size recommendations from the raw sizing chart.
    
    Args:
        user_prefs: User preferences dictionary containing body measurements
        base_dir: Base directory containing the sizes.csv file
        
    Returns:
        Recommended size string (e.g., 'M', 'L', 'XL') or None if no match found
    """
    try:
        # Load sizes CSV
        sizes_path = base_dir / "sizes.csv"
        if not sizes_path.exists():
            logging.warning(f"Sizes file not found: {sizes_path}")
            return None
            
        sizes_df = pd.read_csv(sizes_path)
        
        # Extract user body measurements
        body = user_prefs.get("body", {})
        age = body.get("age")
        weight_kg = body.get("weight_kg")
        height_cm = body.get("height_cm")
        
        if not all([age, weight_kg, height_cm]):
            logging.warning("Missing body measurements for size recommendation")
            return None
        
        # Calculate BMI for better size determination
        height_m = height_cm / 100
        bmi = weight_kg / (height_m * height_m)
        
        # Filter sizes based on user measurements
        matching_sizes = sizes_df[
            (sizes_df["age_min"] <= age) & (sizes_df["age_max"] >= age) &
            (sizes_df["weight_min_kg"] <= weight_kg) & (sizes_df["weight_max_kg"] >= weight_kg) &
            (sizes_df["height_min_cm"] <= height_cm) & (sizes_df["height_max_cm"] >= height_cm)
        ]
        
        if matching_sizes.empty:
            logging.warning(f"No size match found for age={age}, weight={weight_kg}kg, height={height_cm}cm")
            
            # Fallback: Use height-based sizing for adults when exact match fails
            if 18 <= age <= 64:
                return _get_height_based_size(height_cm, weight_kg, bmi)
            return None
        
        # Check if the recommended size seems reasonable
        recommended_size = matching_sizes.iloc[0]["size"]
        
        # Apply sanity check for adults - prevent unrealistic small sizes for tall people
        if 18 <= age <= 64 and height_cm >= 175:
            if recommended_size in ["XXS", "XS", "S"] and bmi >= 18.5:
                # Person is tall and not underweight, should not get tiny sizes
                if height_cm >= 190:
                    adjusted_size = "L"  # Very tall people get at least L
                else:
                    adjusted_size = "M"  # Tall people get at least M
                logging.info(f"Adjusting size from {recommended_size} to {adjusted_size} for tall person (height={height_cm}cm, BMI={bmi:.1f})")
                return adjusted_size
        
        # Additional check for very tall people
        if height_cm >= 185 and recommended_size in ["XXS", "XS", "S"]:
            # Very tall people should get at least M/L, even if they're light
            if height_cm >= 190:
                adjusted_size = "L"  # Very tall people get L
            else:
                adjusted_size = "L" if bmi >= 22 else "M"
            logging.info(f"Adjusting size from {recommended_size} to {adjusted_size} for very tall person (height={height_cm}cm, BMI={bmi:.1f})")
            return adjusted_size
        
        logging.info(f"Recommended size: {recommended_size} for age={age}, weight={weight_kg}kg, height={height_cm}cm, BMI={bmi:.1f}")
        return str(recommended_size)
        
    except Exception as e:
        logging.error(f"Error getting recommended size: {e}")
        return None


def _get_height_based_size(height_cm: float, weight_kg: float, bmi: float) -> str:
    """Fallback height-based sizing for adults when exact match fails."""
    
    # Height-based sizing with BMI adjustments
    if height_cm >= 190:
        base_size = "XL"
    elif height_cm >= 180:
        base_size = "L"
    elif height_cm >= 170:
        base_size = "M"
    elif height_cm >= 160:
        base_size = "S"
    else:
        base_size = "XS"
    
    # Adjust based on BMI
    if bmi >= 28:  # Higher BMI - size up
        size_order = ["XS", "S", "M", "L", "XL", "XXL"]
        current_idx = size_order.index(base_size) if base_size in size_order else 2
        adjusted_idx = min(len(size_order) - 1, current_idx + 1)
        return size_order[adjusted_idx]
    elif bmi <= 18.5:  # Lower BMI - but not below reasonable minimum for height
        if height_cm >= 175:  # Tall but lean - still need reasonable size
            return "M"
        size_order = ["XS", "S", "M", "L", "XL", "XXL"]
        current_idx = size_order.index(base_size) if base_size in size_order else 2
        adjusted_idx = max(0, current_idx - 1)
        return size_order[adjusted_idx]
    
    return base_size


def extract_recommendation_images(recommendations: List[Dict[str, Any]], base_dir: Path) -> Dict[str, List[Dict[str, str]]]:
    """Extract image paths and product info from recommendations.
    
    Args:
        recommendations: List of recommendation dictionaries with article_id, product_type_name, style
        base_dir: Base directory containing the images folder
        
    Returns:
        Dictionary mapping product_type_name to list of image info dicts:
        {
            "product_type_1": [
                {
                    "image_path": "/path/to/image.jpg",
                    "product_type_name": "T-shirt",
                    "style": "casual",
                    "article_id": "123456",
                    "prod_name": "Cool T-Shirt"
                },
                ...
            ],
            ...
        }
    """
    images_dir = base_dir / "images"
    # Placeholder image path (in main folder)
    placeholder_path = base_dir.parent / "0005720_coming-soon-page_550.jpeg"
    result: Dict[str, List[Dict[str, str]]] = {}
    
    for rec in recommendations:
        article_id_raw = rec.get("article_id", "")
        product_type = rec.get("product_type_name", "Unknown")
        style = rec.get("style", "Unknown")
        prod_name = rec.get("prod_name", "Unknown Product")
        
        if not article_id_raw:
            continue
        
        # Convert to string and handle zero-padding for 10-digit article IDs
        article_id_str = str(article_id_raw)
        if len(article_id_str) == 9:  # Missing leading zero
            article_id_str = "0" + article_id_str
            
        # Look for image file with article_id name (try different extensions)
        image_path = None
        for ext in [".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG"]:
            potential_path = images_dir / f"{article_id_str}{ext}"
            if potential_path.exists():
                image_path = str(potential_path)
                break
        
        # Use placeholder if no image found
        if not image_path:
            if placeholder_path.exists():
                image_path = str(placeholder_path)
            else:
                # Skip this recommendation if even placeholder doesn't exist
                continue
        
        if product_type not in result:
            result[product_type] = []
        
        result[product_type].append({
            "image_path": image_path,
            "product_type_name": product_type,
            "style": style,
            "article_id": article_id_str,
            "prod_name": prod_name
        })
    
    return result
