"""
brands.py

Canonical brand names. The LLM extractor stores competitor names verbatim
("Penn Foster's Pet Grooming Certificate", "pennfoster.edu", ...), which
fragments per-brand counts across spelling variants. The brand registry
(api/knowledge/brand_registry.json, built by scripts/build_brand_registry.py)
maps every reviewed variant to one canonical name; canonicalize() applies
that map, falling back to the raw name for brands the registry hasn't seen.

Aggregations should group by mention_response_brands.canonical_name (set at
insert time from here, backfilled by migrations/backfill_canonical_names.py).
brand_name keeps the verbatim string so the registry can be rebuilt from it.
"""

import json
import os

from src.logger import logger

REGISTRY_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "api", "knowledge", "brand_registry.json")

_variant_map = None


def variant_map():
    """{lowercased variant: canonical name} from the registry; {} if missing."""
    global _variant_map
    if _variant_map is None:
        try:
            with open(REGISTRY_PATH, encoding="utf-8") as f:
                registry = json.load(f)
            _variant_map = {
                variant.strip().lower(): brand["name"]
                for brand in registry.get("brands", [])
                for variant in brand.get("variants", [])
            }
        except (OSError, json.JSONDecodeError, KeyError) as e:
            logger.warning(f"brand_registry.json unreadable ({e}) — falling back to raw brand names")
            _variant_map = {}
    return _variant_map


def canonicalize(brand_name):
    if not brand_name:
        return brand_name
    name = brand_name.strip()
    return variant_map().get(name.lower(), name)
