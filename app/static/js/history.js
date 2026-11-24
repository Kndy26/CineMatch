import { api, displayTitle, element, matchScore } from "./site.js";

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
const detailDialog = document.querySelector("#history-dialog");
const detailBody = document.querySelector("#history-detail");
const deleteDialog = document.querySelector("#delete-dialog");
const deleteForm = document.querySelector("#delete-form");
const deleteCancel = document.querySelector("#delete-cancel");
const deleteConfirm = document.querySelector("#delete-confirm");
const deleteStatus = document.querySelector("#delete-status");
const deleteName = document.querySelector("#delete-session-name");
const dateFormat = new Intl.DateTimeFormat("id-ID", { dateStyle: "medium", timeStyle: "short" });

let listRequest;
let detailRequest;
let searchTimer;
let nextOffset = null;
let failedOffset = 0;
let pendingDelete;
let deleting = false;

function useTemplate(id, className = "button button--quiet") {
  const link = element("a", className, "Pakai lagi ↗");
  link.href = `/discover?template=${id}`;
  return link;
}

function sessionCard(session) {
  const card = element("article", "panel history-card");
  card.dataset.sessionId = session.id;
  const title = session.inputs.map((film) => displayTitle(film.title)).join(" + ");
  const metadata = [
    dateFormat.format(new Date(session.created_at)), session.preferred_genre, `${session.results.length} hasil`,
  ].filter(Boolean);
  const copy = element("div");
  copy.append(element("h3", "", title), element("p", "fine-print", metadata.join(" · ")));
  if (session.results.length) {
    const preview = session.results.slice(0, 2).map((film) => displayTitle(film.title)).join(", ");
    const remainder = session.results.length - 2;
    copy.append(element("p", "muted", remainder > 0 ? `${preview} +${remainder}` : preview));
  }
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
  card.append(copy, actions);
  return card;
}

async function loadHistory(offset = 0) {
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
    const page = await api(`/api/recommendations?${params}`, { signal: request.signal });
    if (request.signal.aborted) return;
    nextOffset = page.next_offset;
    list.append(...page.items.map(sessionCard));
    status.textContent = "";
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
    status.textContent = error.message;
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

detailDialog.addEventListener("close", () => detailRequest?.abort());
list.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const card = button.closest("[data-session-id]");
  const sessionId = card.dataset.sessionId;
  if (button.dataset.action === "detail") {
    openDetail(sessionId);
  } else {
    pendingDelete = sessionId;
    deleteName.textContent = card.querySelector("h3").textContent;
    deleteStatus.textContent = "";
    deleteDialog.showModal();
  }
});

deleteCancel.addEventListener("click", () => deleteDialog.close());
deleteDialog.addEventListener("cancel", (event) => {
  if (deleting) event.preventDefault();
});
deleteDialog.addEventListener("close", () => { pendingDelete = null; });
deleteForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!pendingDelete || deleting) return;

  deleting = true;
  deleteConfirm.disabled = true;
  deleteConfirm.textContent = "Menghapus…";
  deleteCancel.disabled = true;
  deleteStatus.textContent = "";
  try {
    await api(`/api/recommendations/${pendingDelete}`, { method: "DELETE" });
    deleteDialog.close();
    clearTimeout(searchTimer);
    await loadHistory();
    if (!status.textContent) status.textContent = "Sesi dihapus dari riwayat.";
  } catch (error) {
    deleteStatus.textContent = error.message;
  } finally {
    deleting = false;
    deleteConfirm.disabled = false;
    deleteConfirm.textContent = "Hapus sesi";
    deleteCancel.disabled = false;
  }
});

loadHistory();
const activeSession = new URLSearchParams(location.search).get("session");
if (activeSession && /^[0-9a-f-]{36}$/i.test(activeSession)) openDetail(activeSession);
