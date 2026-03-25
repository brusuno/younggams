const dateInput = document.querySelector('#bookingDate');
const slotsContainer = document.querySelector('#slots');
const tripSelect = document.querySelector('#tripSelect');
const bookingForm = document.querySelector('#bookingForm');
const message = document.querySelector('#message');
const slotTemplate = document.querySelector('#slotTemplate');

let trips = [];
let pollTimer;

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

function setMessage(text, ok = false) {
  message.textContent = text;
  message.className = `message ${ok ? 'ok' : 'error'}`;
}

function renderTripOptions() {
  const selected = tripSelect.value;
  tripSelect.querySelectorAll('option[data-trip]').forEach((option) => option.remove());

  trips.forEach((trip) => {
    const option = document.createElement('option');
    option.value = trip.id;
    option.dataset.trip = 'true';
    option.textContent = `${trip.name} (${trip.time})`;
    tripSelect.append(option);
  });

  if (selected) tripSelect.value = selected;
}

function renderSlots(slots) {
  slotsContainer.innerHTML = '';

  slots.forEach((slot) => {
    const node = slotTemplate.content.cloneNode(true);
    node.querySelector('.slot-title').textContent = slot.name;
    node.querySelector('.slot-time').textContent = slot.time;
    node.querySelector('.seat-count').textContent = `잔여 좌석 ${slot.remaining}석 / 총 ${slot.maxSeats}석`;

    const state = node.querySelector('.seat-status');
    if (slot.remaining > 0) {
      state.textContent = '예약 가능';
      state.classList.add('ok');
    } else {
      state.textContent = '매진';
      state.classList.add('closed');
    }

    slotsContainer.append(node);
  });
}

async function fetchJSON(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.message || '요청 처리에 실패했습니다.');
  }

  return data;
}

async function loadConfig() {
  const config = await fetchJSON('/api/config');
  trips = config.trips;
  if (config.siteName) {
    document.title = `${config.siteName} | 실시간 바다낚시 예약`;
  }
  renderTripOptions();
}

async function loadAvailability() {
  const date = dateInput.value;
  const result = await fetchJSON(`/api/availability?date=${encodeURIComponent(date)}`);
  renderSlots(result.slots);
}

function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(() => {
    loadAvailability().catch(() => {});
  }, 5000);
}

async function reserveSeats(event) {
  event.preventDefault();

  const customerName = document.querySelector('#customerName').value.trim();
  const customerPhone = document.querySelector('#customerPhone').value.trim();
  const tripId = tripSelect.value;
  const guestCount = Number(document.querySelector('#guestCount').value);
  const bookingDate = dateInput.value;

  if (!customerName || !customerPhone || !tripId || guestCount < 1) {
    setMessage('필수 정보를 모두 입력해주세요.');
    return;
  }

  try {
    await fetchJSON('/api/bookings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bookingDate, tripId, customerName, customerPhone, guestCount }),
    });

    setMessage(`${customerName}님 예약이 완료되었습니다. (${guestCount}명)`, true);
    bookingForm.reset();
    tripSelect.value = '';
    document.querySelector('#guestCount').value = '1';
    await loadAvailability();
  } catch (error) {
    setMessage(error.message);
  }
}

async function init() {
  dateInput.value = todayISO();
  await loadConfig();
  await loadAvailability();
  startPolling();
}

dateInput.addEventListener('change', async () => {
  setMessage('');
  await loadAvailability();
  startPolling();
});

bookingForm.addEventListener('submit', reserveSeats);

init().catch((error) => {
  console.error(error);
  setMessage('초기 데이터를 불러오지 못했습니다. 서버 실행 상태를 확인해주세요.');
});
