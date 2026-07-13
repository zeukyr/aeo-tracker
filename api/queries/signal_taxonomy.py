"""
Signal taxonomy normalization (Phase 7, item 0 of
docs/ai/recommendation-deterministic-signals-todo.md).

`concerns_raised` and `win_reasons` are free-text arrays - "limited hands-on
training" and "not enough practical experience" count as two different rows,
which makes them impossible to template recommendations from or to measure
over time. This module classifies each raw string into a small curated
taxonomy (api/knowledge/concern_taxonomy.json / win_reason_taxonomy.json):

  1. deterministic keyword rules, applied in taxonomy order (first hit wins -
     specific vocabularies like accreditation run before broad ones like
     employer_recognition);
  2. LLM fallback for strings no rule matches;
  3. every classification cached per raw string in
     api/knowledge/signal_classifications.json, so a string is classified once.

Stable types are also what the closed-loop diff-in-diff measures: "did the
practical_hands_on concern's frequency drop after the rec shipped?" is only
answerable over a fixed vocabulary.
"""

import os
import re
import json

from src.logger import logger

_DIR = os.path.join(os.path.dirname(__file__), "..", "knowledge")
_CONCERN_TAXONOMY_PATH = os.path.join(_DIR, "concern_taxonomy.json")
_WIN_TAXONOMY_PATH = os.path.join(_DIR, "win_reason_taxonomy.json")
_CLASSIFICATION_CACHE_PATH = os.path.join(_DIR, "signal_classifications.json")

_taxonomies = {}


def load_taxonomy(kind):
    """kind: 'concern' | 'win_reason'. Compiled patterns cached per process."""
    if kind not in _taxonomies:
        path = _CONCERN_TAXONOMY_PATH if kind == "concern" else _WIN_TAXONOMY_PATH
        with open(path, "r", encoding="utf-8") as f:
            types = json.load(f)["types"]
        for t in types:
            t["_regex"] = re.compile("|".join(t["patterns"]), re.I)
        _taxonomies[kind] = types
    return _taxonomies[kind]


def concern_type(type_id):
    """The taxonomy entry for one concern type id (None if unknown)."""
    return next((t for t in load_taxonomy("concern") if t["id"] == type_id), None)


def _load_class_cache():
    try:
        with open(_CLASSIFICATION_CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"concern": {}, "win_reason": {}}


def _save_class_cache(cache):
    with open(_CLASSIFICATION_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=1, ensure_ascii=False)


def _classify_llm(raw, kind, types):
    """LLM fallback for strings no keyword rule matches. 'other' on failure."""
    import os as _os
    from openai import OpenAI
    client = OpenAI(api_key=_os.getenv("OPENAI_API_KEY"))
    ids = [t["id"] for t in types]
    menu = "\n".join(f'- "{t["id"]}": {t["label"]}' for t in types)
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=30,
            messages=[
                {"role": "system", "content": "You classify short phrases. Respond with valid JSON only."},
                {"role": "user", "content":
                    f'Classify this {kind.replace("_", " ")} raised about an online school '
                    f'into exactly one type:\n{menu}\n- "other": none fit\n\n'
                    f'PHRASE: {raw}\n\nReturn JSON: {{"type": "<id>"}}'},
            ],
            response_format={"type": "json_object"},
        )
        t = json.loads(resp.choices[0].message.content).get("type")
        return t if t in ids else "other"
    except Exception as e:
        logger.warning(f"Signal classification LLM fallback failed for {raw[:60]!r}: {e}")
        return "other"


def classify(raw, kind):
    """Type id for one raw string: rules -> LLM fallback -> cached."""
    raw = (raw or "").strip()
    if not raw:
        return "other"
    cache = _load_class_cache()
    hit = cache.get(kind, {}).get(raw)
    if hit:
        return hit

    types = load_taxonomy(kind)
    result = next((t["id"] for t in types if t["_regex"].search(raw)), None)
    if result is None:
        result = _classify_llm(raw, kind, types)

    cache.setdefault(kind, {})[raw] = result
    _save_class_cache(cache)
    return result


def classify_concern(raw):
    return classify(raw, "concern")


def classify_win_reason(raw):
    return classify(raw, "win_reason")


if __name__ == "__main__":
    import io, sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    from api.db import get_connection
    from collections import Counter
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT unnest(concerns_raised) FROM sentiment_responses")
            concerns = [r[0] for r in cur.fetchall()]
            cur.execute("SELECT unnest(win_reasons) FROM mention_responses")
            wins = [r[0] for r in cur.fetchall()]
    cc = Counter(classify_concern(c) for c in concerns)
    wc = Counter(classify_win_reason(w) for w in wins)
    print("concern types:", json.dumps(cc, indent=1))
    print("win reason types:", json.dumps(wc, indent=1))
