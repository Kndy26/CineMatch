import { api, displayTitle, element, matchScore, artwork } from "./site.js";

const list = document.querySelector("#history-list");
const search = document.querySelector("#history-search");
const status = document.querySelector("#history-status");
const empty = document.querySelector("#history-empty");
const emptyTitle = document.querySelector("#history-empty-title");
const emptyMessage = document.querySelector("#history-empty-message");
const emptyLink = document.querySelector("#history-empty-link");
const clearSearch = document.querySelector("#history-clear-search");
const loading = document.querySelector("#history-loading");
const retry = document.querySelector("#history-retry");
const more = document.querySelector("#history-more");
const reset = document.querySelector("#history-reset");
const detailDialog = document.querySelector("#history-dialog");
const detailBody = document.querySelector("#history-detail");
const deleteDialog = document.querySelector("#delete-dialog");
const deleteForm = document.querySelector("#delete-form");
const deleteCancel = document.querySelector("#delete-cancel");
const deleteConfirm = document.querySelector("#delete-confirm");
const deleteStatus = document.querySelector("#delete-status");
const deleteName = document.querySelector("#delete-session-name");
const deleteTitle = document.querySelector("#delete-dialog-title");
const deleteSingleNote = document.querySelector("#delete-single-note");
const deleteResetNote = document.querySelector("#delete-reset-note");
const dateFormat = new Intl.DateTimeFormat("id-ID", { dateStyle: "medium", timeStyle: "short" });

let listRequest;
let detailRequest;
let searchTimer;
let nextOffset = null;
let failedOffset = 0;
let deleteSessionId = null;
let deleting = false;

function useTemplate(id, className = "button button--quiet") {
  const link = element("a", className, "Pakai lagi ↗");
  link.href = `/discover?template=${id}`;
  return link;
}

function createThumbStack(movies) {
  const stack = element("div", "history-thumb-stack");
  stack.setAttribute("aria-hidden", "true");
  const slice = movies.slice(0, 3);
  for (const film of slice) {
    const curated = artwork[film.movie_id];
    if (curated?.poster) {
      const img = element("img", "history-thumb");
      img.src = `/static/images/posters/${film.movie_id}.jpg`;
      img.alt = "";
      img.width = 44;
      img.height = 66;
      img.loading = "lazy";
      img.addEventListener("error", () => {
        const fallback = element("span", "history-thumb history-thumb--fallback", displayTitle(film.title).slice(0, 2).toUpperCase());
        img.replaceWith(fallback);
      }, { once: true });
      stack.append(img);
    } else {
      const fallback = element("span", "history-thumb history-thumb--fallback", displayTitle(film.title).slice(0, 2).toUpperCase());
      stack.append(fallback);
    }
  }
  return stack;
}

function sessionCard(session) {
  const card = element("article", "panel history-card");
  card.dataset.sessionId = session.id;
  const title = session.inputs.map((film) => displayTitle(film.title)).join(" + ");
  const metadata = [
    dateFormat.format(new Date(session.created_at)), session.preferred_genre, `${session.results.length} rekomendasi`,
  ].filter(Boolean);

  const main = element("div", "history-card-main");
  main.append(createThumbStack(session.inputs));

  const copy = element("div", "history-card-copy");
  copy.append(
    element("h3", "", title),
    element("p", "fine-print", metadata.join(" · "))
  );
  if (session.results.length) {
    const preview = session.results.slice(0, 2).map((film) => displayTitle(film.title)).join(", ");
    const remainder = session.results.length - 2;
    copy.append(element("p", "muted", remainder > 0 ? `Hasil: ${preview} +${remainder}` : `Hasil: ${preview}`));
  }
  main.append(copy);

  const actions = element("div", "action-row");
  const detail = element("button", "button button--quiet", "Detail");
  detail.type = "button";
  detail.dataset.action = "detail";
  detail.setAttribute("aria-label", `Detail sesi ${title}`);
  const remove = element("button", "button button--quiet delete-action", "Hapus");
  remove.type = "button";
  remove.dataset.action = "delete";
  remove.setAttribute("aria-label", `Hapus sesi ${title}`);
  actions.append(detail, useTemplate(session.id), remove);

  card.append(main, actions);
  return card;
}

async function loadHistory(offset = 0, successMessage = "") {
  listRequest?.abort();
  const request = new AbortController();
  listRequest = request;
  const query = search.value.trim();
  empty.hidden = true;
  more.hidden = true;
  retry.hidden = true;
  loading.hidden = offset !== 0;
  list.setAttribute("aria-busy", "true");
  status.classList.remove("notice--error");
  status.textContent = "Memuat riwayat…";
  if (offset === 0) list.replaceChildren();

  try {
    const params = new URLSearchParams({ limit: "12", offset: String(offset) });
    if (query) params.set("q", query);
    const page = await api(`/api/recommendations?${params}`, {
      signal: request.signal,
      cache: "no-store",
    });
    if (request.signal.aborted) return;
    nextOffset = page.next_offset;
    list.append(...page.items.map(sessionCard));
    status.textContent = successMessage;
    if (list.childElementCount === 0) {
      emptyTitle.textContent = query ? "Tidak ada sesi yang cocok" : "Belum ada sesi tersimpan";
      emptyMessage.textContent = query ? "Coba kata kunci atau genre lain." : "Buat rekomendasi pertamamu di Discover.";
      emptyLink.hidden = Boolean(query);
      clearSearch.hidden = !query;
      empty.hidden = false;
    }
    more.hidden = nextOffset === null;
  } catch (error) {
    if (request.signal.aborted) return;
    status.textContent = [successMessage, error.message].filter(Boolean).join(" ");
    status.classList.add("notice--error");
    failedOffset = offset;
    retry.hidden = false;
  } finally {
    if (listRequest === request) {
      loading.hidden = true;
      list.removeAttribute("aria-busy");
    }
  }
}

