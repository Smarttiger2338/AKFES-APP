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
  failed_attempts: number;
  locked_until: string | null;
}

interface LocalServerStatus {
  running: boolean;
  owned_by_admin_app: boolean;
  port: number;
  server_url: string;
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

interface LocalAuditEntry {
  action: string;
  created_at: string;
  detail: string;
}

const formatTime = (timestamp: number | null) =>
  timestamp ? new Date(timestamp * 1000).toLocaleString() : "-";

function App() {
  const [serverUrl, setServerUrl] = useState("http://127.0.0.1:8000");
  const [adminToken, setAdminToken] = useState("");
  const [actor, setActor] = useState("local-admin");
  const [durationDays, setDurationDays] = useState(30);
  const [label, setLabel] = useState("");
  const [licenses, setLicenses] = useState<LicenseSummary[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [localAudit, setLocalAudit] = useState<LocalAuditEntry[]>([]);
  const [issued, setIssued] = useState<IssuedLicense | null>(null);
  const [security, setSecurity] = useState<AdminSecurityStatus | null>(null);
  const [unlocked, setUnlocked] = useState(false);
  const [pin, setPin] = useState("");
  const [newPin, setNewPin] = useState("");
  const [exportPath, setExportPath] = useState("");
  const [importPath, setImportPath] = useState("");
  const [serverStatus, setServerStatus] = useState<LocalServerStatus | null>(null);
  const [updateStatus, setUpdateStatus] = useState<UpdateStatus | null>(null);
  const [notice, setNotice] = useState("Checking administrator security status.");
  const [busy, setBusy] = useState(false);

  const headers = useMemo(
    () => ({
      "Content-Type": "application/json",
      "X-AKFES-Admin-Token": adminToken,
      "X-AKFES-Admin-Actor": actor.trim() || "local-admin",
    }),
    [adminToken, actor],
  );

  const api = async <T,>(path: string, init: RequestInit = {}, baseUrl = serverUrl): Promise<T> => {
    const response = await fetch(`${baseUrl.replace(/\/$/, "")}${path}`, {
      ...init,
      headers: { ...headers, ...(init.headers ?? {}) },
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail ?? `HTTP ${response.status}`);
    }
    return response.json() as Promise<T>;
  };

  const loadLocalAudit = async () => {
    const rows = await invoke<LocalAuditEntry[]>("list_local_admin_audit");
    setLocalAudit(rows);
  };

  const loadServerStatus = async () => {
    const status = await invoke<LocalServerStatus>("get_local_server_status");
    setServerStatus(status);
    setServerUrl(status.server_url);
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
      const status = await loadServerStatus();
      const [licenseRows, auditRows] = await Promise.all([
        api<LicenseSummary[]>("/api/v2/admin/licenses?limit=200", {}, status.server_url),
        api<AuditEntry[]>("/api/v2/admin/audit?limit=100", {}, status.server_url),
        loadLocalAudit(),
      ]);
      setLicenses(licenseRows);
      setAudit(auditRows);
      setNotice(`Loaded ${licenseRows.length} licenses.`);
    } catch (error) {
      setNotice(`Refresh failed: ${String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void Promise.all([
      invoke<AdminSecurityStatus>("get_admin_security_status"),
      loadServerStatus(),
      loadLocalAudit(),
    ])
      .then(([status]) => {
        setSecurity(status);
        if (!status.pin_set) {
          setUnlocked(true);
          setNotice("Set an administrator PIN before daily use.");
          void loadAdminToken();
        } else {
          setNotice("Enter the administrator PIN.");
        }
      })
      .catch((error) => setNotice(`Startup failed: ${String(error)}`));
  }, []);

  useEffect(() => {
    if (adminToken && unlocked) void refresh();
  }, [adminToken, unlocked]);

  const unlockWithPin = async () => {
    setBusy(true);
    try {
      const ok = await invoke<boolean>("verify_admin_pin", { pin });
      if (!ok) {
        const next = await invoke<AdminSecurityStatus>("get_admin_security_status");
        setSecurity(next);
        setNotice(`Wrong PIN. Failed attempts: ${next.failed_attempts}/5.`);
        return;
      }
      setUnlocked(true);
      setPin("");
      await loadAdminToken();
      await loadLocalAudit();
      setNotice("Administrator panel unlocked.");
    } catch (error) {
      setNotice(`PIN check failed: ${String(error)}`);
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
      await loadLocalAudit();
      setNotice("Administrator PIN saved.");
    } catch (error) {
      setNotice(`PIN save failed: ${String(error)}`);
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
      setNotice("License created and copied. This key cannot be viewed again.");
      await refresh();
    } catch (error) {
      setNotice(`Issue failed: ${String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const mutateLicense = async (licenseId: number, action: "revoke" | "reset") => {
    const reason = window.prompt(
      action === "revoke" ? "Revocation reason" : "Device binding reset reason",
      "Admin request",
    );
    if (reason === null) return;
    const path = action === "revoke"
      ? `/api/v2/admin/licenses/${licenseId}/revoke`
      : `/api/v2/admin/licenses/${licenseId}/device-binding/reset`;
    setBusy(true);
    try {
      await api(path, { method: "POST", body: JSON.stringify({ reason }) });
      setNotice(action === "revoke" ? "License revoked." : "Device binding reset.");
      await refresh();
    } catch (error) {
      setNotice(`Action failed: ${String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const rotateAdminToken = async () => {
    const confirmed = window.confirm(
      "Create a new local administrator token?\n\nThe local server will restart and the old token will stop working.",
    );
    if (!confirmed) return;

    setBusy(true);
    try {
      const token = await invoke<string>("rotate_local_admin_token");
      setAdminToken(token);
      setNotice("New administrator token created and server restarted.");
      await refresh();
    } catch (error) {
      setNotice(`Token rotation failed: ${String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const backupDatabase = async () => {
    setBusy(true);
    try {
      const result = await invoke<BackupResult>("backup_local_database");
      setNotice(`Backup created: ${result.path}`);
      await refresh();
    } catch (error) {
      setNotice(`Backup failed: ${String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const restoreLatestBackup = async () => {
    const confirmed = window.confirm(
      "Restore the latest local backup?\n\nThe current database will be backed up first.",
    );
    if (!confirmed) return;

    setBusy(true);
    try {
      const result = await invoke<BackupResult>("restore_latest_database_backup");
      setNotice(`Latest backup restored: ${result.path}`);
      await refresh();
    } catch (error) {
      setNotice(`Restore failed: ${String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const exportLatestBackup = async () => {
    setBusy(true);
    try {
      const result = await invoke<BackupResult>("export_latest_database_backup", {
        destinationDirectory: exportPath,
      });
      setNotice(`Backup exported: ${result.path}`);
      await loadLocalAudit();
    } catch (error) {
      setNotice(`Export failed: ${String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  const importBackup = async () => {
    setBusy(true);
    try {
      const result = await invoke<BackupResult>("import_database_backup", {
        sourceDirectory: importPath,
      });
      setNotice(`Backup imported: ${result.path}`);
      await refresh();
    } catch (error) {
      setNotice(`Import failed: ${String(error)}`);
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
        setNotice(`Update check failed: ${status.error}`);
      } else if (status.update_available) {
        setNotice(`New version available: ${status.latest_version}. Open the release page from GitHub.`);
      } else {
        setNotice("Current version is up to date.");
      }
    } catch (error) {
      setNotice(`Update check failed: ${String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  if (!unlocked) {
    return (
      <main className="shell lock-shell">
        <section className="card lock-card">
          <span>AKFES</span>
          <h1>Administrator Lock</h1>
          <label>Administrator PIN<input type="password" value={pin} onChange={(e) => setPin(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") void unlockWithPin(); }} autoFocus /></label>
          <button className="primary" onClick={() => void unlockWithPin()} disabled={busy || !pin}>Unlock</button>
          {security?.locked_until && <small>Locked until Unix time {security.locked_until}</small>}
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
          <button onClick={() => void checkUpdates()} disabled={busy}>Check Updates</button>
          <button onClick={() => void rotateAdminToken()} disabled={busy || !adminToken}>Rotate Admin Token</button>
          <button onClick={() => void refresh()} disabled={busy || !adminToken}>Refresh</button>
        </div>
      </header>

      <section className="connection card">
        <label>Server URL<input value={serverUrl} onChange={(e) => setServerUrl(e.target.value)} /></label>
        <label>Admin Name<input value={actor} onChange={(e) => setActor(e.target.value)} /></label>
        <label>Admin Token<input type="password" value={adminToken} onChange={(e) => setAdminToken(e.target.value)} /></label>
      </section>

      <section className="grid">
        <article className="card issue">
          <h2>Issue License</h2>
          <label>Days<input type="number" min="1" max="3650" value={durationDays} onChange={(e) => setDurationDays(Number(e.target.value))} /></label>
          <label>Label<input value={label} maxLength={120} onChange={(e) => setLabel(e.target.value)} placeholder="Customer or purpose" /></label>
          <button className="primary" onClick={() => void issueLicense()} disabled={busy || !adminToken}>Create License</button>
          {issued && <div className="issued"><small>Shown once</small><code>{issued.license_key}</code><button onClick={() => void navigator.clipboard.writeText(issued.license_key)}>Copy</button></div>}
        </article>

        <article className="card stats">
          <h2>Overview</h2>
          <strong>{licenses.filter((x) => x.status === "active").length}</strong><span>Active licenses</span>
          <strong>{licenses.filter((x) => x.device_bound).length}</strong><span>Device bindings</span>
          <strong>{licenses.reduce((sum, x) => sum + x.active_session_count, 0)}</strong><span>Active sessions</span>
        </article>
      </section>

      <section className="tools">
        <article className="card status-card">
          <h2>Server Status</h2>
          <p><strong>{serverStatus?.running ? "Running" : "Stopped"}</strong><span>{serverStatus?.server_url ?? serverUrl}</span></p>
          <p><strong>{serverStatus?.owned_by_admin_app ? "Managed" : "External"}</strong><span>Server ownership</span></p>
          <p><strong>{serverStatus?.config_protected ? "Protected" : "Check"}</strong><span>Local config encryption</span></p>
          <p><strong>{serverStatus?.backup_count ?? 0}</strong><span>Local backups</span></p>
          {serverStatus?.startup_error && <code>{serverStatus.startup_error}</code>}
        </article>

        <article className="card admin-tools">
          <h2>Operations</h2>
          <div className="tool-row">
            <button onClick={() => void backupDatabase()} disabled={busy}>Create Backup</button>
            <button onClick={() => void restoreLatestBackup()} disabled={busy || !serverStatus?.backup_count}>Restore Latest</button>
          </div>
          <div className="tool-row">
            <input value={exportPath} onChange={(e) => setExportPath(e.target.value)} placeholder="Export destination folder" />
            <button onClick={() => void exportLatestBackup()} disabled={busy || !exportPath.trim() || !serverStatus?.backup_count}>Export Backup</button>
          </div>
          <div className="tool-row">
            <input value={importPath} onChange={(e) => setImportPath(e.target.value)} placeholder="Import source backup folder" />
            <button onClick={() => void importBackup()} disabled={busy || !importPath.trim()}>Import Backup</button>
          </div>
          <div className="tool-row">
            <input type="password" value={newPin} onChange={(e) => setNewPin(e.target.value)} placeholder={security?.pin_set ? "New admin PIN" : "Set admin PIN"} />
            <button onClick={() => void saveNewPin()} disabled={busy || newPin.trim().length < 4}>{security?.pin_set ? "Change PIN" : "Set PIN"}</button>
          </div>
          {updateStatus && <code>{updateStatus.update_available ? `${updateStatus.latest_version} available` : `Current ${updateStatus.current_version}`}</code>}
        </article>
      </section>

      <section className="card table-card">
        <h2>Licenses</h2>
        <div className="table-wrap"><table><thead><tr><th>ID</th><th>Label</th><th>Status</th><th>Expires</th><th>Device</th><th>Sessions</th><th>Actions</th></tr></thead><tbody>
          {licenses.map((item) => <tr key={item.license_id}><td>{item.license_id}</td><td>{item.label ?? "-"}</td><td><span className={`badge ${item.status}`}>{item.status}</span></td><td>{formatTime(item.expires_at)}</td><td>{item.device_bound ? "Bound" : "Unbound"}</td><td>{item.active_session_count}</td><td><button onClick={() => void mutateLicense(item.license_id, "reset")} disabled={!item.device_bound || item.status !== "active"}>Reset Device</button><button className="danger" onClick={() => void mutateLicense(item.license_id, "revoke")} disabled={item.status === "revoked"}>Revoke</button></td></tr>)}
        </tbody></table></div>
      </section>

      <section className="card table-card">
        <h2>Server Audit</h2>
        <div className="table-wrap"><table><thead><tr><th>Time</th><th>Action</th><th>Admin</th><th>Target</th><th>Details</th></tr></thead><tbody>
          {audit.map((item) => <tr key={item.audit_id}><td>{formatTime(item.created_at)}</td><td>{item.action}</td><td>{item.actor}</td><td>{item.target_type} {item.target_id ?? ""}</td><td><code>{JSON.stringify(item.details)}</code></td></tr>)}
        </tbody></table></div>
      </section>

      <section className="card table-card">
        <h2>Local Admin Audit</h2>
        <div className="table-wrap"><table><thead><tr><th>Unix Time</th><th>Action</th><th>Detail</th></tr></thead><tbody>
          {localAudit.map((item, index) => <tr key={`${item.created_at}-${index}`}><td>{item.created_at}</td><td>{item.action}</td><td><code>{item.detail}</code></td></tr>)}
        </tbody></table></div>
      </section>

      <footer>{notice}</footer>
    </main>
  );
}

export default App;
