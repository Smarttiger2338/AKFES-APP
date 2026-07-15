const SERVER_URL = (window.AKFES_CONFIG?.SERVER_URL || "http://127.0.0.1:5000").replace(/\/$/, "");

let sessionToken = sessionStorage.getItem("hardwareCryptoSessionToken") || "";
let password = "";
let port = null;
let reader = null;
let readableClosed = null;
let readBuffer = "";
let keepReading = false;
let isProcessing = false;
let readyTimer = null;
let readySeen = false;
let serverOnline = false;

const CALIBRATION_SEQUENCE = ["1", "2", "3", "A", "4", "5", "6", "B", "7", "8", "9", "C", "*", "0", "#", "D"];
let keypadMap = {};
let isCalibrating = false;
let calibrationIndex = 0;

let connectionStatus;
let resultEl;
let pwEl;
let logEl;
let mappingStatus;
let loginStatus;
let serverBadge;
let arduinoBadge;
let sessionBadge;
let fileNameEl;
let progressWrap;

function setBadge(element, label, state = "", tone = "") {
    if (!element) return;
    element.className = `badge ${tone}`.trim();
    element.innerHTML = `<span class="badge-dot"></span>${label}${state ? ` · ${state}` : ""}`;
}

function setConnection(text, tone = "") {
    if (connectionStatus) connectionStatus.textContent = text;
    if (/완료|연결됨|대기 중/.test(text)) setBadge(arduinoBadge, "Arduino", "연결됨", "success");
    else if (/실패|없습니다|해제/.test(text)) setBadge(arduinoBadge, "Arduino", "오프라인", "danger");
    else setBadge(arduinoBadge, "Arduino", "확인 중", tone || "warning");
}

function setProgress(active) {
    if (!progressWrap) return;
    progressWrap.hidden = !active;
    progressWrap.classList.toggle("active", active);
}

function setResult(text, ok = null) {
    if (!resultEl) return;
    resultEl.textContent = text;
    const card = document.querySelector(".result-card");
    card?.classList.remove("success", "fail");
    if (ok === true) card?.classList.add("success");
    if (ok === false) card?.classList.add("fail");
}

function log(text) {
    if (!logEl) return;
    if (logEl.textContent === "로그 없음") logEl.textContent = "";
    const time = new Date().toLocaleTimeString("ko-KR", { hour12: false });
    logEl.textContent += `[${time}] ${text}\n`;
    logEl.scrollTop = logEl.scrollHeight;
}

function renderPassword() {
    if (!pwEl) return;
    pwEl.textContent = password ? "•".repeat(password.length) : "키패드 입력 대기 중";
    pwEl.classList.toggle("empty", !password);
}

function getMode() {
    return document.querySelector("input[name='mode']:checked")?.value || "encrypt";
}

