const API_BASE = `${(import.meta.env.VITE_API_BASE_URL || "").replace(/\/+$/, "")}/api/v1`;
const DIRECT_LOCAL_API_BASES = [
  "http://127.0.0.1:8001/api/v1",
  "http://127.0.0.1:8000/api/v1",
];

export async function apiRequest<T>(
  path: string,
  idToken: string,
  options: RequestInit = {}
): Promise<T> {
  const reqInit: RequestInit = {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${idToken}`,
      ...(options.headers || {}),
    },
  };

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, reqInit);
  } catch (networkErr) {
    let directResp: Response | null = null;
    if (typeof window !== "undefined" && window.location.protocol === "http:") {
      for (const directBase of DIRECT_LOCAL_API_BASES) {
        try {
          directResp = await fetch(`${directBase}${path}`, reqInit);
          break;
        } catch {
          // Continue to next fallback port
        }
      }
    }
    if (!directResp) {
      throw new Error(
        `Backend service unreachable (${networkErr instanceof Error ? networkErr.message : "Failed to fetch"}). Ensure the FastAPI server is running on port 8001.`
      );
    }
    response = directResp;
  }

  // If Vite dev proxy returns >= 500 or 404, retry directly against local FastAPI ports if on http:
  if (response.status >= 500 || response.status === 404) {
    if (typeof window !== "undefined" && window.location.protocol === "http:") {
      for (const directBase of DIRECT_LOCAL_API_BASES) {
        try {
          const directResp = await fetch(`${directBase}${path}`, reqInit);
          if (directResp.ok || (directResp.status < 500 && directResp.status !== 404)) {
            response = directResp;
            break;
          }
        } catch {
          // Continue to next fallback port
        }
      }
    }
  }

  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}));
    let detail =
      typeof errorBody.detail === "string"
        ? errorBody.detail
        : Array.isArray(errorBody.detail)
          ? errorBody.detail.map((e: { msg?: string }) => e.msg).join(", ")
          : `Request failed with status ${response.status}`;

    if (response.status === 404 && detail === "Not Found") {
      detail = `API endpoint '${path}' not found (404). Please ensure the backend is running with the latest routes (uvicorn app.main:app --port 8001 --reload).`;
    }

    throw new Error(detail);
  }

  return (await response.json()) as T;
}
