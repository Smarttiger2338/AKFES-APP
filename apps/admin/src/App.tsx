import { invoke } from "@tauri-apps/api/core";
import { useEffect, useMemo, useState } from "react";

interface LicenseSummary {
  license_id: number;
  label: string | null;
  created_at: number;
  expires_at: number;
  revoked_at: number | null;
  status: "active" | "expired" | "revoked";
  device_bound: boolean;
  active_session_count: number;
}

interface AuditEntry {
  audit_id: number;
  action: string;
  actor: string;
  target_type: string;
  target_id: string | null;
  details: Record<string, unknown>;
  created_at: number;
}

interface IssuedLicense {
  license_key: string;
  license_id: number;
  created_at: number;
  expires_at: number;
}

const formatTime = (timestamp: number | null) =>
  timestamp ? new Date(timestamp * 1000).toLocaleString("ko-KR") : "-";

function App() {
  const [serverUrl, setServerUrl] = useState("http://127.0.0.1:8000");
  const [adminToken, setAdminToken] = useState("");
  const [actor, setActor] = useState("local-admin");
  const [durationDays, setDurationDays] = useState(30);
  const [label, setLabel] = useState("");
  const [licenses, setLicenses] = useState<LicenseSummary[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [issued, setIssued] = useState<IssuedLicense | null>(null);
  const [notice, setNotice] = useState("로컬 관리자 토큰을 불러오는 중입니다.");
  const [busy, setBusy] = useState(false);

  const headers = useMemo(
    () => ({
      "Content-Type": "application/json",
      "X-AKFES-Admin-Token": adminToken,
      "X-AKFES-Admin-Actor": actor.trim() || "local-admin",
    }),
    [adminToken, actor],
  );

  const api = async <T,>(path: string, init: RequestInit = {}): Promise<T> => {
    const response = await fetch(`${serverUrl.replace(/\/$/, "")}${path}`, {
      ...init,
      headers: { ...headers, ...(init.headers ?? {}) },
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail ?? `HTTP ${response.status}`);
    }
    return response.json() as Promise<T>;
  };

  const refresh = async () => {
    if (!adminToken) return;
    setBusy(true);
    try {
      const [licenseRows, auditRows] = await Promise.all([
        api<LicenseSummary[]>("/api/v2/admin/licenses?limit=200"),
        api<AuditEntry[]>("/api/v2/admin/audit?limit=100"),
      ]);
      setLicenses(licenseRows);
      setAudit(auditRows);
      setNotice(`라이선스 ${licenseRows.length}개를 불러왔습니다.`);
    } catch (error) {
      setNotice(`조회 실패: ${String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void invoke<string>("load_local_admin_token")
      .then((token) => {
        setAdminToken(token);
        setNotice("로컬 관리자 토큰을 불러왔습니다.");
      })
      .catch(() => setNotice("토큰을 직접 입력하거나 AKFES를 한 번 실행하세요."));
  }, []);

  useEffect(() => {
    if (adminToken) void refresh();
  }, [adminToken]);

  const issueLicense = async () => {
    setBusy(true);
    try {
      const result = await api<IssuedLicense>("/api/v2/admin/licenses", {
        method: "POST",
        body: JSON.stringify({
          duration_seconds: Math.max(1, durationDays) * 86_400,
          label: label.trim() || null,
        }),
      });
      setIssued(result);
      setLabel("");
      await navigator.clipboard.writeText(result.license_key).catch(() => undefined);
      setNotice("라이선스를 생성하고 클립보드에 복사했습니다. 이 키는 다시 조회할 수 없습니다.");
      await refresh();
    } catch (error) {
      setNotice(`발급 실패: ${String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const mutateLicense = async (licenseId: number, action: "revoke" | "reset") => {
    const reason = window.prompt(action === "revoke" ? "취소 사유" : "장치 바인딩 초기화 사유", "관리자 요청");
    if (reason === null) return;
    const path = action === "revoke"
      ? `/api/v2/admin/licenses/${licenseId}/revoke`
      : `/api/v2/admin/licenses/${licenseId}/device-binding/reset`;
    setBusy(true);
    try {
      await api(path, { method: "POST", body: JSON.stringify({ reason }) });
      setNotice(action === "revoke" ? "라이선스를 취소했습니다." : "장치 바인딩을 초기화했습니다.");
      await refresh();
    } catch (error) {
      setNotice(`처리 실패: ${String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="shell">
      <header>
        <div><span>AKFES</span><h1>License Manager</h1></div>
        <button onClick={() => void refresh()} disabled={busy || !adminToken}>새로고침</button>
      </header>

      <section className="connection card">
        <label>서버 주소<input value={serverUrl} onChange={(e) => setServerUrl(e.target.value)} /></label>
        <label>관리자 이름<input value={actor} onChange={(e) => setActor(e.target.value)} /></label>
        <label>관리자 토큰<input type="password" value={adminToken} onChange={(e) => setAdminToken(e.target.value)} /></label>
      </section>

      <section className="grid">
        <article className="card issue">
          <h2>새 라이선스 발급</h2>
          <label>기간(일)<input type="number" min="1" max="3650" value={durationDays} onChange={(e) => setDurationDays(Number(e.target.value))} /></label>
          <label>라벨<input value={label} maxLength={120} onChange={(e) => setLabel(e.target.value)} placeholder="사용자 또는 용도" /></label>
          <button className="primary" onClick={() => void issueLicense()} disabled={busy || !adminToken}>라이선스 생성</button>
          {issued && <div className="issued"><small>한 번만 표시됩니다</small><code>{issued.license_key}</code><button onClick={() => void navigator.clipboard.writeText(issued.license_key)}>복사</button></div>}
        </article>

        <article className="card stats">
          <h2>현황</h2>
          <strong>{licenses.filter((x) => x.status === "active").length}</strong><span>활성 라이선스</span>
          <strong>{licenses.filter((x) => x.device_bound).length}</strong><span>장치 바인딩</span>
          <strong>{licenses.reduce((sum, x) => sum + x.active_session_count, 0)}</strong><span>활성 세션</span>
        </article>
      </section>

      <section className="card table-card">
        <h2>라이선스 목록</h2>
        <div className="table-wrap"><table><thead><tr><th>ID</th><th>라벨</th><th>상태</th><th>만료</th><th>장치</th><th>세션</th><th>관리</th></tr></thead><tbody>
          {licenses.map((item) => <tr key={item.license_id}><td>{item.license_id}</td><td>{item.label ?? "-"}</td><td><span className={`badge ${item.status}`}>{item.status}</span></td><td>{formatTime(item.expires_at)}</td><td>{item.device_bound ? "바인딩됨" : "미바인딩"}</td><td>{item.active_session_count}</td><td><button onClick={() => void mutateLicense(item.license_id, "reset")} disabled={!item.device_bound || item.status !== "active"}>장치 초기화</button><button className="danger" onClick={() => void mutateLicense(item.license_id, "revoke")} disabled={item.status === "revoked"}>취소</button></td></tr>)}
        </tbody></table></div>
      </section>

      <section className="card table-card">
        <h2>감사 로그</h2>
        <div className="table-wrap"><table><thead><tr><th>시각</th><th>작업</th><th>관리자</th><th>대상</th><th>세부 정보</th></tr></thead><tbody>
          {audit.map((item) => <tr key={item.audit_id}><td>{formatTime(item.created_at)}</td><td>{item.action}</td><td>{item.actor}</td><td>{item.target_type} {item.target_id ?? ""}</td><td><code>{JSON.stringify(item.details)}</code></td></tr>)}
        </tbody></table></div>
      </section>

      <footer>{notice}</footer>
    </main>
  );
}

export default App;
