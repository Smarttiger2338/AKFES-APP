import { invoke } from "@tauri-apps/api/core";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { useMemo, useState } from "react";
import type { ChangeEvent } from "react";

interface SerialPortInfo {
  name: string;
  portType: string;
}

const steps = ["라이선스", "장치 연결", "파일 작업", "결과"] as const;

function App() {
  const appWindow = useMemo(() => getCurrentWindow(), []);
  const [step, setStep] = useState(0);
  const [ports, setPorts] = useState<SerialPortInfo[]>([]);
  const [selectedPort, setSelectedPort] = useState("");
  const [loadingPorts, setLoadingPorts] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [mode, setMode] = useState<"encrypt" | "decrypt">("encrypt");
  const [notice, setNotice] = useState("Tauri v2 초기화가 완료되었습니다.");

  const refreshPorts = async () => {
    setLoadingPorts(true);
    try {
      const result = await invoke<SerialPortInfo[]>("list_serial_ports");
      setPorts(result);
      if (result.length > 0 && !selectedPort) {
        setSelectedPort(result[0].name);
      }
      setNotice(result.length > 0 ? `${result.length}개의 포트를 찾았습니다.` : "사용 가능한 시리얼 포트가 없습니다.");
    } catch (error) {
      setNotice(`포트 검색 실패: ${String(error)}`);
    } finally {
      setLoadingPorts(false);
    }
  };

  const onFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] ?? null;
    setSelectedFile(file);
    setNotice(file ? `${file.name} 파일을 선택했습니다.` : "선택된 파일이 없습니다.");
  };

  const next = () => setStep((current) => Math.min(current + 1, steps.length - 1));
  const previous = () => setStep((current) => Math.max(current - 1, 0));

  return (
    <div className="app-shell">
      <header className="titlebar" data-tauri-drag-region>
        <div className="brand" data-tauri-drag-region>
          <span className="brand-mark">A</span>
          <div data-tauri-drag-region>
            <strong>AKFES</strong>
            <small>Secure Desktop v2</small>
          </div>
        </div>
        <div className="window-actions">
          <button aria-label="최소화" onClick={() => appWindow.minimize()}>—</button>
          <button aria-label="최대화 또는 복원" onClick={() => appWindow.toggleMaximize()}>□</button>
          <button className="close" aria-label="닫기" onClick={() => appWindow.close()}>×</button>
        </div>
      </header>

      <main className="workspace">
        <section className="hero">
          <div>
            <span className="eyebrow">ZERO TRUST FILE SECURITY</span>
            <h1>안전한 파일 작업을 시작합니다</h1>
            <p>Electron과 PySide6를 제거하고 Tauri v2, Rust, React, TypeScript로 다시 구성한 데스크톱 클라이언트입니다.</p>
          </div>
          <span className="status-pill">초기화 단계</span>
        </section>

        <nav className="stepper" aria-label="작업 단계">
          {steps.map((label, index) => (
            <button
              key={label}
              className={index === step ? "active" : index < step ? "complete" : ""}
              onClick={() => setStep(index)}
            >
              <span>{index + 1}</span>
              {label}
            </button>
          ))}
        </nav>

        <section className="panel stage-panel">
          {step === 0 && (
            <div className="stage-grid">
              <div>
                <span className="section-number">01</span>
                <h2>라이선스 인증</h2>
                <p>FastAPI 서버 이전 단계에서 실제 서버 인증과 장치 바인딩을 연결합니다.</p>
              </div>
              <div className="form-card">
                <label htmlFor="license">라이선스 키</label>
                <input id="license" type="password" placeholder="서버 연결 전" disabled />
                <div className="inline-note">현재 화면은 Tauri UI 구조 확인용이며 인증 성공을 위조하지 않습니다.</div>
              </div>
            </div>
          )}

          {step === 1 && (
            <div className="stage-grid">
              <div>
                <span className="section-number">02</span>
                <h2>Arduino 연결</h2>
                <p>시리얼 포트 검색은 브라우저 API가 아니라 Rust 명령으로 실행됩니다.</p>
              </div>
              <div className="form-card">
                <label htmlFor="port">사용 가능한 포트</label>
                <select id="port" value={selectedPort} onChange={(event) => setSelectedPort(event.target.value)}>
                  <option value="">포트를 선택하세요</option>
                  {ports.map((port) => (
                    <option key={port.name} value={port.name}>{port.name} · {port.portType}</option>
                  ))}
                </select>
                <button className="secondary" onClick={refreshPorts} disabled={loadingPorts}>
                  {loadingPorts ? "검색 중..." : "포트 새로고침"}
                </button>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="stage-grid">
              <div>
                <span className="section-number">03</span>
                <h2>파일 작업</h2>
                <p>서버 이전이 완료되면 이 화면에서 암호화 또는 복호화 요청을 전송합니다.</p>
              </div>
              <div className="form-card">
                <div className="mode-switch" role="group" aria-label="작업 모드">
                  <button className={mode === "encrypt" ? "selected" : ""} onClick={() => setMode("encrypt")}>암호화</button>
                  <button className={mode === "decrypt" ? "selected" : ""} onClick={() => setMode("decrypt")}>복호화</button>
                </div>
                <label className="file-picker">
                  <input type="file" onChange={onFileChange} />
                  <strong>{selectedFile?.name ?? "파일 선택"}</strong>
                  <span>{selectedFile ? `${(selectedFile.size / 1024).toFixed(1)} KB` : "모든 파일 형식 지원 예정"}</span>
                </label>
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="result-state">
              <div className="result-icon">A</div>
              <h2>Tauri v2 기본 구조 준비 완료</h2>
              <p>다음 작업은 FastAPI 서버 이전과 실제 암호화 요청 연결입니다.</p>
              <dl>
                <div><dt>장치 포트</dt><dd>{selectedPort || "미선택"}</dd></div>
                <div><dt>작업 모드</dt><dd>{mode === "encrypt" ? "암호화" : "복호화"}</dd></div>
                <div><dt>선택 파일</dt><dd>{selectedFile?.name ?? "미선택"}</dd></div>
              </dl>
            </div>
          )}

          <footer className="panel-footer">
            <span className="notice">{notice}</span>
            <div>
              <button className="secondary" onClick={previous} disabled={step === 0}>이전</button>
              <button className="primary" onClick={next} disabled={step === steps.length - 1}>다음</button>
            </div>
          </footer>
        </section>
      </main>
    </div>
  );
}

export default App;
