import { api, displayTitle, element, movieCard } from "./site.js";

const form = document.querySelector("#discover-form");
const field = document.querySelector("#movie-search");
const genre = document.querySelector("#genre");
const yearFrom = document.querySelector("#year-from");
const yearTo = document.querySelector("#year-to");
const options = document.querySelector("#movie-suggestions");
const searchStatus = document.querySelector("#movie-search-status");
const selectedArea = document.querySelector("#selected-area");
const selectedMovies = document.querySelector("#selected-movies");
const submitButton = form.querySelector("button[type=submit]");
const submitSpinner = submitButton.querySelector(".btn-spinner");
const submitLabel = submitButton.querySelector(".btn-label");
const submitArrow = submitButton.querySelector(".btn-arrow");
const status = document.querySelector("#discover-status");
const resultTitle = document.querySelector("#results-title");
const resultStatus = document.querySelector("#results-status");
const resultCards = document.querySelector("#recommendation-cards");
const empty = document.querySelector("#discover-empty");
const emptyIcon = document.querySelector("#discover-empty-icon");
const emptyZeroIcon = emptyIcon?.querySelector(".icon-zero");
const emptyNoResultsIcon = emptyIcon?.querySelector(".icon-no-results");
const emptyTitle = document.querySelector("#discover-empty-title");
const emptyMessage = document.querySelector("#discover-empty-message");
const quickStartButton = document.querySelector("#discover-quick-start");
const resetGenre = document.querySelector("#discover-reset-genre");
const genrePills = document.querySelectorAll("#genre-quick-pills .genre-pill");
const loading = document.querySelector("#recommendation-loading");
const historyLink = document.querySelector("#saved-history-link");
const activeFilters = document.querySelector("#active-filters");
const resetFormFilters = document.querySelector("#reset-form-filters");
const errorState = document.querySelector("#discover-error");
const errorMessage = document.querySelector("#discover-error-message");
const retryButton = document.querySelector("#discover-retry");
const maxMovies = Number(form.dataset.maxMovies);

const RECENT_MOVIES_KEY = "cinematch:recent-movies";
const MAX_RECENT_MOVIES = 5;
const QUICK_PICKS = [
  { movie_id: 109487, title: "Interstellar (2014)", year: 2014 },
  { movie_id: 1, title: "Toy Story (1995)", year: 1995 },
  { movie_id: 58559, title: "Dark Knight, The (2008)", year: 2008 },
  { movie_id: 79132, title: "Inception (2010)", year: 2010 },
];

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

function syncFormFilterReset() {
  const hasFilters = Boolean(genre.value || yearFrom.value.trim() || yearTo.value.trim());
  resetFormFilters.hidden = !hasFilters;
  for (const pill of genrePills) {
    const active = pill.dataset.genre === genre.value;
    pill.setAttribute("aria-pressed", String(active));
    pill.classList.toggle("is-active", active);
  }
}

function renderActiveFilters(appliedGenre, appliedFrom, appliedTo) {
  activeFilters.replaceChildren();
  if (appliedGenre) {
    const li = element("li");
    const chip = element("button", "chip chip--filter", `Genre: ${appliedGenre} ×`);
    chip.type = "button";
    chip.disabled = busy;
    chip.setAttribute("aria-label", `Hapus filter genre ${appliedGenre}`);
    chip.addEventListener("click", () => {
      genre.value = "";
      syncFormFilterReset();
      form.requestSubmit();
    });
    li.append(chip);
    activeFilters.append(li);
  }
  if (appliedFrom !== null || appliedTo !== null) {
    const label =
      appliedFrom !== null && appliedTo !== null && appliedFrom === appliedTo
        ? `Tahun: ${appliedFrom}`
        : `Tahun: ${appliedFrom ?? "Awal"}–${appliedTo ?? "Akhir"}`;
    const li = element("li");
    const chip = element("button", "chip chip--filter", `${label} ×`);
    chip.type = "button";
    chip.disabled = busy;
    chip.setAttribute("aria-label", "Hapus filter rentang tahun");
    chip.addEventListener("click", () => {
      yearFrom.value = "";
      yearTo.value = "";
      syncFormFilterReset();
      form.requestSubmit();
    });
    li.append(chip);
    activeFilters.append(li);
  }
  activeFilters.hidden = activeFilters.children.length === 0;
}

