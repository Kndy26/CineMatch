export const artwork = JSON.parse(document.querySelector("#movie-artwork").textContent);
const tmdbEnabled = document.body.dataset.tmdbEnabled === "true";
const metadataRequests = new Map();
const percent = new Intl.NumberFormat("id-ID", { style: "percent", maximumFractionDigits: 0 });
const number = new Intl.NumberFormat("id-ID");

export function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

export function displayTitle(title) {
  return title.replace(/ \(\d{4}\)$/, "").replace(/^(.+), (The|A|An)$/, "$2 $1");
}

export function matchScore(score) {
  return `${percent.format(score)} Match`;
}

export async function api(path, options) {
  const response = await fetch(path, options);
  if (response.status === 204) return null;
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = typeof payload?.detail === "string" ? payload.detail : "Permintaan belum berhasil.";
    throw new Error(detail);
  }
  return payload;
}

function addPosterFallback(image, title) {
  const fallback = image.closest(".spotlight-media")
    ? element("span", "spotlight-fallback", title)
    : image.closest(".poster-media")
      ? element("span", "poster-fallback-modern")
      : element("span", "poster-fallback", title);
  fallback.setAttribute("aria-hidden", "true");
  image.replaceWith(fallback);
}

function metadataFor(movie) {
  const curated = artwork[movie.movie_id];
  const local = {
    poster_url: curated?.poster ? `/static/images/posters/${movie.movie_id}.jpg` : null,
    synopsis: curated?.synopsis || null,
    synopsis_language: curated?.synopsis ? "id-ID" : null,
  };
  if (!tmdbEnabled || !movie.tmdb_id || (local.poster_url && local.synopsis)) {
    return Promise.resolve(local);
  }
  if (!metadataRequests.has(movie.movie_id)) {
    const request = api(`/api/movies/${movie.movie_id}/metadata`).catch(() => local);
    metadataRequests.set(movie.movie_id, request);
  }
  return metadataRequests.get(movie.movie_id);
}

function populatePoster(fallback, movie) {
  const title = displayTitle(movie.title);
  metadataFor(movie).then(({ poster_url }) => {
    if (!poster_url) return;
    const image = document.createElement("img");
    image.alt = "";
    image.loading = "lazy";
    image.width = 342;
    image.height = 513;
    image.addEventListener("error", () => addPosterFallback(image, title), { once: true });
    image.src = poster_url;
    fallback.replaceWith(image);
  });
}

function posterImage(movie) {
  const poster = element("span", "poster-image");
  const fallback = element("span", "poster-fallback", displayTitle(movie.title));
  fallback.setAttribute("aria-hidden", "true");
  poster.append(fallback);
  populatePoster(fallback, movie);
  return poster;
}

export function movieCard(movie) {
  const title = displayTitle(movie.title);
  const card = element("button", "poster-card");
  card.type = "button";
  card.dataset.movieId = movie.movie_id;
  const poster = posterImage(movie);
  const metaParts = [movie.year, ...movie.genres.slice(0, 2)].filter(Boolean);
  const meta = metaParts.join(" · ");
  if (movie.similarity_score !== undefined) {
    const score = matchScore(movie.similarity_score);
    poster.append(element("span", "match-label", score));
    card.setAttribute("aria-label", `Detail ${title}, ${meta ? meta + ', ' : ''}skor kemiripan ${score}`);
  } else {
    card.setAttribute("aria-label", `Detail ${title}${meta ? ', ' + meta : ''}`);
  }
  card.append(poster, element("span", "poster-title", title), element("span", "poster-meta", meta));
  return card;
}

