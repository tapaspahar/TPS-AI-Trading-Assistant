"""One friendly, consistent voice for user-facing TPS guidance."""

ASSISTANT_NAME = "Cutie"


def cutie_says(message: str) -> str:
    return f"{ASSISTANT_NAME} keh rahi hai: {message}"
