import React, { useMemo, useState } from "react";
import {
  COUNTRY_DIALING_OPTIONS,
  formatNationalPhoneInput,
  toE164Phone,
} from "../lib/phoneUtils";

export interface CountryPhoneInputProps {
  countryIso2: string;
  phoneNumber: string;
  onCountryChange: (iso2: string) => void;
  onPhoneChange: (formattedNational: string) => void;
  disabled?: boolean;
}

export const CountryPhoneInput: React.FC<CountryPhoneInputProps> = ({
  countryIso2,
  phoneNumber,
  onCountryChange,
  onPhoneChange,
  disabled = false,
}) => {
  const [searchQuery, setSearchQuery] = useState("");
  const [dropdownOpen, setDropdownOpen] = useState(false);

  const selectedCountry = useMemo(
    () =>
      COUNTRY_DIALING_OPTIONS.find((c) => c.iso2 === countryIso2) ??
      COUNTRY_DIALING_OPTIONS[0],
    [countryIso2]
  );

  const filteredCountries = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return COUNTRY_DIALING_OPTIONS;
    return COUNTRY_DIALING_OPTIONS.filter(
      (c) =>
        c.name.toLowerCase().includes(q) ||
        c.iso2.toLowerCase().includes(q) ||
        c.dialCode.includes(q)
    );
  }, [searchQuery]);

  const e164Preview = useMemo(
    () => toE164Phone(phoneNumber, selectedCountry.iso2),
    [phoneNumber, selectedCountry.iso2]
  );

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const formatted = formatNationalPhoneInput(e.target.value);
    onPhoneChange(formatted);
  };

  return (
    <div className="space-y-1.5">
      <label
        htmlFor="phone-manual-input"
        className="block text-sm font-medium text-slate-200"
      >
        Phone Number <span className="text-rose-400">*</span>{" "}
        <span className="text-xs font-normal text-slate-400">
          (E.164 Required for Escalation & MFA)
        </span>
      </label>

      <div className="relative flex rounded-lg border border-slate-700 bg-slate-900 focus-within:border-indigo-500 focus-within:ring-1 focus-within:ring-indigo-500">
        <button
          type="button"
          disabled={disabled}
          onClick={() => setDropdownOpen((prev) => !prev)}
          aria-label="Select country dialing code"
          className="flex items-center gap-1.5 rounded-l-lg border-r border-slate-700 bg-slate-800/80 px-3 py-2.5 text-sm font-medium text-slate-100 hover:bg-slate-800"
        >
          <span>{selectedCountry.flag}</span>
          <span>{selectedCountry.dialCode}</span>
          <span className="text-xs text-slate-400">({selectedCountry.iso2})</span>
        </button>

        <input
          id="phone-manual-input"
          type="tel"
          disabled={disabled}
          value={phoneNumber}
          onChange={handleInputChange}
          placeholder={selectedCountry.placeholder}
          className="w-full rounded-r-lg bg-transparent px-3 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none"
          required
        />

        {dropdownOpen && (
          <div className="absolute left-0 top-full z-30 mt-1 w-80 rounded-lg border border-slate-700 bg-slate-900 p-2 shadow-xl">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search country or +code..."
              className="mb-2 w-full rounded border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-xs text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
            />
            <ul className="max-h-48 overflow-y-auto divide-y divide-slate-800/60">
              {filteredCountries.map((country) => (
                <li key={country.iso2}>
                  <button
                    type="button"
                    onClick={() => {
                      onCountryChange(country.iso2);
                      setDropdownOpen(false);
                      setSearchQuery("");
                    }}
                    className="flex w-full items-center justify-between px-2.5 py-1.5 text-left text-xs text-slate-200 hover:bg-slate-800"
                  >
                    <span>
                      {country.flag} {country.name} ({country.iso2})
                    </span>
                    <span className="font-mono text-indigo-400">
                      {country.dialCode}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {phoneNumber.trim().length > 0 && (
        <div className="flex items-center justify-between text-xs">
          <span className="text-slate-400">
            Normalized E.164:{" "}
            <code className="font-mono text-indigo-300">
              {e164Preview.e164 || "-"}
            </code>
          </span>
          {!e164Preview.isValid && (
            <span className="text-rose-400">{e164Preview.error}</span>
          )}
        </div>
      )}
    </div>
  );
};
