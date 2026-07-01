const SERVER_URL = (window.AKFES_CONFIG && window.AKFES_CONFIG.SERVER_URL ? window.AKFES_CONFIG.SERVER_URL : "http://127.0.0.1:5000").replace(/\/$/, "");

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

function setConnection(text) {
    connectionStatus.textContent = text;
}

function setResult(text, ok = null) {
    resultEl.textContent = text;
    const card = document.querySelector(".result-card");
    card.classList.remove("success", "fail");
    if (ok === true) card.classList.add("success");
    if (ok === false) card.classList.add("fail");
}

function log(text) {
    if (logEl.textContent === "로그 없음") logEl.textContent = "";
    const time = new Date().toLocaleTimeString();
    logEl.textContent += `[${time}] ${text}\n`;
    logEl.scrollTop = logEl.scrollHeight;
}

function renderPassword() {
    pwEl.textContent = "*".repeat(password.length);
}

function getMode() {
    return document.querySelector("input[name='mode']:checked").value;
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
    const count = Object.keys(keypadMap).length;

    if (isCalibrating) {
        mappingStatus.textContent = `매핑 중: [${CALIBRATION_SEQUENCE[calibrationIndex]}] 키를 누르세요. (${calibrationIndex + 1}/16)`;
    } else if (count >= 16) {
        mappingStatus.textContent = "매핑 완료";
    } else if (count > 0) {
        mappingStatus.textContent = `매핑 일부 저장됨: ${count}/16`;
    } else {
        mappingStatus.textContent = "기본 상태";
    }
}

function startCalibration() {
    keypadMap = {};
    isCalibrating = true;
    calibrationIndex = 0;
    password = "";
    renderPassword();
    renderMapStatus();
    setConnection("키패드 매핑 중입니다. 화면에 표시된 키를 누르세요.");
    log("매핑 시작");
}

function resetMapping() {
    keypadMap = {};
    isCalibrating = false;
    calibrationIndex = 0;
    sessionStorage.removeItem("hardwareCryptoKeypadMap");
    renderMapStatus();
    setConnection("키패드 매핑 초기화 완료");
    log("매핑 초기화");
}

function normalizePair(pairText) {
    const parts = pairText.split(",").map((x) => parseInt(x.trim(), 10)).filter((x) => !Number.isNaN(x));
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
        } else {
            renderMapStatus();
        }
        return;
    }

    const key = keypadMap[pair];
    if (!key) {
        setConnection("등록되지 않은 키입니다. 고급 설정에서 매핑을 진행하세요.");
        log(`등록되지 않은 핀쌍: ${pair}`);
        return;
    }

    handleKey(key);
}

