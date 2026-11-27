"""Layer 1: fetch and validate ticket input for the support triage agent."""

import json
import time
from collections.abc import Mapping
from typing import Any, Callable

import requests


def fetch_with_retry(
    url: str,
    max_retries: int = 3,
    timeout: float = 5.0,
    backoff_factor: float = 1.0,
) -> Any:
    """Fetch JSON, retrying timeouts and HTTP 429/5xx responses.

    ``max_retries`` is the maximum number of total attempts, including the
    initial request.
    """
    if max_retries < 1:
        raise ValueError("max_retries must be at least 1")
    if timeout <= 0:
        raise ValueError("timeout must be greater than 0")
    if backoff_factor < 0:
        raise ValueError("backoff_factor cannot be negative")

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, timeout=timeout)
        except requests.Timeout:
            if attempt == max_retries:
                raise
        else:
            status = response.status_code
            is_retryable_status = status == 429 or 500 <= status <= 599

            if is_retryable_status:
                if attempt == max_retries:
                    response.raise_for_status()
            else:
                response.raise_for_status()
                try:
                    return response.json()
                except requests.exceptions.JSONDecodeError as exc:
                    raise ValueError("API response was not valid JSON") from exc

        time.sleep(backoff_factor * (2 ** (attempt - 1)))

    raise RuntimeError("Request retry loop ended unexpectedly")


def build_layer1_input(
    ticket_payload: object,
    operational_context: object,
) -> dict[str, object]:
    """Validate and normalize the ticket and operational context.

    Invalid input is returned with ``input_valid=False`` and validation
    messages so the decision layer can safely choose ``hold_for_review``.
    """
    errors: list[str] = []

    if not isinstance(ticket_payload, Mapping):
        ticket: Mapping[str, object] = {}
        errors.append("ticket payload must be a JSON object")
    else:
        ticket = ticket_payload

    if not isinstance(operational_context, Mapping):
        context: Mapping[str, object] = {}
        errors.append("operational context must be a JSON object")
    else:
        context = operational_context

    ticket_id = ticket.get("ticket_id")
    if not isinstance(ticket_id, str) or not ticket_id.strip():
        errors.append("ticket_id must be a non-empty string")
        ticket_id = None

    customer_tier = ticket.get("customer_tier")
    if not isinstance(customer_tier, str) or customer_tier not in {
        "free",
        "pro",
        "enterprise",
    }:
        errors.append("customer_tier must be free, pro, or enterprise")
        customer_tier = None

    message = ticket.get("message")
    if not isinstance(message, str) or not message.strip():
        errors.append("message must be a non-empty string")
        message = None

    open_tickets_count = ticket.get("open_tickets_count")
    if type(open_tickets_count) is not int or open_tickets_count < 0:
        errors.append("open_tickets_count must be a non-negative integer")
        open_tickets_count = None

    on_call_engineer_available = context.get("on_call_engineer_available")
    if type(on_call_engineer_available) is not bool:
        errors.append("on_call_engineer_available must be a boolean")
        on_call_engineer_available = None

    is_maintenance_window = context.get("is_maintenance_window")
    if type(is_maintenance_window) is not bool:
        errors.append("is_maintenance_window must be a boolean")
        is_maintenance_window = None

    return {
        "ticket_id": ticket_id,
        "customer_tier": customer_tier,
        "message": message,
        "open_tickets_count": open_tickets_count,
        "on_call_engineer_available": on_call_engineer_available,
        "is_maintenance_window": is_maintenance_window,
        "input_valid": not errors,
        "validation_errors": errors,
    }


