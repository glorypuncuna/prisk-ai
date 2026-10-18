import React, { useState } from "react";
import {
  fetchCurrentUserProfile,
  registerUserProfile,
  UserProfile,
} from "../api/authApi";
import { CountryPhoneInput } from "../components/CountryPhoneInput";
import {
  FirebaseIdentitySession,
  signInWithEmailPassword,
  signInWithOAuthProvider,
  signUpWithEmailPassword,
} from "../lib/firebaseClient";
import { toE164Phone } from "../lib/phoneUtils";

export interface AuthPageProps {
  onAuthenticated: (
    session: FirebaseIdentitySession,
    profile: UserProfile
  ) => void;
}

type AuthMode = "login" | "register" | "sso-complete-profile";

export const AuthPage: React.FC<AuthPageProps> = ({ onAuthenticated }) => {
  const [mode, setMode] = useState<AuthMode>("login");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [countryIso2, setCountryIso2] = useState("ID");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [pendingSsoSession, setPendingSsoSession] =
    useState<FirebaseIdentitySession | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setIsSubmitting(true);
    try {
      const session = await signInWithEmailPassword(email, password);
      try {
        const profile = await fetchCurrentUserProfile(session.idToken);
        onAuthenticated(session, profile);
      } catch (err) {
        const statusErr = err as Error & { status?: number };
        if (statusErr.status === 404) {
          setPendingSsoSession(session);
          setMode("sso-complete-profile");
        } else {
          throw err;
        }
      }
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Authentication failed"
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRegisterSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    const phoneResult = toE164Phone(phoneNumber, countryIso2);
    if (!phoneResult.isValid) {
      setErrorMessage(
        phoneResult.error || "Please enter a valid E.164 phone number."
      );
      return;
    }

    setIsSubmitting(true);
    try {
      const session = await signUpWithEmailPassword(email, password);
      const profile = await registerUserProfile(session.idToken, {
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        phone_number: phoneResult.e164,
        country_code: countryIso2,
        email: session.email,
      });
      onAuthenticated(session, profile);
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Registration failed"
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleOAuthSignIn = async (provider: "google.com" | "microsoft.com") => {
    setErrorMessage(null);
    setIsSubmitting(true);
    try {
      const session = await signInWithOAuthProvider(provider, email || undefined);
      try {
        const profile = await fetchCurrentUserProfile(session.idToken);
        onAuthenticated(session, profile);
      } catch (err) {
        const statusErr = err as Error & { status?: number };
        if (statusErr.status === 404) {
          setPendingSsoSession(session);
          setEmail(session.email);
          setMode("sso-complete-profile");
        } else {
          throw err;
        }
      }
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "SSO sign-in failed"
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCompleteSsoProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!pendingSsoSession) return;
    setErrorMessage(null);

    const phoneResult = toE164Phone(phoneNumber, countryIso2);
    if (!phoneResult.isValid) {
      setErrorMessage(
        phoneResult.error || "Please enter a valid E.164 phone number."
      );
      return;
    }

    setIsSubmitting(true);
    try {
      const profile = await registerUserProfile(pendingSsoSession.idToken, {
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        phone_number: phoneResult.e164,
        country_code: countryIso2,
        email: pendingSsoSession.email,
      });
      onAuthenticated(pendingSsoSession, profile);
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Profile completion failed"
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4 py-12">
      <div className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900/95 p-8 shadow-2xl">
        <div className="mb-6 text-center">
          <span className="inline-block rounded-full border border-indigo-500/30 bg-indigo-500/10 px-3 py-1 text-xs font-semibold tracking-wider text-indigo-300">
            pRiskAI IDENTITY PLATFORM
          </span>
          <h1 className="mt-3 text-2xl font-bold text-white">
            {mode === "login" && "Sign in to pRiskAI"}
            {mode === "register" && "Create Enterprise Account"}
            {mode === "sso-complete-profile" && "Complete Your Profile"}
          </h1>
          <p className="mt-1 text-xs text-slate-400">
            Enterprise Meeting Intelligence & HITL Risk Governance
          </p>
        </div>

        {mode !== "sso-complete-profile" && (
          <div className="mb-6 grid grid-cols-2 gap-2 rounded-lg bg-slate-950 p-1">
            <button
              type="button"
              onClick={() => {
                setMode("login");
                setErrorMessage(null);
              }}
              className={`rounded-md py-2 text-xs font-semibold transition ${
                mode === "login"
                  ? "bg-indigo-600 text-white"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Sign In
            </button>
            <button
              type="button"
              onClick={() => {
                setMode("register");
                setErrorMessage(null);
              }}
              className={`rounded-md py-2 text-xs font-semibold transition ${
                mode === "register"
                  ? "bg-indigo-600 text-white"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Register
            </button>
          </div>
        )}

        {errorMessage && (
          <div
            role="alert"
            className="mb-4 rounded-lg border border-rose-500/40 bg-rose-500/10 px-3.5 py-2.5 text-xs text-rose-300"
          >
            {errorMessage}
          </div>
        )}

        {mode === "login" && (
          <form onSubmit={handleLoginSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-200">
                Enterprise Email
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@enterprise.com"
                required
                className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-200">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
                className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
              />
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full rounded-lg bg-indigo-600 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-50"
            >
              {isSubmitting ? "Signing In..." : "Sign In"}
            </button>
          </form>
        )}

        {mode === "register" && (
          <form onSubmit={handleRegisterSubmit} className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-slate-200">
                  First Name <span className="text-rose-400">*</span>
                </label>
                <input
                  type="text"
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                  placeholder="Budi"
                  required
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-200">
                  Last Name <span className="text-rose-400">*</span>
                </label>
                <input
                  type="text"
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                  placeholder="Santoso"
                  required
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-200">
                Enterprise Email <span className="text-rose-400">*</span>
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="budi.santoso@enterprise.com"
                required
                className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-200">
                Password <span className="text-rose-400">*</span>
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Minimum 8 characters"
                minLength={8}
                required
                className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
              />
            </div>

            <CountryPhoneInput
              countryIso2={countryIso2}
              phoneNumber={phoneNumber}
              onCountryChange={setCountryIso2}
              onPhoneChange={setPhoneNumber}
              disabled={isSubmitting}
            />

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full rounded-lg bg-indigo-600 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-50"
            >
              {isSubmitting
                ? "Registering Profile..."
                : "Create Account (Default: External Stakeholder)"}
            </button>
          </form>
        )}

        {mode === "sso-complete-profile" && (
          <form onSubmit={handleCompleteSsoProfile} className="space-y-4">
            <p className="text-xs text-slate-300">
              Your SSO identity (
              <span className="font-mono text-indigo-300">
                {pendingSsoSession?.email}
              </span>
              ) has been verified via{" "}
              <span className="font-semibold">
                {pendingSsoSession?.authProvider}
              </span>
              . Please provide your name and E.164 phone number to complete
              onboarding.
            </p>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-slate-200">
                  First Name <span className="text-rose-400">*</span>
                </label>
                <input
                  type="text"
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                  required
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-200">
                  Last Name <span className="text-rose-400">*</span>
                </label>
                <input
                  type="text"
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                  required
                  className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
                />
              </div>
            </div>

            <CountryPhoneInput
              countryIso2={countryIso2}
              phoneNumber={phoneNumber}
              onCountryChange={setCountryIso2}
              onPhoneChange={setPhoneNumber}
              disabled={isSubmitting}
            />

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full rounded-lg bg-indigo-600 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-50"
            >
              {isSubmitting ? "Saving Profile..." : "Complete Registration"}
            </button>
          </form>
        )}

        {mode !== "sso-complete-profile" && (
          <div className="mt-6">
            <div className="relative flex items-center justify-center">
              <div className="w-full border-t border-slate-800" />
              <span className="bg-slate-900 px-3 text-xs text-slate-400">
                Or continue with Enterprise SSO
              </span>
              <div className="w-full border-t border-slate-800" />
            </div>

            <div className="mt-4 grid grid-cols-2 gap-3">
              <button
                type="button"
                disabled={isSubmitting}
                onClick={() => handleOAuthSignIn("google.com")}
                className="flex items-center justify-center gap-2 rounded-lg border border-slate-700 bg-slate-800/70 px-3 py-2 text-xs font-semibold text-slate-100 hover:bg-slate-800"
              >
                <span>Google Workspace</span>
              </button>
              <button
                type="button"
                disabled={isSubmitting}
                onClick={() => handleOAuthSignIn("microsoft.com")}
                className="flex items-center justify-center gap-2 rounded-lg border border-slate-700 bg-slate-800/70 px-3 py-2 text-xs font-semibold text-slate-100 hover:bg-slate-800"
              >
                <span>Microsoft Entra ID</span>
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