const popularPreview = document.querySelector("#popular-films");
const popularToggle = document.querySelector("#popular-toggle");
if (popularPreview && popularToggle) {
  const cards = Array.from(popularPreview.querySelectorAll(".poster-card-modern"));
  const label = popularToggle.firstElementChild;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let heightAnimation = null;

  function updatePopularPreview() {
    const expanded = popularToggle.getAttribute("aria-expanded") === "true";
    popularPreview.classList.toggle("is-collapsed", !expanded);
    const visibleHeight = popularPreview.clientHeight;
    popularToggle.hidden = !expanded && popularPreview.scrollHeight <= visibleHeight;
    for (const card of cards) {
      card.inert = !expanded && card.offsetTop + card.offsetHeight > visibleHeight;
    }
  }

  popularToggle.addEventListener("click", () => {
    const wasExpanded = popularToggle.getAttribute("aria-expanded") === "true";
    const newlyRevealed = cards.filter((card) => card.inert);
    const firstClippedCard = newlyRevealed[0];
    const fromHeight = popularPreview.getBoundingClientRect().height;

    heightAnimation?.cancel();
    popularPreview.style.maxBlockSize = "";
    popularPreview.style.overflow = "";

    popularToggle.setAttribute("aria-expanded", String(!wasExpanded));
    label.textContent = wasExpanded ? "Tampilkan semua film populer" : "Tampilkan lebih sedikit";
    updatePopularPreview();

    if (!reducedMotion) {
      const toHeight = popularPreview.getBoundingClientRect().height;
      if (Math.abs(toHeight - fromHeight) > 2) {
        popularPreview.style.overflow = "hidden";
        heightAnimation = popularPreview.animate(
          [
            { maxBlockSize: `${fromHeight}px` },
            { maxBlockSize: `${toHeight}px` },
          ],
          {
            duration: 260,
            easing: "cubic-bezier(0.23, 1, 0.32, 1)",
          }
        );
        heightAnimation.onfinish = () => {
          popularPreview.style.overflow = "";
          heightAnimation = null;
        };
        heightAnimation.oncancel = () => {
          popularPreview.style.overflow = "";
          heightAnimation = null;
        };
      }

      if (!wasExpanded && newlyRevealed.length) {
        newlyRevealed.forEach((card, index) => {
          card.animate(
            [
              { opacity: 0, transform: "translateY(14px) scale(0.97)" },
              { opacity: 1, transform: "translateY(0) scale(1)" },
            ],
            {
              duration: 240,
              delay: Math.min(index * 25, 100),
              easing: "cubic-bezier(0.23, 1, 0.32, 1)",
              fill: "both",
            }
          );
        });
      }
    }

    if (wasExpanded) {
      popularToggle.scrollIntoView({ block: "center", behavior: reducedMotion ? "instant" : "smooth" });
    } else {
      firstClippedCard?.focus({ preventScroll: true });
    }
  });

  updatePopularPreview();
  new ResizeObserver(() => {
    if (!heightAnimation) updatePopularPreview();
  }).observe(popularPreview);
}

const renderedCard = ":is(.poster-card, .poster-card-modern, .spotlight-card)";
const renderedTitle = ".poster-title, .spotlight-title";
for (const image of document.querySelectorAll(`${renderedCard} img`)) {
  const card = image.closest(renderedCard);
  const title = card?.querySelector(renderedTitle)?.textContent;
  if (!title) continue;
  if (image.complete && image.naturalWidth === 0) {
    addPosterFallback(image, title);
  } else {
    image.addEventListener("error", () => addPosterFallback(image, title), { once: true });
  }
}

if (tmdbEnabled) {
  const posterObserver = new IntersectionObserver((entries, observer) => {
    for (const { target: fallback, isIntersecting } of entries) {
      if (!isIntersecting) continue;
      observer.unobserve(fallback);
      const card = fallback.closest(renderedCard);
      populatePoster(fallback, {
        title: card.querySelector(renderedTitle).textContent,
        movie_id: Number(card.dataset.movieId),
        tmdb_id: Number(card.dataset.tmdbId),
      });
    }
  }, { rootMargin: "200px" });

  for (const fallback of document.querySelectorAll(`${renderedCard}[data-tmdb-id] :is(.poster-fallback, .poster-fallback-modern, .spotlight-fallback)`)) {
    posterObserver.observe(fallback);
  }
}

const movieDialog = document.querySelector("#movie-dialog");
const movieTitle = document.querySelector("#movie-dialog-title");
const movieBody = document.querySelector("#movie-dialog-body");
let movieRequest;
let lastMovieOpener = null;

