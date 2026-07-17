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
- [x] 서명 검증 재사용 모듈과 검증용 API
- [x] 인증·관리·서명 흐름 자동 테스트 추가

## 진행 예정

- [ ] 장치 바인딩 정책 강화
- [ ] 실제 파일 암호화·복호화 API 연결
- [ ] Tauri 라이선스 로그인 화면과 FastAPI 연결
- [ ] 결과 파일 저장 대화상자 연결
- [ ] 앱 아이콘 및 Windows 설치 프로그램
- [ ] 코드 서명과 자동 릴리스
- [ ] Windows + Arduino + 서버 통합 테스트

## 요청 서명 규칙

서명 문자열은 다음 순서의 줄바꿈 결합입니다.

```text
AKFES-V2
HTTP_METHOD
REQUEST_PATH
CHALLENGE
SHA256_REQUEST_BODY
DEVICE_ID_OR_EMPTY
```

클라이언트는 세션 토큰을 HMAC 키로 사용해 SHA-256 서명을 계산합니다. 챌린지는 한 번만 사용할 수 있고, 발급받은 세션과 다른 세션에서는 사용할 수 없습니다.

## 검증 상태

- 정상 서명 요청 테스트 추가
- 잘못된 서명과 변조된 본문 거부 테스트 추가
- 동일 챌린지 재사용 거부 테스트 추가
- 잘못된 서명 시 챌린지가 소모되지 않는지 테스트 추가
- 실제 Arduino 연결과 Windows Tauri 빌드는 해당 개발 환경에서 추가 검증 필요

## 현재 한계

서버 인증과 요청 서명 계층은 준비됐지만 파일 암호화·복호화 API와 Tauri 클라이언트는 아직 이 서명 검증 계층을 사용하지 않습니다.
