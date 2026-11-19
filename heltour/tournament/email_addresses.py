from email_normalize import normalize
from email_validator import EmailNotValidError, validate_email


def normalized(email: str) -> str:
    try:
        address = validate_email(email, check_deliverability=False).normalized
    except EmailNotValidError:
        return ''
    return normalize(address, skip_dns=True).normalized_address
