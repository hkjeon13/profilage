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

function formatChartDate(value) {
  if (!value) return "";
  const parsed = new Date(value);
  if (!Number.isNaN(parsed.getTime())) {
    return parsed.toLocaleDateString("ko-KR", {
      month: "numeric",
      day: "numeric",
    });
  }
  return String(value).split(",")[0];
}

function formatTooltipDate(value) {
  if (!value) return "";
  const parsed = new Date(value);
  if (!Number.isNaN(parsed.getTime())) {
    return parsed.toLocaleDateString("ko-KR", {
      year: "numeric",
      month: "long",
      day: "numeric",
    });
  }
  return String(value).split(",")[0];
}

function renderStockChart(stock) {
  const points = (stock?.graph || [])
    .map((point) => ({
      price: Number(point.price),
      date: point.date,
      volume: Number(point.volume),
    }))
    .filter((point) => Number.isFinite(point.price));

  if (points.length < 2) return "";

  const width = 640;
  const height = 180;
  const paddingX = 14;
  const paddingY = 18;
  const prices = points.map((point) => point.price);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const range = max - min || 1;
  const chartWidth = width - paddingX * 2;
  const chartHeight = height - paddingY * 2;
  const coordinates = points.map((point, index) => {
    const x =
      paddingX + (index / Math.max(points.length - 1, 1)) * chartWidth;
    const y = paddingY + ((max - point.price) / range) * chartHeight;
    return { x, y, price: point.price, date: point.date };
  });
  const interactionPoints = coordinates.map((point, index) => ({
    index,
    x: Number(point.x.toFixed(2)),
    y: Number(point.y.toFixed(2)),
    price: point.price,
    date: point.date,
    volume: points[index].volume,
  }));
  const linePath = coordinates
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`)
    .join(" ");
  const areaPath = `${linePath} L ${coordinates.at(-1).x.toFixed(2)} ${height - paddingY} L ${coordinates[0].x.toFixed(2)} ${height - paddingY} Z`;
  const trendClass =
    coordinates.at(-1).price >= coordinates[0].price ? "is-up" : "is-down";

  return `
    <div class="stock-chart" aria-label="1개월 주가 차트" data-chart-points="${encodeURIComponent(JSON.stringify(interactionPoints))}" data-chart-width="${width}">
      <div class="stock-chart-tooltip" role="status" aria-live="polite">
        <strong>${formatChartDate(points.at(-1).date)}</strong>
        <span>${formatNumber(points.at(-1).price)} KRW</span>
      </div>
      <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="1개월 주가 추이" tabindex="0">
        <path class="stock-chart-grid" d="M ${paddingX} ${height / 2} H ${width - paddingX}" />
        <path class="stock-chart-area ${trendClass}" d="${areaPath}" />
        <path class="stock-chart-line ${trendClass}" d="${linePath}" />
        <line class="stock-chart-guide" x1="${coordinates.at(-1).x.toFixed(2)}" y1="${paddingY}" x2="${coordinates.at(-1).x.toFixed(2)}" y2="${height - paddingY}" />
        <circle class="stock-chart-dot ${trendClass}" cx="${coordinates.at(-1).x.toFixed(2)}" cy="${coordinates.at(-1).y.toFixed(2)}" r="4" />
        <rect class="stock-chart-hit-area" x="0" y="0" width="${width}" height="${height}" />
      </svg>
      <div class="stock-chart-meta">
        <span>${formatChartDate(points[0].date)}</span>
        <span>${formatNumber(min)} - ${formatNumber(max)}</span>
        <span>${formatChartDate(points.at(-1).date)}</span>
      </div>
    </div>
  `;
}

function updateStockChartSelection(chart, point) {
  const tooltip = chart.querySelector(".stock-chart-tooltip");
  const guide = chart.querySelector(".stock-chart-guide");
  const dot = chart.querySelector(".stock-chart-dot");
  if (!tooltip || !guide || !dot) return;

  const chartWidth = Number(chart.dataset.chartWidth || 640);
  const tooltipPosition = Math.min(Math.max((point.x / chartWidth) * 100, 15), 85);
  const volumeText = Number.isFinite(point.volume)
    ? `<small>거래량 ${formatNumber(point.volume)}</small>`
    : "";

  tooltip.style.left = `${tooltipPosition}%`;
  tooltip.innerHTML = `
    <strong>${formatTooltipDate(point.date)}</strong>
    <span>${formatNumber(point.price)} KRW</span>
    ${volumeText}
  `;
  guide.setAttribute("x1", point.x);
  guide.setAttribute("x2", point.x);
  dot.setAttribute("cx", point.x);
  dot.setAttribute("cy", point.y);
  chart.classList.add("is-active");
}

function setupStockChartInteractions() {
  document.querySelectorAll(".stock-chart").forEach((chart) => {
    const svg = chart.querySelector("svg");
    if (!svg || !chart.dataset.chartPoints) return;

    const points = JSON.parse(decodeURIComponent(chart.dataset.chartPoints));
    if (!points.length) return;

    const selectNearestPoint = (clientX) => {
      if (!Number.isFinite(clientX)) return;
      const rect = svg.getBoundingClientRect();
      const chartWidth = Number(chart.dataset.chartWidth || 640);
      const x = ((clientX - rect.left) / rect.width) * chartWidth;
      const nearest = points.reduce((current, point) =>
        Math.abs(point.x - x) < Math.abs(current.x - x) ? point : current,
      );
      updateStockChartSelection(chart, nearest);
    };
    const selectFromTouch = (event) => {
      selectNearestPoint(event.touches?.[0]?.clientX);
    };

    updateStockChartSelection(chart, points.at(-1));

    chart.addEventListener("pointermove", (event) => {
      selectNearestPoint(event.clientX);
    });
    chart.addEventListener("pointerdown", (event) => {
      try {
        chart.setPointerCapture?.(event.pointerId);
      } catch {
        // Synthetic and some mobile browser pointer events cannot be captured.
      }
      selectNearestPoint(event.clientX);
    });
    chart.addEventListener("mousemove", (event) => {
      selectNearestPoint(event.clientX);
    });
    chart.addEventListener("mousedown", (event) => {
      selectNearestPoint(event.clientX);
    });
    chart.addEventListener("click", (event) => {
      selectNearestPoint(event.clientX);
    });
    chart.addEventListener("touchstart", selectFromTouch, { passive: true });
    chart.addEventListener("touchmove", selectFromTouch, { passive: true });
    svg.addEventListener("focus", () => {
      updateStockChartSelection(chart, points.at(-1));
    });
    svg.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
      event.preventDefault();
      const activeX = Number(chart.querySelector(".stock-chart-dot")?.getAttribute("cx"));
      const currentIndex = points.findIndex((point) => point.x === activeX);
      const fallbackIndex = points.length - 1;
      const nextIndex =
        event.key === "ArrowLeft"
          ? Math.max((currentIndex < 0 ? fallbackIndex : currentIndex) - 1, 0)
          : Math.min((currentIndex < 0 ? fallbackIndex : currentIndex) + 1, points.length - 1);
      updateStockChartSelection(chart, points[nextIndex]);
    });
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

function renderProfileSkeleton() {
  profileTitle.innerHTML = `<span class="skeleton-line skeleton-hero-title"></span>`;
  profileSubtitle.innerHTML = `<span class="skeleton-line skeleton-hero-subtitle"></span>`;
  profileDetail.innerHTML = `
    <div class="detail-header skeleton-detail-header" aria-hidden="true">
      <span class="skeleton-line skeleton-title"></span>
      <span class="skeleton-line skeleton-short"></span>
    </div>
    <div class="detail-body" aria-hidden="true">
      ${Array.from({ length: 2 })
        .map(
          () => `
            <article class="info-block skeleton-block">
              <span class="skeleton-line skeleton-section-title"></span>
              <span class="skeleton-line"></span>
              <span class="skeleton-line"></span>
              <span class="skeleton-line skeleton-short"></span>
            </article>
          `,
        )
        .join("")}
      <article class="info-block skeleton-block">
        <span class="skeleton-line skeleton-section-title"></span>
        <span class="skeleton-line skeleton-price"></span>
        <span class="skeleton-line skeleton-short"></span>
        <span class="skeleton-chart"></span>
      </article>
      <article class="info-block full skeleton-block">
        <span class="skeleton-line skeleton-section-title"></span>
        <span class="skeleton-line"></span>
        <span class="skeleton-line skeleton-wide"></span>
      </article>
    </div>
  `;
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
  setupStockChartInteractions();
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
        ${renderStockChart(stock)}
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
  setupStockChartInteractions();
}

async function loadProfile() {
  const crno = new URLSearchParams(window.location.search).get("crno");
  if (!crno) {
    renderError("법인등록번호가 필요합니다.");
    return;
  }

  renderProfileSkeleton();

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
        corporate_registration_number: crno,
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
