const form = document.querySelector("#search-form");
const queryInput = document.querySelector("#company-query");
const statusEl = document.querySelector("#search-status");
const resultList = document.querySelector("#result-list");
const luckySearchButton = document.querySelector("#lucky-search");

const outlineUrl = "/api/company/get_corp_outline";
const listedUrl = "/api/company/get_krx_listed_item";
const COMPARE_STORAGE_KEY = "profilage.compareCompanies";
const MAX_COMPARE_COMPANIES = 4;

function currentSearchQuery() {
  return queryInput.value.trim();
}

function profileUrl(corporateRegistrationNumber, returnQuery = currentSearchQuery()) {
  const endpoint = new URL("/profile", window.location.origin);
  endpoint.searchParams.set("crno", corporateRegistrationNumber);
  if (returnQuery) {
    endpoint.searchParams.set("return_q", returnQuery);
  }
  return `${endpoint.pathname}${endpoint.search}`;
}

function syncSearchUrl(query) {
  const nextUrl = new URL(window.location.href);
  if (query) {
    nextUrl.searchParams.set("q", query);
  } else {
    nextUrl.searchParams.delete("q");
  }
  window.history.replaceState({}, "", nextUrl);
}

function normalizeItems(payload) {
  const item = payload?.body?.items?.item;
  if (!item) return [];
  return Array.isArray(item) ? item : [item];
}

function text(value, fallback = "-") {
  return value === undefined || value === null || value === "" ? fallback : value;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function attr(value, fallback = "") {
  return escapeHtml(text(value, fallback));
}

function formatResultNumber(value) {
  if (value === undefined || value === null || value === "") return "-";
  const numeric = Number(String(value).replaceAll(",", ""));
  return Number.isFinite(numeric) ? numeric.toLocaleString("ko-KR") : text(value);
}

function compareItems() {
  try {
    const parsed = JSON.parse(localStorage.getItem(COMPARE_STORAGE_KEY) || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveCompareItems(items) {
  localStorage.setItem(
    COMPARE_STORAGE_KEY,
    JSON.stringify(items.slice(0, MAX_COMPARE_COMPANIES)),
  );
}

function setStatus(message) {
  statusEl.textContent = message;
}

function clearResults() {
  resultList.innerHTML = "";
}

function renderSearchSkeleton(count = 5) {
  clearResults();
  const fragment = document.createDocumentFragment();

  Array.from({ length: count }).forEach(() => {
    const card = document.createElement("div");
    card.className = "result-card skeleton-card";
    card.setAttribute("aria-hidden", "true");
    card.innerHTML = `
      <span class="skeleton-line skeleton-title"></span>
      <span class="skeleton-line"></span>
      <span class="skeleton-line skeleton-short"></span>
    `;
    fragment.appendChild(card);
  });

  resultList.appendChild(fragment);
}

function renderResults(items) {
  clearResults();
  const fragment = document.createDocumentFragment();

  items.forEach((company) => {
    const displayName = company.listedCorpName || company.corpNm || company.itmsNm;
    const market = company.mrktCtg || company.corpRegMrktDcdNm;
    const card = document.createElement("article");
    card.className = "result-card entity-result-row";
    card.dataset.crno = company.crno;
    card.innerHTML = `
      <div class="result-card-main">
        <div class="result-title-stack">
          <span class="entity-type-badge">기업</span>
          <a class="result-title-link" href="${attr(profileUrl(company.crno))}">
            <strong>${escapeHtml(text(displayName, "기업명 정보 없음"))}</strong>
          </a>
          <span class="result-subtitle">${escapeHtml(text(company.corpEnsnNm || company.listedItemName || company.enpRprFnm, "보조 정보 없음"))}</span>
        </div>
        <div class="result-actions">
          <span class="result-market-badge">${escapeHtml(company.isListed ? text(market, "상장") : "비상장/확인 필요")}</span>
          <a class="result-profile-link" href="${attr(profileUrl(company.crno))}">프로필 보기</a>
          <button
            type="button"
            data-result-compare-add="${attr(company.crno)}"
            data-result-name="${attr(displayName)}"
          >비교 추가</button>
        </div>
      </div>
      <div class="result-meta-grid">
        <span><b>법인등록번호</b>${escapeHtml(text(company.crno))}</span>
        <span><b>업종</b>${escapeHtml(text(company.enpMainBizNm || company.itmsNm, "정보 없음"))}</span>
        <span><b>대표자</b>${escapeHtml(text(company.enpRprFnm, "정보 없음"))}</span>
        <span><b>직원 수</b>${escapeHtml(formatResultNumber(company.enpEmpeCnt))}</span>
      </div>
      <div class="result-data-badges">
        <span>${company.isListed ? "주가 가능" : "주가 미제공"}</span>
        <span>기본정보</span>
        ${company.isListed ? `<span>${escapeHtml(text(company.srtnCd, "종목코드"))}</span>` : ""}
      </div>
    `;
    fragment.appendChild(card);
  });

  resultList.appendChild(fragment);
  setupResultCompareButtons();
}

function setupResultCompareButtons() {
  document.querySelectorAll("[data-result-compare-add]").forEach((button) => {
    if (button.dataset.bound === "true") return;
    button.dataset.bound = "true";
    button.addEventListener("click", () => {
      const crno = button.dataset.resultCompareAdd;
      const name = button.dataset.resultName;
      const nextItems = [
        ...compareItems().filter((item) => item.crno !== crno),
        { crno, name },
      ].slice(0, MAX_COMPARE_COMPANIES);
      saveCompareItems(nextItems);
      button.textContent = "추가됨";
      button.disabled = true;
    });
  });
}

function listedNameCandidates(query) {
  const suffixes = [
    "",
    "전자",
    "전기",
    "물산",
    "SDI",
    "에스디에스",
    "중공업",
    "생명보험",
    "화재해상보험",
    "증권",
    "카드",
    "바이오로직스",
    "하이닉스",
    "화학",
  ];

  return suffixes
    .map((suffix) => `${query}${suffix}`)
    .filter((value, index, values) => value && values.indexOf(value) === index);
}

function mergeCompanyResults(outlineItems, listedItems) {
  const companies = new Map();
  const listedMarketNames = new Set(["유가", "코스닥", "코넥스"]);

  listedItems.forEach((item, index) => {
    const key = item.crno || `${item.itmsNm}-${item.srtnCd}`;
    companies.set(key, {
      ...item,
      corpNm: item.corpNm || item.itmsNm,
      listedCorpName: item.corpNm || item.itmsNm,
      listedItemName: item.itmsNm,
      isListed: true,
      searchRank: index,
    });
  });

  outlineItems.forEach((item) => {
    const key = item.crno || `${item.corpNm}-${item.bzno}`;
    const existing = companies.get(key) || {};
    const isListed =
      Boolean(existing.isListed) || listedMarketNames.has(item.corpRegMrktDcdNm);
    companies.set(key, {
      ...item,
      ...existing,
      corpNm: existing.corpNm || item.corpNm || existing.itmsNm,
      listedCorpName: existing.listedCorpName,
      mrktCtg: existing.mrktCtg || item.corpRegMrktDcdNm,
      isListed,
      searchRank: existing.searchRank ?? 100,
    });
  });

  return Array.from(companies.values()).sort((left, right) => {
    if (left.isListed !== right.isListed) return left.isListed ? -1 : 1;
    if (left.searchRank !== right.searchRank) return left.searchRank - right.searchRank;
    return text(left.corpNm).localeCompare(text(right.corpNm), "ko");
  });
}

async function fetchJson(url, params) {
  const endpoint = new URL(url, window.location.origin);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      endpoint.searchParams.set(key, value);
    }
  });

  const response = await fetch(endpoint);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || "요청에 실패했습니다.");
  }
  return response.json();
}

