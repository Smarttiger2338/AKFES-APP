# AKFES v2 Migration

이 브랜치는 AKFES를 Tauri v2 기반 데스크톱 애플리케이션으로 리팩터링하는 작업 공간입니다.

- Desktop: Tauri v2 + Rust + React + TypeScript
- Server: FastAPI + Uvicorn
- Hardware: Arduino UNO + USB Serial
- Security target: 서버 중심 권한 검증, 장치 바인딩, 일회용 챌린지, 요청 서명, AES-256-GCM

## 완료된 작업

- [x] Tauri v2 + React + TypeScript 데스크톱 구조
- [x] Rust 시리얼 검색·연결·해제·백그라운드 수신
- [x] Arduino `READY`, `PAIR:`, `KEY:` 처리와 키패드 매핑
- [x] FastAPI 서버 기본 구조와 보안 헤더
- [x] SQLite 기반 라이선스·세션 저장소
- [x] 라이선스 발급·검증·목록·취소
- [x] 취소된 라이선스의 세션 즉시 무효화
- [x] 관리자 감사 로그
- [x] HMAC 다이제스트 기반 라이선스 키·세션 토큰 저장
- [x] 만료 시간이 있는 일회용 챌린지 발급
- [x] HTTP 메서드·경로·본문 해시·장치 ID 기반 HMAC-SHA256 요청 서명
- [x] 챌린지 재사용 방지와 세션별 챌린지 바인딩
- [x] 첫 로그인 장치에 라이선스 자동 바인딩
- [x] 다른 장치 로그인과 장치 ID 없는 요청 차단
- [x] 장치 ID 원문 대신 HMAC 다이제스트 저장
- [x] 관리자 장치 바인딩 초기화와 기존 세션 무효화
- [x] AES-256-GCM 파일 암호화·복호화 서비스
- [x] PBKDF2-HMAC-SHA256 256비트 키 파생
- [x] 인증된 원본 파일명과 버전·반복 횟수 포함 AKFES v2 파일 포맷
- [x] 서명·세션·장치 바인딩이 필요한 파일 API
- [x] 잘못된 비밀번호·암호문 변조·잘못된 포맷 거부 테스트
- [x] Tauri 시작 전 FastAPI 라이선스 인증 게이트
- [x] 데스크톱 장치 ID 생성·로컬 저장과 서버 장치 바인딩
- [x] 세션 토큰의 sessionStorage 저장과 앱 재시작 전 세션 재검증
- [x] 서버 주소 설정, 인증 오류 표시, 로그아웃 UI
- [x] Vite·Tauri Origin CORS와 로컬 FastAPI CSP 연결
- [x] 클라이언트 일회용 챌린지 발급과 Web Crypto HMAC-SHA256 서명
- [x] 암호화·복호화 API 실제 호출과 오류 상태 표시
- [x] 처리 성공·실패에 따른 Arduino LED 명령 연결
- [x] Rust 네이티브 결과 파일 저장 대화상자와 직접 파일 쓰기
- [x] 저장 파일명 경로 제거·Windows 금지 문자 정리·길이 제한
- [x] Rust 네이티브 파일 열기 대화상자와 파일 크기 검증
- [x] 파일 선택 취소·오류의 사용자 상태 표시
- [x] 저장 성공 경로·저장 취소 상태 표시
- [x] Tauri 명령을 사용할 수 없는 브라우저 미리보기 폴백
- [x] GitHub Actions FastAPI pytest·Ruff 검사
- [x] GitHub Actions React·TypeScript 프로덕션 빌드 검사
- [x] GitHub Actions Tauri Rust `cargo check`
- [x] CI 첫 실행 오류 수정과 세 작업 통과
- [x] 개선 우선순위와 운영 로드맵 문서화

## 진행 예정

- [ ] 서버 세션 명시적 로그아웃·취소 API
- [ ] 대용량 파일 스트리밍 또는 임시 파일 처리
- [ ] Windows TPM 기반 장치 키 검토
- [ ] 실제 AKFES 앱 아이콘과 Windows 설치 프로그램
- [ ] 코드 서명과 자동 릴리스
- [ ] Windows + Arduino + 서버 통합 테스트

## 네이티브 파일 선택·저장 흐름

1. 기존 파일 선택 영역을 누르면 Rust의 운영체제 파일 열기 대화상자가 우선 실행됩니다.
2. 선택된 파일은 일반 파일인지 확인하고 100MB 제한을 검사한 뒤 Rust에서 읽습니다.
3. 파일명과 바이트 크기를 검증한 뒤 기존 React `File` 상태로 전달합니다.
4. 사용자가 대화상자를 취소하면 기존 선택을 변경하지 않고 취소 상태를 표시합니다.
5. 서버 처리 결과는 Rust의 저장 대화상자를 통해 사용자가 지정한 경로에 기록합니다.
6. 저장 성공 시 실제 경로를 결과 화면에 표시합니다.
7. 저장 취소 시 결과 데이터는 앱 메모리에 유지되어 다시 저장할 수 있습니다.
8. Tauri 명령을 사용할 수 없는 웹 미리보기에서만 브라우저 파일 선택·다운로드를 사용합니다.

## 네이티브 파일 안전 처리

- 디렉터리가 아닌 일반 파일만 선택할 수 있습니다.
- 선택 파일은 현재 JSON Base64 전송 한계에 맞춰 100MB로 제한합니다.
- Rust가 보고한 크기와 전달된 바이트 길이가 다르면 파일을 거부합니다.
- 서버가 반환한 파일명에서 디렉터리 경로를 제거합니다.
- Windows 금지 문자와 제어 문자를 정리합니다.
- 비어 있거나 너무 긴 저장 파일명은 안전한 기본값과 길이 제한을 적용합니다.
- 빈 결과 데이터는 저장하지 않습니다.

## GitHub Actions CI

`.github/workflows/ci.yml`은 FastAPI Ruff·pytest, React·TypeScript 프로덕션 빌드, Tauri Rust `cargo check`를 독립 작업으로 실행합니다. 첫 실행에서 발견된 Python 규칙 위반과 Tauri 아이콘 컨텍스트 오류를 수정했으며 세 작업이 모두 통과합니다.

## 데스크톱 파일 작업 흐름

1. 사용자가 네이티브 대화상자로 파일을 선택하고 Arduino 키패드로 비밀번호를 입력합니다.
2. 클라이언트가 파일을 Base64로 변환하고 `/api/v2/auth/challenge`에서 일회용 챌린지를 받습니다.
3. Web Crypto API로 메서드·경로·챌린지·본문 SHA-256·장치 ID를 HMAC-SHA256 서명합니다.
4. `/api/v2/files/encrypt` 또는 `/api/v2/files/decrypt`에 동일한 원문 본문과 서명을 전송합니다.
5. 서버 결과의 Base64를 바이트로 복원하고 응답 크기를 검증합니다.
6. Rust가 네이티브 저장 대화상자를 열고 사용자가 고른 경로에 직접 기록합니다.
7. 성공 시 저장 경로와 초록 LED를 표시하고, 실패 시 오류와 빨강 LED를 표시합니다.

## 현재 한계

파일 API가 JSON Base64 방식이므로 대용량 파일에서는 메모리 사용량과 전송량이 증가합니다. 네이티브 선택에서도 전체 파일을 Rust와 WebView 메모리에 올리므로 후속 단계에서 스트리밍 또는 임시 파일 기반 처리가 필요합니다.
