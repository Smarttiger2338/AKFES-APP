import { useEffect, useMemo, useState } from "react";
import type { FormEvent, ReactNode } from "react";

import {
  ApiError,
  clearStoredSession,
  getApiUrl,
  getOrCreateDeviceId,
  loadStoredSession,
  login,
  saveApiUrl,
  saveSession,
  verifySession,
} from "./auth";
import type { AuthSession } from "./auth";

interface AuthGateProps {
  children: ReactNode;
}

type AuthState = "checking" | "signed-out" | "signing-in" | "signed-in";

function formatUnixTime(value: number): string {
  return new Date(value * 1000).toLocaleString();
}

function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return "라이선스 키 또는 세션이 올바르지 않습니다.";
    if (error.status === 403) return "라이선스가 만료·취소되었거나 다른 장치에 바인딩되어 있습니다.";
    if (error.status === 422) return `입력값을 확인하세요. ${error.message}`;
    return `서버 오류(${error.status}): ${error.message}`;
  }
  if (error instanceof TypeError) return "FastAPI 서버에 연결할 수 없습니다. 서버 주소와 실행 상태를 확인하세요.";
  return error instanceof Error ? error.message : String(error);
}

export default function AuthGate({ children }: AuthGateProps) {
  const deviceId = useMemo(() => getOrCreateDeviceId(), []);
  const [apiUrl, setApiUrl] = useState(() => getApiUrl());
  const [licenseKey, setLicenseKey] = useState("");
  const [session, setSession] = useState<AuthSession | null>(() => loadStoredSession());
  const [authState, setAuthState] = useState<AuthState>("checking");
  const [message, setMessage] = useState("저장된 세션을 확인하고 있습니다.");

  useEffect(() => {
    let active = true;
    const stored = loadStoredSession();
    if (!stored) {
      setAuthState("signed-out");
      setMessage("라이선스 키를 입력해 서버 인증을 완료하세요.");
      return () => {
        active = false;
      };
    }

    void verifySession(apiUrl, stored)
      .then((verified) => {
        if (!active) return;
        saveSession(verified);
        setSession(verified);
        setAuthState("signed-in");
        setMessage("저장된 세션을 확인했습니다.");
      })
      .catch(() => {
        if (!active) return;
        clearStoredSession();
        setSession(null);
        setAuthState("signed-out");
        setMessage("저장된 세션이 만료되었거나 서버에서 거부되었습니다.");
      });

    return () => {
      active = false;
    };
  }, [apiUrl]);

  const submitLogin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!licenseKey.trim()) {
      setMessage("라이선스 키를 입력하세요.");
      return;
    }

    setAuthState("signing-in");
    setMessage("FastAPI 서버에서 라이선스와 장치 바인딩을 확인하고 있습니다.");

    try {
      const normalizedApiUrl = saveApiUrl(apiUrl);
      setApiUrl(normalizedApiUrl);
      const authenticated = await login(normalizedApiUrl, licenseKey, deviceId);
      saveSession(authenticated);
      setSession(authenticated);
      setLicenseKey("");
      setAuthState("signed-in");
      setMessage("라이선스 인증과 장치 바인딩을 완료했습니다.");
    } catch (error) {
      clearStoredSession();
      setSession(null);
      setAuthState("signed-out");
      setMessage(describeError(error));
    }
  };

  const logout = () => {
    clearStoredSession();
    setSession(null);
    setAuthState("signed-out");
    setMessage("이 앱에 저장된 세션을 삭제했습니다. 서버 세션은 만료 시 자동 종료됩니다.");
  };

  if (authState === "signed-in" && session) {
    return (
      <div className="authenticated-shell">
        <div className="auth-session-bar">
          <div>
            <strong>라이선스 #{session.licenseId}</strong>
            <span>세션 만료 {formatUnixTime(session.sessionExpiresAt)}</span>
          </div>
          <div>
            <span className="auth-device-label" title={session.deviceId}>장치 바인딩 완료</span>
            <button className="secondary" onClick={logout}>로그아웃</button>
          </div>
        </div>
        {children}
      </div>
    );
  }

  return (
    <main className="auth-gate-shell">
      <section className="auth-gate-card">
        <div className="auth-gate-brand">
          <span className="brand-mark">A</span>
          <div>
            <strong>AKFES</strong>
            <small>Secure Desktop v2</small>
          </div>
        </div>

        <div className="auth-gate-copy">
          <span className="eyebrow">ZERO TRUST ACCESS</span>
          <h1>라이선스 인증</h1>
          <p>FastAPI 서버가 라이선스 상태를 확인하고 이 데스크톱 장치에 바인딩된 세션을 발급합니다.</p>
        </div>

        <form className="auth-gate-form" onSubmit={submitLogin}>
          <label htmlFor="api-url">FastAPI 서버 주소</label>
          <input
            id="api-url"
            type="url"
            value={apiUrl}
            onChange={(event) => setApiUrl(event.target.value)}
            placeholder="http://127.0.0.1:8000"
            autoComplete="url"
            disabled={authState === "signing-in" || authState === "checking"}
          />

          <label htmlFor="license-key">라이선스 키</label>
          <input
            id="license-key"
            type="password"
            value={licenseKey}
            onChange={(event) => setLicenseKey(event.target.value)}
            placeholder="AKFES-XXXXX-XXXXX-XXXXX-XXXXX"
            autoComplete="off"
            spellCheck={false}
            disabled={authState === "signing-in" || authState === "checking"}
          />

          <div className="auth-device-box">
            <span>장치 식별자</span>
            <code>{deviceId}</code>
            <small>이 값은 로컬에 생성되며 서버에는 HMAC 다이제스트 형태로 바인딩됩니다.</small>
          </div>

          <button
            className="primary auth-submit"
            type="submit"
            disabled={authState === "signing-in" || authState === "checking" || !licenseKey.trim()}
          >
            {authState === "checking" ? "세션 확인 중..." : authState === "signing-in" ? "인증 중..." : "인증하고 시작"}
          </button>
        </form>

        <div className="inline-note auth-message" role="status">{message}</div>
      </section>
    </main>
  );
}