async function loadCompanySearchResults(query) {
  const listedRequests = listedNameCandidates(query).map((itemName) =>
    fetchJson(listedUrl, {
      item_name: itemName,
      page: 1,
      per_page: 1,
    }).catch(() => null),
  );
  const [outlinePayload, ...listedPayloads] = await Promise.all([
    fetchJson(outlineUrl, {
      company_name: query,
      page: 1,
      per_page: 1000,
    }),
    ...listedRequests,
  ]);
  const outlineItems = normalizeItems(outlinePayload);
  const listedItems = listedPayloads.flatMap((payload) => normalizeItems(payload));
  const listedCrnos = new Set(listedItems.map((item) => item.crno).filter(Boolean));
  const initialItems = mergeCompanyResults(outlineItems, listedItems).slice(0, 20);
  const listedByCrnoPayloads = await Promise.all(
    initialItems
      .map((item) => item.crno)
      .filter(
        (crno, index, crnos) =>
          crno && !listedCrnos.has(crno) && crnos.indexOf(crno) === index,
      )
      .map((crno) =>
        fetchJson(listedUrl, {
          corporate_registration_number: crno,
          page: 1,
          per_page: 1,
        }).catch(() => null),
      ),
  );
  return mergeCompanyResults(
    outlineItems,
    [
      ...listedItems,
      ...listedByCrnoPayloads.flatMap((payload) => normalizeItems(payload)),
    ],
  ).slice(0, 20);
}

async function searchCompanies(query) {
  document.body.classList.remove("is-idle");
  queryInput.value = query;
  syncSearchUrl(query);
  setStatus("검색 중...");
  renderSearchSkeleton();

  try {
    const items = await loadCompanySearchResults(query);

    if (items.length === 0) {
      setStatus("검색 결과가 없습니다.");
      clearResults();
      return;
    }

    setStatus(`${items.length.toLocaleString("ko-KR")}개 결과`);
    renderResults(items);
  } catch (error) {
    setStatus(error.message);
    clearResults();
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const query = currentSearchQuery();
  if (!query) {
    setStatus("기업명을 입력해주세요.");
    clearResults();
    syncSearchUrl("");
    return;
  }
  searchCompanies(query);
});

luckySearchButton?.addEventListener("click", () => {
  queryInput.value = "삼성전자";
  searchCompanies("삼성전자");
});

document.querySelectorAll("[data-example-query]").forEach((button) => {
  button.addEventListener("click", () => {
    searchCompanies(button.dataset.exampleQuery || "");
  });
});

const restoredQuery = new URLSearchParams(window.location.search).get("q");
if (restoredQuery) {
  searchCompanies(restoredQuery);
}
