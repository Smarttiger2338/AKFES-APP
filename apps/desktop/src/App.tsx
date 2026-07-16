import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import type { UnlistenFn } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent } from "react";

interface SerialPortInfo {
  name: string;
  portType: string;
}

type SerialStatus = "disconnected" | "connecting" | "connected" | "error";
type KeypadMap = Record<string, string>;

const steps = ["라이선스", "장치 연결", "파일 작업", "결과"] as const;
const calibrationSequence = ["1", "2", "3", "A", "4", "5", "6", "B", "7", "8", "9", "C", "*", "0", "#", "D"] as const;
const keypadMapStorageKey = "akfes-v2-keypad-map";

function loadKeypadMap(): KeypadMap {
  try {
    const stored = localStorage.getItem(keypadMapStorageKey);
    return stored ? (JSON.parse(stored) as KeypadMap) : {};
  } catch {
    return {};
  }
}

function normalizePair(rawPair: string): string | null {
  const pins = rawPair
    .split(",")
    .map((value) => Number.parseInt(value.trim(), 10))
    .filter((value) => Number.isFinite(value));

  if (pins.length !== 2) return null;
  pins.sort((left, right) => left - right);
  return `${pins[0]},${pins[1]}`;
}

function App() {
  const appWindow = useMemo(() => getCurrentWindow(), []);
  const [step, setStep] = useState(0);
  const [ports, setPorts] = useState<SerialPortInfo[]>([]);
  const [selectedPort, setSelectedPort] = useState("");
  const [loadingPorts, setLoadingPorts] = useState(false);
  const [serialStatus, setSerialStatus] = useState<SerialStatus>("disconnected");
  const [serialLog, setSerialLog] = useState<string[]>([]);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [mode, setMode] = useState<"encrypt" | "decrypt">("encrypt");
  const [password, setPassword] = useState("");
  const [keypadMap, setKeypadMap] = useState<KeypadMap>(() => loadKeypadMap());
  const [calibrationIndex, setCalibrationIndex] = useState<number | null>(null);
  const [notice, setNotice] = useState("Arduino 연결 모듈이 준비되었습니다.");

  const keypadMapRef = useRef(keypadMap);
  const calibrationIndexRef = useRef<number | null>(calibrationIndex);
  const passwordRef = useRef(password);
  const handshakeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    keypadMapRef.current = keypadMap;
    localStorage.setItem(keypadMapStorageKey, JSON.stringify(keypadMap));
  }, [keypadMap]);

  useEffect(() => {
    calibrationIndexRef.current = calibrationIndex;
  }, [calibrationIndex]);

  useEffect(() => {
    passwordRef.current = password;
  }, [password]);

  const clearHandshakeTimer = useCallback(() => {
    if (handshakeTimerRef.current) {
      clearTimeout(handshakeTimerRef.current);
      handshakeTimerRef.current = null;
    }
  }, []);

  const appendLog = useCallback((message: string) => {
    const timestamp = new Date().toLocaleTimeString();
    setSerialLog((current) => [...current.slice(-79), `[${timestamp}] ${message}`]);
  }, []);

  const handleKey = useCallback((key: string) => {
    if (key === "#") {
      setNotice(passwordRef.current ? `비밀번호 ${passwordRef.current.length}자리 입력을 확인했습니다.` : "입력된 비밀번호가 없습니다.");
      return;
    }

    if (key === "*") {
      setPassword((current) => current.slice(0, -1));
      return;
    }

    if (/^[0-9A-D]$/.test(key)) {
      setPassword((current) => {
        if (current.length >= 64) {
          setNotice("비밀번호는 최대 64자리까지 입력할 수 있습니다.");
          return current;
        }
        return `${current}${key}`;
      });
    }
  }, []);

  const handleSerialLine = useCallback((line: string) => {
    appendLog(`수신: ${line}`);

    if (line.includes("READY")) {
      clearHandshakeTimer();
      setSerialStatus("connected");
      setNotice("Arduino 준비 신호를 확인했습니다.");
      return;
    }

    if (line.startsWith("PAIR:")) {
      const pair = normalizePair(line.slice(5));
      if (!pair) {
        setNotice("Arduino에서 잘못된 키패드 핀쌍을 받았습니다.");
        return;
      }

      const currentCalibrationIndex = calibrationIndexRef.current;
      if (currentCalibrationIndex !== null) {
        const key = calibrationSequence[currentCalibrationIndex];
        setKeypadMap((current) => ({ ...current, [pair]: key }));
        appendLog(`매핑: ${pair} → ${key}`);

        const nextIndex = currentCalibrationIndex + 1;
        if (nextIndex >= calibrationSequence.length) {
          setCalibrationIndex(null);
          setNotice("키패드 16개 키 매핑을 완료했습니다.");
        } else {
          setCalibrationIndex(nextIndex);
          setNotice(`[${calibrationSequence[nextIndex]}] 키를 눌러주세요. (${nextIndex + 1}/16)`);
        }
        return;
      }

      const mappedKey = keypadMapRef.current[pair];
      if (!mappedKey) {
        setNotice(`등록되지 않은 키패드 핀쌍입니다: ${pair}`);
        return;
      }

      handleKey(mappedKey);
      return;
    }

    if (line.startsWith("KEY:")) {
      const key = line.slice(4, 5);
      if (/^[0-9A-D*#]$/.test(key)) handleKey(key);
    }
  }, [appendLog, clearHandshakeTimer, handleKey]);

  useEffect(() => {
    let active = true;
    const unlisteners: UnlistenFn[] = [];

    Promise.all([
      listen<string>("serial-opened", (event) => {
        if (!active) return;
        appendLog(`포트 열림: ${event.payload}`);
        setSerialStatus("connecting");
      }),
      listen<string>("serial-line", (event) => {
        if (active) handleSerialLine(event.payload);
      }),
      listen<string>("serial-error", (event) => {
        if (!active) return;
        clearHandshakeTimer();
        appendLog(`오류: ${event.payload}`);
        setSerialStatus("error");
        setNotice(event.payload);
      }),
      listen<string>("serial-disconnected", (event) => {
        if (!active) return;
        clearHandshakeTimer();
        appendLog(`연결 종료: ${event.payload}`);
        setSerialStatus("disconnected");
        setNotice("Arduino 연결이 종료되었습니다.");
      }),
    ]).then((registered) => {
      if (active) {
        unlisteners.push(...registered);
      } else {
        registered.forEach((unlisten) => unlisten());
      }
    });

    return () => {
      active = false;
      clearHandshakeTimer();
      unlisteners.forEach((unlisten) => unlisten());
    };
  }, [appendLog, clearHandshakeTimer, handleSerialLine]);

  const refreshPorts = async () => {
    setLoadingPorts(true);
    try {
      const result = await invoke<SerialPortInfo[]>("list_serial_ports");
      setPorts(result);
      if (result.length > 0 && !result.some((port) => port.name === selectedPort)) {
        setSelectedPort(result[0].name);
      }
      setNotice(result.length > 0 ? `${result.length}개의 포트를 찾았습니다.` : "사용 가능한 시리얼 포트가 없습니다.");
    } catch (error) {
      setNotice(`포트 검색 실패: ${String(error)}`);
    } finally {
      setLoadingPorts(false);
    }
  };

  const connectPort = async () => {
    if (!selectedPort) {
      setNotice("연결할 포트를 먼저 선택하세요.");
      return;
    }

    clearHandshakeTimer();
    setSerialLog([]);
    setSerialStatus("connecting");
    setNotice(`${selectedPort} 포트를 열고 Arduino 준비 신호를 기다립니다.`);

    try {
      await invoke("connect_serial_port", { portName: selectedPort, baudRate: 9600 });
      handshakeTimerRef.current = setTimeout(() => {
        setSerialStatus("error");
        setNotice("Arduino READY 신호를 받지 못했습니다. 포트와 펌웨어를 확인하세요.");
      }, 6_000);
    } catch (error) {
      setSerialStatus("error");
      setNotice(`Arduino 연결 실패: ${String(error)}`);
    }
  };

  const disconnectPort = async () => {
    clearHandshakeTimer();
    try {
      await invoke("disconnect_serial_port");
    } catch (error) {
      setNotice(`연결 종료 실패: ${String(error)}`);
    }
  };

  const sendLedCommand = async (command: "SUCCESS" | "FAIL") => {
    if (serialStatus !== "connected") {
      setNotice("LED 테스트 전에 Arduino를 연결하세요.");
      return;
    }

    try {
      await invoke("write_serial_command", { command });
      appendLog(`송신: ${command}`);
      setNotice(command === "SUCCESS" ? "초록색 LED 테스트 명령을 전송했습니다." : "빨간색 LED 테스트 명령을 전송했습니다.");
    } catch (error) {
      setNotice(`LED 명령 전송 실패: ${String(error)}`);
    }
  };

  const startCalibration = () => {
    if (serialStatus !== "connected") {
      setNotice("키패드 매핑 전에 Arduino를 연결하세요.");
      return;
    }

    setKeypadMap({});
    setPassword("");
    setCalibrationIndex(0);
    setNotice(`[${calibrationSequence[0]}] 키를 눌러주세요. (1/16)`);
    appendLog("키패드 매핑 시작");
  };

  const resetCalibration = () => {
    setKeypadMap({});
    setCalibrationIndex(null);
    setPassword("");
    localStorage.removeItem(keypadMapStorageKey);
    setNotice("저장된 키패드 매핑을 초기화했습니다.");
    appendLog("키패드 매핑 초기화");
  };

  const onFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] ?? null;
    setSelectedFile(file);
    setNotice(file ? `${file.name} 파일을 선택했습니다.` : "선택된 파일이 없습니다.");
  };

  const next = () => {
    if (step === 1 && serialStatus !== "connected") {
      setNotice("Arduino 연결을 완료한 뒤 다음 단계로 이동하세요.");
      return;
    }
    if (step === 2 && (!selectedFile || !password)) {
      setNotice("파일 선택과 키패드 비밀번호 입력을 모두 완료하세요.");
      return;
    }
    setStep((current) => Math.min(current + 1, steps.length - 1));
  };

  const previous = () => setStep((current) => Math.max(current - 1, 0));
  const mappedKeyCount = Object.keys(keypadMap).length;
  const mappingLabel = calibrationIndex !== null
    ? `[${calibrationSequence[calibrationIndex]}] 입력 대기 · ${calibrationIndex + 1}/16`
    : mappedKeyCount >= calibrationSequence.length
      ? "매핑 완료"
      : `${mappedKeyCount}/16 저장됨`;
  const serialStatusLabel = serialStatus === "connected"
    ? "Arduino 연결됨"
    : serialStatus === "connecting"
      ? "연결 확인 중"
      : serialStatus === "error"
        ? "연결 오류"
        : "연결 안 됨";
  const nextDisabled = step === steps.length - 1
    || (step === 1 && serialStatus !== "connected")
    || (step === 2 && (!selectedFile || !password));

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
            <h1>하드웨어 키패드 입력을 연결합니다</h1>
            <p>Rust가 시리얼 포트를 직접 열고 Arduino의 READY 신호와 키패드 핀쌍을 수신합니다. 서버 인증과 파일 암호화는 다음 이전 단계에서 연결됩니다.</p>
          </div>
          <span className={`status-pill serial-${serialStatus}`}>{serialStatusLabel}</span>
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
                <p>FastAPI 서버 이전 단계에서 실제 서버 인증, 세션 토큰, 장치 바인딩을 연결합니다.</p>
              </div>
              <div className="form-card">
                <label htmlFor="license">라이선스 키</label>
                <input id="license" type="password" placeholder="FastAPI 이전 전" disabled />
                <div className="inline-note">현재 단계에서는 인증 성공을 임의로 표시하지 않습니다. Arduino 연결 기능만 실제로 동작합니다.</div>
              </div>
            </div>
          )}

          {step === 1 && (
            <div className="stage-grid serial-stage">
              <div>
                <span className="section-number">02</span>
                <h2>Arduino 연결</h2>
                <p>포트 열기, READY 핸드셰이크, 키패드 데이터 수신, 상태 LED 명령을 Rust에서 처리합니다.</p>
                <div className={`device-status ${serialStatus}`}>
                  <span className="device-dot" />
                  <div>
                    <strong>{serialStatusLabel}</strong>
                    <small>{selectedPort || "포트 미선택"}</small>
                  </div>
                </div>
              </div>
              <div className="form-card serial-card">
                <label htmlFor="port">사용 가능한 포트</label>
                <select id="port" value={selectedPort} onChange={(event) => setSelectedPort(event.target.value)} disabled={serialStatus === "connecting" || serialStatus === "connected"}>
                  <option value="">포트를 선택하세요</option>
                  {ports.map((port) => (
                    <option key={port.name} value={port.name}>{port.name} · {port.portType}</option>
                  ))}
                </select>
                <div className="button-row">
                  <button className="secondary" onClick={refreshPorts} disabled={loadingPorts || serialStatus === "connecting" || serialStatus === "connected"}>
                    {loadingPorts ? "검색 중..." : "포트 새로고침"}
                  </button>
                  {serialStatus === "connected" || serialStatus === "connecting" ? (
                    <button className="secondary danger" onClick={disconnectPort}>연결 해제</button>
                  ) : (
                    <button className="primary" onClick={connectPort} disabled={!selectedPort}>Arduino 연결</button>
                  )}
                </div>

                <div className="mapping-panel">
                  <div>
                    <span>키패드 매핑</span>
                    <strong>{mappingLabel}</strong>
                  </div>
                  <div className="button-row compact">
                    <button className="secondary" onClick={startCalibration}>16키 매핑</button>
                    <button className="secondary" onClick={resetCalibration}>초기화</button>
                  </div>
                </div>

                <div className="button-row led-tests">
                  <button className="secondary success-test" onClick={() => sendLedCommand("SUCCESS")}>초록 LED 테스트</button>
                  <button className="secondary fail-test" onClick={() => sendLedCommand("FAIL")}>빨강 LED 테스트</button>
                </div>

                <pre className="serial-log" aria-label="시리얼 통신 로그">
                  {serialLog.length > 0 ? serialLog.join("\n") : "시리얼 로그가 여기에 표시됩니다."}
                </pre>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="stage-grid">
              <div>
                <span className="section-number">03</span>
                <h2>파일 작업 준비</h2>
                <p>Arduino 키패드에서 비밀번호를 입력합니다. 별표는 한 글자 삭제, 우물정자는 입력 확인으로 동작합니다.</p>
                <div className="password-summary">
                  <span>키패드 비밀번호</span>
                  <strong>{password ? "●".repeat(password.length) : "입력 대기"}</strong>
                  <small>{password.length}/64자리</small>
                  <button className="secondary" onClick={() => setPassword("")} disabled={!password}>비밀번호 지우기</button>
                </div>
              </div>
              <div className="form-card">
                <div className="mode-switch" role="group" aria-label="작업 모드">
                  <button className={mode === "encrypt" ? "selected" : ""} onClick={() => setMode("encrypt")}>암호화</button>
                  <button className={mode === "decrypt" ? "selected" : ""} onClick={() => setMode("decrypt")}>복호화</button>
                </div>
                <label className="file-picker">
                  <input type="file" onChange={onFileChange} />
                  <strong>{selectedFile?.name ?? "파일 선택"}</strong>
                  <span>{selectedFile ? `${(selectedFile.size / 1024).toFixed(1)} KB` : "모든 파일 형식 지원"}</span>
                </label>
                <div className="inline-note">실제 파일 전송과 암호화·복호화는 FastAPI 이전 후 활성화됩니다.</div>
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="result-state">
              <div className="result-icon">A</div>
              <h2>하드웨어 입력 단계 완료</h2>
              <p>Arduino 연결과 키패드 비밀번호 수신이 실제로 연결되었습니다. 이 화면은 파일 암호화 성공을 의미하지 않습니다.</p>
              <dl>
                <div><dt>장치 포트</dt><dd>{selectedPort || "미선택"}</dd></div>
                <div><dt>장치 상태</dt><dd>{serialStatusLabel}</dd></div>
                <div><dt>키패드 매핑</dt><dd>{mappedKeyCount}/16</dd></div>
                <div><dt>비밀번호 길이</dt><dd>{password.length}자리</dd></div>
                <div><dt>작업 모드</dt><dd>{mode === "encrypt" ? "암호화" : "복호화"}</dd></div>
                <div><dt>선택 파일</dt><dd>{selectedFile?.name ?? "미선택"}</dd></div>
              </dl>
            </div>
          )}

          <footer className="panel-footer">
            <span className="notice">{notice}</span>
            <div>
              <button className="secondary" onClick={previous} disabled={step === 0}>이전</button>
              <button className="primary" onClick={next} disabled={nextDisabled}>다음</button>
            </div>
          </footer>
        </section>
      </main>
    </div>
  );
}

export default App;
