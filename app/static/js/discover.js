import { api, displayTitle, element, movieCard } from "./site.js";

const form = document.querySelector("#discover-form");
const field = document.querySelector("#movie-search");
const genre = document.querySelector("#genre");
const options = document.querySelector("#movie-suggestions");
const searchStatus = document.querySelector("#movie-search-status");
const selectedArea = document.querySelector("#selected-area");
const selectedMovies = document.querySelector("#selected-movies");
const submitButton = form.querySelector("button[type=submit]");
const status = document.querySelector("#discover-status");
const resultTitle = document.querySelector("#results-title");
const resultStatus = document.querySelector("#results-status");
const resultCards = document.querySelector("#recommendation-cards");
const empty = document.querySelector("#discover-empty");
const emptyTitle = document.querySelector("#discover-empty-title");
const emptyMessage = document.querySelector("#discover-empty-message");
const resetGenre = document.querySelector("#discover-reset-genre");
const loading = document.querySelector("#recommendation-loading");
const historyLink = document.querySelector("#saved-history-link");
const maxMovies = Number(form.dataset.maxMovies);

const selected = new Map();
let currentOptions = [];
let activeOption = -1;
let searchTimer;
let searchRequest;
let busy = false;

function clearOptions() {
  currentOptions = [];
  activeOption = -1;
  options.replaceChildren();
  options.hidden = true;
  field.setAttribute("aria-expanded", "false");
  field.removeAttribute("aria-activedescendant");
}

function stopSearch() {
  clearTimeout(searchTimer);
  searchRequest?.abort();
  clearOptions();
}

function resetResults() {
  resultCards.replaceChildren();
  resultStatus.textContent = "";
  resultStatus.classList.remove("notice--error");
  historyLink.hidden = true;
  empty.hidden = false;
  emptyTitle.textContent = "Siap untuk menemukan film?";
  emptyMessage.textContent = "Tambahkan judul yang kamu suka, lalu cari rekomendasi.";
  resetGenre.hidden = true;
}

function showSelected() {
  selectedArea.hidden = selected.size === 0;
  selectedMovies.replaceChildren();
  for (const movie of selected.values()) {
    const title = displayTitle(movie.title);
    const item = element("li");
    const chip = element("button", "chip", `${title} ×`);
    chip.type = "button";
    chip.disabled = busy;
    chip.setAttribute("aria-label", `Hapus ${title} dari pilihan film`);
    chip.addEventListener("click", () => {
      selected.delete(movie.movie_id);
      showSelected();
      resetResults();
      status.textContent = "";
      searchStatus.textContent = `${title} dihapus dari pilihan.`;
      field.focus();
    });
    item.append(chip);
    selectedMovies.append(item);
  }
}

function setBusy(value) {
  busy = value;
  field.disabled = value;
  genre.disabled = value;
  submitButton.disabled = value;
  showSelected();
}

function choose(movie) {
  stopSearch();
  if (selected.size >= maxMovies) {
    searchStatus.textContent = `Maksimal ${maxMovies} film. Hapus salah satu pilihan untuk menambah lagi.`;
    return;
  }
  selected.set(movie.movie_id, movie);
  const title = displayTitle(movie.title);
  field.value = "";
  searchStatus.textContent = `${title} ditambahkan ke pilihan film.`;
  status.textContent = "";
  showSelected();
  resetResults();
  field.focus();
}

function showOptions(movies) {
  clearOptions();
  currentOptions = movies.filter((movie) => !selected.has(movie.movie_id));
  if (currentOptions.length === 0) {
    searchStatus.textContent = "Tidak ada judul lain yang cocok.";
    return;
  }
  searchStatus.textContent = "";
  for (const [index, movie] of currentOptions.entries()) {
    const option = element("li");
    option.id = `movie-option-${index}`;
    option.setAttribute("role", "option");
    option.setAttribute("aria-selected", "false");
    option.append(element("span", "", displayTitle(movie.title)), element("span", "", movie.year || ""));
    option.addEventListener("pointerdown", (event) => event.preventDefault());
    option.addEventListener("click", () => choose(movie));
    options.append(option);
  }
  options.hidden = false;
  field.setAttribute("aria-expanded", "true");
}