function formatBytes(bytes) {
    if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
    const units = ["B", "KB", "MB", "GB"];
    const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
    return `${(bytes / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function updateSelectedFile(file) {
    if (!fileNameEl) return;
    fileNameEl.textContent = file ? `${file.name} · ${formatBytes(file.size)}` : "선택된 파일 없음";
    fileNameEl.classList.toggle("selected", Boolean(file));
}

function loadMap() {
    try {
        keypadMap = JSON.parse(sessionStorage.getItem("hardwareCryptoKeypadMap") || "{}");
    } catch {
        keypadMap = {};
    }
    renderMapStatus();
}

function saveMap() {
    sessionStorage.setItem("hardwareCryptoKeypadMap", JSON.stringify(keypadMap));
    renderMapStatus();
}

function renderMapStatus() {
    if (!mappingStatus) return;
    const count = Object.keys(keypadMap).length;
    if (isCalibrating) mappingStatus.textContent = `매핑 중: [${CALIBRATION_SEQUENCE[calibrationIndex]}] 키를 누르세요. (${calibrationIndex + 1}/16)`;
    else if (count >= 16) mappingStatus.textContent = "매핑 완료";
    else if (count > 0) mappingStatus.textContent = `매핑 일부 저장됨: ${count}/16`;
    else mappingStatus.textContent = "기본 상태";
}

function startCalibration() {
    keypadMap = {};
    isCalibrating = true;
    calibrationIndex = 0;
    password = "";
    renderPassword();
    renderMapStatus();
    setConnection("키패드 매핑 중입니다. 표시된 키를 누르세요.");
    log("키패드 매핑 시작");
}

function resetMapping() {
    keypadMap = {};
    isCalibrating = false;
    calibrationIndex = 0;
    sessionStorage.removeItem("hardwareCryptoKeypadMap");
    renderMapStatus();
    setConnection("키패드 매핑 초기화 완료");
    log("키패드 매핑 초기화");
}

function normalizePair(pairText) {
    const parts = pairText.split(",").map((x) => Number.parseInt(x.trim(), 10)).filter(Number.isFinite);
    if (parts.length !== 2) return null;
    parts.sort((a, b) => a - b);
    return `${parts[0]},${parts[1]}`;
}

function handlePair(pairText) {
    const pair = normalizePair(pairText);
    if (!pair) return;
    if (isCalibrating) {
        const key = CALIBRATION_SEQUENCE[calibrationIndex];
        keypadMap[pair] = key;
        log(`매핑: ${pair} → ${key}`);
        calibrationIndex += 1;
        if (calibrationIndex >= CALIBRATION_SEQUENCE.length) {
            isCalibrating = false;
            saveMap();
            setConnection("키패드 매핑 완료");
        } else renderMapStatus();
        return;
    }
    const key = keypadMap[pair];
    if (!key) {
        setConnection("등록되지 않은 키입니다. 고급 설정에서 매핑하세요.", "warning");
        log(`등록되지 않은 핀쌍: ${pair}`);
        return;
    }
    handleKey(key);
}

function handleKey(key) {
    if (isProcessing) return;
    if (key === "#") return void runProcess();
    if (key === "*") {
        password = password.slice(0, -1);
        renderPassword();
        return;
    }
    if (/^[0-9A-D]$/.test(key)) {
        if (password.length >= 64) return setResult("비밀번호는 최대 64자까지 입력할 수 있습니다.", false);
        password += key;
        renderPassword();
    }
}

function handleSerialLine(line) {
    const raw = line.replace(/\r/g, "");
    const trimmed = raw.trim();
    if (!trimmed && !raw.includes("PAIR:") && !raw.includes("KEY:")) return;
    if (trimmed.includes("READY")) {
        readySeen = true;
        if (readyTimer) clearTimeout(readyTimer);
        setConnection("아두이노 연결 완료");
        log(trimmed);
        return;
    }
    if (raw.includes("PAIR:")) return void handlePair(raw.slice(raw.indexOf("PAIR:") + 5).trim());
    if (raw.includes("KEY:")) {
        const key = raw.slice(raw.indexOf("KEY:") + 4, raw.indexOf("KEY:") + 5);
        if (/^[0-9A-D*#]$/.test(key)) handleKey(key);
        return;
    }
    log(trimmed);
}

function handleSerialText(text) {
    log(`수신: ${JSON.stringify(text)}`);
    readBuffer += text;
    const lines = readBuffer.split(/\n/);
    readBuffer = lines.pop() || "";
    lines.forEach(handleSerialLine);
}

async function sendArduinoCommand(command) {
    if (!port?.writable) return;
    try {
        const writer = port.writable.getWriter();
        await writer.write(new TextEncoder().encode(command));
        writer.releaseLock();
    } catch (err) {
        log(`아두이노 명령 실패: ${err.message}`);
    }
}

function formatExpireTime(unixSeconds) {
    if (!unixSeconds) return "알 수 없음";
    return new Date(unixSeconds * 1000).toLocaleString("ko-KR");
}

function updateLoginStatus(text = null, tone = "") {
    if (!loginStatus) return;
    loginStatus.textContent = text || (sessionToken ? "로그인됨" : "로그인 필요");
    if (sessionToken) setBadge(sessionBadge, "Session", "인증됨", "success");
    else setBadge(sessionBadge, "Session", "미인증", tone || "danger");
}

async function loginWithLicenseKey() {
    const input = document.getElementById("licenseKey");
    const licenseKey = input.value.trim();
    if (!licenseKey) return updateLoginStatus("라이선스 KEY를 입력하세요.", "warning");
    try {
        updateLoginStatus("KEY 검증 중...", "warning");
        const res = await fetch(`${SERVER_URL}/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ license_key: licenseKey })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "로그인 실패");
        sessionToken = data.session_token;
        sessionStorage.setItem("hardwareCryptoSessionToken", sessionToken);
        input.value = "";
        updateLoginStatus(`로그인 완료 · KEY 만료: ${formatExpireTime(data.license_expires_at)}`);
        log("라이선스 인증 완료");
    } catch (err) {
        sessionToken = "";
        sessionStorage.removeItem("hardwareCryptoSessionToken");
        updateLoginStatus(`로그인 실패: ${err.message}`, "danger");
        log(`라이선스 인증 실패: ${err.message}`);
    }
}

