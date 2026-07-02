const profileTitle = document.querySelector("#profile-title");
const profileSubtitle = document.querySelector("#profile-subtitle");
const profileDetail = document.querySelector("#profile-detail");

const infoUrl = "/api/company/get_company_info";
const stockUrl = "/api/company/get_stock_price";

function normalizeItems(payload) {
  const item = payload?.body?.items?.item;
  if (!item) return [];
  return Array.isArray(item) ? item : [item];
}

function firstItem(payload) {
  return normalizeItems(payload)[0] || {};
}

function text(value, fallback = "-") {
  return value === undefined || value === null || value === "" ? fallback : value;
}

function formatNumber(value) {
  if (value === undefined || value === null || value === "") return "-";
  const numeric = Number(String(value).replaceAll(",", ""));
  return Number.isFinite(numeric) ? numeric.toLocaleString("ko-KR") : value;
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

function renderError(message) {
  profileTitle.textContent = "기업 프로필을 열 수 없습니다";
  profileSubtitle.textContent = message;
  profileDetail.innerHTML = `
    <div class="empty-state">
      <span class="empty-kicker">Error</span>
      <p>${message}</p>
    </div>
  `;
}

function renderCompanyDetail({ outline, listed, stock }) {
  const summary = stock?.summary || {};
  const price = summary.price || summary.extracted_price;
  const change = summary.price_movement?.percentage || summary.price_movement?.value;

  profileTitle.textContent = text(outline.corpNm, "기업 프로필");
  profileSubtitle.textContent = text(outline.corpEnsnNm, "영문명 정보 없음");

  profileDetail.innerHTML = `
    <div class="detail-header">
      <h2>${text(outline.corpNm)}</h2>
      <p>${text(outline.corpEnsnNm, "영문명 정보 없음")}</p>
    </div>
    <div class="detail-body">
      <article class="info-block">
        <h3>기업 개요</h3>
        <dl class="kv">
          <dt>법인등록번호</dt><dd>${text(outline.crno)}</dd>
          <dt>대표자</dt><dd>${text(outline.enpRprFnm)}</dd>
          <dt>사업자번호</dt><dd>${text(outline.bzno)}</dd>
          <dt>설립일</dt><dd>${text(outline.enpEstbDt)}</dd>
        </dl>
      </article>
      <article class="info-block">
        <h3>상장 정보</h3>
        <dl class="kv">
          <dt>종목명</dt><dd>${text(listed.itmsNm)}</dd>
          <dt>단축코드</dt><dd>${text(listed.srtnCd)}</dd>
          <dt>시장</dt><dd>${text(listed.mrktCtg)}</dd>
          <dt>ISIN</dt><dd>${text(listed.isinCd)}</dd>
        </dl>
      </article>
      <article class="info-block">
        <h3>주가</h3>
        <div class="price">${formatNumber(price)}</div>
        <div class="price-meta">${text(change, "변동 정보 없음")}</div>
      </article>
      <article class="info-block full">
        <h3>주소</h3>
        <dl class="kv">
          <dt>도로명</dt><dd>${text(outline.enpBsadr)}</dd>
          <dt>홈페이지</dt><dd>${text(outline.enpHmpgUrl)}</dd>
        </dl>
      </article>
    </div>
  `;
}

async function loadProfile() {
  const crno = new URLSearchParams(window.location.search).get("crno");
  if (!crno) {
    renderError("법인등록번호가 필요합니다.");
    return;
  }

  try {
    const info = await fetchJson(infoUrl, {
      corporate_registration_number: crno,
      page: 1,
      per_page: 10,
    });
    const outline = firstItem(info.corp_outline);
    const listed = firstItem(info.krx_listed_item);
    let stock = null;

    if (listed.srtnCd) {
      stock = await fetchJson(stockUrl, {
        stock_code: listed.srtnCd.replace(/^A/, ""),
        exchange: "KRX",
        language: "ko",
        window: "1M",
      }).catch(() => null);
    }

    renderCompanyDetail({
      outline,
      listed,
      stock,
    });
  } catch (error) {
    renderError(error.message);
  }
}

loadProfile();