function handleKey(key) {
    if (isProcessing) return;

    if (key === "#") {
        runProcess();
        return;
    }

    if (key === "*") {
        password = password.slice(0, -1);
        renderPassword();
        return;
    }

    if (/^[0-9A-D]$/.test(key)) {
        if (password.length >= 64) {
            setResult("비밀번호는 최대 64자까지 입력할 수 있습니다.", false);
            return;
        }
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

    if (raw.includes("PAIR:")) {
        handlePair(raw.slice(raw.indexOf("PAIR:") + 5).trim());
        return;
    }

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
    readBuffer = lines.pop();

    for (const line of lines) handleSerialLine(line);
}

async function sendArduinoCommand(command) {
    if (!port || !port.writable) return;

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
    return new Date(unixSeconds * 1000).toLocaleString();
}

function updateLoginStatus(text = null) {
    if (!loginStatus) return;
    if (text) {
        loginStatus.textContent = text;
        return;
    }
    loginStatus.textContent = sessionToken ? "로그인됨" : "로그인 필요";
}

async function loginWithLicenseKey() {
    const input = document.getElementById("licenseKey");
    const licenseKey = input.value.trim();
    if (!licenseKey) {
        updateLoginStatus("라이선스 KEY를 입력하세요.");
        return;
    }
    try {
        updateLoginStatus("KEY 검증 중...");
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
        updateLoginStatus(`로그인 완료 / KEY 만료: ${formatExpireTime(data.license_expires_at)}`);
    } catch (err) {
        sessionToken = "";
        sessionStorage.removeItem("hardwareCryptoSessionToken");
        updateLoginStatus(`로그인 실패: ${err.message}`);
    }
}

function logoutLicenseKey() {
    sessionToken = "";
    sessionStorage.removeItem("hardwareCryptoSessionToken");
    updateLoginStatus("로그아웃됨");
}

async function checkServer() {
    try {
        setConnection("서버 확인 중...");
        const res = await fetch(`${SERVER_URL}/health`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        setConnection("서버 연결 완료");
    } catch (err) {
        setConnection(`서버 연결 실패: ${err.message}`);
    }
}

function getDownloadName(disposition) {
    if (!disposition) return "result.bin";

    const utf8 = disposition.match(/filename\*=UTF-8''([^;]+)/i);
    if (utf8) return decodeURIComponent(utf8[1]);

    const normal = disposition.match(/filename="?([^"]+)"?/i);
    if (normal) return normal[1];

    return "result.bin";
}

async function runProcess() {
    if (isProcessing) return;

    if (!sessionToken) {
        setResult("라이선스 KEY 로그인이 필요합니다.", false);
        return;
    }

    const file = document.getElementById("file").files[0];
    if (!file) {
        setResult("파일을 먼저 선택하세요.", false);
        return;
    }

    if (!password) {
        setResult("키패드로 비밀번호를 입력하세요.", false);
        return;
    }

    isProcessing = true;
    setResult("처리 중...");

    try {
        const fd = new FormData();
        fd.append("file", file);
        fd.append("mode", getMode());
        fd.append("password", password);

        const res = await fetch(`${SERVER_URL}/process`, {
            method: "POST",
            headers: {
                "Authorization": `Bearer ${sessionToken}`
            },
            body: fd
        });

        if (!res.ok) {
            let message = "처리 실패";
            try {
                const data = await res.json();
                message = data.error || message;
            } catch {}
            throw new Error(message);
        }

        const blob = await res.blob();
        const filename = getDownloadName(res.headers.get("Content-Disposition"));
        const url = URL.createObjectURL(blob);

        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();

        setTimeout(() => URL.revokeObjectURL(url), 1000);

        await sendArduinoCommand("SUCCESS\n");
        setResult(`완료: ${filename}`, true);
        password = "";
        renderPassword();
    } catch (err) {
        await sendArduinoCommand("FAIL\n");
        if (err.message.includes("로그인") || err.message.includes("만료") || err.message.includes("토큰") || err.message.includes("인증")) {
            sessionToken = "";
            sessionStorage.removeItem("hardwareCryptoSessionToken");
            updateLoginStatus("세션 만료 또는 인증 실패. 다시 로그인하세요.");
        }

        setResult(`실패: ${err.message}`, false);
        password = "";
        renderPassword();
    } finally {
        isProcessing = false;
    }
}

async function disconnectArduino() {
    keepReading = false;

    if (readyTimer) {
        clearTimeout(readyTimer);
        readyTimer = null;
    }

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

    setConnection("아두이노 연결 해제됨");
}

async function connectArduino() {
    if (!("serial" in navigator)) {
        setConnection("Chrome 또는 Edge에서만 아두이노 연결이 가능합니다.");
        return;
    }

    await disconnectArduino();

    try {
        readySeen = false;
        readBuffer = "";
        setConnection("포트를 선택하세요.");
        port = await navigator.serial.requestPort();

        if (!port) {
            setConnection("포트 선택이 취소되었습니다.");
            setBadge(arduinoBadge, "Arduino", "");
            return;
        }

        setConnection("연결 중...");
        await port.open({
            baudRate: 9600,
            dataBits: 8,
            stopBits: 1,
            parity: "none",
            flowControl: "none",
            bufferSize: 255
        });

        await new Promise((resolve) => setTimeout(resolve, 1600));

        readyTimer = setTimeout(() => {
            if (!readySeen) {
                setConnection("포트는 열렸지만 READY 신호가 없습니다. 아두이노 업로드/배선을 확인하세요.");
            }
        }, 3500);

        const decoder = new TextDecoderStream();
        readableClosed = port.readable.pipeTo(decoder.writable).catch(() => {});
        reader = decoder.readable.getReader();
        keepReading = true;

        setConnection("아두이노 신호 대기 중...");

        while (keepReading) {
            const { value, done } = await reader.read();
            if (done) break;
            if (value) handleSerialText(value);
        }
    } catch (err) {
        setConnection(`아두이노 연결 실패: ${err.message}`);
        await disconnectArduino();
    }
}

function bindContactLinks() {
    document.querySelectorAll("[data-contact]").forEach((el) => {
        el.addEventListener("click", (event) => {
            event.preventDefault();

            const type = el.getAttribute("data-contact");
            const contacts = window.AKFES_CONTACTS || {};
            const url = contacts[type];

            if (!url) {
                setResult(`${type} 연락처가 아직 설정되지 않았습니다. client/static/contact_config.js에서 설정하세요.`, false);
                return;
            }

            window.open(url, "_blank", "noopener,noreferrer");
        });
    });

    document.querySelectorAll("[data-missing-contact]").forEach((el) => {
        el.addEventListener("click", (event) => {
            event.preventDefault();
            const type = el.getAttribute("data-missing-contact");
            setResult(`${type} 연락처가 아직 설정되지 않았습니다. client/static/contact_config.js에서 설정하세요.`, false);
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

    bindContactLinks();
    loadMap();
    updateLoginStatus();
}

document.addEventListener("DOMContentLoaded", bindEvents);
