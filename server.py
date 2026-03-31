import json
import os
import secrets
import shutil
import sqlite3
from datetime import datetime, timedelta
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PORT = int(os.environ.get('PORT', '4173'))
ADMIN_KEY = os.environ.get('ADMIN_KEY', 'admin1234')
TRIPS = [
    {'id': 'dawn', 'name': '새벽 출항', 'time': '05:30 ~ 11:30'},
    {'id': 'day', 'name': '오전 출항', 'time': '09:00 ~ 15:00'},
    {'id': 'sunset', 'name': '오후 출항', 'time': '13:30 ~ 19:30'},
]
BOATS = [
    {'id': 'eunsol-1', 'name': '은솔 1호', 'maxSeats': 22},
    {'id': 'eunsol-2', 'name': '은솔 2호', 'maxSeats': 18},
]
DEFAULT_BOAT_ID = BOATS[0]['id']
BOAT_BY_ID = {boat['id']: boat for boat in BOATS}
BOARDS = {'catch', 'notice'}
DB_PATH = Path(__file__).parent / 'booking.db'
BACKUP_DIR = Path(__file__).parent / 'backups'


def now_iso():
    return datetime.utcnow().isoformat(timespec='seconds')


def get_conn():
    conn = sqlite3.connect(DB_PATH, isolation_level=None)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_booking_boat_column(conn):
    columns = conn.execute('PRAGMA table_info(bookings)').fetchall()
    names = {column['name'] for column in columns}
    if 'boat_id' not in names:
        conn.execute(f"ALTER TABLE bookings ADD COLUMN boat_id TEXT NOT NULL DEFAULT '{DEFAULT_BOAT_ID}'")


