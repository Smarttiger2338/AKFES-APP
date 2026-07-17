export interface AuthSession {
  sessionToken: string;
  licenseId: number;
  licenseExpiresAt: number;
  sessionExpiresAt: number;
  deviceId: string;
}

interface LoginResponse {
  session_token: string;
  license_id: number;
  license_expires_at: number;
  session_expires_at: number;
  device_id: string | null;
}

interface SessionResponse {
  valid: boolean;
  license_id: number;
  session_expires_at: number;
  device_id: string | null;
}

const apiUrlStorageKey = "akfes-v2-api-url";
const deviceIdStorageKey = "akfes-v2-device-id";
const sessionStorageKey = "akfes-v2-auth-session";
const defaultApiUrl = "http://127.0.0.1:8000";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function normalizeApiUrl(value: string): string {
  const normalized = value.trim().replace(/\/+$/, "");
  const url = new URL(normalized || defaultApiUrl);
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error("API 주소는 http 또는 https 형식이어야 합니다.");
  }
  return url.toString().replace(/\/$/, "");
}

async function responseError(response: Response): Promise<ApiError> {
  try {
    const payload = await response.json() as { detail?: unknown };
    const detail = typeof payload.detail === "string" ? payload.detail : response.statusText;
    return new ApiError(detail || "서버 요청에 실패했습니다.", response.status);
  } catch {
    return new ApiError(response.statusText || "서버 요청에 실패했습니다.", response.status);
  }
}

export function getApiUrl(): string {
  try {
    return normalizeApiUrl(localStorage.getItem(apiUrlStorageKey) ?? defaultApiUrl);
  } catch {
    return defaultApiUrl;
  }
}

export function saveApiUrl(value: string): string {
  const normalized = normalizeApiUrl(value);
  localStorage.setItem(apiUrlStorageKey, normalized);
  return normalized;
}

export function getOrCreateDeviceId(): string {
  const stored = localStorage.getItem(deviceIdStorageKey)?.trim();
  if (stored) return stored;

  const generated = `desktop-${crypto.randomUUID()}`;
  localStorage.setItem(deviceIdStorageKey, generated);
  return generated;
}

export function loadStoredSession(): AuthSession | null {
  try {
    const raw = sessionStorage.getItem(sessionStorageKey);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as AuthSession;
    if (!parsed.sessionToken || !parsed.deviceId || parsed.sessionExpiresAt <= Math.floor(Date.now() / 1000)) {
      clearStoredSession();
      return null;
    }
    return parsed;
  } catch {
    clearStoredSession();
    return null;
  }
}

export function saveSession(session: AuthSession): void {
  sessionStorage.setItem(sessionStorageKey, JSON.stringify(session));
}

export function clearStoredSession(): void {
  sessionStorage.removeItem(sessionStorageKey);
}

export async function login(apiUrl: string, licenseKey: string, deviceId: string): Promise<AuthSession> {
  const response = await fetch(`${normalizeApiUrl(apiUrl)}/api/v2/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      license_key: licenseKey.trim(),
      device_id: deviceId,
    }),
  });

  if (!response.ok) throw await responseError(response);
  const payload = await response.json() as LoginResponse;
  if (!payload.device_id) throw new Error("서버가 장치 바인딩 정보를 반환하지 않았습니다.");

  return {
    sessionToken: payload.session_token,
    licenseId: payload.license_id,
    licenseExpiresAt: payload.license_expires_at,
    sessionExpiresAt: payload.session_expires_at,
    deviceId: payload.device_id,
  };
}

export async function verifySession(apiUrl: string, session: AuthSession): Promise<AuthSession> {
  const response = await fetch(`${normalizeApiUrl(apiUrl)}/api/v2/auth/session`, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${session.sessionToken}`,
      "X-AKFES-Device-ID": session.deviceId,
    },
  });

  if (!response.ok) throw await responseError(response);
  const payload = await response.json() as SessionResponse;
  if (!payload.valid || payload.device_id !== session.deviceId) {
    throw new ApiError("세션 장치 정보가 일치하지 않습니다.", 401);
  }

  return {
    ...session,
    licenseId: payload.license_id,
    sessionExpiresAt: payload.session_expires_at,
  };
}