def describe_ticket(
    layer1_input: object,
    extractor: Callable[[str], object],
) -> dict[str, object]:
    """Extract structured issue signals without making a routing decision."""
    errors: list[object] = []
    if isinstance(layer1_input, Mapping):
        inherited_errors = layer1_input.get("validation_errors", [])
        if isinstance(inherited_errors, list):
            errors.extend(inherited_errors)
        elif inherited_errors:
            errors.append("validation_errors must be a list")
    else:
        errors.append("layer 1 input must be an object")

    def fallback() -> dict[str, object]:
        return {
            "issue_type": None,
            "sentiment": None,
            "affects_production": None,
            "validation_errors": errors,
        }

    if not isinstance(layer1_input, Mapping):
        return fallback()
    if layer1_input.get("input_valid") is not True:
        if not errors:
            errors.append("input_valid must be true")
        return fallback()

    message = layer1_input.get("message")
    if not isinstance(message, str) or not message.strip():
        errors.append("message must be a non-empty string")
        return fallback()

    try:
        raw_result = extractor(message)
    except Exception as exc:
        errors.append(f"extractor failed: {type(exc).__name__}")
        return fallback()

    if isinstance(raw_result, str):
        try:
            result = json.loads(raw_result)
        except json.JSONDecodeError:
            errors.append("extractor output was not valid JSON")
            return fallback()
    else:
        result = raw_result

    expected_fields = {"issue_type", "sentiment", "affects_production"}
    if not isinstance(result, Mapping) or set(result) != expected_fields:
        errors.append("extractor output must contain exactly the required signal fields")
        return fallback()

    issue_type = result["issue_type"]
    sentiment = result["sentiment"]
    affects_production = result["affects_production"]
    if not isinstance(issue_type, str) or issue_type not in {
        "outage",
        "billing",
        "bug",
        "how_to",
    }:
        errors.append("issue_type must be outage, billing, bug, or how_to")
    if not isinstance(sentiment, str) or sentiment not in {
        "angry",
        "neutral",
        "calm",
    }:
        errors.append("sentiment must be angry, neutral, or calm")
    if type(affects_production) is not bool:
        errors.append("affects_production must be a boolean")

    if errors:
        return fallback()

    return {
        "issue_type": issue_type,
        "sentiment": sentiment,
        "affects_production": affects_production,
        "validation_errors": errors,
    }


def decide_action(
    description: object,
    context: object,
    customer_tier: object,
) -> dict[str, object]:
    """Apply deterministic routing rules to validated signals and context."""
    hold_for_review = {
        "action": "hold_for_review",
        "backup_alert": False,
    }

    if not isinstance(description, Mapping) or not isinstance(context, Mapping):
        return hold_for_review

    if description.get("input_valid", True) is not True:
        return hold_for_review

    validation_errors = description.get("validation_errors", [])
    if not isinstance(validation_errors, list) or validation_errors:
        return hold_for_review

    issue_type = description.get("issue_type")
    sentiment = description.get("sentiment")
    affects_production = description.get("affects_production")
    on_call_engineer_available = context.get("on_call_engineer_available")
    is_maintenance_window = context.get("is_maintenance_window")

    if not isinstance(customer_tier, str) or customer_tier not in {
        "free",
        "pro",
        "enterprise",
    }:
        return hold_for_review
    if not isinstance(issue_type, str) or issue_type not in {
        "outage",
        "billing",
        "bug",
        "how_to",
    }:
        return hold_for_review
    if not isinstance(sentiment, str) or sentiment not in {
        "angry",
        "neutral",
        "calm",
    }:
        return hold_for_review
    if type(affects_production) is not bool:
        return hold_for_review
    if type(on_call_engineer_available) is not bool:
        return hold_for_review
    if type(is_maintenance_window) is not bool:
        return hold_for_review

    if (
        customer_tier == "enterprise"
        and affects_production is True
        and issue_type == "outage"
    ):
        return {
            "action": "escalate_urgent",
            "backup_alert": not on_call_engineer_available,
        }

    if issue_type == "how_to" and sentiment != "angry":
        return {
            "action": "auto_reply_faq",
            "backup_alert": False,
        }

    if is_maintenance_window is True and issue_type == "bug":
        return hold_for_review

    return {
        "action": "assign_engineering",
        "backup_alert": False,
    }


