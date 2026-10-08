"""Optional named-entity recognition for person names and addresses (SRS 4.1 / Deep
profile). spaCy is a soft dependency: if it (or the model) is not installed, every
function here degrades to "no NER", so the dependency-free core and the default images
keep working. NER only runs on the Deep scan profile, where recall of free-text names
and addresses matters more than speed.

The model and language are configured by environment:
  PRIVACYMON_NER_MODEL   spaCy model name (default ``en_core_web_sm``; the SRS targets
                         ``en_core_web_trf`` where a GPU is available).
Entity → PrivacyMon category:
  PERSON               -> person_name
  GPE / LOC / FAC      -> address (place/location references)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from .models import Category

# spaCy label → our category.
_LABEL_CATEGORY = {
    "PERSON": Category.PERSON_NAME,
    "GPE": Category.ADDRESS,
    "LOC": Category.ADDRESS,
    "FAC": Category.ADDRESS,
}


@dataclass(frozen=True)
class NerSpan:
    text: str
    label: str
    category: Category


@lru_cache(maxsize=1)
def _load_model():
    """Load and cache the spaCy model, or return None if spaCy/the model is absent.
    Cached so a scan loads the model once. Never raises."""
    model_name = os.getenv("PRIVACYMON_NER_MODEL", "en_core_web_sm")
    try:
        import spacy  # noqa: PLC0415 — optional dependency, imported lazily
    except Exception:  # noqa: BLE001 — spaCy not installed
        return None
    try:
        return spacy.load(model_name, disable=["lemmatizer", "tagger", "parser"])
    except Exception:  # noqa: BLE001 — model not downloaded
        try:
            return spacy.blank("en")  # no NER pipe → yields nothing, but proves availability
        except Exception:  # noqa: BLE001
            return None


def ner_available() -> bool:
    """True when a usable NER model is loaded."""
    nlp = _load_model()
    return nlp is not None and nlp.has_pipe("ner")


def extract_entities(text: str, *, max_chars: int = 100_000) -> list[NerSpan]:
    """Return the PERSON / place entities spaCy finds in ``text`` (deduplicated). Empty
    when NER is unavailable or the text is blank. Never raises."""
    if not text or not text.strip():
        return []
    nlp = _load_model()
    if nlp is None or not nlp.has_pipe("ner"):
        return []
    try:
        doc = nlp(text[:max_chars])
    except Exception:  # noqa: BLE001
        return []
    seen: set[tuple[str, str]] = set()
    out: list[NerSpan] = []
    for ent in doc.ents:
        cat = _LABEL_CATEGORY.get(ent.label_)
        if cat is None:
            continue
        key = (ent.text.strip().lower(), cat.value)
        if key in seen:
            continue
        seen.add(key)
        out.append(NerSpan(text=ent.text.strip(), label=ent.label_, category=cat))
    return out
