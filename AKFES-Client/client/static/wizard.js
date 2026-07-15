document.addEventListener("DOMContentLoaded", () => {
  let currentStep = 1;
  const screens = [...document.querySelectorAll(".step-screen")];
  const indicators = [...document.querySelectorAll("[data-step-indicator]")];

  function showStep(step) {
    currentStep = Math.max(1, Math.min(4, step));
    screens.forEach((screen) => screen.classList.toggle("active", Number(screen.dataset.step) === currentStep));
    indicators.forEach((item) => {
      const itemStep = Number(item.dataset.stepIndicator);
      item.classList.toggle("active", itemStep === currentStep);
      item.classList.toggle("completed", itemStep < currentStep);
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  document.querySelectorAll("[data-next]").forEach((button) => button.addEventListener("click", () => showStep(currentStep + 1)));
  document.querySelectorAll("[data-prev]").forEach((button) => button.addEventListener("click", () => showStep(currentStep - 1)));
  document.querySelectorAll("[data-restart]").forEach((button) => button.addEventListener("click", () => showStep(3)));

  const loginStatus = document.getElementById("loginStatus");
  const connectionStatus = document.getElementById("connectionStatus");
  const result = document.getElementById("result");

  if (loginStatus) {
    new MutationObserver(() => {
      if (/로그인 완료|로그인됨/.test(loginStatus.textContent)) setTimeout(() => showStep(2), 350);
    }).observe(loginStatus, { childList: true, characterData: true, subtree: true });
  }

  if (connectionStatus) {
    new MutationObserver(() => {
      if (/아두이노 연결 완료/.test(connectionStatus.textContent)) setTimeout(() => showStep(3), 350);
    }).observe(connectionStatus, { childList: true, characterData: true, subtree: true });
  }

  if (result) {
    new MutationObserver(() => {
      if (/^완료:/.test(result.textContent.trim())) setTimeout(() => showStep(4), 400);
    }).observe(result, { childList: true, characterData: true, subtree: true });
  }

  showStep(1);
});