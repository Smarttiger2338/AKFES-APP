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

interface AdminSecurityStatus {
  pin_set: boolean;
  config_protected: boolean;
}

interface LocalServerStatus {
  running: boolean;
  owned_by_admin_app: boolean;
  config_protected: boolean;
  config_path: string;
  database_path: string;
  backup_count: number;
  latest_backup_path: string | null;
  startup_error: string | null;
}

interface BackupResult {
  path: string;
}

interface UpdateStatus {
  current_version: string;
  latest_version: string | null;
  update_available: boolean;
  release_name: string | null;
  release_url: string | null;
  published_at: string | null;
  error: string | null;
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
  const [security, setSecurity] = useState<AdminSecurityStatus | null>(null);
  const [unlocked, setUnlocked] = useState(false);
  const [pin, setPin] = useState("");
  const [newPin, setNewPin] = useState("");
  const [serverStatus, setServerStatus] = useState<LocalServerStatus | null>(null);
  const [updateStatus, setUpdateStatus] = useState<UpdateStatus | null>(null);
  const [notice, setNotice] = useState("관리자 보안 상태를 확인하는 중입니다.");
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

  const loadServerStatus = async () => {
    const status = await invoke<LocalServerStatus>("get_local_server_status");
    setServerStatus(status);
    return status;
  };

  const loadAdminToken = async () => {
    const token = await invoke<string>("load_local_admin_token");
    setAdminToken(token);
  };

