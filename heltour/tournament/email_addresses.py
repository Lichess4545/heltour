from email_validator import EmailNotValidError, validate_email


def normalized(email: str) -> str:
    try:
        return validate_email(email, check_deliverability=False).normalized
    except EmailNotValidError:
        return ''