function resetResults() {
  resultCards.replaceChildren();
  resultStatus.textContent = "";
  resultStatus.classList.remove("notice--error");
  historyLink.hidden = true;
  activeFilters.replaceChildren();
  activeFilters.hidden = true;
  errorState.hidden = true;
  empty.hidden = false;
  if (emptyIcon) {
    emptyIcon.classList.add("state-icon--gold");
    emptyIcon.classList.remove("state-icon--muted");
  }
  if (emptyZeroIcon) emptyZeroIcon.hidden = false;
  if (emptyNoResultsIcon) emptyNoResultsIcon.hidden = true;
  emptyTitle.textContent = "Siap untuk menemukan film?";
  emptyMessage.textContent = "Tambahkan judul yang kamu suka, lalu cari rekomendasi.";
  quickStartButton.hidden = selected.size > 0;
  resetGenre.hidden = true;
}

function showSelected() {
  selectedArea.hidden = selected.size === 0;
  if (resetGenre.hidden) quickStartButton.hidden = selected.size > 0;
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
  yearFrom.disabled = value;
  yearTo.disabled = value;
  submitButton.disabled = value;
  submitSpinner.hidden = !value;
  submitArrow.hidden = value;
  submitLabel.textContent = value ? "Mencari rekomendasi…" : "Cari rekomendasi";
  resetFormFilters.disabled = value;
  quickStartButton.disabled = value;
  retryButton.disabled = value;
  for (const btn of activeFilters.querySelectorAll("button")) {
    btn.disabled = value;
  }
  for (const pill of genrePills) {
    pill.disabled = value;
  }
  showSelected();
}