function logoutLicenseKey() {
    sessionToken = "";
    sessionStorage.removeItem("hardwareCryptoSessionToken");
    updateLoginStatus("로그아웃됨", "danger");
    log("세션 로그아웃");
}

async function checkServer() {
    try {
        setBadge(serverBadge, "Server", "확인 중", "warning");
        const res = await fetch(`${SERVER_URL}/health`, { cache: "no-store" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        serverOnline = true;
        setBadge(serverBadge, "Server", "온라인", "success");
        if (!port) connectionStatus.textContent = "서버 연결 완료 · 아두이노 연결 대기";
        log("서버 상태 확인 완료");
    } catch (err) {
        serverOnline = false;
        setBadge(serverBadge, "Server", "오프라인", "danger");
        connectionStatus.textContent = `서버 연결 실패: ${err.message}`;
        log(`서버 연결 실패: ${err.message}`);
    }
}

function getDownloadName(disposition) {
    if (!disposition) return "result.bin";
    const utf8 = disposition.match(/filename\*=UTF-8''([^;]+)/i);
    if (utf8) return decodeURIComponent(utf8[1]);
    const normal = disposition.match(/filename="?([^";]+)"?/i);
    return normal ? normal[1] : "result.bin";
}

async function runProcess() {
    if (isProcessing) return;
    if (!sessionToken) return setResult("라이선스 KEY 로그인이 필요합니다.", false);
    const file = document.getElementById("file").files[0];
    if (!file) return setResult("파일을 먼저 선택하세요.", false);
    if (!password) return setResult("키패드로 비밀번호를 입력하세요.", false);

    isProcessing = true;
    setProgress(true);
    setResult(`${getMode() === "encrypt" ? "암호화" : "복호화"} 처리 중...`);
    document.getElementById("runBtn").disabled = true;

    try {
        const fd = new FormData();
        fd.append("file", file);
        fd.append("mode", getMode());
        fd.append("password", password);
        const res = await fetch(`${SERVER_URL}/process`, {
            method: "POST",
            headers: { Authorization: `Bearer ${sessionToken}` },
            body: fd
        });
        if (!res.ok) {
            let message = "처리 실패";
            try { message = (await res.json()).error || message; } catch {}
            throw new Error(message);
        }
        const blob = await res.blob();
        const filename = getDownloadName(res.headers.get("Content-Disposition"));
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = filename;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
        await sendArduinoCommand("SUCCESS\n");
        setResult(`완료: ${filename}`, true);
        log(`파일 처리 완료: ${filename}`);
        password = "";
        renderPassword();
    } catch (err) {
        await sendArduinoCommand("FAIL\n");
        if (/로그인|만료|토큰|인증/.test(err.message)) {
            sessionToken = "";
            sessionStorage.removeItem("hardwareCryptoSessionToken");
            updateLoginStatus("세션 만료 또는 인증 실패. 다시 로그인하세요.", "danger");
        }
        setResult(`실패: ${err.message}`, false);
        log(`파일 처리 실패: ${err.message}`);
        password = "";
        renderPassword();
    } finally {
        isProcessing = false;
        setProgress(false);
        document.getElementById("runBtn").disabled = false;
    }
}

async function disconnectArduino() {
    keepReading = false;
    if (readyTimer) clearTimeout(readyTimer);
    readyTimer = null;
    if (reader) {
        try { await reader.cancel(); } catch {}
        try { reader.releaseLock(); } catch {}
        reader = null;
    }
    if (readableClosed) {
        try { await readableClosed; } catch {}
        readableClosed = null;
    }
    if (port) {
        try { await port.close(); } catch {}
        port = null;
    }
    setConnection("아두이노 연결 해제됨", "danger");
}

async function connectArduino() {
    if (!("serial" in navigator)) return setConnection("현재 환경에서 Web Serial을 지원하지 않습니다.", "danger");
    await disconnectArduino();
    try {
        readySeen = false;
        readBuffer = "";
        setConnection("포트를 선택하세요.", "warning");
        port = await navigator.serial.requestPort();
        if (!port) return setConnection("포트 선택이 취소되었습니다.", "danger");
        setConnection("아두이노 연결 중...", "warning");
        await port.open({ baudRate: 9600, dataBits: 8, stopBits: 1, parity: "none", flowControl: "none", bufferSize: 255 });
        await new Promise((resolve) => setTimeout(resolve, 1600));
        readyTimer = setTimeout(() => {
            if (!readySeen) setConnection("포트는 열렸지만 READY 신호가 없습니다.", "warning");
        }, 3500);
        const decoder = new TextDecoderStream();
        readableClosed = port.readable.pipeTo(decoder.writable).catch(() => {});
        reader = decoder.readable.getReader();
        keepReading = true;
        setConnection("아두이노 신호 대기 중...", "warning");
        while (keepReading) {
            const { value, done } = await reader.read();
            if (done) break;
            if (value) handleSerialText(value);
        }
    } catch (err) {
        setConnection(`아두이노 연결 실패: ${err.message}`, "danger");
        await disconnectArduino();
    }
}

function bindContactLinks() {
    document.querySelectorAll("[data-contact]").forEach((element) => {
        element.addEventListener("click", (event) => {
            event.preventDefault();
            const type = element.dataset.contact;
            const url = (window.AKFES_CONTACTS || {})[type];
            if (!url) return setResult(`${type} 연락처가 설정되지 않았습니다.`, false);
            window.open(url, "_blank", "noopener,noreferrer");
        });
    });
}

function bindDropZone() {
    const input = document.getElementById("file");
    const zone = document.getElementById("dropZone");
    if (!input || !zone) return;
    zone.addEventListener("click", () => input.click());
    zone.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") input.click();
    });
    ["dragenter", "dragover"].forEach((name) => zone.addEventListener(name, (event) => {
        event.preventDefault();
        zone.classList.add("dragging");
    }));
    ["dragleave", "drop"].forEach((name) => zone.addEventListener(name, (event) => {
        event.preventDefault();
        zone.classList.remove("dragging");
    }));
    zone.addEventListener("drop", (event) => {
        const file = event.dataTransfer.files?.[0];
        if (!file) return;
        const transfer = new DataTransfer();
        transfer.items.add(file);
        input.files = transfer.files;
        input.dispatchEvent(new Event("change"));
    });
    input.addEventListener("change", () => updateSelectedFile(input.files[0]));
}

