document.addEventListener("DOMContentLoaded", () => {
  let currentStep = 1;
  let noticeTimer = null;

  const screens = [...document.querySelectorAll(".step-screen")];
  const indicators = [...document.querySelectorAll("[data-step-indicator]")];
  const loginStatus = document.getElementById("loginStatus");
  const connectionStatus = document.getElementById("connectionStatus");
  const result = document.getElementById("result");
  const notice = document.getElementById("wizardNotice");
  const deviceNextButton = document.getElementById("deviceNextBtn");

  const hasSession = () => Boolean(sessionStorage.getItem("hardwareCryptoSessionToken"));
  const isArduinoConnected = () => /아두이노 연결 완료/.test(connectionStatus?.textContent || "");
  const hasSuccessfulResult = () => /^완료:/.test((result?.textContent || "").trim());

  function showNotice(message) {
    if (!notice) return;
    notice.textContent = message;
    notice.hidden = false;
    notice.classList.remove("show");
    requestAnimationFrame(() => notice.classList.add("show"));
    clearTimeout(noticeTimer);
    noticeTimer = setTimeout(() => {
      notice.classList.remove("show");
      setTimeout(() => { notice.hidden = true; }, 180);
    }, 2600);
  }

  function canOpenStep(step) {
    if (step <= 1) return true;
    if (!hasSession()) {
      showNotice("먼저 라이선스 인증을 완료하세요.");
      return false;
    }
    if (step >= 3 && !isArduinoConnected()) {
      showNotice("Arduino 연결을 완료해야 파일 작업으로 이동할 수 있습니다.");
      return false;
    }
    if (step === 4 && !hasSuccessfulResult()) {
      showNotice("파일 처리가 완료된 뒤 결과 화면을 열 수 있습니다.");
      return false;
    }
    return true;
  }

  function updateDeviceNextState() {
    if (deviceNextButton) deviceNextButton.disabled = !isArduinoConnected();
  }

  function showStep(step, options = {}) {
    const nextStep = Math.max(1, Math.min(4, Number(step) || 1));
    if (!options.force && !canOpenStep(nextStep)) return false;

    currentStep = nextStep;
    screens.forEach((screen) => {
      const active = Number(screen.dataset.step) === currentStep;
      screen.classList.toggle("active", active);
      screen.hidden = !active;
      screen.setAttribute("aria-hidden", String(!active));
    });

    indicators.forEach((item) => {
      const itemStep = Number(item.dataset.stepIndicator);
      item.classList.toggle("active", itemStep === currentStep);
      item.classList.toggle("completed", itemStep < currentStep);
      item.setAttribute("aria-current", itemStep === currentStep ? "step" : "false");
    });

    updateDeviceNextState();
    document.querySelector(`.step-screen[data-step="${currentStep}"] h1`)?.focus?.({ preventScroll: true });
    window.scrollTo({ top: 0, behavior: options.instant ? "auto" : "smooth" });
    return true;
  }

  document.querySelectorAll("[data-next]").forEach((button) => {
    button.addEventListener("click", () => showStep(currentStep + 1));
  });

  document.querySelectorAll("[data-prev]").forEach((button) => {
    button.addEventListener("click", () => showStep(currentStep - 1, { force: true }));
  });

  document.querySelectorAll("[data-restart]").forEach((button) => {
    button.addEventListener("click", () => {
      if (result) result.textContent = "새 작업을 준비합니다.";
      showStep(isArduinoConnected() ? 3 : 2, { force: true });
    });
  });

  indicators.forEach((item) => {
    item.addEventListener("click", () => {
      const step = Number(item.dataset.stepIndicator);
      if (step <= currentStep) showStep(step, { force: true });
      else showStep(step);
    });
  });

  if (loginStatus) {
    new MutationObserver(() => {
      const text = loginStatus.textContent || "";
      if (/로그인 완료|로그인됨/.test(text) && hasSession()) {
        setTimeout(() => showStep(2), 250);
      }
      if (/로그아웃|로그인 실패|세션 만료|인증 실패/.test(text)) {
        showStep(1, { force: true });
      }
    }).observe(loginStatus, { childList: true, characterData: true, subtree: true });
  }

  if (connectionStatus) {
    new MutationObserver(() => {
      updateDeviceNextState();
      const connected = isArduinoConnected();
      const badge = document.getElementById("arduinoBadge");
      if (badge) {
        badge.className = `badge ${connected ? "success" : "danger"}`;
        badge.innerHTML = `<span class="badge-dot"></span>Arduino · ${connected ? "연결됨" : "연결 안 됨"}`;
      }
      if (connected && currentStep === 2) setTimeout(() => showStep(3), 250);
    }).observe(connectionStatus, { childList: true, characterData: true, subtree: true });
  }

  if (result) {
    new MutationObserver(() => {
      if (hasSuccessfulResult()) setTimeout(() => showStep(4), 300);
    }).observe(result, { childList: true, characterData: true, subtree: true });
  }

  window.addEventListener("keydown", (event) => {
    if (event.altKey && event.key === "ArrowLeft" && currentStep > 1) {
      event.preventDefault();
      showStep(currentStep - 1, { force: true });
    }
  });

  updateDeviceNextState();
  showStep(hasSession() ? 2 : 1, { force: true, instant: true });
});