function getRecentMovies() {
  try {
    const raw = localStorage.getItem(RECENT_MOVIES_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveRecentMovie(movie) {
  try {
    const existing = getRecentMovies().filter((item) => item.movie_id !== movie.movie_id);
    const entry = { movie_id: movie.movie_id, title: movie.title, year: movie.year ?? null };
    localStorage.setItem(RECENT_MOVIES_KEY, JSON.stringify([entry, ...existing].slice(0, MAX_RECENT_MOVIES)));
  } catch {
    // Abaikan jika localStorage diblokir
  }
}

function clearRecentMovies() {
  try {
    localStorage.removeItem(RECENT_MOVIES_KEY);
  } catch {
    // Abaikan jika localStorage diblokir
  }
}

function choose(movie) {
  stopSearch();
  if (selected.size >= maxMovies) {
    searchStatus.textContent = `Maksimal ${maxMovies} film. Hapus salah satu pilihan untuk menambah lagi.`;
    return;
  }
  selected.set(movie.movie_id, movie);
  saveRecentMovie(movie);
  const title = displayTitle(movie.title);
  field.value = "";
  searchStatus.textContent = `${title} ditambahkan ke pilihan film.`;
  status.textContent = "";
  showSelected();
  resetResults();
  field.focus();
}

function showOptions(movies, headingLabel = "", silentIfEmpty = false, onClear = null) {
  clearOptions();
  currentOptions = movies.filter((movie) => !selected.has(movie.movie_id));
  if (currentOptions.length === 0) {
    if (!silentIfEmpty) {
      searchStatus.textContent = "Tidak ada judul lain yang cocok.";
    }
    return;
  }
  searchStatus.textContent = "";
  if (headingLabel) {
    const heading = element("li", "suggestions-heading");
    heading.setAttribute("role", "presentation");
    heading.append(element("span", "", headingLabel));
    if (onClear) {
      const clearBtn = element("button", "suggestions-clear", "Hapus");
      clearBtn.type = "button";
      clearBtn.setAttribute("aria-label", "Hapus daftar terakhir dipilih");
      clearBtn.addEventListener("pointerdown", (event) => event.preventDefault());
      clearBtn.addEventListener("click", (event) => {
        event.stopPropagation();
        onClear();
      });
      heading.append(clearBtn);
    }
    options.append(heading);
  }
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

function showQuickSuggestions() {
  if (busy || selected.size >= maxMovies) return;
  const recent = getRecentMovies().filter((movie) => !selected.has(movie.movie_id));
  if (recent.length > 0) {
    showOptions(recent, "Terakhir dipilih", true, () => {
      clearRecentMovies();
      showQuickSuggestions();
      searchStatus.textContent = "Daftar terakhir dipilih dihapus.";
      field.focus();
    });
    return;
  }
  const picks = QUICK_PICKS.filter((movie) => !selected.has(movie.movie_id));
  showOptions(picks, "Contoh populer", true);
}

function selectOption(index) {
  const count = currentOptions.length;
  activeOption = (index + count) % count;
  const optionElements = Array.from(options.querySelectorAll('[role="option"]'));
  for (const [position, option] of optionElements.entries()) {
    option.setAttribute("aria-selected", String(position === activeOption));
  }
  const active = optionElements[activeOption];
  if (active) {
    field.setAttribute("aria-activedescendant", active.id);
    active.scrollIntoView({ block: "nearest" });
  }
}

field.addEventListener("focus", () => {
  if (field.value.trim().length === 0) {
    showQuickSuggestions();
  }
});

field.addEventListener("input", () => {
  stopSearch();
  searchStatus.textContent = "";
  const query = field.value.trim();
  if (query.length === 0) {
    showQuickSuggestions();
    return;
  }
  if (query.length < 2) {
    searchStatus.textContent = "Ketik minimal 2 huruf untuk mencari judul.";
    return;
  }

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

genre.addEventListener("change", () => {
  syncFormFilterReset();
  resetResults();
});
for (const pill of genrePills) {
  pill.addEventListener("click", () => {
    const targetGenre = pill.dataset.genre || "";
    genre.value = genre.value === targetGenre ? "" : targetGenre;
    syncFormFilterReset();
    resetResults();
  });
}
yearFrom.addEventListener("input", () => {
  syncFormFilterReset();
  resetResults();
});
yearTo.addEventListener("input", () => {
  syncFormFilterReset();
  resetResults();
});
resetFormFilters.addEventListener("click", () => {
  genre.value = "";
  yearFrom.value = "";
  yearTo.value = "";
  syncFormFilterReset();
  resetResults();
  field.focus();
});
retryButton.addEventListener("click", () => form.requestSubmit());
quickStartButton.addEventListener("click", () => {
  if (busy) return;
  selected.clear();
  for (const movie of QUICK_PICKS.slice(0, 2)) {
    selected.set(movie.movie_id, movie);
  }
  genre.value = "";
  yearFrom.value = "";
  yearTo.value = "";
  syncFormFilterReset();
  showSelected();
  form.requestSubmit();
});
resetGenre.addEventListener("click", () => {
  genre.value = "";
  yearFrom.value = "";
  yearTo.value = "";
  syncFormFilterReset();
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

  const rawFrom = yearFrom.value.trim();
  const rawTo = yearTo.value.trim();
  const fromYear = rawFrom ? Number(rawFrom) : null;
  const toYear = rawTo ? Number(rawTo) : null;
  if (fromYear !== null && !Number.isInteger(fromYear)) {
    status.textContent = "Tahun awal harus berupa angka bulat.";
    status.classList.add("notice--error");
    yearFrom.focus();
    return;
  }
  if (toYear !== null && !Number.isInteger(toYear)) {
    status.textContent = "Tahun akhir harus berupa angka bulat.";
    status.classList.add("notice--error");
    yearTo.focus();
    return;
  }
  if (fromYear !== null && toYear !== null && fromYear > toYear) {
    status.textContent = "Tahun awal tidak boleh lebih besar dari tahun akhir.";
    status.classList.add("notice--error");
    yearFrom.focus();
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
      body: JSON.stringify({
        movie_ids: [...selected.keys()],
        genre: genre.value || null,
        year_from: fromYear,
        year_to: toYear,
      }),
    });
    resultCards.replaceChildren(...saved.results.map(movieCard));
    renderActiveFilters(genre.value || null, fromYear, toYear);
    resultStatus.textContent = saved.results.length
      ? `${saved.results.length} film ditemukan. Sesi disimpan ke riwayat.`
      : "Sesi disimpan ke riwayat.";
    if (!saved.results.length) {
      const hasFilter = Boolean(genre.value || fromYear !== null || toYear !== null);
      if (emptyIcon) {
        emptyIcon.classList.remove("state-icon--gold");
        emptyIcon.classList.add("state-icon--muted");
      }
      if (emptyZeroIcon) emptyZeroIcon.hidden = true;
      if (emptyNoResultsIcon) emptyNoResultsIcon.hidden = false;
      emptyTitle.textContent = "Belum ada film yang cocok";
      emptyMessage.textContent = hasFilter ? "Coba ganti film pilihan atau cari tanpa filter." : "Coba pilih judul lain.";
      quickStartButton.hidden = true;
      resetGenre.hidden = !hasFilter;
      empty.hidden = false;
    }
    historyLink.href = `/history?session=${saved.id}`;
    historyLink.hidden = false;
    resultTitle.focus();
  } catch (error) {
    empty.hidden = true;
    activeFilters.hidden = true;
    resultStatus.textContent = "";
    resultStatus.classList.remove("notice--error");
    errorMessage.textContent = error.message || "Terjadi gangguan koneksi atau layanan sedang tidak tersedia.";
    errorState.hidden = false;
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
      if (session.year_from != null) yearFrom.value = session.year_from;
      if (session.year_to != null) yearTo.value = session.year_to;
      syncFormFilterReset();
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