def execute_action(
    decision: dict,
    ticket_id: str | None,
) -> dict:
    """Create an audit/output record for a routing decision."""
    clean_ticket_id = (
        ticket_id if isinstance(ticket_id, str) and ticket_id.strip() else None
    )

    def failed_output(reason: str) -> dict:
        return {
            "ticket_id": clean_ticket_id,
            "action": "hold_for_review",
            "backup_alert": False,
            "reason": reason,
            "status": "failed",
            "summary": f"Ticket {clean_ticket_id or '(unknown ID)'}: {reason} Status: failed.",
        }

    if ticket_id is not None and clean_ticket_id is None:
        return failed_output("Invalid ticket_id; no action was dispatched.")
    if not isinstance(decision, Mapping):
        return failed_output("Invalid decision object; no action was dispatched.")

    action = decision.get("action")
    backup_alert = decision.get("backup_alert")
    valid_actions = {
        "escalate_urgent",
        "assign_engineering",
        "auto_reply_faq",
        "hold_for_review",
    }
    if (
        not isinstance(action, str)
        or action not in valid_actions
        or type(backup_alert) is not bool
        or (backup_alert and action != "escalate_urgent")
    ):
        return failed_output("Invalid decision fields; no action was dispatched.")
    if clean_ticket_id is None and action != "hold_for_review":
        return failed_output("Missing ticket_id; no action was dispatched.")

    default_reasons = {
        "escalate_urgent": "Enterprise production outage requires urgent escalation.",
        "assign_engineering": "Ticket was assigned to engineering.",
        "auto_reply_faq": "Non-angry how-to request was routed to the FAQ response.",
        "hold_for_review": "Ticket requires human review.",
    }
    reason = decision.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        reason = default_reasons[action]
    if backup_alert:
        reason = f"{reason} Backup alert required because no on-call engineer is available."

    status = "held" if action == "hold_for_review" else "ok"
    ticket_label = clean_ticket_id or "(unknown ID)"
    return {
        "ticket_id": clean_ticket_id,
        "action": action,
        "backup_alert": backup_alert,
        "reason": reason,
        "status": status,
        "summary": f"Ticket {ticket_label}: {reason} Status: {status}.",
    }


def run_triage_agent(
    raw_payload: dict,
    context: dict,
    extractor: Callable[[str], object] | None = None,
) -> dict:
    """Run input validation, signal extraction, decision, and audit output.

    Supply the model-backed extractor from Layer 2. If none is configured,
    valid tickets safely fall back to review with the extraction failure recorded.
    """
    layer1_input = build_layer1_input(raw_payload, context)

    if extractor is None:
        def missing_extractor(_: str) -> object:
            raise RuntimeError("No ticket extractor configured")

        active_extractor = missing_extractor
    else:
        active_extractor = extractor

    description = describe_ticket(layer1_input, active_extractor)
    decision = decide_action(
        description,
        context,
        layer1_input.get("customer_tier"),
    )

    validation_errors = description.get("validation_errors", [])
    if decision.get("action") == "hold_for_review" and validation_errors:
        decision["reason"] = "Review required: " + "; ".join(
            str(error) for error in validation_errors
        )

    ticket_id = layer1_input.get("ticket_id")
    clean_ticket_id = ticket_id if isinstance(ticket_id, str) else None
    return execute_action(decision, clean_ticket_id)


