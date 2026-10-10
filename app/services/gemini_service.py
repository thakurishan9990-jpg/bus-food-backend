import google.generativeai as genai

from app.config import settings

FALLBACK_SUMMARY = "Reviews unavailable right now — showing Google rating only."
MODEL_NAME = "gemini-1.5-flash"


def summarize_reviews(dhaba_name: str, raw_reviews: list[dict]) -> str:
    """Summarize a dhaba's Google reviews into a short, honest blurb, e.g.

    "Good food, weak hygiene" or "Fast service, limited veg options".
    Falls back to a static message if Gemini is unavailable or returns nothing.
    """
    if not settings.gemini_api_key or not raw_reviews:
        return FALLBACK_SUMMARY

    review_texts = [r.get("text", "") for r in raw_reviews if r.get("text")]
    if not review_texts:
        return FALLBACK_SUMMARY

    prompt = (
        f"Summarize these customer reviews for a highway dhaba called '{dhaba_name}' "
        "in 1 short sentence (max 10 words), covering food quality and any recurring "
        "complaints (e.g. hygiene, wait time). Be blunt and specific, not generic.\n\n"
        + "\n---\n".join(review_texts[:10])
    )

    try:
        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel(MODEL_NAME)
        response = model.generate_content(prompt)
        summary = (response.text or "").strip()
        return summary or FALLBACK_SUMMARY
    except Exception:
        return FALLBACK_SUMMARY
