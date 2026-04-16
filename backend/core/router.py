import logging

from core.retry import (
    should_auto_retry,
    should_escalate_critic,
    should_escalate_human,
    is_immediate_human,
)

logger = logging.getLogger(__name__)


def route_after_qa(state) -> str:
    task = state["task"]
    qa = task.qa_result

    if qa is None:
        logger.info("EDGE ROUTING from qa: returning 'escalate_human' (qa_result is None)")
        return "escalate_human"

    if qa.status == "pass" and getattr(qa, "acceptance_met", True):
        logger.info("EDGE ROUTING from qa: returning 'ciso' (tests passed)")
        return "ciso"

    if should_auto_retry(task.retry_count, qa):
        logger.info("EDGE ROUTING from qa: returning 'developer' (auto-retry)")
        return "developer"

    if should_escalate_critic(task.retry_count):
        logger.info("EDGE ROUTING from qa: returning 'critic'")
        return "critic"

    logger.info("EDGE ROUTING from qa: returning 'escalate_human' (max retries)")
    return "escalate_human"


def route_after_ciso(state) -> str:
    task = state["task"]
    gate = task.ciso_gate

    if gate is None:
        logger.info("EDGE ROUTING from ciso: returning 'escalate_human' (ciso_gate is None)")
        return "escalate_human"

    decision = getattr(gate, "decision", None) or (
        "block" if getattr(gate, "blocked", False) else "approve"
    )

    if decision == "approve":
        logger.info("EDGE ROUTING from ciso: returning 'deploy' (approved)")
        return "deploy"

    if is_immediate_human(gate):
        logger.info("EDGE ROUTING from ciso: returning 'escalate_human' (immediate human)")
        return "escalate_human"

    logger.info("EDGE ROUTING from ciso: returning 'developer' (security rejected)")
    return "developer"


def route_after_critic(state) -> str:
    task = state["task"]
    critic = task.critic_output

    if should_escalate_human(task.retry_count):
        logger.info("EDGE ROUTING from critic: returning 'escalate_human'")
        return "escalate_human"

    if critic and getattr(critic, "approved", False):
        logger.info("EDGE ROUTING from critic: returning 'deploy' (critic approved)")
        return "deploy"

    logger.info("EDGE ROUTING from critic: returning 'developer'")
    return "developer"


def route_after_ceo(state) -> str:
    """
    If CEO set approved=False, escalate to human immediately.
    Otherwise proceed to CTO.
    """
    task = state["task"]
    if not task.ceo_approved:
        logger.info("EDGE ROUTING from ceo: returning 'escalate_human' (not approved)")
        return "escalate_human"
    logger.info("EDGE ROUTING from ceo: returning 'cto'")
    return "cto"


def route_after_tl_review(state) -> str:
    """
    TL Review runs after Developer.
    - approved -> qa
    - rejected + count < MAX -> developer (with tl_review_feedback injected)
    - rejected + count >= MAX -> escalate_human
    """
    from core.retry import should_escalate_tl_review
    task = state["task"]

    tl = task.team_leader_output
    approved = getattr(tl, "review_approved", True) if tl else True

    if approved:
        logger.info("EDGE ROUTING from tl_review: returning 'qa' (approved)")
        return "qa"

    if should_escalate_tl_review(task.tl_review_count):
        logger.info("EDGE ROUTING from tl_review: returning 'escalate_human' (max tl retries)")
        return "escalate_human"

    logger.info("EDGE ROUTING from tl_review: returning 'developer' (rejected, retrying)")
    return "developer"


def route_after_tl_final(state) -> str:
    """
    TL Final runs after DevOps.
    - approved -> write_memory -> END
    - rejected + count < MAX -> developer (with tl_final_feedback)
    - rejected + count >= MAX -> escalate_human
    """
    from core.retry import should_escalate_tl_final
    task = state["task"]

    tl = task.team_leader_output
    approved = getattr(tl, "final_approved", True) if tl else True

    if approved:
        logger.info("EDGE ROUTING from tl_final: returning 'write_memory' (approved)")
        return "write_memory"

    if should_escalate_tl_final(task.tl_final_count):
        logger.info("EDGE ROUTING from tl_final: returning 'escalate_human' (max final retries)")
        return "escalate_human"

    logger.info("EDGE ROUTING from tl_final: returning 'developer' (rejected, retrying)")
    return "developer"
