document.addEventListener("DOMContentLoaded", () => {
  const TOTAL_STEPS = 4;
  const screens = [...document.querySelectorAll(".step-screen")];
  const indicators = [...document.querySelectorAll("[data-step-indicator]")];
  const notice = document.getElementById("wizardNotice");
  const toastHost = document.getElementById("toastHost");
  const deviceNextBtn = document.getElementById("deviceNextBtn");
  const headerStage = document.getElementById("headerStage");
  const heroTitle = document.getElementById("heroTitle");
  const heroDescription = document.getElementById("heroDescription");
  const stepper = document.querySelector(".stepper");
  const splash = document.getElementById("splash");
  const licenseInput = document.getElementById("licenseKey");
  const toggleLicenseBtn = document.getElementById("toggleLicenseBtn");
  const loginStatus = document.getElementById("loginStatus");
  const connectionStatus = document.getElementById("connectionStatus");
  const result = document.getElementById("result");
  const fileInput = document.getElementById("file");
  const passwordDisplay = document.getElementById("pw");
  const progressTitle = document.getElementById("progressTitle");

  const stageCopy = {
    1: {
      header: "License Verification",
      title: "보안 세션을 시작하세요",
      description: "라이선스 인증부터 파일 처리까지 한 단계씩 안전하게 진행합니다."
    },
    2: {
      header: "Hardware Connection",
      title: "물리적 입력 장치를 연결하세요",
      description: "Arduino Uno와 키패드의 시리얼 연결 상태를 확인합니다."
    },
    3: {
      header: "Secure File Processing",
      title: "파일을 안전하게 처리하세요",
      description: "AES-256-GCM 암호화 또는 복호화를 실행합니다."
    },
    4: {
      header: "Process Result",
      title: "작업 결과를 확인하세요",
      description: "처리된 파일은 자동으로 저장되며 결과가 아래에 표시됩니다."
    }
  };

  let currentStep = 1;
  let authenticated = Boolean(sessionStorage.getItem("hardwareCryptoSessionToken"));
  let arduinoConnected = false;
  let processCompleted = false;
  let noticeTimer = null;
  let lastLoginText = "";
  let lastConnectionText = "";
  let lastResultText = "";

  function hideSplash() {
    window.setTimeout(() => {
      splash?.classList.add("hide");
      window.setTimeout(() => splash?.remove(), 650);
    }, 850);
  }

  function showNotice(message) {
    if (!notice) return;
    window.clearTimeout(noticeTimer);
    notice.textContent = message;
    notice.hidden = false;
    requestAnimationFrame(() => notice.classList.add("show"));
    noticeTimer = window.setTimeout(() => {
      notice.classList.remove("show");
      window.setTimeout(() => { notice.hidden = true; }, 230);
    }, 2500);
  }

  function toast(title, message, tone = "") {
    if (!toastHost) return;
    const item = document.createElement("div");
    item.className = `toast ${tone}`.trim();
    const strong = document.createElement("strong");
    const span = document.createElement("span");
    strong.textContent = title;
    span.textContent = message;
    item.append(strong, span);
    toastHost.appendChild(item);
    window.setTimeout(() => {
      item.classList.add("out");
      window.setTimeout(() => item.remove(), 300);
    }, 3300);
  }

  function canOpenStep(step) {
    if (step <= 1) return true;
    if (step === 2) return authenticated;
    if (step === 3) return authenticated && arduinoConnected;
    if (step === 4) return authenticated && arduinoConnected && processCompleted;
    return false;
  }

  function explainBlockedStep(step) {
    if (!authenticated) return "먼저 라이선스 인증을 완료하세요.";
    if (step >= 3 && !arduinoConnected) return "Arduino 연결을 완료해야 다음 단계로 이동할 수 있습니다.";
    if (step === 4 && !processCompleted) return "파일 처리를 완료한 후 결과 화면을 열 수 있습니다.";
    return "현재 단계에서는 해당 화면을 열 수 없습니다.";
  }

  function updateProgress(step) {
    const ratio = ((step - 1) / (TOTAL_STEPS - 1)) * 75;
    stepper?.style.setProperty("--step-progress", `${ratio}%`);
  }

  function updateHero(step) {
    const copy = stageCopy[step];
    if (!copy) return;
    if (headerStage) headerStage.textContent = copy.header;
    if (heroTitle) heroTitle.textContent = copy.title;
    if (heroDescription) heroDescription.textContent = copy.description;
  }

  function updateMeter() {
    const value = passwordDisplay?.textContent || "";
    const isEmpty = value.includes("대기 중") || value.length === 0;
    const length = isEmpty ? 0 : value.length;
    document.querySelectorAll(".password-meter i").forEach((bar, index) => {
      bar.classList.toggle("active", length >= (index + 1) * 2);
    });
  }

  function setResultVisual(text) {
    const card = document.querySelector(".result-card");
    if (!card) return;
    card.classList.remove("success", "fail");
    if (/^완료:/.test(text.trim())) card.classList.add("success");
    if (/^실패:/.test(text.trim())) card.classList.add("fail");
  }

  function showStep(step, options = {}) {
    const target = Math.max(1, Math.min(TOTAL_STEPS, Number(step) || 1));
    if (!options.force && !canOpenStep(target)) {
      showNotice(explainBlockedStep(target));
      return false;
    }

    const direction = target >= currentStep ? "forward" : "back";
    currentStep = target;

    screens.forEach((screen) => {
      const active = Number(screen.dataset.step) === currentStep;
      screen.hidden = !active;
      screen.classList.toggle("active", active);
      screen.classList.remove("enter-forward", "enter-back");
      if (active) {
        void screen.offsetWidth;
        screen.classList.add(direction === "forward" ? "enter-forward" : "enter-back");
      }
    });

    indicators.forEach((item) => {
      const itemStep = Number(item.dataset.stepIndicator);
      item.classList.toggle("active", itemStep === currentStep);
      item.classList.toggle("completed", itemStep < currentStep && canOpenStep(itemStep + 1));
      item.setAttribute("aria-current", itemStep === currentStep ? "step" : "false");
    });

    updateProgress(currentStep);
    updateHero(currentStep);
    document.querySelector(`.step-screen[data-step="${currentStep}"] h2`)?.focus?.({ preventScroll: true });
    window.scrollTo({ top: 0, behavior: "smooth" });
    return true;
  }

  function restartWork() {
    processCompleted = false;
    if (result) result.textContent = "아직 실행하지 않았습니다.";
    setResultVisual("");
    showStep(3, { force: authenticated && arduinoConnected });
    toast("새 작업 준비 완료", "파일과 비밀번호를 다시 선택하세요.", "success");
  }

  document.querySelectorAll("[data-next]").forEach((button) => {
    button.addEventListener("click", () => showStep(currentStep + 1));
  });

  document.querySelectorAll("[data-prev]").forEach((button) => {
    button.addEventListener("click", () => showStep(currentStep - 1, { force: true }));
  });

  document.querySelectorAll("[data-restart]").forEach((button) => {
    button.addEventListener("click", restartWork);
  });

  indicators.forEach((item) => {
    const open = () => showStep(Number(item.dataset.stepIndicator));
    item.addEventListener("click", open);
    item.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        open();
      }
    });
  });

  toggleLicenseBtn?.addEventListener("click", () => {
    if (!licenseInput) return;
    const showing = licenseInput.type === "text";
    licenseInput.type = showing ? "password" : "text";
    toggleLicenseBtn.setAttribute("aria-label", showing ? "라이선스 키 표시" : "라이선스 키 숨기기");
    licenseInput.focus();
  });

  document.addEventListener("keydown", (event) => {
    if (event.altKey && event.key === "ArrowRight") {
      event.preventDefault();
      showStep(currentStep + 1);
    }
    if (event.altKey && event.key === "ArrowLeft") {
      event.preventDefault();
      showStep(currentStep - 1, { force: true });
    }
  });

  if (loginStatus) {
    new MutationObserver(() => {
      const text = loginStatus.textContent.trim();
      if (text === lastLoginText) return;
      lastLoginText = text;

      const success = /로그인 완료|로그인됨/.test(text);
      const failure = /실패|만료|로그아웃|로그인 필요/.test(text);

      if (success) {
        authenticated = true;
        toast("라이선스 인증 완료", "보안 세션이 활성화되었습니다.", "success");
        window.setTimeout(() => showStep(2), 450);
      } else if (failure) {
        authenticated = false;
        arduinoConnected = false;
        processCompleted = false;
        if (currentStep > 1) showStep(1, { force: true });
        if (/실패|만료/.test(text)) toast("인증 오류", text, "error");
      }
    }).observe(loginStatus, { childList: true, characterData: true, subtree: true });
  }

  if (connectionStatus) {
    new MutationObserver(() => {
      const text = connectionStatus.textContent.trim();
      if (text === lastConnectionText) return;
      lastConnectionText = text;

      arduinoConnected = /아두이노 연결 완료/.test(text);
      if (deviceNextBtn) deviceNextBtn.disabled = !arduinoConnected;

      if (arduinoConnected) {
        toast("Arduino 연결 완료", "키패드 입력 장치가 준비되었습니다.", "success");
        window.setTimeout(() => showStep(3), 500);
      } else if (/실패|해제|READY 신호가 없습니다/.test(text)) {
        processCompleted = false;
        if (currentStep >= 3) showStep(2, { force: true });
        if (/실패|READY/.test(text)) toast("장치 연결 확인", text, "error");
      }
    }).observe(connectionStatus, { childList: true, characterData: true, subtree: true });
  }

  if (result) {
    new MutationObserver(() => {
      const text = result.textContent.trim();
      if (text === lastResultText) return;
      lastResultText = text;
      setResultVisual(text);

      if (/^완료:/.test(text)) {
        processCompleted = true;
        toast("파일 처리 완료", text.replace(/^완료:\s*/, ""), "success");
        window.setTimeout(() => showStep(4), 550);
      } else if (/^실패:/.test(text)) {
        processCompleted = false;
        toast("파일 처리 실패", text.replace(/^실패:\s*/, ""), "error");
      }

      if (progressTitle && /처리 중/.test(text)) {
        progressTitle.textContent = text.includes("복호화") ? "파일 복호화 중" : "파일 암호화 중";
      }
    }).observe(result, { childList: true, characterData: true, subtree: true });
  }

  if (passwordDisplay) {
    new MutationObserver(updateMeter).observe(passwordDisplay, { childList: true, characterData: true, subtree: true });
  }

  fileInput?.addEventListener("change", () => {
    const file = fileInput.files?.[0];
    if (file) toast("파일 선택 완료", `${file.name} 파일을 불러왔습니다.`);
  });

  document.querySelectorAll("input[name='mode']").forEach((input) => {
    input.addEventListener("change", () => {
      toast("작업 모드 변경", input.value === "encrypt" ? "암호화 모드를 선택했습니다." : "복호화 모드를 선택했습니다.");
    });
  });

  authenticated = Boolean(sessionStorage.getItem("hardwareCryptoSessionToken"));
  if (authenticated) {
    toast("기존 세션 복원", "저장된 인증 세션을 불러왔습니다.", "success");
    showStep(2, { force: true });
  } else {
    showStep(1, { force: true });
  }

  updateMeter();
  hideSplash();
});
