# 은솔마린 통합 홈페이지

은솔마린 운영에 필요한 예약/게시판/관리 기능을 포함한 웹앱입니다.

## 구성 페이지
- 메인: `/`
- 예약: `/booking.html`
- 배 소개: `/boats.html`
- 게시판(조업현황/공지): `/board.html`
- 관리자(예약 조회/변경/취소, 백업/모니터링): `/admin.html`

## 핵심 기능
- 배별 예약 관리(1호/2호 분리)
- 휴대폰 인증(SMS 코드) 후 예약
- 예약/취소/변경 시 알림 로그 기록(`notifications.log`)  
  *(실제 알림톡 연동 전 개발 모드)*
- 관리자 기능
  - 예약 조회/변경/취소
  - DB 백업 생성(`/api/admin/backup`)
  - 모니터링 지표 조회(`/api/admin/metrics`)

## 환경변수
- `PORT` (기본: `4173`)
- `ADMIN_KEY` (기본: `admin1234`)

## 주요 API
- `POST /api/auth/send-code`
- `POST /api/auth/verify-code`
- `GET /api/availability?date=YYYY-MM-DD&boatId=<boat-id>`
- `GET /api/calendar?month=YYYY-MM&boatId=<boat-id>`
- `POST /api/bookings` (`verifyToken`, `boatId` 포함)
- `GET /api/admin/bookings` (헤더 `X-Admin-Key` 필요)
- `PATCH /api/admin/bookings/:id` (헤더 `X-Admin-Key` 필요)
- `DELETE /api/admin/bookings/:id` (헤더 `X-Admin-Key` 필요)
- `POST /api/admin/backup` (헤더 `X-Admin-Key` 필요)
- `GET /api/admin/metrics` (헤더 `X-Admin-Key` 필요)

## 실행
```bash
npm start
```

## 배포 주의
- 이 프로젝트는 **정적 호스팅만으로는 동작하지 않고**, 반드시 `server.py` 백엔드와 함께 배포해야 합니다.
- CORS/OPTIONS를 포함해 크로스도메인 호출이 가능하도록 서버가 설정되어 있습니다.
