from models.schemas import QAResult, CISOGate

MAX_AUTO_RETRIES = 3
CRITIC_AT_RETRY = 3
HUMAN_AT_RETRY = 5
IMMEDIATE_HUMAN_SEVERITIES = {"critical"}


def should_auto_retry(retry_count: int, qa: QAResult) -> bool:
    """True when QA failed and we're within auto-retry window."""
    if qa.status == "pass":
        return False
    return retry_count < MAX_AUTO_RETRIES


def should_escalate_critic(retry_count: int) -> bool:
    """True when we've exhausted auto-retries and Critic hasn't reviewed yet."""
    return retry_count == CRITIC_AT_RETRY


def should_escalate_human(retry_count: int) -> bool:
    """True when Critic-assisted retry also failed."""
    return retry_count >= HUMAN_AT_RETRY


def is_immediate_human(ciso: CISOGate) -> bool:
    """True when CISO found a critical severity finding — skip retry entirely."""
    return any(
        getattr(f, "severity", "").lower() in IMMEDIATE_HUMAN_SEVERITIES
        for f in (ciso.findings or [])
    )


def build_retry_context(qa: QAResult, memory_hits: list[dict]) -> str:
    """
    Formats QA failures + memory hints into a string injected into the
    Dev agent's next prompt. Called by DeveloperAgent._build_prompt().
    """
    parts = ["--- QA FAILURES TO FIX (fix ONLY these, touch nothing else) ---"]

    for f in (qa.failures or []):
        name = getattr(f, "name", None) or getattr(f, "test", "unknown")
        error = getattr(f, "error", "no error message")
        severity = getattr(f, "severity", "unknown")
        location = getattr(f, "location", None) or getattr(f, "file", "unknown")
        parts.append(f"FAIL [{severity.upper()}]: {name}")
        parts.append(f"  Error:    {error}")
        parts.append(f"  Location: {location}")

    if memory_hits:
        parts.append("\n--- RELEVANT PAST KNOWLEDGE (consider these hints) ---")
        for hit in memory_hits:
            score = hit.get("score", 0)
            content = hit.get("content", "")
            parts.append(f"[{score:.0%}] {content}")

    return "\n".join(parts)
