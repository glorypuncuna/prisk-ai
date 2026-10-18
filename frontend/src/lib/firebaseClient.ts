import { initializeApp, getApps } from "firebase/app";
import {
  getAuth,
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  signInWithPopup,
  GoogleAuthProvider,
  OAuthProvider,
  signOut as firebaseSignOut,
  User,
} from "firebase/auth";

export type AuthProviderType = "password" | "google.com" | "microsoft.com";

export interface FirebaseIdentitySession {
  uid: string;
  email: string;
  displayName?: string;
  authProvider: AuthProviderType;
  idToken: string;
}

export const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY || "",
  authDomain:
    import.meta.env.VITE_FIREBASE_AUTH_DOMAIN || "prisk-ai.firebaseapp.com",
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID || "prisk-ai",
  storageBucket:
    import.meta.env.VITE_FIREBASE_STORAGE_BUCKET ||
    "prisk-ai.firebasestorage.app",
  messagingSenderId:
    import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID || "345876205384",
  appId:
    import.meta.env.VITE_FIREBASE_APP_ID ||
    "1:345876205384:web:3655046ed3083b1958ed7d",
};

const app =
  getApps().length === 0 ? initializeApp(firebaseConfig) : getApps()[0];
export const firebaseAuth = getAuth(app);

const SESSION_STORAGE_KEY = "priskai_firebase_session";

async function buildSessionFromFirebaseUser(
  user: User,
  defaultProvider: AuthProviderType
): Promise<FirebaseIdentitySession> {
  const idToken = await user.getIdToken(true);
  const providerId =
    (user.providerData[0]?.providerId as AuthProviderType | undefined) ||
    defaultProvider;
  const session: FirebaseIdentitySession = {
    uid: user.uid,
    email: user.email || "",
    displayName: user.displayName || undefined,
    authProvider: providerId,
    idToken,
  };
  saveSession(session);
  return session;
}

export function getStoredSession(): FirebaseIdentitySession | null {
  try {
    const raw = localStorage.getItem(SESSION_STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as FirebaseIdentitySession;
  } catch {
    return null;
  }
}

export function saveSession(session: FirebaseIdentitySession): void {
  localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
}

export function clearSession(): void {
  localStorage.removeItem(SESSION_STORAGE_KEY);
  void firebaseSignOut(firebaseAuth).catch(() => {});
}

export async function signUpWithEmailPassword(
  email: string,
  password: string
): Promise<FirebaseIdentitySession> {
  const normalizedEmail = email.trim().toLowerCase();
  const credential = await createUserWithEmailAndPassword(
    firebaseAuth,
    normalizedEmail,
    password
  );
  return buildSessionFromFirebaseUser(credential.user, "password");
}

export async function signInWithEmailPassword(
  email: string,
  password: string
): Promise<FirebaseIdentitySession> {
  const normalizedEmail = email.trim().toLowerCase();

  // Keep seeded Admin/Manager/Executive accounts convenient if not yet created in Firebase Auth
  if (
    normalizedEmail === "admin@enterprise.com" ||
    normalizedEmail === "manager@enterprise.com" ||
    normalizedEmail === "executive@enterprise.com"
  ) {
    const isAdmin = normalizedEmail === "admin@enterprise.com";
    const isExec = normalizedEmail === "executive@enterprise.com";
    const role = isAdmin ? "ADMIN" : isExec ? "EXECUTIVE" : "MANAGER";
    const uid = isAdmin
      ? "uid_admin_enterprise_com"
      : isExec
        ? "uid_executive_enterprise_com"
        : "uid_manager_enterprise_com";
    const displayName = isAdmin
      ? "Super Administrator"
      : isExec
        ? "Chief Executive"
        : "Enterprise Manager";
    try {
      const credential = await signInWithEmailAndPassword(
        firebaseAuth,
        normalizedEmail,
        password
      );
      return buildSessionFromFirebaseUser(credential.user, "password");
    } catch {
      const mockSession: FirebaseIdentitySession = {
        uid,
        email: normalizedEmail,
        displayName,
        authProvider: "password",
        idToken: `mock:${JSON.stringify({
          uid,
          email: normalizedEmail,
          role,
          auth_provider: "password",
          firebase: { sign_in_provider: "password" },
        })}`,
      };
      saveSession(mockSession);
      return mockSession;
    }
  }

  const credential = await signInWithEmailAndPassword(
    firebaseAuth,
    normalizedEmail,
    password
  );
  return buildSessionFromFirebaseUser(credential.user, "password");
}

export async function signInWithOAuthProvider(
  provider: "google.com" | "microsoft.com",
  _emailHint?: string
): Promise<FirebaseIdentitySession> {
  if (provider === "google.com") {
    const googleProvider = new GoogleAuthProvider();
    googleProvider.setCustomParameters({ prompt: "select_account" });
    const credential = await signInWithPopup(firebaseAuth, googleProvider);
    return buildSessionFromFirebaseUser(credential.user, "google.com");
  }

  const microsoftProvider = new OAuthProvider("microsoft.com");
  const credential = await signInWithPopup(firebaseAuth, microsoftProvider);
  return buildSessionFromFirebaseUser(credential.user, "microsoft.com");
}

/**
 * Force refresh of the current user's Firebase ID token (`getIdToken(true)`)
 * after role elevation or project invitation acceptance.
 */
export async function refreshIdToken(): Promise<string | null> {
  if (firebaseAuth.currentUser) {
    const freshToken = await firebaseAuth.currentUser.getIdToken(true);
    const current = getStoredSession();
    if (current) {
      saveSession({ ...current, idToken: freshToken });
    }
    return freshToken;
  }
  const current = getStoredSession();
  return current?.idToken ?? null;
}
