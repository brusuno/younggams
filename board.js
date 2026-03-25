const postForm = document.querySelector('#postForm');
const postList = document.querySelector('#postList');
const postMessage = document.querySelector('#postMessage');
const boardTitle = document.querySelector('#boardTitle');
const listTitle = document.querySelector('#listTitle');
const tabButtons = document.querySelectorAll('.tab-btn');

let activeBoard = location.hash === '#notice' ? 'notice' : 'catch';

function setMessage(text, ok = false) {
  postMessage.textContent = text;
  postMessage.className = `message ${ok ? 'ok' : 'error'}`;
}

async function fetchJSON(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.message || '요청 실패');
  return data;
}

function setBoardUI() {
  const label = activeBoard === 'catch' ? '조업현황' : '공지사항';
  boardTitle.textContent = `${label} 글쓰기`;
  listTitle.textContent = `${label} 목록`;
  tabButtons.forEach((btn) => btn.classList.toggle('active', btn.dataset.tab === activeBoard));
}

function renderPosts(posts) {
  postList.innerHTML = '';
  if (!posts.length) {
    postList.innerHTML = '<p class="muted">등록된 게시글이 없습니다.</p>';
    return;
  }

  posts.forEach((post) => {
    const card = document.createElement('article');
    card.className = 'post-card';
    card.innerHTML = `
      <h3>${post.title}</h3>
      <p class="post-meta">${post.author} · ${post.createdAt}</p>
      <p>${post.content}</p>
    `;
    postList.append(card);
  });
}

async function loadPosts() {
  const data = await fetchJSON(`/api/posts?board=${activeBoard}`);
  renderPosts(data.posts);
}

postForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const author = document.querySelector('#author').value.trim();
  const title = document.querySelector('#title').value.trim();
  const content = document.querySelector('#content').value.trim();

  if (!author || !title || !content) {
    setMessage('필수 항목을 입력해주세요.');
    return;
  }

  try {
    await fetchJSON('/api/posts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ board: activeBoard, author, title, content }),
    });
    setMessage('게시글이 등록되었습니다.', true);
    postForm.reset();
    await loadPosts();
  } catch (error) {
    setMessage(error.message);
  }
});

tabButtons.forEach((btn) => {
  btn.addEventListener('click', async () => {
    activeBoard = btn.dataset.tab;
    location.hash = activeBoard;
    setBoardUI();
    await loadPosts();
  });
});

setBoardUI();
loadPosts().catch((error) => setMessage(error.message));