def init_db():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                booking_date TEXT NOT NULL,
                trip_id TEXT NOT NULL,
                customer_name TEXT NOT NULL,
                customer_phone TEXT NOT NULL,
                guest_count INTEGER NOT NULL CHECK (guest_count > 0),
                created_at TEXT NOT NULL,
                boat_id TEXT NOT NULL DEFAULT 'eunsol-1'
            )
            '''
        )
        ensure_booking_boat_column(conn)
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                board TEXT NOT NULL,
                author TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            '''
        )
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS phone_verifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT NOT NULL,
                code TEXT NOT NULL,
                verified INTEGER NOT NULL DEFAULT 0,
                token TEXT,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            '''
        )


def is_valid_date(date_text):
    try:
        datetime.strptime(date_text, '%Y-%m-%d')
        return True
    except ValueError:
        return False


def is_valid_month(month_text):
    try:
        datetime.strptime(month_text, '%Y-%m')
        return True
    except ValueError:
        return False


def append_notification(message):
    with open(Path(__file__).parent / 'notifications.log', 'a', encoding='utf-8') as file:
        file.write(f'[{now_iso()}] {message}\n')


def validate_admin(handler):
    key = handler.headers.get('X-Admin-Key', '')
    if key != ADMIN_KEY:
        handler._send_json({'message': '관리자 인증 실패'}, HTTPStatus.UNAUTHORIZED)
        return False
    return True


def get_availability(conn, booking_date, boat_id):
    boat = BOAT_BY_ID[boat_id]
    rows = conn.execute(
        '''
        SELECT trip_id, COALESCE(SUM(guest_count), 0) AS reserved
        FROM bookings
        WHERE booking_date = ? AND boat_id = ?
        GROUP BY trip_id
        ''',
        (booking_date, boat_id),
    ).fetchall()
    reserved_by_trip = {row['trip_id']: int(row['reserved']) for row in rows}
    return [
        {
            **trip,
            'maxSeats': boat['maxSeats'],
            'reserved': reserved_by_trip.get(trip['id'], 0),
            'remaining': max(0, boat['maxSeats'] - reserved_by_trip.get(trip['id'], 0)),
        }
        for trip in TRIPS
    ]


def get_month_summary(conn, month_text, boat_id):
    rows = conn.execute(
        '''
        SELECT booking_date, COALESCE(SUM(guest_count), 0) AS reserved
        FROM bookings
        WHERE booking_date LIKE ? AND boat_id = ?
        GROUP BY booking_date
        ''',
        (f'{month_text}-%', boat_id),
    ).fetchall()
    total_capacity = BOAT_BY_ID[boat_id]['maxSeats'] * len(TRIPS)
    return {
        row['booking_date']: {
            'reserved': int(row['reserved']),
            'capacity': total_capacity,
            'remaining': max(0, total_capacity - int(row['reserved'])),
        }
        for row in rows
    }


def get_posts(conn, board):
    rows = conn.execute(
        'SELECT id, board, author, title, content, created_at FROM posts WHERE board = ? ORDER BY id DESC LIMIT 100',
        (board,),
    ).fetchall()
    return [{'id': r['id'], 'board': r['board'], 'author': r['author'], 'title': r['title'], 'content': r['content'], 'createdAt': r['created_at']} for r in rows]


def list_bookings(conn, booking_date=None):
    query = 'SELECT id, booking_date, boat_id, trip_id, customer_name, customer_phone, guest_count, created_at FROM bookings'
    params = []
    if booking_date:
        query += ' WHERE booking_date = ?'
        params.append(booking_date)
    query += ' ORDER BY id DESC LIMIT 300'
    rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


class Handler(SimpleHTTPRequestHandler):
    def _send_json(self, payload, status=HTTPStatus.OK):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get('Content-Length', '0'))
        return json.loads(self.rfile.read(length).decode('utf-8')) if length > 0 else {}

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == '/healthz':
            return self._send_json({'ok': True, 'service': 'eunsol-marine'})

        if parsed.path == '/api/config':
            return self._send_json({'siteName': '은솔마린', 'trips': TRIPS, 'boats': BOATS})

        if parsed.path == '/api/availability':
            qs = parse_qs(parsed.query)
            booking_date = qs.get('date', [None])[0]
            boat_id = qs.get('boatId', [DEFAULT_BOAT_ID])[0]
            if not booking_date or not is_valid_date(booking_date):
                return self._send_json({'message': 'date 형식은 YYYY-MM-DD 이어야 합니다.'}, HTTPStatus.BAD_REQUEST)
            if boat_id not in BOAT_BY_ID:
                return self._send_json({'message': '유효하지 않은 배입니다.'}, HTTPStatus.BAD_REQUEST)
            with get_conn() as conn:
                slots = get_availability(conn, booking_date, boat_id)
            return self._send_json({'date': booking_date, 'boatId': boat_id, 'slots': slots})

        if parsed.path == '/api/calendar':
            qs = parse_qs(parsed.query)
            month = qs.get('month', [None])[0]
            boat_id = qs.get('boatId', [DEFAULT_BOAT_ID])[0]
            if not month or not is_valid_month(month):
                return self._send_json({'message': 'month 형식은 YYYY-MM 이어야 합니다.'}, HTTPStatus.BAD_REQUEST)
            if boat_id not in BOAT_BY_ID:
                return self._send_json({'message': '유효하지 않은 배입니다.'}, HTTPStatus.BAD_REQUEST)
            with get_conn() as conn:
                days = get_month_summary(conn, month, boat_id)
            return self._send_json({'month': month, 'boatId': boat_id, 'days': days})

        if parsed.path == '/api/posts':
            board = parse_qs(parsed.query).get('board', [None])[0]
            if board not in BOARDS:
                return self._send_json({'message': 'board는 catch 또는 notice 이어야 합니다.'}, HTTPStatus.BAD_REQUEST)
            with get_conn() as conn:
                posts = get_posts(conn, board)
            return self._send_json({'board': board, 'posts': posts})

        if parsed.path == '/api/admin/bookings':
            if not validate_admin(self):
                return
            booking_date = parse_qs(parsed.query).get('date', [None])[0]
            with get_conn() as conn:
                items = list_bookings(conn, booking_date)
            return self._send_json({'bookings': items})

        if parsed.path == '/api/admin/metrics':
            if not validate_admin(self):
                return
            with get_conn() as conn:
                booking_count = conn.execute('SELECT COUNT(*) AS count FROM bookings').fetchone()['count']
                post_count = conn.execute('SELECT COUNT(*) AS count FROM posts').fetchone()['count']
            return self._send_json({'bookingCount': booking_count, 'postCount': post_count, 'serverTime': now_iso()})

        if parsed.path == '/':
            self.path = '/index.html'
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/bookings':
            return self.create_booking()
        if parsed.path == '/api/posts':
            return self.create_post()
        if parsed.path == '/api/auth/send-code':
            return self.send_sms_code()
        if parsed.path == '/api/auth/verify-code':
            return self.verify_sms_code()
        if parsed.path == '/api/admin/backup':
            if not validate_admin(self):
                return
            return self.create_backup()
        return self._send_json({'message': 'Not Found'}, HTTPStatus.NOT_FOUND)

    def do_PATCH(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith('/api/admin/bookings/'):
            if not validate_admin(self):
                return
            booking_id = parsed.path.split('/')[-1]
            return self.update_booking(booking_id)
        return self._send_json({'message': 'Not Found'}, HTTPStatus.NOT_FOUND)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith('/api/admin/bookings/'):
            if not validate_admin(self):
                return
            booking_id = parsed.path.split('/')[-1]
            return self.cancel_booking(booking_id)
        return self._send_json({'message': 'Not Found'}, HTTPStatus.NOT_FOUND)

    def send_sms_code(self):
        data = self._read_json()
        phone = (data.get('phone') or '').strip()
        if len(phone) < 10:
            return self._send_json({'message': '휴대폰 번호를 확인해주세요.'}, HTTPStatus.BAD_REQUEST)
        code = str(secrets.randbelow(900000) + 100000)
        expires_at = (datetime.utcnow() + timedelta(minutes=5)).isoformat(timespec='seconds')
        with get_conn() as conn:
            conn.execute(
                'INSERT INTO phone_verifications (phone, code, expires_at, created_at) VALUES (?, ?, ?, ?)',
                (phone, code, expires_at, now_iso()),
            )
        append_notification(f'[SMS] {phone} 인증코드: {code}')
        return self._send_json({'message': '인증코드가 전송되었습니다. (개발모드: notifications.log 확인)'})

    def verify_sms_code(self):
        data = self._read_json()
        phone = (data.get('phone') or '').strip()
        code = (data.get('code') or '').strip()
        with get_conn() as conn:
            row = conn.execute(
                '''
                SELECT id, expires_at FROM phone_verifications
                WHERE phone = ? AND code = ? AND verified = 0
                ORDER BY id DESC LIMIT 1
                ''',
                (phone, code),
            ).fetchone()
            if not row:
                return self._send_json({'message': '인증코드가 올바르지 않습니다.'}, HTTPStatus.BAD_REQUEST)
            if datetime.fromisoformat(row['expires_at']) < datetime.utcnow():
                return self._send_json({'message': '인증코드가 만료되었습니다.'}, HTTPStatus.BAD_REQUEST)
            token = secrets.token_hex(16)
            conn.execute('UPDATE phone_verifications SET verified = 1, token = ? WHERE id = ?', (token, row['id']))
        return self._send_json({'message': '인증 완료', 'verifyToken': token})

    def create_booking(self):
        data = self._read_json()
        booking_date = data.get('bookingDate')
        trip_id = data.get('tripId')
        boat_id = data.get('boatId') or DEFAULT_BOAT_ID
        customer_name = (data.get('customerName') or '').strip()
        customer_phone = (data.get('customerPhone') or '').strip()
        verify_token = (data.get('verifyToken') or '').strip()
        try:
            guest_count = int(data.get('guestCount'))
        except (TypeError, ValueError):
            guest_count = 0

        if not booking_date or not trip_id or not customer_name or not customer_phone:
            return self._send_json({'message': '필수 항목이 누락되었습니다.'}, HTTPStatus.BAD_REQUEST)
        if not verify_token:
            return self._send_json({'message': '휴대폰 인증을 먼저 완료해주세요.'}, HTTPStatus.BAD_REQUEST)
        if not is_valid_date(booking_date) or boat_id not in BOAT_BY_ID or trip_id not in {t['id'] for t in TRIPS}:
            return self._send_json({'message': '입력값이 올바르지 않습니다.'}, HTTPStatus.BAD_REQUEST)
        if guest_count < 1 or guest_count > 6:
            return self._send_json({'message': '예약 인원은 1~6명 사이여야 합니다.'}, HTTPStatus.BAD_REQUEST)

        with get_conn() as conn:
            verified = conn.execute('SELECT id FROM phone_verifications WHERE phone = ? AND token = ? AND verified = 1', (customer_phone, verify_token)).fetchone()
            if not verified:
                return self._send_json({'message': '휴대폰 인증 토큰이 유효하지 않습니다.'}, HTTPStatus.BAD_REQUEST)

            conn.execute('BEGIN IMMEDIATE')
            slots = get_availability(conn, booking_date, boat_id)
            selected = next((slot for slot in slots if slot['id'] == trip_id), None)
            if not selected or selected['remaining'] < guest_count:
                conn.execute('ROLLBACK')
                return self._send_json({'message': '잔여 좌석이 부족합니다.'}, HTTPStatus.CONFLICT)

            conn.execute(
                'INSERT INTO bookings (booking_date, trip_id, customer_name, customer_phone, guest_count, created_at, boat_id) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (booking_date, trip_id, customer_name, customer_phone, guest_count, now_iso(), boat_id),
            )
            conn.execute('COMMIT')

        append_notification(f'[알림톡] 예약완료 {customer_name}/{customer_phone}/{boat_id}/{booking_date}/{trip_id}/{guest_count}명')
        return self._send_json({'message': '예약이 완료되었습니다.'}, HTTPStatus.CREATED)

    def create_post(self):
        data = self._read_json()
        board = data.get('board')
        author = (data.get('author') or '').strip()
        title = (data.get('title') or '').strip()
        content = (data.get('content') or '').strip()
        if board not in BOARDS or not author or not title or not content:
            return self._send_json({'message': '작성값을 확인해주세요.'}, HTTPStatus.BAD_REQUEST)
        with get_conn() as conn:
            conn.execute('INSERT INTO posts (board, author, title, content, created_at) VALUES (?, ?, ?, ?, ?)', (board, author, title, content, now_iso()))
        return self._send_json({'message': '게시글이 등록되었습니다.'}, HTTPStatus.CREATED)

    def update_booking(self, booking_id):
        data = self._read_json()
        fields = []
        values = []
        allowed = {'booking_date', 'trip_id', 'guest_count', 'boat_id'}
        for key in allowed:
            if key in data:
                fields.append(f'{key} = ?')
                values.append(data[key])
        if not fields:
            return self._send_json({'message': '변경할 필드가 없습니다.'}, HTTPStatus.BAD_REQUEST)
        values.append(booking_id)
        with get_conn() as conn:
            conn.execute(f"UPDATE bookings SET {', '.join(fields)} WHERE id = ?", values)
        append_notification(f'[알림톡] 예약변경 id={booking_id}')
        return self._send_json({'message': '예약이 변경되었습니다.'})

    def cancel_booking(self, booking_id):
        with get_conn() as conn:
            row = conn.execute('SELECT customer_name, customer_phone FROM bookings WHERE id = ?', (booking_id,)).fetchone()
            if not row:
                return self._send_json({'message': '예약이 존재하지 않습니다.'}, HTTPStatus.NOT_FOUND)
            conn.execute('DELETE FROM bookings WHERE id = ?', (booking_id,))
        append_notification(f"[알림톡] 예약취소 id={booking_id} {row['customer_name']}/{row['customer_phone']}")
        return self._send_json({'message': '예약이 취소되었습니다.'})

    def create_backup(self):
        stamp = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
        backup_path = BACKUP_DIR / f'backup-{stamp}.db'
        shutil.copy2(DB_PATH, backup_path)
        return self._send_json({'message': '백업 완료', 'path': str(backup_path.name)})


if __name__ == '__main__':
    init_db()
    server = ThreadingHTTPServer(('0.0.0.0', PORT), Handler)
    print(f'은솔마린 서버 실행: http://localhost:{PORT}')
    server.serve_forever()
