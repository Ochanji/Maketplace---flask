// ── Flash message auto-close ───────────────────────────────────────────────
document.querySelectorAll('.flash-close').forEach(btn => {
  btn.addEventListener('click', () => btn.closest('.flash').remove());
});
setTimeout(() => {
  document.querySelectorAll('.flash').forEach(el => el.style.opacity = '0');
  setTimeout(() => document.querySelectorAll('.flash').forEach(el => el.remove()), 400);
}, 5000);

// ── Dropdown toggle on click (mobile) ─────────────────────────────────────
document.querySelectorAll('.dropdown').forEach(dd => {
  dd.addEventListener('click', e => {
    const isMenu = e.target.closest('.dropdown-menu');
    if (isMenu) return;
    dd.classList.toggle('open');
  });
});
document.addEventListener('click', e => {
  if (!e.target.closest('.dropdown')) {
    document.querySelectorAll('.dropdown.open').forEach(d => d.classList.remove('open'));
  }
});

// ── Color input live preview ────────────────────────────────────────────────
document.querySelectorAll('input[type="color"]').forEach(input => {
  const preview = document.getElementById(input.dataset.preview);
  if (preview) {
    preview.style.background = input.value;
    input.addEventListener('input', () => preview.style.background = input.value);
  }
});

// ── Wishlist heart toggle ──────────────────────────────────────────────────
document.querySelectorAll('.product-wishlist').forEach(btn => {
  btn.addEventListener('click', () => {
    const isLiked = btn.dataset.liked === 'true';
    btn.dataset.liked = isLiked ? 'false' : 'true';
    btn.textContent = isLiked ? '♡' : '♥';
    btn.style.color = isLiked ? '' : '#ec4899';
  });
});

// ── Scroll reveal animation ────────────────────────────────────────────────
const observer = new IntersectionObserver(entries => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.style.opacity = '1';
      entry.target.style.transform = 'translateY(0)';
    }
  });
}, { threshold: 0.1 });

document.querySelectorAll('.product-card, .feature-card, .stat-card').forEach(el => {
  el.style.opacity = '0';
  el.style.transform = 'translateY(20px)';
  el.style.transition = 'opacity .5s ease, transform .5s ease';
  observer.observe(el);
});

// ── Delete confirm ─────────────────────────────────────────────────────────
document.querySelectorAll('.confirm-delete').forEach(form => {
  form.addEventListener('submit', e => {
    if (!confirm('Are you sure you want to delete this? This cannot be undone.')) {
      e.preventDefault();
    }
  });
});

// ── Image URL preview ─────────────────────────────────────────────────────
const imgInput = document.getElementById('image_url');
const imgPreview = document.getElementById('img-preview');
if (imgInput && imgPreview) {
  const update = () => {
    const url = imgInput.value.trim();
    if (url) { imgPreview.src = url; imgPreview.style.display = 'block'; }
    else imgPreview.style.display = 'none';
  };
  imgInput.addEventListener('input', update);
  update();
}
