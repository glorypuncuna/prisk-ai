export interface CountryDialingOption {
  iso2: string;
  name: string;
  dialCode: string;
  flag: string;
  placeholder: string;
}

export const COUNTRY_DIALING_OPTIONS: CountryDialingOption[] = [
  { iso2: "ID", name: "Indonesia", dialCode: "+62", flag: "🇮🇩", placeholder: "812-3456-7890" },
  { iso2: "US", name: "United States", dialCode: "+1", flag: "🇺🇸", placeholder: "415-555-2671" },
  { iso2: "SG", name: "Singapore", dialCode: "+65", flag: "🇸🇬", placeholder: "8123-4567" },
  { iso2: "GB", name: "United Kingdom", dialCode: "+44", flag: "🇬🇧", placeholder: "7700-900077" },
  { iso2: "AU", name: "Australia", dialCode: "+61", flag: "🇦🇺", placeholder: "412-345-678" },
  { iso2: "MY", name: "Malaysia", dialCode: "+60", flag: "🇲🇾", placeholder: "12-345-6789" },
  { iso2: "PH", name: "Philippines", dialCode: "+63", flag: "🇵🇭", placeholder: "917-123-4567" },
  { iso2: "TH", name: "Thailand", dialCode: "+66", flag: "🇹🇭", placeholder: "81-234-5678" },
  { iso2: "JP", name: "Japan", dialCode: "+81", flag: "🇯🇵", placeholder: "90-1234-5678" },
  { iso2: "KR", name: "South Korea", dialCode: "+82", flag: "🇰🇷", placeholder: "10-1234-5678" },
  { iso2: "VN", name: "Vietnam", dialCode: "+84", flag: "🇻🇳", placeholder: "91-234-5678" },
  { iso2: "IN", name: "India", dialCode: "+91", flag: "🇮🇳", placeholder: "98765-43210" },
  { iso2: "DE", name: "Germany", dialCode: "+49", flag: "🇩🇪", placeholder: "1512-3456789" },
  { iso2: "FR", name: "France", dialCode: "+33", flag: "🇫🇷", placeholder: "6-12-34-56-78" },
  { iso2: "NL", name: "Netherlands", dialCode: "+31", flag: "🇳🇱", placeholder: "6-12345678" },
];

/**
 * Format raw manual phone input into readable groups while typing.
 */
export function formatNationalPhoneInput(rawInput: string): string {
  const digitsOnly = rawInput.replace(/[^\d]/g, "");
  if (digitsOnly.length <= 3) {
    return digitsOnly;
  }
  if (digitsOnly.length <= 7) {
    return `${digitsOnly.slice(0, 3)}-${digitsOnly.slice(3)}`;
  }
  return `${digitsOnly.slice(0, 3)}-${digitsOnly.slice(3, 7)}-${digitsOnly.slice(7, 13)}`;
}

/**
 * Convert country selection + manual subscriber input into strict E.164 (`+[country][subscriber]`).
 */
export function toE164Phone(
  manualInput: string,
  countryIso2: string
): { e164: string; isValid: boolean; error?: string } {
  const country =
    COUNTRY_DIALING_OPTIONS.find((c) => c.iso2 === countryIso2) ??
    COUNTRY_DIALING_OPTIONS[0];

  const trimmed = manualInput.trim();
  if (!trimmed) {
    return {
      e164: "",
      isValid: false,
      error: "Phone number is required",
    };
  }

  // Strip spaces, dashes, and parentheses
  let digits = trimmed.replace(/[\s\-()]/g, "");
  if (digits.startsWith("+")) {
    const rawDigits = digits.slice(1);
    if (!/^\d{8,15}$/.test(rawDigits) || rawDigits.startsWith("0")) {
      return {
        e164: digits,
        isValid: false,
        error: "E.164 phone number must contain 8 to 15 digits after '+'",
      };
    }
    return { e164: `+${rawDigits}`, isValid: true };
  }

  // Strip trunk prefix '0' if entered by the user (e.g., 081234567890 -> 81234567890)
  if (digits.startsWith("0")) {
    digits = digits.slice(1);
  }

  if (!/^\d{6,13}$/.test(digits)) {
    return {
      e164: `${country.dialCode}${digits}`,
      isValid: false,
      error: "Subscriber phone number must contain between 6 and 13 digits",
    };
  }

  const normalized = `${country.dialCode}${digits}`;
  const totalDigits = normalized.slice(1);
  if (totalDigits.length < 8 || totalDigits.length > 15) {
    return {
      e164: normalized,
      isValid: false,
      error: "Normalized E.164 number must be between 8 and 15 total digits",
    };
  }

  return { e164: normalized, isValid: true };
}
