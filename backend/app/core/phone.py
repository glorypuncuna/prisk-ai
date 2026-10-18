import re

# Mapping of common dialing codes to ISO 3166-1 alpha-2 region codes
DIALING_CODE_TO_REGION: dict[str, str] = {
    "+1": "US",
    "+44": "GB",
    "+61": "AU",
    "+62": "ID",
    "+65": "SG",
    "+60": "MY",
    "+63": "PH",
    "+66": "TH",
    "+81": "JP",
    "+82": "KR",
    "+84": "VN",
    "+91": "IN",
    "+49": "DE",
    "+33": "FR",
    "+31": "NL",
}

REGION_TO_DIALING_CODE: dict[str, str] = {v: k for k, v in DIALING_CODE_TO_REGION.items()}


def normalize_e164_phone(phone_number: str, country_code: str = "ID") -> str:
    """Validate and format a phone number into strict E.164 format (`+[country][subscriber]`).

    Uses Google's `phonenumbers` library when available, with strict E.164 validation.
    Raises ValueError if the phone number cannot be parsed or is not a valid subscriber number.
    """
    raw_phone = (phone_number or "").strip()
    raw_country = (country_code or "ID").strip().upper()

    if not raw_phone:
        raise ValueError("Phone number is required and must be a valid E.164 phone number")

    region = DIALING_CODE_TO_REGION.get(raw_country, raw_country)
    if not re.fullmatch(r"[A-Z]{2}", region):
        region = "ID"

    try:
        import phonenumbers  # type: ignore[import-untyped]

        parsed = phonenumbers.parse(raw_phone, region)
        if not phonenumbers.is_possible_number(parsed) or not phonenumbers.is_valid_number(parsed):
            raise ValueError(
                f"Invalid phone number '{phone_number}' for region '{region}'. Must conform to E.164."
            )
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except ImportError:
        cleaned = re.sub(r"[\s\-\(\)]", "", raw_phone)
        if cleaned.startswith("+"):
            digits = cleaned[1:]
            if not digits.isdigit() or not (8 <= len(digits) <= 15) or digits.startswith("0"):
                raise ValueError(
                    f"Invalid phone number '{phone_number}'. E.164 numbers must have 8 to 15 digits."
                )
            return f"+{digits}"

        if cleaned.startswith("0"):
            cleaned = cleaned[1:]
        if not cleaned.isdigit() or not (6 <= len(cleaned) <= 13):
            raise ValueError(
                f"Invalid phone number '{phone_number}' for region '{region}'."
            )
        prefix = (
            raw_country
            if raw_country.startswith("+")
            else REGION_TO_DIALING_CODE.get(region, "+62")
        )
        e164_candidate = f"{prefix}{cleaned}"
        digits_only = e164_candidate[1:]
        if not (8 <= len(digits_only) <= 15):
            raise ValueError(
                f"Invalid phone number '{phone_number}'. Normalized E.164 length out of range."
            )
        return e164_candidate
    except Exception as exc:
        if isinstance(exc, ValueError):
            raise
        raise ValueError(
            f"Invalid phone number '{phone_number}' for country '{country_code}'. Must be a valid number."
        ) from exc