if __name__ == "__main__":
    def sample_extractor(_: str) -> str:
        return json.dumps(
            {
                "issue_type": "bug",
                "sentiment": "neutral",
                "affects_production": True,
            }
        )

    valid_input = build_layer1_input(
        {
            "ticket_id": "T-100",
            "customer_tier": "pro",
            "message": "The dashboard crashes when I export a report.",
            "open_tickets_count": 1,
        },
        {
            "on_call_engineer_available": True,
            "is_maintenance_window": False,
        },
    )
    invalid_input = build_layer1_input(
        {
            "ticket_id": "T-101",
            "customer_tier": "free",
            "message": "",
            "open_tickets_count": 0,
        },
        {
            "on_call_engineer_available": True,
            "is_maintenance_window": False,
        },
    )

    print("Valid input:", describe_ticket(valid_input, sample_extractor))
    print("Invalid input:", describe_ticket(invalid_input, sample_extractor))

    outage_message = "The production API is completely unavailable."
    outage_description = describe_ticket(
        {**valid_input, "message": outage_message},
        lambda _: json.dumps(
            {
                "issue_type": "outage",
                "sentiment": "angry",
                "affects_production": True,
            }
        ),
    )
    enterprise_outage = decide_action(
        outage_description,
        {
            "on_call_engineer_available": True,
            "is_maintenance_window": False,
        },
        "enterprise",
    )
    pro_outage = decide_action(
        outage_description,
        {
            "on_call_engineer_available": True,
            "is_maintenance_window": False,
        },
        "pro",
    )
    assert enterprise_outage["action"] == "escalate_urgent"
    assert pro_outage["action"] == "assign_engineering"
    print(
        f"Same outage message, enterprise vs pro: "
        f"{enterprise_outage['action']} vs {pro_outage['action']}"
    )

    bug_message = "The report export button fails."
    bug_description = describe_ticket(
        {**valid_input, "message": bug_message},
        lambda _: json.dumps(
            {
                "issue_type": "bug",
                "sentiment": "neutral",
                "affects_production": False,
            }
        ),
    )
    outside_maintenance = decide_action(
        bug_description,
        {
            "on_call_engineer_available": True,
            "is_maintenance_window": False,
        },
        "pro",
    )
    during_maintenance = decide_action(
        bug_description,
        {
            "on_call_engineer_available": True,
            "is_maintenance_window": True,
        },
        "pro",
    )
    assert outside_maintenance["action"] == "assign_engineering"
    assert during_maintenance["action"] == "hold_for_review"
    print(
        f"Same bug message, maintenance off vs on: "
        f"{outside_maintenance['action']} vs {during_maintenance['action']}"
    )

    invalid_description = {
        **outage_description,
        "input_valid": False,
    }
    assert decide_action(
        invalid_description,
        {
            "on_call_engineer_available": False,
            "is_maintenance_window": False,
        },
        "enterprise",
    ) == {"action": "hold_for_review", "backup_alert": False}

    def extractor_for(
        issue_type: str,
        sentiment: str,
        affects_production: bool,
    ) -> Callable[[str], str]:
        signals = {
            "issue_type": issue_type,
            "sentiment": sentiment,
            "affects_production": affects_production,
        }
        return lambda _: json.dumps(signals)

    outage_payload = {
        "ticket_id": "T-200",
        "customer_tier": "enterprise",
        "message": "The production API is completely unavailable.",
        "open_tickets_count": 0,
    }
    outage_extractor = extractor_for("outage", "angry", True)
    urgent_with_on_call = run_triage_agent(
        outage_payload,
        {
            "on_call_engineer_available": True,
            "is_maintenance_window": False,
        },
        outage_extractor,
    )
    urgent_without_on_call = run_triage_agent(
        outage_payload,
        {
            "on_call_engineer_available": False,
            "is_maintenance_window": False,
        },
        outage_extractor,
    )
    assert urgent_with_on_call["action"] == "escalate_urgent"
    assert urgent_with_on_call["backup_alert"] is False
    assert urgent_with_on_call["status"] == "ok"
    assert urgent_without_on_call["action"] == "escalate_urgent"
    assert urgent_without_on_call["backup_alert"] is True
    assert urgent_without_on_call["status"] == "ok"

    how_to_result = run_triage_agent(
        {
            "ticket_id": "T-201",
            "customer_tier": "free",
            "message": "How do I reset my password?",
            "open_tickets_count": 0,
        },
        {
            "on_call_engineer_available": True,
            "is_maintenance_window": False,
        },
        extractor_for("how_to", "calm", False),
    )
    assert how_to_result["action"] == "auto_reply_faq"
    assert how_to_result["status"] == "ok"

    maintenance_bug_result = run_triage_agent(
        {
            "ticket_id": "T-202",
            "customer_tier": "pro",
            "message": "The report export button fails.",
            "open_tickets_count": 0,
        },
        {
            "on_call_engineer_available": True,
            "is_maintenance_window": True,
        },
        extractor_for("bug", "neutral", False),
    )
    assert maintenance_bug_result["action"] == "hold_for_review"
    assert maintenance_bug_result["status"] == "held"

    malformed_result = run_triage_agent({}, {}, outage_extractor)
    assert malformed_result["ticket_id"] is None
    assert malformed_result["action"] == "hold_for_review"
    assert malformed_result["backup_alert"] is False
    assert malformed_result["status"] == "held"
    print("Layer 4 end-to-end assertions passed.")