function bindNavigation() {
    document.querySelectorAll(".nav-item").forEach((item) => {
        item.addEventListener("click", () => {
            document.querySelectorAll(".nav-item").forEach((entry) => entry.classList.remove("active"));
            item.classList.add("active");
        });
    });
}

function bindEvents() {
    connectionStatus = document.getElementById("connectionStatus");
    resultEl = document.getElementById("result");
    pwEl = document.getElementById("pw");
    logEl = document.getElementById("serialLog");
    mappingStatus = document.getElementById("mappingStatus");
    loginStatus = document.getElementById("loginStatus");
    serverBadge = document.getElementById("serverBadge");
    arduinoBadge = document.getElementById("arduinoBadge");
    sessionBadge = document.getElementById("sessionBadge");
    fileNameEl = document.getElementById("fileName");
    progressWrap = document.getElementById("progressWrap");

    document.getElementById("loginBtn").addEventListener("click", loginWithLicenseKey);
    document.getElementById("logoutBtn").addEventListener("click", logoutLicenseKey);
    document.getElementById("serverBtn").addEventListener("click", checkServer);
    document.getElementById("connectBtn").addEventListener("click", connectArduino);
    document.getElementById("disconnectBtn").addEventListener("click", disconnectArduino);
    document.getElementById("runBtn").addEventListener("click", runProcess);
    document.getElementById("clearBtn").addEventListener("click", () => {
        password = "";
        renderPassword();
        setResult("비밀번호를 초기화했습니다.");
    });
    document.getElementById("calibrateBtn").addEventListener("click", startCalibration);
    document.getElementById("resetMapBtn").addEventListener("click", resetMapping);
    document.getElementById("licenseKey").addEventListener("keydown", (event) => {
        if (event.key === "Enter") loginWithLicenseKey();
    });

    bindContactLinks();
    bindDropZone();
    bindNavigation();
    loadMap();
    renderPassword();
    updateSelectedFile(document.getElementById("file").files[0]);
    updateLoginStatus();
    setBadge(serverBadge, "Server", "확인 전", "warning");
    setBadge(arduinoBadge, "Arduino", "연결 안 됨", "danger");
    checkServer();
}

document.addEventListener("DOMContentLoaded", bindEvents);