movieDialog.addEventListener("close", () => {
  movieRequest?.abort();
  lastMovieOpener?.focus();
});
document.addEventListener("click", async (event) => {
  const opener = event.target.closest("button[data-movie-id]");
  if (!opener) return;

  lastMovieOpener = opener;
  movieRequest?.abort();
  const request = new AbortController();
  movieRequest = request;
  movieTitle.textContent = "Detail film";
  movieBody.replaceChildren(element("p", "muted", "Memuat detail film…"));
  if (!movieDialog.open) movieDialog.showModal();

  try {
    const movie = await api(`/api/movies/${opener.dataset.movieId}`, { signal: request.signal });
    if (request.signal.aborted) return;
    movieTitle.textContent = displayTitle(movie.title);
    const copy = element("div");
    const meta = [movie.year, ...movie.genres].filter(Boolean).join(" · ");
    const initialSynopsis = artwork[movie.movie_id]?.synopsis;
    const synopsis = element("p", "", initialSynopsis || (
      tmdbEnabled && movie.tmdb_id ? "Memuat sinopsis…" : "Sinopsis belum tersedia di CineMatch."
    ));
    copy.append(
      element("p", "muted", meta),
      synopsis,
      element("p", "fine-print", `${number.format(movie.train_rating_count)} rating pada data awal MovieLens`),
    );
    const actions = element("div", "action-row");
    const discover = element("a", "button button--gold", "Pilih untuk Discover");
    discover.href = `/discover?movie=${movie.movie_id}`;
    actions.append(discover);
    if (movie.tmdb_id) {
      const reference = element("a", "text-link", "Detail di TMDB ↗");
      reference.href = `https://www.themoviedb.org/movie/${movie.tmdb_id}`;
      reference.target = "_blank";
      reference.rel = "noopener noreferrer";
      actions.append(reference);
    }
    copy.append(actions);
    const detail = element("div", "film-detail");
    detail.append(posterImage(movie), copy);
    movieBody.replaceChildren(detail);
    const metadata = await metadataFor(movie);
    if (!request.signal.aborted) {
      synopsis.textContent = metadata.synopsis || "Sinopsis belum tersedia di CineMatch.";
      if (metadata.synopsis_language) synopsis.lang = metadata.synopsis_language;
    }
  } catch (error) {
    if (!request.signal.aborted) {
      movieBody.replaceChildren(element("p", "notice--error", error.message));
    }
  }
});

function initNavIndicator() {
  const nav = document.querySelector(".site-nav");
  const indicator = nav?.querySelector(".nav-indicator");
  const activeLink = nav?.querySelector('a[aria-current="page"]');
  if (!nav || !indicator || !activeLink) return;

  const NAV_STORAGE_KEY = "cinematch:nav-indicator";
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const positionAt = (link) => {
    const navRect = nav.getBoundingClientRect();
    const linkRect = link.getBoundingClientRect();
    const inset = 4;
    const x = linkRect.left - navRect.left + inset;
    const width = Math.max(0, linkRect.width - inset * 2);
    return { x, width };
  };

  const target = positionAt(activeLink);
  nav.classList.add("has-indicator");
  indicator.style.width = `${target.width}px`;
  indicator.style.transform = `translateX(${target.x}px) scaleX(1)`;
  indicator.style.opacity = "1";

  let prev = null;
  try {
    const raw = sessionStorage.getItem(NAV_STORAGE_KEY);
    if (raw) {
      prev = JSON.parse(raw);
      sessionStorage.removeItem(NAV_STORAGE_KEY);
    }
  } catch {
    prev = null;
  }

  if (
    !reducedMotion &&
    prev &&
    typeof prev.x === "number" &&
    typeof prev.width === "number" &&
    target.width > 0 &&
    (Math.abs(prev.x - target.x) > 1 || Math.abs(prev.width - target.width) > 1)
  ) {
    indicator.animate(
      [
        { transform: `translateX(${prev.x}px) scaleX(${prev.width / target.width})` },
        { transform: `translateX(${target.x}px) scaleX(1)` },
      ],
      {
        duration: 220,
        easing: "cubic-bezier(0.77, 0, 0.175, 1)",
        fill: "both",
      }
    );
  }

  const saveOrigin = () => {
    try {
      sessionStorage.setItem(NAV_STORAGE_KEY, JSON.stringify(positionAt(activeLink)));
    } catch {
      // Abaikan jika sessionStorage diblokir
    }
  };

  window.addEventListener("pagehide", saveOrigin);
  window.addEventListener("resize", () => {
    const updated = positionAt(activeLink);
    indicator.style.width = `${updated.width}px`;
    indicator.style.transform = `translateX(${updated.x}px) scaleX(1)`;
  });
}

initNavIndicator();
