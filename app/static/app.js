const form = document.querySelector("#search-form");
const queryInput = document.querySelector("#company-query");
const statusEl = document.querySelector("#search-status");
const resultList = document.querySelector("#result-list");
const luckySearchButton = document.querySelector("#lucky-search");

const outlineUrl = "/api/company/get_corp_outline";
const listedUrl = "/api/company/get_krx_listed_item";

function profileUrl(corporateRegistrationNumber) {
  return `/profile?crno=${encodeURIComponent(corporateRegistrationNumber)}`;
}

function normalizeItems(payload) {
  const item = payload?.body?.items?.item;
  if (!item) return [];
  return Array.isArray(item) ? item : [item];
}

function text(value, fallback = "-") {
  return value === undefined || value === null || value === "" ? fallback : value;
}

function setStatus(message) {
  statusEl.textContent = message;
}

function renderResults(items) {
  resultList.innerHTML = "";
  const fragment = document.createDocumentFragment();

  items.forEach((company) => {
    const displayName = company.listedCorpName || company.corpNm || company.itmsNm;
    const market = company.mrktCtg || company.corpRegMrktDcdNm;
    const link = document.createElement("a");
    link.className = "result-card";
    link.href = profileUrl(company.crno);
    link.dataset.crno = company.crno;
    link.innerHTML = `
      <strong>${text(displayName)}</strong>
      <span>법인등록번호 ${text(company.crno)}</span>
      <span>${company.isListed ? `상장 ${text(market)} · ${text(company.srtnCd)}` : `${text(company.enpRprFnm, "대표자 정보 없음")} · ${text(company.bzno, "사업자등록번호 없음")}`}</span>
    `;
    fragment.appendChild(link);
  });

  resultList.appendChild(fragment);
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

async function searchCompanies(query) {
  document.body.classList.remove("is-idle");
  setStatus("검색 중...");
  resultList.innerHTML = "";

  try {
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
    const items = mergeCompanyResults(
      outlineItems,
      [
        ...listedItems,
        ...listedByCrnoPayloads.flatMap((payload) => normalizeItems(payload)),
      ],
    ).slice(0, 20);

    if (items.length === 0) {
      setStatus("검색 결과가 없습니다.");
      return;
    }

    setStatus(`${items.length.toLocaleString("ko-KR")}개 결과`);
    renderResults(items);
  } catch (error) {
    setStatus(error.message);
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const query = queryInput.value.trim();
  if (!query) {
    setStatus("기업명을 입력해주세요.");
    return;
  }
  searchCompanies(query);
});

luckySearchButton.addEventListener("click", () => {
  queryInput.value = "삼성전자";
  searchCompanies("삼성전자");
});
