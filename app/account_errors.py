"""Account access failures are distinct from individual publication failures."""
import json
import re


def account_access_failed(error: Exception, *, verification: bool = False) -> bool:
    message = str(getattr(error, "detail", error))
    payload = None
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", message):
        try:
            value, _ = decoder.raw_decode(message[match.start():])
        except ValueError:
            continue
        if isinstance(value, dict):
            candidate = value.get("error", value)
            if isinstance(candidate, dict) and "code" in candidate:
                payload = candidate
                break
    lower = message.lower()
    # Temporary API failures must never cancel an account's entire agenda.
    if (payload and payload.get("is_transient") is True) or re.search(r'''["']is_transient["']\s*:\s*true''', lower):
        return False
    if payload:
        try:
            code = int(payload.get("code"))
            subcode = int(payload.get("error_subcode", 0))
        except (ValueError, TypeError):
            return False
        if subcode == 2207032:
            return False
        # 190: access token invalid; 102: invalid/expired session.
        if code in (190, 102):
            return True
        # Only the account verification endpoint establishes account-level
        # permission failure. A publish endpoint can reject a specific object.
        if verification and code in (10, 200):
            return True
        # OAuthException is an error family, not proof of an invalid token.
        return False
    if re.search(r'''\b(?:code|código)["']?\s*[:= ]\s*(?:190|102)\b''', lower):
        return True
    return any(phrase in lower for phrase in (
        "invalid access token", "invalid token", "error validating access token",
        "access token has expired", "access token expired", "session has expired",
        "checkpoint required", "checkpoint_required", "account has been disabled",
    ))
