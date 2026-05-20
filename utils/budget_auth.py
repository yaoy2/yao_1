import hmac
import os


def _clean_password(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _read_mapping_value(mapping, key, *, clean=True):
    if mapping is None:
        return None
    try:
        value = mapping.get(key)
    except Exception:
        try:
            value = mapping[key]
        except Exception:
            return None
    if clean:
        return _clean_password(value)
    return value


def get_budget_password(secrets=None, environ=None):
    environ = os.environ if environ is None else environ

    for key in ("budget_password", "BUDGET_PASSWORD"):
        password = _read_mapping_value(secrets, key)
        if password:
            return password

    budget_section = _read_mapping_value(secrets, "budget", clean=False)
    if budget_section is not None:
        password = _read_mapping_value(budget_section, "password")
        if password:
            return password

    return _read_mapping_value(environ, "BUDGET_PASSWORD")


def is_budget_password_valid(input_password, configured_password):
    input_password = _clean_password(input_password)
    configured_password = _clean_password(configured_password)
    if not input_password or not configured_password:
        return False
    return hmac.compare_digest(input_password, configured_password)
