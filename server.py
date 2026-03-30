import json
import os
import sqlite3
from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PORT = int(os.environ.get('PORT', '4173'))
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
DB_PATH = os.path.join(os.path.dirname(__file__), 'booking.db')


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

    slots = []
    for trip in TRIPS:
        reserved = reserved_by_trip.get(trip['id'], 0)
        slots.append({**trip, 'maxSeats': boat['maxSeats'], 'reserved': reserved, 'remaining': max(0, boat['maxSeats'] - reserved)})
    return slots


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

    days = {}
    boat = BOAT_BY_ID[boat_id]
    total_capacity = boat['maxSeats'] * len(TRIPS)
    for row in rows:
        reserved = int(row['reserved'])
        days[row['booking_date']] = {'reserved': reserved, 'capacity': total_capacity, 'remaining': max(0, total_capacity - reserved)}
    return days


def get_posts(conn, board):
    rows = conn.execute(
        '''
        SELECT id, board, author, title, content, created_at
        FROM posts
        WHERE board = ?
        ORDER BY id DESC
        LIMIT 100
        ''',
        (board,),
    ).fetchall()
    return [
        {
            'id': row['id'],
            'board': row['board'],
            'author': row['author'],
            'title': row['title'],
            'content': row['content'],
            'createdAt': row['created_at'],
        }
        for row in rows
    ]


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
        if length <= 0:
            return None
        raw = self.rfile.read(length)
        return json.loads(raw.decode('utf-8'))

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
            if not booking_date:
                return self._send_json({'message': 'date 쿼리가 필요합니다.'}, HTTPStatus.BAD_REQUEST)
            if not is_valid_date(booking_date):
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
            if not month:
                return self._send_json({'message': 'month 쿼리가 필요합니다.'}, HTTPStatus.BAD_REQUEST)
            if not is_valid_month(month):
                return self._send_json({'message': 'month 형식은 YYYY-MM 이어야 합니다.'}, HTTPStatus.BAD_REQUEST)
            if boat_id not in BOAT_BY_ID:
                return self._send_json({'message': '유효하지 않은 배입니다.'}, HTTPStatus.BAD_REQUEST)
            with get_conn() as conn:
                days = get_month_summary(conn, month, boat_id)
            return self._send_json({'month': month, 'boatId': boat_id, 'days': days})

        if parsed.path == '/api/posts':
            qs = parse_qs(parsed.query)
            board = qs.get('board', [None])[0]
            if board not in BOARDS:
                return self._send_json({'message': 'board는 catch 또는 notice 이어야 합니다.'}, HTTPStatus.BAD_REQUEST)
            with get_conn() as conn:
                posts = get_posts(conn, board)
            return self._send_json({'board': board, 'posts': posts})

        if parsed.path == '/':
            self.path = '/index.html'
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/bookings':
            return self.create_booking()
        if parsed.path == '/api/posts':
            return self.create_post()
        return self._send_json({'message': 'Not Found'}, HTTPStatus.NOT_FOUND)

    def create_booking(self):
        try:
            payload = self._read_json() or {}
        except json.JSONDecodeError:
            return self._send_json({'message': 'JSON 형식이 올바르지 않습니다.'}, HTTPStatus.BAD_REQUEST)

        booking_date = payload.get('bookingDate')
        trip_id = payload.get('tripId')
        boat_id = payload.get('boatId') or DEFAULT_BOAT_ID
        customer_name = (payload.get('customerName') or '').strip()
        customer_phone = (payload.get('customerPhone') or '').strip()
        guest_count = payload.get('guestCount')
        try:
            guest_count = int(guest_count)
        except (TypeError, ValueError):
            guest_count = 0

        if not booking_date or not trip_id or not customer_name or not customer_phone:
            return self._send_json({'message': '필수 항목이 누락되었습니다.'}, HTTPStatus.BAD_REQUEST)
        if not is_valid_date(booking_date):
            return self._send_json({'message': '예약 날짜 형식이 올바르지 않습니다.'}, HTTPStatus.BAD_REQUEST)
        if guest_count < 1 or guest_count > 6:
            return self._send_json({'message': '예약 인원은 1~6명 사이여야 합니다.'}, HTTPStatus.BAD_REQUEST)
        if trip_id not in {trip['id'] for trip in TRIPS}:
            return self._send_json({'message': '존재하지 않는 회차입니다.'}, HTTPStatus.BAD_REQUEST)
        if boat_id not in BOAT_BY_ID:
            return self._send_json({'message': '유효하지 않은 배입니다.'}, HTTPStatus.BAD_REQUEST)

        now = datetime.utcnow().isoformat(timespec='seconds')
        with get_conn() as conn:
            conn.execute('BEGIN IMMEDIATE')
            slots = get_availability(conn, booking_date, boat_id)
            selected = next((slot for slot in slots if slot['id'] == trip_id), None)
            if not selected or selected['remaining'] < guest_count:
                conn.execute('ROLLBACK')
                return self._send_json({'message': '잔여 좌석이 부족합니다.'}, HTTPStatus.CONFLICT)
            conn.execute(
                '''
                INSERT INTO bookings (booking_date, trip_id, customer_name, customer_phone, guest_count, created_at, boat_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ''',
                (booking_date, trip_id, customer_name, customer_phone, guest_count, now, boat_id),
            )
            conn.execute('COMMIT')
        return self._send_json({'message': '예약이 완료되었습니다.'}, HTTPStatus.CREATED)

    def create_post(self):
        try:
            payload = self._read_json() or {}
        except json.JSONDecodeError:
            return self._send_json({'message': 'JSON 형식이 올바르지 않습니다.'}, HTTPStatus.BAD_REQUEST)

        board = payload.get('board')
        author = (payload.get('author') or '').strip()
        title = (payload.get('title') or '').strip()
        content = (payload.get('content') or '').strip()
        if board not in BOARDS:
            return self._send_json({'message': 'board는 catch 또는 notice 이어야 합니다.'}, HTTPStatus.BAD_REQUEST)
        if not author or not title or not content:
            return self._send_json({'message': '작성자/제목/내용을 입력해주세요.'}, HTTPStatus.BAD_REQUEST)

        now = datetime.utcnow().isoformat(timespec='seconds')
        with get_conn() as conn:
            conn.execute(
                'INSERT INTO posts (board, author, title, content, created_at) VALUES (?, ?, ?, ?, ?)',
                (board, author, title, content, now),
            )
        return self._send_json({'message': '게시글이 등록되었습니다.'}, HTTPStatus.CREATED)


if __name__ == '__main__':
    init_db()
    server = ThreadingHTTPServer(('0.0.0.0', PORT), Handler)
    print(f'은솔마린 서버 실행: http://localhost:{PORT}')
    server.serve_forever()
