const AUTOPLAY_DELAY = 7500;
const VELOCITY_WINDOW = 110;

const carousel = document.querySelector(".hero-carousel");
const cards = Array.from(carousel?.querySelectorAll(".spotlight-card") ?? []);
window.addEventListener("pageshow", (event) => {
  if (event.persisted) window.location.reload();
});
if (cards.length > 1) {
  initializeCarousel(carousel, cards);
}

function initializeCarousel(carousel, cards) {
  const stage = carousel.querySelector(".spotlight-stage");
  const controls = carousel.querySelector(".spotlight-controls");
  const counter = carousel.querySelector(".spotlight-count");
  const playback = carousel.querySelector(".spotlight-playback");
  const announcement = carousel.querySelector(".spotlight-announcement");
  const dialog = document.querySelector("#movie-dialog");
  const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
  const count = cards.length;
  const wrap = (value) => ((value % count) + count) % count;

  let position = 0;
  let spacing = cards[0].offsetWidth * 0.84;
  let destination = null;
  let animationFrame = 0;
  let dragFrame = 0;
  let autoplayTimer;
  let drag = null;
  let suppressClick = false;
  let autoplay = !reducedMotion.matches;
  let inView = false;

  function paint() {
    cards.forEach((card, index) => {
      // Reuse the same cards on both sides of the loop. They wrap while faded out.
      const offset = wrap(index - position + count / 2) - count / 2;
      const distance = Math.abs(offset);
      const scale = Math.max(0.55, 1 - distance * 0.16);
      const angle = Math.sign(offset) * Math.min(34, distance * 23);
      const opacity = Math.max(0, 1 - distance * 0.26 - Math.max(0, distance - 2) * 0.45);
      card.style.transform = `translate3d(${offset * spacing}px, 0, 0) rotateY(${-angle}deg) scale(${scale})`;
      card.style.opacity = opacity;
      card.style.zIndex = 100 - Math.round(distance * 20);
    });
  }

  function queueAutoplay() {
    clearTimeout(autoplayTimer);
    if (!autoplay || !inView || document.hidden || drag || destination !== null) return;
    autoplayTimer = setTimeout(() => {
      if (dialog.open || carousel.querySelector(":focus-visible")) {
        queueAutoplay();
        return;
      }
      animateTo(Math.round(position) + 1, 680, false);
    }, AUTOPLAY_DELAY);
  }

  function settle(target, announce) {
    const focusedCard = stage.contains(document.activeElement);
    const index = wrap(target);
    position = index;
    destination = null;
    paint();

    cards[index].inert = false;
    if (focusedCard && document.activeElement !== cards[index]) {
      cards[index].focus({ preventScroll: true });
    }
    cards.forEach((card, slot) => { card.inert = slot !== index; });
    counter.textContent = `${String(index + 1).padStart(2, "0")} / ${String(count).padStart(2, "0")}`;
    if (announce && !focusedCard) {
      const title = cards[index].querySelector(".spotlight-title").textContent;
      announcement.textContent = `${title}, film ${index + 1} dari ${count}`;
    }
    queueAutoplay();
  }

  function stopMotion() {
    cancelAnimationFrame(animationFrame);
    cancelAnimationFrame(dragFrame);
    dragFrame = 0;
    destination = null;
    clearTimeout(autoplayTimer);
  }

  function animateTo(target, duration = 550, announce = true) {
    stopMotion();
    if (reducedMotion.matches || Math.abs(target - position) < 0.001) {
      settle(target, announce);
      return;
    }

    destination = target;
    const origin = position;
    const start = performance.now();
    function frame(now) {
      const progress = Math.min(1, (now - start) / duration);
      if (progress >= 1) {
        settle(target, announce);
        return;
      }
      position = origin + (target - origin) * (1 - (1 - progress) ** 3);
      paint();
      animationFrame = requestAnimationFrame(frame);
    }
    animationFrame = requestAnimationFrame(frame);
  }

  function step(direction) {
    animateTo((destination ?? Math.round(position)) + direction);
  }

  function setAutoplay(value) {
    autoplay = value;
    playback.classList.toggle("is-paused", !autoplay);
    playback.setAttribute("aria-label", autoplay ? "Jeda putar otomatis" : "Mulai putar otomatis");
    queueAutoplay();
  }

  function sampleDrag(pointerX) {
    const now = performance.now();
    drag.samples.push({ x: pointerX, at: now });
    while (drag.samples.length > 1 && now - drag.samples[0].at > VELOCITY_WINDOW) {
      drag.samples.shift();
    }
  }

  function endDrag(event, fling) {
    if (drag?.id !== event.pointerId) return;
    let velocity = 0;
    if (fling && drag.moved) {
      sampleDrag(event.clientX);
      const first = drag.samples[0];
      const last = drag.samples.at(-1);
      const elapsed = last.at - first.at;
      if (elapsed >= 18) velocity = (first.x - last.x) / (elapsed * spacing);
      position = drag.origin + (drag.x - event.clientX) / spacing;
    }
    suppressClick = drag.moved;
    drag = null;
    stage.classList.remove("is-dragging");

    const coast = reducedMotion.matches ? 0 : Math.max(-12, Math.min(12, velocity * 330));
    const target = Math.round(position + coast);
    const duration = Math.min(1650, 360 + Math.abs(target - position) * 115);
    animateTo(target, duration, suppressClick);
  }

  stage.addEventListener("pointerdown", (event) => {
    if (!event.isPrimary || event.button !== 0 || drag) return;
    stopMotion();
    suppressClick = false;
    drag = { id: event.pointerId, x: event.clientX, y: event.clientY, origin: position, moved: false, samples: [] };
    sampleDrag(event.clientX);
  });

  stage.addEventListener("pointermove", (event) => {
    if (drag?.id !== event.pointerId) return;
    const dx = event.clientX - drag.x;
    if (!drag.moved) {
      const dy = Math.abs(event.clientY - drag.y);
      if (dy > 8 && dy > Math.abs(dx)) {
        endDrag(event, false);
        return;
      }
      if (Math.abs(dx) < 8) return;
      drag.moved = true;
      stage.classList.add("is-dragging");
      stage.setPointerCapture(event.pointerId);
    }

    sampleDrag(event.clientX);
    position = drag.origin - dx / spacing;
    if (!dragFrame) {
      dragFrame = requestAnimationFrame(() => {
        dragFrame = 0;
        paint();
      });
    }
  });
  stage.addEventListener("pointerup", (event) => endDrag(event, true));
  stage.addEventListener("pointercancel", (event) => endDrag(event, false));
  stage.addEventListener("lostpointercapture", (event) => {
    if (event.target === stage) endDrag(event, false);
  });
  stage.addEventListener("pointerleave", (event) => {
    if (drag && !drag.moved) endDrag(event, false);
  });
  stage.addEventListener("dragstart", (event) => event.preventDefault());
  stage.addEventListener("click", (event) => {
    if (suppressClick && event.detail > 0) {
      event.preventDefault();
      event.stopPropagation();
    }
  }, true);

  for (const button of controls.querySelectorAll("[data-carousel-step]")) {
    button.addEventListener("click", () => step(Number(button.dataset.carouselStep)));
  }
  carousel.addEventListener("keydown", (event) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    step(event.key === "ArrowRight" ? 1 : -1);
  });
  playback.addEventListener("click", () => setAutoplay(!autoplay));
  reducedMotion.addEventListener("change", (event) => setAutoplay(!event.matches));
  document.addEventListener("visibilitychange", queueAutoplay);

  new ResizeObserver(() => {
    spacing = cards[0].offsetWidth * 0.84;
    paint();
  }).observe(cards[0]);
  new IntersectionObserver(([entry]) => {
    inView = entry.intersectionRatio >= 0.4;
    queueAutoplay();
  }, { threshold: 0.4 }).observe(stage);

  stage.classList.add("is-ready");
  controls.hidden = false;
  settle(0, false);
  setAutoplay(autoplay);
}