search.addEventListener("input", () => {
  clearTimeout(searchTimer);
  listRequest?.abort();
  retry.hidden = true;
  more.hidden = true;
  searchTimer = setTimeout(() => loadHistory(), 250);
});
clearSearch.addEventListener("click", () => {
  clearTimeout(searchTimer);
  search.value = "";
  search.focus();
  loadHistory();
});
retry.addEventListener("click", () => loadHistory(failedOffset));
more.addEventListener("click", () => {
  if (nextOffset !== null) loadHistory(nextOffset);
});

async function openDetail(sessionId) {
  detailRequest?.abort();
  const request = new AbortController();
  detailRequest = request;
  detailBody.replaceChildren(element("p", "muted", "Memuat detail sesi…"));
  if (!detailDialog.open) detailDialog.showModal();

  try {
    const session = await api(`/api/recommendations/${sessionId}`, { signal: request.signal });
    if (request.signal.aborted) return;
    const titles = session.inputs.map((film) => displayTitle(film.title)).join(" + ");
    const recommendations = element("ul", "session-detail-list");
    for (const movie of session.results) {
      const row = element("li");
      row.append(element("span", "", displayTitle(movie.title)), element("span", "", matchScore(movie.similarity_score)));
      recommendations.append(row);
    }
    const meta = [dateFormat.format(new Date(session.created_at)), session.preferred_genre].filter(Boolean);
    const actions = element("div", "action-row");
    actions.append(useTemplate(session.id, "button button--gold"));
    detailBody.replaceChildren(
      element("h3", "", titles),
      element("p", "fine-print", meta.join(" · ")),
      session.results.length ? recommendations : element("p", "muted", "Sesi ini tidak memiliki hasil rekomendasi."),
      actions,
    );
  } catch (error) {
    if (!request.signal.aborted) detailBody.replaceChildren(element("p", "notice--error", error.message));
  }
}

let lastDetailOpener = null;
let lastDeleteOpener = null;

function openDelete(button, sessionId, title = "") {
  if (deleting || deleteDialog.open) return;
  const resetAll = sessionId === null;
  lastDeleteOpener = button;
  deleteSessionId = sessionId;
  deleteTitle.textContent = resetAll ? "Reset preferensi?" : "Hapus sesi ini?";
  deleteConfirm.textContent = resetAll ? "Hapus semua riwayat" : "Hapus sesi";
  deleteName.textContent = title;
  deleteSingleNote.hidden = resetAll;
  deleteResetNote.hidden = !resetAll;
  deleteStatus.textContent = "";
  deleteDialog.showModal();
}

detailDialog.addEventListener("close", () => {
  detailRequest?.abort();
  lastDetailOpener?.focus();
});
list.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const card = button.closest("[data-session-id]");
  const sessionId = card.dataset.sessionId;
  if (button.dataset.action === "detail") {
    lastDetailOpener = button;
    openDetail(sessionId);
  } else {
    openDelete(button, sessionId, card.querySelector("h3").textContent);
  }
});

reset.addEventListener("click", () => openDelete(reset, null));
deleteCancel.addEventListener("click", () => deleteDialog.close());
deleteDialog.addEventListener("cancel", (event) => {
  if (deleting) event.preventDefault();
});
deleteDialog.addEventListener("close", () => {
  if (!deleteDialog.open) lastDeleteOpener?.focus();
});
deleteForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!deleteDialog.open || deleting) return;

  const sessionId = deleteSessionId;
  const resetAll = sessionId === null;
  const path = resetAll ? "/api/recommendations" : `/api/recommendations/${sessionId}`;
  const action = deleteConfirm.textContent;
  deleting = true;
  deleteConfirm.disabled = true;
  deleteConfirm.textContent = "Menghapus…";
  deleteCancel.disabled = true;
  deleteStatus.textContent = "";
  try {
    await api(path, { method: "DELETE" });
  } catch (error) {
    deleteStatus.textContent = error.message;
    return;
  } finally {
    deleting = false;
    deleteConfirm.disabled = false;
    deleteConfirm.textContent = action;
    deleteCancel.disabled = false;
  }

  deleteDialog.close();
  clearTimeout(searchTimer);
  if (resetAll) search.value = "";
  const url = new URL(window.location.href);
  const openSession = url.searchParams.get("session");
  if (openSession && (resetAll || openSession === sessionId)) {
    url.searchParams.delete("session");
    window.history.replaceState(window.history.state, "", url);
  }
  const message = resetAll ? "Preferensi direset. Semua riwayat telah dihapus." : "Sesi dihapus dari riwayat.";
  await loadHistory(0, message);
  if (!resetAll && !deleteDialog.open) search.focus();
});

window.addEventListener("pageshow", (event) => {
  if (event.persisted) loadHistory();
});
loadHistory();
const activeSession = new URLSearchParams(location.search).get("session");
if (activeSession && /^[0-9a-f-]{36}$/i.test(activeSession)) openDetail(activeSession);
