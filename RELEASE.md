# AKFES Release Guide

AKFES는 사용자 앱, 관리자 앱, FastAPI 사이드카를 하나의 버전으로 배포합니다.

## 릴리스 구성

GitHub 태그 `vX.Y.Z`를 push하면 `.github/workflows/release.yml`이 다음 파일을 생성합니다.

- `AKFES-vX.Y.Z-Windows-x64-Setup.exe`
- `AKFES-License-Manager-vX.Y.Z-Windows-x64-Setup.exe`
- `akfes-server-vX.Y.Z-Windows-x64.exe`
- `SHA256SUMS.txt`

각 설치 프로그램에는 동일한 FastAPI 서버 사이드카가 포함됩니다.

## 버전 준비

릴리스 태그와 다음 파일의 `version`이 모두 같아야 합니다.

- `package.json`
- `apps/desktop/package.json`
- `apps/admin/package.json`
- `apps/desktop/src-tauri/tauri.conf.json`
- `apps/admin/src-tauri/tauri.conf.json`

예를 들어 버전이 `2.0.0`이라면 태그는 `v2.0.0`이어야 합니다.

## 릴리스 명령

```bash
git checkout main
git pull
git tag -a v2.0.0 -m "AKFES v2.0.0"
git push origin v2.0.0
```

워크플로가 테스트와 빌드를 통과하면 GitHub Release가 자동 생성됩니다.

## 코드 서명

현재 워크플로는 Tauri 업데이트 서명용 다음 GitHub Actions Secret을 사용할 준비가 되어 있습니다.

- `TAURI_SIGNING_PRIVATE_KEY`
- `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`

Windows SmartScreen 경고를 줄이려면 별도의 Authenticode 코드 서명 인증서가 필요합니다. 인증서를 발급받기 전에는 빌드가 정상이어도 Windows에서 "알 수 없는 게시자" 경고가 표시될 수 있습니다.

인증서와 비밀번호는 저장소에 커밋하지 말고 GitHub Actions Secret 또는 조직의 보안 비밀 저장소에 보관해야 합니다.

## 릴리스 전 확인

1. FastAPI Ruff와 pytest 통과
2. 사용자·관리자 React 빌드 통과
3. 사용자·관리자 Rust `cargo check` 통과
4. PyInstaller 서버 `/health` 스모크 테스트 통과
5. 사용자 앱 설치·실행·종료 확인
6. 관리자 앱 설치·실행·라이선스 발급 확인
7. Arduino 연결·키패드 입력·LED 확인
8. 암호화 후 복호화하여 원본 해시 일치 확인
9. `SHA256SUMS.txt`와 배포 파일 해시 확인
10. Windows Defender와 SmartScreen에서 수동 확인

## 데이터 위치

런타임 데이터는 설치 폴더가 아닌 사용자 앱 데이터에 저장됩니다.

```text
%LOCALAPPDATA%\AKFES\
```

주요 파일:

- `akfes.sqlite3`: 라이선스·세션·감사 로그
- `server-runtime.json`: 로컬 서버 비밀값
- `license-manager-startup-error.txt`: 관리자 앱 시작 오류 기록

제거 후에도 데이터가 남을 수 있으므로 완전 초기화가 필요한 경우 앱을 종료한 뒤 이 폴더를 별도로 삭제합니다.

## 알려진 제한

- 실제 브랜드 아이콘은 아직 임시 아이콘을 대체해야 합니다.
- Authenticode 인증서가 없으면 Windows 게시자 경고가 발생할 수 있습니다.
- 현재 AES-GCM 파일 처리는 파일 전체를 메모리에 적재합니다.
- 자동 업데이트 UI는 서명 키와 안정적인 업데이트 호스팅 정책을 확정한 뒤 활성화해야 합니다.
