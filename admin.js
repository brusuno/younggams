const adminKeyInput = document.querySelector('#adminKey');
const adminDateInput = document.querySelector('#adminDate');
const loadBookingsBtn = document.querySelector('#loadBookingsBtn');
const backupBtn = document.querySelector('#backupBtn');
const metricsBtn = document.querySelector('#metricsBtn');
const adminMessage = document.querySelector('#adminMessage');
const bookingAdminList = document.querySelector('#bookingAdminList');
const metricsBox = document.querySelector('#metricsBox');

function setMessage(text, ok = false) {
  adminMessage.textContent = text;
  adminMessage.className = `message ${ok ? 'ok' : 'error'}`;
}

async function fetchAdmin(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-Admin-Key': adminKeyInput.value.trim(),
      ...(options.headers || {}),
    },
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.message || '요청 실패');
  return data;
}

function renderBookings(items) {
  bookingAdminList.innerHTML = '';
  if (!items.length) {
    bookingAdminList.innerHTML = '<p class="muted">예약 데이터가 없습니다.</p>';
    return;
  }

  items.forEach((item) => {
    const card = document.createElement('article');
    card.className = 'post-card';
    card.innerHTML = `
      <h3>#${item.id} ${item.customer_name} (${item.customer_phone})</h3>
      <p class="post-meta">${item.booking_date} / ${item.boat_id} / ${item.trip_id} / ${item.guest_count}명</p>
      <div class="verify-row">
        <input type="number" min="1" max="6" value="${item.guest_count}" data-guest="${item.id}" />
        <button data-update="${item.id}">인원변경</button>
        <button data-cancel="${item.id}">예약취소</button>
      </div>
    `;
    bookingAdminList.append(card);
  });

  bookingAdminList.querySelectorAll('[data-update]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const id = btn.dataset.update;
      const guestCount = Number(bookingAdminList.querySelector(`[data-guest="${id}"]`).value);
      try {
        await fetchAdmin(`/api/admin/bookings/${id}`, {
          method: 'PATCH',
          body: JSON.stringify({ guest_count: guestCount }),
        });
        setMessage('예약이 변경되었습니다.', true);
        await loadBookings();
      } catch (error) {
        setMessage(error.message);
      }
    });
  });

  bookingAdminList.querySelectorAll('[data-cancel]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const id = btn.dataset.cancel;
      try {
        await fetchAdmin(`/api/admin/bookings/${id}`, { method: 'DELETE' });
        setMessage('예약이 취소되었습니다.', true);
        await loadBookings();
      } catch (error) {
        setMessage(error.message);
      }
    });
  });
}

async function loadBookings() {
  const q = adminDateInput.value ? `?date=${adminDateInput.value}` : '';
  const data = await fetchAdmin(`/api/admin/bookings${q}`);
  renderBookings(data.bookings);
}

loadBookingsBtn.addEventListener('click', async () => {
  try {
    await loadBookings();
    setMessage('예약 조회 완료', true);
  } catch (error) {
    setMessage(error.message);
  }
});

backupBtn.addEventListener('click', async () => {
  try {
    const result = await fetchAdmin('/api/admin/backup', { method: 'POST' });
    setMessage(`백업 완료: ${result.path}`, true);
  } catch (error) {
    setMessage(error.message);
  }
});

metricsBtn.addEventListener('click', async () => {
  try {
    const data = await fetchAdmin('/api/admin/metrics');
    metricsBox.textContent = JSON.stringify(data, null, 2);
    setMessage('모니터링 조회 완료', true);
  } catch (error) {
    setMessage(error.message);
  }
});
