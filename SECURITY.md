# Security Policy

## Supported versions

보안 수정은 최신 안정 릴리스와 현재 개발 브랜치에 우선 적용합니다.

| Version | Supported |
| --- | --- |
| Latest stable | Yes |
| Current development branch | Yes |
| Older releases | Best effort |

## 취약점 제보

공개 Issue에 실제 라이선스 키, 관리자 토큰, 서버 비밀값, 사용자 파일 또는 재현 가능한 공격 코드를 게시하지 마세요.

저장소 소유자에게 비공개 채널로 다음 내용을 전달하세요.

- 영향을 받는 버전
- 문제를 재현한 환경
- 예상 동작과 실제 동작
- 최소 재현 절차
- 민감정보를 제거한 로그
- 가능한 완화 방법

## 비밀정보

다음 값은 저장소, Issue, PR, 로그, 스크린샷에 포함하면 안 됩니다.

- `AKFES_ADMIN_TOKEN`
- `AKFES_LICENSE_HMAC_SECRET`
- `TAURI_SIGNING_PRIVATE_KEY`
- 코드 서명 인증서와 비밀번호
- 실제 사용자 라이선스 키
- `%LOCALAPPDATA%\AKFES\server-runtime.json` 내용

비밀정보가 노출되면 즉시 폐기하고 새 값으로 교체해야 합니다.

## 기본 보안 설계

- 라이선스 키와 세션 토큰 원문을 DB에 저장하지 않음
- 사용자별 무작위 서버 비밀값
- 로컬호스트 전용 FastAPI 바인딩
- 첫 로그인 장치 바인딩
- 만료 세션과 명시적 로그아웃
- 일회용 챌린지와 HMAC 요청 서명
- AES-256-GCM 인증 암호화
- 관리자 감사 로그

## 배포 무결성

공식 릴리스에는 `SHA256SUMS.txt`가 포함됩니다. 설치 파일을 실행하기 전에 다운로드한 파일의 SHA-256 해시를 비교하는 것을 권장합니다.

Windows Authenticode 코드 서명이 적용되기 전까지 Windows SmartScreen에서 게시자 경고가 나타날 수 있습니다. 이는 해시 검증을 대체하지 않습니다.
