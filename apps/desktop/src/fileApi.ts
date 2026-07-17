import { invoke } from "@tauri-apps/api/core";

import { ApiError } from "./auth";
import type { AuthSession } from "./auth";

export type FileOperationMode = "encrypt" | "decrypt";

interface ChallengeResponse {
  challenge: string;
  expires_at: number;
  algorithm: string;
  canonical_version: string;
}

interface FileOperationResponse {
  filename: string;
  data_base64: string;
  size_bytes: number;
  algorithm: string;
  key_derivation: string;
}

interface NativeSelectedFile {
  filename: string;
  bytes: number[];
  sizeBytes: number;
}

interface NativeSaveResult {
  status: "saved" | "cancelled";
  path: string | null;
}

export interface ProcessedFile {
  filename: string;
  bytes: Uint8Array;
  sizeBytes: number;
  algorithm: string;
  keyDerivation: string;
}

async function responseError(response: Response): Promise<ApiError> {
  try {
    const payload = await response.json() as { detail?: unknown };
    const detail = typeof payload.detail === "string" ? payload.detail : response.statusText;
    return new ApiError(detail || "서버 요청에 실패했습니다.", response.status);
  } catch {
    return new ApiError(response.statusText || "서버 요청에 실패했습니다.", response.status);
  }
}

function bytesToBase64(bytes: Uint8Array): string {
  const chunkSize = 0x8000;
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    const chunk = bytes.subarray(offset, offset + chunkSize);
    binary += String.fromCharCode(...chunk);
  }
  return btoa(binary);
}

function base64ToBytes(value: string): Uint8Array {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

function toHex(bytes: ArrayBuffer): string {
  return Array.from(new Uint8Array(bytes), (value) => value.toString(16).padStart(2, "0")).join("");
}

async function sha256Hex(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return toHex(digest);
}

async function calculateSignature(
  sessionToken: string,
  method: string,
  path: string,
  challenge: string,
  body: string,
  deviceId: string,
): Promise<string> {
  const canonical = [
    "AKFES-V2",
    method.toUpperCase(),
    path,
    challenge,
    await sha256Hex(body),
    deviceId,
  ].join("\n");
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(sessionToken),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(canonical));
  return toHex(signature);
}

async function issueChallenge(apiUrl: string, session: AuthSession): Promise<string> {
  const response = await fetch(`${apiUrl}/api/v2/auth/challenge`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${session.sessionToken}`,
      "X-AKFES-Device-ID": session.deviceId,
    },
  });
  if (!response.ok) throw await responseError(response);
  const payload = await response.json() as ChallengeResponse;
  if (payload.algorithm !== "HMAC-SHA256" || payload.canonical_version !== "AKFES-V2") {
    throw new Error("서버의 요청 서명 규칙이 클라이언트와 일치하지 않습니다.");
  }
  return payload.challenge;
}

export async function processFile(
  apiUrl: string,
  session: AuthSession,
  mode: FileOperationMode,
  file: File,
  password: string,
): Promise<ProcessedFile> {
  const fileBytes = new Uint8Array(await file.arrayBuffer());
  const path = `/api/v2/files/${mode}`;
  const body = JSON.stringify({
    filename: file.name,
    password,
    data_base64: bytesToBase64(fileBytes),
  });
  const challenge = await issueChallenge(apiUrl, session);
  const signature = await calculateSignature(
    session.sessionToken,
    "POST",
    path,
    challenge,
    body,
    session.deviceId,
  );

  const response = await fetch(`${apiUrl}${path}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${session.sessionToken}`,
      "Content-Type": "application/json",
      "X-AKFES-Device-ID": session.deviceId,
      "X-AKFES-Challenge": challenge,
      "X-AKFES-Signature": signature,
    },
    body,
  });
  if (!response.ok) throw await responseError(response);

  const payload = await response.json() as FileOperationResponse;
  const bytes = base64ToBytes(payload.data_base64);
  if (bytes.byteLength !== payload.size_bytes) {
    throw new Error("서버가 반환한 파일 크기 정보가 실제 데이터와 일치하지 않습니다.");
  }
  return {
    filename: payload.filename,
    bytes,
    sizeBytes: payload.size_bytes,
    algorithm: payload.algorithm,
    keyDerivation: payload.key_derivation,
  };
}

function browserDownload(result: ProcessedFile): void {
  const copiedBytes = new Uint8Array(result.bytes);
  const blob = new Blob([copiedBytes.buffer], { type: "application/octet-stream" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = result.filename;
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
}

function updateSaveStatus(message: string, path: string | null): void {
  const notice = document.querySelector<HTMLElement>(".notice");
  if (notice) notice.textContent = message;

  const resultList = document.querySelector<HTMLDListElement>(".result-state dl");
  if (!resultList) return;
  let row = resultList.querySelector<HTMLElement>("[data-akfes-save-status]");
  if (!row) {
    row = document.createElement("div");
    row.dataset.akfesSaveStatus = "true";
    row.innerHTML = "<dt>저장 상태</dt><dd></dd>";
    resultList.appendChild(row);
  }
  const value = row.querySelector<HTMLElement>("dd");
  if (value) value.textContent = path ?? message;
}

export async function downloadProcessedFile(result: ProcessedFile): Promise<void> {
  try {
    const outcome = await invoke<NativeSaveResult>("save_processed_file", {
      filename: result.filename,
      bytes: Array.from(result.bytes),
    });
    if (outcome.status === "cancelled") {
      updateSaveStatus("파일 저장을 취소했습니다. 결과는 앱 메모리에 유지됩니다.", null);
      return;
    }
    updateSaveStatus(`결과 파일을 저장했습니다: ${outcome.path ?? result.filename}`, outcome.path);
  } catch {
    browserDownload(result);
    updateSaveStatus("브라우저 다운로드 방식으로 결과 파일을 저장했습니다.", null);
  }
}

const nativePickerBypass = new WeakSet<HTMLInputElement>();
let nativePickerInstalled = false;

function installNativeFilePickerBridge(): void {
  if (nativePickerInstalled || typeof document === "undefined") return;
  nativePickerInstalled = true;

  document.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement) || target.type !== "file") return;
    if (!target.closest(".file-picker")) return;
    if (nativePickerBypass.has(target)) {
      nativePickerBypass.delete(target);
      return;
    }

    event.preventDefault();
    void invoke<NativeSelectedFile | null>("select_native_file")
      .then((selection) => {
        if (!selection) {
          const notice = document.querySelector<HTMLElement>(".notice");
          if (notice) notice.textContent = "파일 선택을 취소했습니다.";
          return;
        }
        const bytes = new Uint8Array(selection.bytes);
        if (bytes.byteLength !== selection.sizeBytes) {
          throw new Error("선택한 파일 크기 정보가 실제 데이터와 일치하지 않습니다.");
        }
        const file = new File([bytes], selection.filename, {
          type: "application/octet-stream",
          lastModified: Date.now(),
        });
        const transfer = new DataTransfer();
        transfer.items.add(file);
        target.files = transfer.files;
        target.dispatchEvent(new Event("change", { bubbles: true }));
      })
      .catch((error) => {
        const message = error instanceof Error ? error.message : String(error);
        const notice = document.querySelector<HTMLElement>(".notice");
        if (notice) notice.textContent = `네이티브 파일 선택 실패: ${message}`;
        nativePickerBypass.add(target);
        target.click();
      });
  }, true);
}

installNativeFilePickerBridge();