  const refresh = async () => {
    if (!adminToken || !unlocked) return;
    setBusy(true);
    try {
      const [licenseRows, auditRows] = await Promise.all([
        api<LicenseSummary[]>("/api/v2/admin/licenses?limit=200"),
        api<AuditEntry[]>("/api/v2/admin/audit?limit=100"),
        loadServerStatus(),
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
    void Promise.all([
      invoke<AdminSecurityStatus>("get_admin_security_status"),
      loadServerStatus(),
    ])
      .then(([status]) => {
        setSecurity(status);
        if (!status.pin_set) {
          setUnlocked(true);
          setNotice("처음 사용 전 관리자 PIN을 설정하세요.");
          void loadAdminToken();
        } else {
          setNotice("관리자 PIN을 입력하세요.");
        }
      })
      .catch((error) => setNotice(`초기화 실패: ${String(error)}`));
  }, []);

  useEffect(() => {
    if (adminToken && unlocked) void refresh();
  }, [adminToken, unlocked]);

  const unlockWithPin = async () => {
    setBusy(true);
    try {
      const ok = await invoke<boolean>("verify_admin_pin", { pin });
      if (!ok) {
        setNotice("PIN이 올바르지 않습니다.");
        return;
      }
      setUnlocked(true);
      setPin("");
      await loadAdminToken();
      setNotice("관리자 패널 잠금이 해제되었습니다.");
    } catch (error) {
      setNotice(`PIN 확인 실패: ${String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const saveNewPin = async () => {
    setBusy(true);
    try {
      const status = await invoke<AdminSecurityStatus>("set_admin_pin", { pin: newPin });
      setSecurity(status);
      setNewPin("");
      setNotice("관리자 PIN을 저장했습니다.");
    } catch (error) {
      setNotice(`PIN 저장 실패: ${String(error)}`);
    } finally {
      setBusy(false);
    }
  };

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
    const reason = window.prompt(
      action === "revoke" ? "취소 사유" : "장치 바인딩 초기화 사유",
      "관리자 요청",
    );
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

  const rotateAdminToken = async () => {
    const confirmed = window.confirm(
      "로컬 관리자 토큰을 새로 생성할까요?\n\n현재 관리자 앱이 시작한 로컬 서버가 다시 시작되고 기존 관리자 토큰은 즉시 무효화됩니다.",
    );
    if (!confirmed) return;

    setBusy(true);
    try {
      const token = await invoke<string>("rotate_local_admin_token");
      setAdminToken(token);
      setNotice("새 로컬 관리자 토큰을 생성하고 서버를 다시 시작했습니다.");
      await refresh();
    } catch (error) {
      setNotice(`관리자 토큰 재생성 실패: ${String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const backupDatabase = async () => {
    setBusy(true);
    try {
      const result = await invoke<BackupResult>("backup_local_database");
      setNotice(`백업을 만들었습니다: ${result.path}`);
      await loadServerStatus();
    } catch (error) {
      setNotice(`백업 실패: ${String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const restoreLatestBackup = async () => {
    const confirmed = window.confirm(
      "최신 백업으로 복원할까요?\n\n현재 데이터베이스는 복원 전에 자동 백업됩니다.",
    );
    if (!confirmed) return;

    setBusy(true);
    try {
      const result = await invoke<BackupResult>("restore_latest_database_backup");
      setNotice(`최신 백업을 복원했습니다: ${result.path}`);
      await refresh();
    } catch (error) {
      setNotice(`복원 실패: ${String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const checkUpdates = async () => {
    setBusy(true);
    try {
      const status = await invoke<UpdateStatus>("check_for_updates");
      setUpdateStatus(status);
      if (status.error) {
        setNotice(`업데이트 확인 실패: ${status.error}`);
      } else if (status.update_available) {
        setNotice(`새 버전이 있습니다: ${status.latest_version}`);
      } else {
        setNotice("현재 버전이 최신입니다.");
      }
    } catch (error) {
      setNotice(`업데이트 확인 실패: ${String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  if (!unlocked) {
    return (
      <main className="shell lock-shell">
        <section className="card lock-card">
          <span>AKFES</span>
          <h1>관리자 잠금</h1>
          <label>관리자 PIN<input type="password" value={pin} onChange={(e) => setPin(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") void unlockWithPin(); }} autoFocus /></label>
          <button className="primary" onClick={() => void unlockWithPin()} disabled={busy || !pin}>잠금 해제</button>
          <footer>{notice}</footer>
        </section>
      </main>
    );
  }

  return (
    <main className="shell">
      <header>
        <div><span>AKFES</span><h1>License Manager</h1></div>
        <div className="header-actions">
          <button onClick={() => void checkUpdates()} disabled={busy}>업데이트 확인</button>
          <button onClick={() => void rotateAdminToken()} disabled={busy || !adminToken}>관리자 토큰 재생성</button>
          <button onClick={() => void refresh()} disabled={busy || !adminToken}>새로고침</button>
        </div>
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

      <section className="tools">
        <article className="card status-card">
          <h2>서버 상태</h2>
          <p><strong>{serverStatus?.running ? "실행 중" : "중지됨"}</strong><span>{serverStatus?.owned_by_admin_app ? "관리자 앱이 실행한 서버" : "외부 서버 또는 대기 중"}</span></p>
          <p><strong>{serverStatus?.config_protected ? "보호됨" : "확인 필요"}</strong><span>로컬 설정 암호화</span></p>
          <p><strong>{serverStatus?.backup_count ?? 0}</strong><span>저장된 백업</span></p>
          {serverStatus?.startup_error && <code>{serverStatus.startup_error}</code>}
        </article>

        <article className="card admin-tools">
          <h2>운영 도구</h2>
          <div className="tool-row">
            <button onClick={() => void backupDatabase()} disabled={busy}>백업 생성</button>
            <button onClick={() => void restoreLatestBackup()} disabled={busy || !serverStatus?.backup_count}>최신 백업 복원</button>
          </div>
          <div className="tool-row">
            <input type="password" value={newPin} onChange={(e) => setNewPin(e.target.value)} placeholder={security?.pin_set ? "새 관리자 PIN" : "관리자 PIN 설정"} />
            <button onClick={() => void saveNewPin()} disabled={busy || newPin.trim().length < 4}>{security?.pin_set ? "PIN 변경" : "PIN 설정"}</button>
          </div>
          {updateStatus && <code>{updateStatus.update_available ? `${updateStatus.latest_version} 업데이트 가능` : `현재 ${updateStatus.current_version}`}</code>}
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
        <div className="table-wrap"><table><thead><tr><th>시각</th><th>작업</th><th>관리자</th><th>대상</th><th>상세 정보</th></tr></thead><tbody>
          {audit.map((item) => <tr key={item.audit_id}><td>{formatTime(item.created_at)}</td><td>{item.action}</td><td>{item.actor}</td><td>{item.target_type} {item.target_id ?? ""}</td><td><code>{JSON.stringify(item.details)}</code></td></tr>)}
        </tbody></table></div>
      </section>

      <footer>{notice}</footer>
    </main>
  );
}

export default App;