function selectOption(index) {
  const count = currentOptions.length;
  activeOption = (index + count) % count;
  for (const [position, option] of Array.from(options.children).entries()) {
    option.setAttribute("aria-selected", String(position === activeOption));
  }
  const active = options.children[activeOption];
  field.setAttribute("aria-activedescendant", active.id);
  active.scrollIntoView({ block: "nearest" });
}

field.addEventListener("input", () => {
  stopSearch();
  searchStatus.textContent = "";
  const query = field.value.trim();
  if (query.length < 2) return;

  searchTimer = setTimeout(async () => {
    const request = new AbortController();
    searchRequest = request;
    searchStatus.textContent = "Mencari film…";
    try {
      const params = new URLSearchParams({ q: query, limit: "10" });
      const movies = await api(`/api/movies/search?${params}`, { signal: request.signal });
      if (!request.signal.aborted) showOptions(movies);
    } catch (error) {
      if (!request.signal.aborted) searchStatus.textContent = error.message;
    }
  }, 220);
});

field.addEventListener("blur", () => {
  stopSearch();
  searchStatus.textContent = "";
});
field.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    stopSearch();
    searchStatus.textContent = "";
    return;
  }
  if (currentOptions.length === 0) return;
  if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    event.preventDefault();
    const next = event.key === "ArrowDown" ? activeOption + 1 : activeOption - 1;
    selectOption(activeOption < 0 && event.key === "ArrowUp" ? currentOptions.length - 1 : next);
  } else if (event.key === "Enter") {
    event.preventDefault();
    choose(currentOptions[Math.max(activeOption, 0)]);
  }
});

genre.addEventListener("change", resetResults);
resetGenre.addEventListener("click", () => {
  genre.value = "";
  form.requestSubmit();
});
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (busy) return;
  stopSearch();
  if (selected.size === 0) {
    status.textContent = "Pilih setidaknya satu film dari hasil pencarian.";
    status.classList.add("notice--error");
    field.focus();
    return;
  }

  resetResults();
  status.textContent = "";
  status.classList.remove("notice--error");
  setBusy(true);
  empty.hidden = true;
  loading.hidden = false;
  resultCards.setAttribute("aria-busy", "true");
  resultStatus.textContent = "Mencari rekomendasi…";

  try {
    const saved = await api("/api/recommendations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ movie_ids: [...selected.keys()], genre: genre.value || null }),
    });
    resultCards.replaceChildren(...saved.results.map(movieCard));
    resultStatus.textContent = saved.results.length
      ? `${saved.results.length} film ditemukan. Sesi disimpan ke riwayat.`
      : "Sesi disimpan ke riwayat.";
    if (!saved.results.length) {
      emptyTitle.textContent = "Belum ada film yang cocok";
      emptyMessage.textContent = genre.value ? "Coba ganti film pilihan atau cari tanpa filter genre." : "Coba pilih judul lain.";
      resetGenre.hidden = !genre.value;
      empty.hidden = false;
    }
    historyLink.href = `/history?session=${saved.id}`;
    historyLink.hidden = false;
    resultTitle.focus();
  } catch (error) {
    resultStatus.textContent = error.message;
    resultStatus.classList.add("notice--error");
  } finally {
    loading.hidden = true;
    resultCards.removeAttribute("aria-busy");
    setBusy(false);
  }
});

async function loadPreference() {
  const params = new URLSearchParams(location.search);
  const template = params.get("template");
  const movieId = params.get("movie");
  if (!template && !movieId) return;

  setBusy(true);
  status.textContent = "Memuat pilihan film…";
  try {
    if (template) {
      const session = await api(`/api/recommendations/${encodeURIComponent(template)}`);
      for (const movie of session.inputs) selected.set(movie.movie_id, movie);
      if ([...genre.options].some((option) => option.value === session.preferred_genre)) {
        genre.value = session.preferred_genre;
      }
    } else {
      const movie = await api(`/api/movies/${encodeURIComponent(movieId)}`);
      selected.set(movie.movie_id, movie);
    }
    status.textContent = template ? "Pilihan film dari riwayat siap dipakai." : "Film ditambahkan.";
  } catch (error) {
    status.textContent = error.message;
    status.classList.add("notice--error");
  } finally {
    setBusy(false);
  }
}

loadPreference();
