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


## Removed legacy normalization helpers (TF-IDF era) to keep module minimal.


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
    """Embedding-based recommender per new approach:
    1. Encode catalog style values & product_type_name unique values.
    2. Map user style_clean & single_item_type_clean to closest catalog values by cosine similarity.
    3. Filter dataframe to rows with those exact matched values.
    4. Build per-row product description (concatenate relevant textual cols) and encode.
    5. Encode user description text and rank by cosine similarity.
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

        filt_df = self.df
        if matched_style:
            filt_df = filt_df[filt_df[STYLE_COLUMN] == matched_style]
        if matched_item_type:
            filt_df = filt_df[filt_df["product_type_name"] == matched_item_type]
        if filt_df.empty:
            logging.info("[embed] No rows after filtering; returning empty list.")
            return []

        # Build / encode product texts
        texts = filt_df.apply(self._build_row_text, axis=1).tolist()
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
                })
            return base
        q_emb = self._encode(user_desc)
        prod_embs = np.nan_to_num(prod_embs, copy=False)
        q_emb = np.nan_to_num(q_emb, copy=False)
        with np.errstate(over='ignore', invalid='ignore', divide='ignore'):
            sims = (prod_embs * q_emb).sum(axis=1)
        if not np.all(np.isfinite(sims)):
            sims = np.nan_to_num(sims, nan=-1.0, posinf=1.0, neginf=-1.0)
        order = np.argsort(-sims)[: top_k * 3]
        results: List[Dict[str, Any]] = []
        for i in order:
            row = filt_df.iloc[i]
            desc_sim = float(sims[i])
            results.append({
                "article_id": int(row.article_id),  # type: ignore[arg-type]
                "product_type_name": row.product_type_name,
                "prod_name": row.get("prod_name", ""),
                "style": row.get(STYLE_COLUMN, ""),
                "score": desc_sim,
                "style_match_score": style_sim,
                "item_type_match_score": item_sim,
                "desc_similarity": desc_sim,
            })
            if len(results) >= top_k:
                break
        return results

    # ------------------------------------------------------------------
    # Outfit (multi-item) flow
    # ------------------------------------------------------------------
    def recommend_outfit_from_preferences(self, prefs: Dict[str, Any], top_k: int = 3, include_flattened: bool = False) -> Dict[str, Any]:
        """Per-item outfit recommendations (top_k per requested item) with optional flattened list.

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
            base = {"style": matched_style, "style_match_score": style_sim, "items": {}}
            if include_flattened:
                base["flattened"] = []  # type: ignore[index]
            return base
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
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        flattened: List[Dict[str, Any]] | None = [] if include_flattened else None
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
                grouped[requested_item] = []
                continue
            user_desc = (desc_map.get(raw_item) or desc_map.get(requested_item) or "").strip()
            if user_desc:
                texts = item_df.apply(self._build_row_text, axis=1).tolist()
                prod_embs = self.model.encode(texts, normalize_embeddings=True)
                q_emb = self._encode(user_desc)
                prod_embs = np.nan_to_num(prod_embs, copy=False)
                q_emb = np.nan_to_num(q_emb, copy=False)
                with np.errstate(over='ignore', invalid='ignore', divide='ignore'):
                    sims = (prod_embs * q_emb).sum(axis=1)
                if not np.all(np.isfinite(sims)):
                    sims = np.nan_to_num(sims, nan=-1.0, posinf=1.0, neginf=-1.0)
                order = np.argsort(-sims)
            else:
                sims = np.zeros(len(item_df))
                order = list(range(len(item_df)))
            recs: List[Dict[str, Any]] = []
            for idx in order:
                row = item_df.iloc[idx]
                recs.append({
                    "requested_item": requested_item,
                    "article_id": int(row.article_id),  # type: ignore[arg-type]
                    "product_type_name": row.product_type_name,
                    "prod_name": row.get("prod_name", ""),
                    "style": row.get(STYLE_COLUMN, ""),
                    "score": float(sims[idx]) if user_desc else None,
                    "style_match_score": style_sim,
                    "item_type_match_score": item_sim if matched_item_type else None,
                    "desc_similarity": float(sims[idx]) if user_desc else None,
                })
                if len(recs) >= top_k:
                    break
            grouped[requested_item] = recs
            if include_flattened and flattened is not None:
                flattened.extend(recs)
        result: Dict[str, Any] = {"style": matched_style, "style_match_score": style_sim, "items": grouped}
        if include_flattened and flattened is not None:
            result["flattened"] = flattened
        return result

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
