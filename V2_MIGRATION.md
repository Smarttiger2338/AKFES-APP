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
- [x] Tauri 파일 선택과 Base64 요청 변환
- [x] 클라이언트 일회용 챌린지 발급과 Web Crypto HMAC-SHA256 서명
- [x] 암호화·복호화 API 실제 호출과 오류 상태 표시
- [x] 처리 성공·실패에 따른 Arduino LED 명령 연결
- [x] 서버 결과 파일 다운로드와 다시 저장 버튼

## 진행 예정

- [ ] Tauri 네이티브 결과 파일 저장 대화상자 연결
- [ ] 대용량 파일 스트리밍 또는 임시 파일 처리
- [ ] 서버 세션 명시적 로그아웃·취소 API
- [ ] 앱 아이콘 및 Windows 설치 프로그램
- [ ] 코드 서명과 자동 릴리스
- [ ] Windows + Arduino + 서버 통합 테스트

## 데스크톱 인증 흐름

1. 앱이 로컬 장치 ID를 생성해 `localStorage`에 저장합니다.
2. 사용자가 FastAPI 주소와 라이선스 키를 입력합니다.
3. `/api/v2/auth/login`으로 라이선스와 장치 바인딩을 확인합니다.
4. 세션 토큰은 앱 창의 `sessionStorage`에만 저장합니다.
5. 새로고침 시 `/api/v2/auth/session`으로 세션과 장치 ID를 다시 검증합니다.
6. 세션이 없거나 거부되면 Arduino·파일 작업 화면에 진입할 수 없습니다.

## 데스크톱 파일 작업 흐름

1. 사용자가 파일을 선택하고 Arduino 키패드로 비밀번호를 입력합니다.
2. 클라이언트가 파일을 Base64로 변환하고 `/api/v2/auth/challenge`에서 일회용 챌린지를 받습니다.
3. Web Crypto API로 메서드·경로·챌린지·본문 SHA-256·장치 ID를 HMAC-SHA256 서명합니다.
4. `/api/v2/files/encrypt` 또는 `/api/v2/files/decrypt`에 동일한 원문 본문과 서명을 전송합니다.
5. 서버 결과의 Base64를 바이트로 복원하고 응답 크기를 검증합니다.
6. 성공 시 결과 파일 다운로드와 초록 LED 명령, 실패 시 오류 표시와 빨강 LED 명령을 수행합니다.

## 파일 API

- `POST /api/v2/files/encrypt`
- `POST /api/v2/files/decrypt`

요청 JSON에는 `filename`, `password`, `data_base64`가 포함됩니다. 요청 전체는 기존 `Authorization`, `X-AKFES-Device-ID`, `X-AKFES-Challenge`, `X-AKFES-Signature` 헤더로 검증됩니다.

암호화 포맷은 다음 정보를 인증된 헤더로 저장합니다.

- AKFES v2 매직 바이트와 포맷 버전
- PBKDF2 반복 횟수
- 16바이트 무작위 솔트
- 12바이트 AES-GCM 논스
- 원본 파일명
- AES-GCM 암호문과 인증 태그

기본 PBKDF2 반복 횟수는 `200000`이며 `AKFES_PBKDF2_ITERATIONS`로 조정할 수 있습니다.

## 현재 한계

현재 결과 저장은 WebView 다운로드 방식이며 Tauri 네이티브 파일 저장 대화상자는 아직 연결되지 않았습니다. 또한 파일 API가 JSON Base64 방식이므로 대용량 파일에서는 메모리 사용량과 전송량이 증가합니다.
