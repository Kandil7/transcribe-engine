"""Pure-stdlib Arabic normalization for transcript_norm (v1).

Bump NORM_VERSION whenever the fold changes so mixed-version rows stay
identifiable via VideoRecord.norm_version. Norm is for retrieval; keep
transcript_raw verbatim for ASR training.
"""

import re
import unicodedata

NORM_VERSION = "v1"

_ALEF = re.compile("[آأإٱ]")
_TATWEEL = "ـ"
_DIACRITICS = re.compile("[\u064b-\u065f\u0670]")
_EASTERN_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def normalize_ar(text: str) -> str:
    """Fold orthographic variants irrelevant to transcription quality."""
    t = unicodedata.normalize("NFKC", text)
    t = _ALEF.sub("ا", t)
    t = t.replace("ؤ", "و").replace("ئ", "ي").replace("ء", "")
    t = t.replace("ى", "ي").replace("ة", "ه")
    t = t.replace("ک", "ك").replace("ی", "ي").replace("پ", "ب").replace("ڤ", "ف")
    t = t.replace(_TATWEEL, "")
    t = _DIACRITICS.sub("", t)
    t = t.translate(_EASTERN_DIGITS)
    t = re.sub(r"\s+", " ", t).strip()
    return t
