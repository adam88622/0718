/* ==========================================================================
   台股融資維持率查詢 — render.js (FN-028 / FN-029 / FN-030)
   純 DOM 操作，無框架
   ========================================================================== */

/**
 * 依警戒等級回傳對應 CSS class（FN-030）
 * @param {"danger"|"warn"|"safe"|"na"|string|null|undefined} level
 * @returns {string} "w-danger" | "w-warn" | "w-safe" | "w-na"
 */
function warningClass(level) {
  switch (level) {
    case "danger":
      return "w-danger";
    case "warn":
      return "w-warn";
    case "safe":
      return "w-safe";
    case "na":
    default:
      return "w-na";
  }
}

/** 簡易 HTML escape，避免將後端字串（如股票名稱）直接注入造成 XSS */
function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** 顯示/隱藏 loading 區塊，並連動禁用查詢按鈕（FN-029） */
function showLoading(isLoading) {
  const loadingEl = document.getElementById("loading");
  const submitBtn = document.getElementById("submit-btn");

  if (loadingEl) {
    loadingEl.classList.toggle("hidden", !isLoading);
  }
  if (submitBtn) {
    submitBtn.disabled = !!isLoading;
  }
}

/** 顯示整體錯誤訊息，並清空結果區（FN-029） */
function renderError(message) {
  const errorEl = document.getElementById("error");
  const resultEl = document.getElementById("result");

  if (resultEl) {
    resultEl.innerHTML = "";
  }
  if (errorEl) {
    errorEl.textContent = message || "發生未知錯誤，請稍後再試。";
    errorEl.classList.remove("hidden");
  }
}

/** 清除錯誤訊息區塊 */
function clearError() {
  const errorEl = document.getElementById("error");
  if (errorEl) {
    errorEl.textContent = "";
    errorEl.classList.add("hidden");
  }
}

/**
 * 市場代碼轉中文顯示
 * @param {"tse"|"otc"|string} market
 */
function marketLabel(market) {
  if (market === "tse") return "上市";
  if (market === "otc") return "上櫃";
  return market || "未知";
}

/**
 * 股價相對月線(MA20)/季線(MA60) 位階：↑=股價在均線上、↓=在下、—=資料不足
 */
function maPosHtml(item) {
  function tag(label, above, ma) {
    if (above === null || above === undefined || ma === null || ma === undefined) {
      return `<span class="ma-na">${label}—</span>`;
    }
    const cls = above ? "ma-up" : "ma-down";
    const arrow = above ? "↑" : "↓";
    const maTxt = Number(ma).toLocaleString("zh-TW", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    return `<span class="${cls}" title="${label}線 ${maTxt}（股價在${above ? "上" : "下"}）">${label}${arrow}</span>`;
  }
  return `${tag("月", item.above_ma20, item.ma20_price)} ${tag("季", item.above_ma60, item.ma60_price)}`;
}

/**
 * 繪製查詢結果卡片（FN-028）
 * @param {Object} data MaintenanceResponse
 */
function renderResult(data) {
  clearError();

  const resultEl = document.getElementById("result");
  if (!resultEl) return;

  if (!data) {
    renderError("查詢結果為空，請稍後再試。");
    return;
  }

  const price = data.price || {};
  const average = data.average || {};
  const margin = data.margin || {};
  const ratio = data.ratio || {};

  // ---- 標頭：代號 / 名稱 / market badge / 即時-收盤 pill ----
  const priceTypeClass = price.price_type === "即時" ? "intraday" : "closed";
  const fallbackTag = price.is_fallback
    ? '<span class="fallback-tag">參考價</span>'
    : "";

  const headHtml = `
    <div class="result-head">
      <span class="stock-code">${escapeHtml(data.code)}</span>
      <span class="stock-name">${escapeHtml(data.name)}</span>
      <span class="market-badge">${escapeHtml(marketLabel(data.market))}</span>
      ${
        price.status === "ok"
          ? `<span class="price-type-pill ${priceTypeClass}">${escapeHtml(price.price_type || "")}</span>${fallbackTag}`
          : ""
      }
    </div>
  `;

  // ---- 現價區塊 ----
  let priceValueHtml;
  let priceSubHtml = "";
  if (price.status === "ok" && price.value !== null && price.value !== undefined) {
    priceValueHtml = Number(price.value).toLocaleString("zh-TW", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const subParts = [];
    if (price.prev_close !== null && price.prev_close !== undefined) {
      subParts.push("昨收 " + Number(price.prev_close).toLocaleString("zh-TW", { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
    }
    if (price.as_of) {
      subParts.push(escapeHtml(price.as_of));
    }
    priceSubHtml = subParts.length ? `<div class="info-sub">${subParts.join(" ・ ")}</div>` : "";
  } else {
    priceValueHtml = `<span class="no-data">無資料</span>`;
  }

  // ---- N 日均價區塊 ----
  let avgValueHtml;
  let avgSubHtml = "";
  if (average.status === "ok" && average.value !== null && average.value !== undefined) {
    avgValueHtml = Number(average.value).toLocaleString("zh-TW", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const rangeText = average.start && average.end ? `區間 ${escapeHtml(average.start)} ~ ${escapeHtml(average.end)}` : "";
    const countText = average.count !== null && average.count !== undefined ? `（實際 ${average.count} 筆 / 需求 ${average.n_requested} 筆）` : "";
    const noteText = average.insufficient && average.note ? `<br>⚠ ${escapeHtml(average.note)}` : "";
    avgSubHtml = `<div class="info-sub">${rangeText}${countText}${noteText}</div>`;
  } else {
    avgValueHtml = `<span class="no-data">無資料</span>`;
    if (average.note) {
      avgSubHtml = `<div class="info-sub">${escapeHtml(average.note)}</div>`;
    }
  }

  // ---- 融資餘額區塊 ----
  let marginValueHtml;
  let marginSubHtml = "";
  if (margin.status === "ok" && margin.balance_lots !== null && margin.balance_lots !== undefined) {
    marginValueHtml = Number(margin.balance_lots).toLocaleString("zh-TW") + " 張";
    if (margin.as_of) {
      marginSubHtml = `<div class="info-sub">資料日期 ${escapeHtml(margin.as_of)}</div>`;
    }
  } else {
    marginValueHtml = `<span class="no-data">無資料</span>`;
  }

  // ---- 融資成本（推估）區塊 ----
  const cost = data.cost || {};
  let costValueHtml;
  let costSubHtml = "";
  if (cost.value !== null && cost.value !== undefined) {
    costValueHtml = Number(cost.value).toLocaleString("zh-TW", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const srcLabel = cost.source === "加權融資成本"
      ? "加權推估（券商法）"
      : "N 日均價（簡易）";
    costSubHtml = `<div class="info-sub">${escapeHtml(srcLabel)}${cost.as_of ? "・截至 " + escapeHtml(cost.as_of) : ""}</div>`;
  } else {
    costValueHtml = `<span class="no-data">無資料</span>`;
  }

  const infoGridHtml = `
    <div class="info-grid">
      <div class="info-block">
        <div class="info-label">現價</div>
        <div class="info-value">${priceValueHtml}</div>
        ${priceSubHtml}
      </div>
      <div class="info-block">
        <div class="info-label">融資成本（推估）</div>
        <div class="info-value">${costValueHtml}</div>
        ${costSubHtml}
      </div>
      <div class="info-block">
        <div class="info-label">N 日均價（參考）</div>
        <div class="info-value">${avgValueHtml}</div>
        ${avgSubHtml}
      </div>
      <div class="info-block">
        <div class="info-label">融資餘額</div>
        <div class="info-value">${marginValueHtml}</div>
        ${marginSubHtml}
      </div>
      <div class="info-block">
        <div class="info-label">交易時段</div>
        <div class="info-value">${data.session === "intraday" ? "盤中" : "已收盤"}</div>
      </div>
    </div>
  `;

  // ---- 維持率大字 ----
  let ratioBigHtml;
  const wClass = warningClass(ratio.warning);
  if (ratio.status === "ok" && ratio.value !== null && ratio.value !== undefined) {
    ratioBigHtml = `${Number(ratio.value).toLocaleString("zh-TW", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}<span class="unit">%</span>`;
  } else {
    ratioBigHtml = `無法計算`;
  }

  const ratioSectionHtml = `
    <div class="ratio-section ${wClass}">
      <div class="ratio-label">融資維持率</div>
      <div class="ratio-big">${ratioBigHtml}</div>
      <div class="ratio-tooltip-wrap" tabindex="0">
        <span class="ratio-tooltip-icon">?</span>
        <span>警戒門檻說明</span>
        <span class="ratio-tooltip-text">
          維持率 ≥ 166.67%：回本基準（安全）<br>
          130% ~ 166.67%：虧損中，尚未達追繳線（注意）<br>
          &lt; 130%：達整戶追繳線（危險，可能被追繳或斷頭）<br>
          166.67% ≈ 1 / 融資成數 60%
        </span>
      </div>
    </div>
  `;

  // ---- 公式明細 ----
  const formula = ratio.formula || {};
  let formulaHtml = "";
  if (ratio.status === "ok" && formula.expression) {
    const fPrice = formula.price !== null && formula.price !== undefined
      ? Number(formula.price).toLocaleString("zh-TW", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
      : "—";
    const fAvg = formula.n_day_avg !== null && formula.n_day_avg !== undefined
      ? Number(formula.n_day_avg).toLocaleString("zh-TW", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
      : "—";
    const fRate = formula.margin_rate !== null && formula.margin_rate !== undefined ? formula.margin_rate : "—";

    formulaHtml = `
      <div class="formula-block">
        <div class="formula-title">計算明細（現價 ${fPrice} ／ 融資成本 ${fAvg} ／ 融資成數 ${fRate}）</div>
        <code>${escapeHtml(formula.expression)}</code>
      </div>
    `;
  } else {
    formulaHtml = `
      <div class="formula-block">
        <div class="formula-title">計算明細</div>
        <code>現價或 N 日均價無資料，無法計算維持率</code>
      </div>
    `;
  }

  // ---- 來源 / 時間戳 ----
  const sources = [];
  if (price.source) sources.push("現價: " + price.source);
  if (average.source) sources.push("均價: " + average.source);
  if (margin.source) sources.push("融資: " + margin.source);
  const sourceText = sources.length ? sources.join(" ・ ") : "";

  const metaHtml = `
    <div class="result-meta">
      ${sourceText ? escapeHtml(sourceText) + "<br>" : ""}
      資料產生時間：${escapeHtml(data.generated_at || "")}
    </div>
  `;

  resultEl.innerHTML = `
    <div class="result-card">
      ${headHtml}
      ${infoGridHtml}
      ${ratioSectionHtml}
      ${formulaHtml}
      ${metaHtml}
    </div>
  `;

  const footerTs = document.getElementById("generated-at-footer");
  if (footerTs) {
    footerTs.textContent = data.generated_at ? "最後查詢時間：" + data.generated_at : "";
  }
}

/* ==========================================================================
   融資維持率警示清單（F-010）
   ========================================================================== */

/**
 * 依 band 回傳對應 CSS class（F-010）
 * @param {"danger"|"warn1"|"warn2"|"safe"|string|null|undefined} band
 * @returns {string} "w-danger" | "w-warn1" | "w-warn2" | "w-safe"
 */
function alertBandClass(band) {
  switch (band) {
    case "danger":
      return "w-danger";
    case "warn1":
      return "w-warn1";
    case "warn2":
      return "w-warn2";
    case "safe":
      return "w-safe";
    default:
      return "w-na";
  }
}

/** band 中文標籤 */
function alertBandLabel(band) {
  switch (band) {
    case "danger":
      return "危險";
    case "warn1":
      return "注意一";
    case "warn2":
      return "注意二";
    case "safe":
      return "安全";
    default:
      return "未知";
  }
}

/** 顯示/隱藏警示清單 loading 區塊，並連動禁用掃描按鈕（F-010） */
function showAlertLoading(isLoading) {
  const loadingEl = document.getElementById("alert-loading");
  const scanBtn = document.getElementById("alert-scan-btn");

  if (loadingEl) {
    loadingEl.classList.toggle("hidden", !isLoading);
  }
  if (scanBtn) {
    scanBtn.disabled = !!isLoading;
  }
}

/** 顯示警示清單錯誤訊息，並清空結果區（F-010） */
function renderAlertError(message) {
  const errorEl = document.getElementById("alert-error");
  const resultEl = document.getElementById("alert-result");

  if (resultEl) {
    resultEl.innerHTML = "";
  }
  if (errorEl) {
    errorEl.textContent = message || "掃描失敗，請稍後再試。";
    errorEl.classList.remove("hidden");
  }
}

/** 清除警示清單錯誤訊息區塊（F-010） */
function clearAlertError() {
  const errorEl = document.getElementById("alert-error");
  if (errorEl) {
    errorEl.textContent = "";
    errorEl.classList.add("hidden");
  }
}

/**
 * 繪製警示清單（統計列 + 表格）（F-010）
 * @param {Object} data AlertsResponse（見 GET /api/alerts 契約）
 * @param {number|"all"} filterMax 門檻篩選：數字表示只顯示 ratio <= filterMax 的項目，"all" 表示不篩選
 */
function renderAlerts(data, filterMax) {
  clearAlertError();

  const resultEl = document.getElementById("alert-result");
  if (!resultEl) return;

  if (!data) {
    renderAlertError("掃描結果為空，請稍後再試。");
    return;
  }

  const items = Array.isArray(data.items) ? data.items : [];
  const filtered =
    filterMax === "all" || filterMax === null || filterMax === undefined
      ? items
      : items.filter((item) => typeof item.ratio === "number" && item.ratio <= Number(filterMax));

  const freshCountHtml =
    data.fresh_count !== null && data.fresh_count !== undefined
      ? `<span>急殺 <strong>${escapeHtml(data.fresh_count)}</strong> 檔</span>`
      : "";
  const chronicExcludedHtml =
    data.chronic_excluded !== null && data.chronic_excluded !== undefined
      ? `<span>慢性套牢排除 <strong>${escapeHtml(data.chronic_excluded)}</strong> 檔</span>`
      : "";

  const statsHtml = `
    <div class="alert-stats">
      <span>掃描 <strong>${escapeHtml(data.count)}</strong> 檔</span>
      <span>排除 <strong>${escapeHtml(data.excluded)}</strong> 檔</span>
      <span>價格日 <strong>${escapeHtml(data.price_as_of)}</strong></span>
      <span>融資日（上市）<strong>${escapeHtml(data.margin_as_of_tse)}</strong></span>
      <span>融資日（上櫃）<strong>${escapeHtml(data.margin_as_of_otc)}</strong></span>
      <span>符合篩選 <strong>${filtered.length}</strong> 檔</span>
      ${freshCountHtml}
      ${chronicExcludedHtml}
    </div>
  `;

  if (filtered.length === 0) {
    resultEl.innerHTML = `
      ${statsHtml}
      <div class="alert-empty">無符合條件標的</div>
    `;
    return;
  }

  const rowsHtml = filtered
    .map((item) => {
      const bandClass = alertBandClass(item.band);
      const bandLabel = alertBandLabel(item.band);
      const ratioText =
        typeof item.ratio === "number"
          ? item.ratio.toLocaleString("zh-TW", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
          : "—";
      const priceText =
        typeof item.price === "number"
          ? item.price.toLocaleString("zh-TW", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
          : "—";
      const costVal = typeof item.cost === "number" ? item.cost : item.n_day_avg;
      let avgText =
        typeof costVal === "number"
          ? costVal.toLocaleString("zh-TW", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
          : "—";
      if (item.cost_source === "N日均價") {
        avgText += `<span class="adj-tag" title="此檔無券商級成本種子，退回 N 日均價簡易估計">N日均價</span>`;
      } else if (item.adjusted) {
        avgText += `<span class="adj-tag" title="近期有除權息/分割，均價僅取事件後資料還原計算">＊還原</span>`;
      }
      const marginText =
        typeof item.margin_lots === "number" ? item.margin_lots.toLocaleString("zh-TW") : "—";
      let nameText = item.name ? escapeHtml(item.name) : escapeHtml(item.code);
      if (item.fresh_washout) {
        nameText += ` <span class="fresh-badge">🆕急殺</span>`;
      }
      const rowClass = bandClass + (item.fresh_washout ? " row-fresh" : "");
      const maCell = maPosHtml(item);

      return `
        <tr class="${rowClass}">
          <td>${escapeHtml(item.code)}</td>
          <td>${nameText}</td>
          <td>${escapeHtml(marketLabel(item.market))}</td>
          <td>${priceText}</td>
          <td>${avgText}</td>
          <td>${marginText} 張</td>
          <td class="ratio-cell">${ratioText}%</td>
          <td><span class="band-pill ${bandClass}">${bandLabel}</span></td>
          <td class="ma-cell">${maCell}</td>
        </tr>
      `;
    })
    .join("");

  resultEl.innerHTML = `
    ${statsHtml}
    <div class="alert-table-wrap">
      <table class="alert-table">
        <thead>
          <tr>
            <th>代號</th>
            <th>名稱</th>
            <th>市場</th>
            <th>現價</th>
            <th>融資成本</th>
            <th>融資餘額</th>
            <th>維持率</th>
            <th>警戒等級</th>
            <th>月線/季線</th>
          </tr>
        </thead>
        <tbody>
          ${rowsHtml}
        </tbody>
      </table>
    </div>
  `;
}

/* ==========================================================================
   大盤融資維持率指標橫幅（F-012）
   ========================================================================== */

/**
 * 依大盤位階回傳對應 CSS class（沿用既有 w-danger/w-warn1/w-safe/w-na 色系）
 * @param {"extreme_washout"|"washing"|"overheated"|"normal"|string|null|undefined} level
 * @returns {string}
 */
function marketLevelClass(level) {
  switch (level) {
    case "extreme_washout":
      return "w-safe";
    case "washing":
      return "w-warn1";
    case "overheated":
      return "w-danger";
    case "normal":
    default:
      return "w-na";
  }
}

/**
 * 繪製大盤走勢迷你 SVG sparkline（手繪折線，無圖表庫）
 * @param {Array<{date:string, ratio:number}>} series
 * @param {number|null|undefined} ma60 若提供，畫一條 MA60 虛線參考線
 * @param {string} levelClass 沿用 w-* class 供 currentColor 上色
 * @returns {string} HTML（含外層 wrap 與 svg）
 */
function buildMarketSparkline(series, ma60, levelClass) {
  const values = Array.isArray(series)
    ? series.map((p) => p && p.ratio).filter((v) => typeof v === "number" && !Number.isNaN(v))
    : [];

  if (values.length === 0) {
    return "";
  }

  let min = Math.min.apply(null, values);
  let max = Math.max.apply(null, values);
  if (typeof ma60 === "number" && !Number.isNaN(ma60)) {
    min = Math.min(min, ma60);
    max = Math.max(max, ma60);
  }
  if (min === max) {
    min -= 1;
    max += 1;
  }

  const w = 600;
  const h = 48;
  const pad = 3;
  const n = values.length;
  const scaleY = (v) => h - pad - ((v - min) / (max - min)) * (h - pad * 2);

  const points = values
    .map((v, i) => {
      const x = n === 1 ? 0 : (i / (n - 1)) * w;
      return x.toFixed(1) + "," + scaleY(v).toFixed(1);
    })
    .join(" ");

  let ma60Line = "";
  if (typeof ma60 === "number" && !Number.isNaN(ma60)) {
    const y = scaleY(ma60).toFixed(1);
    ma60Line = `<line x1="0" y1="${y}" x2="${w}" y2="${y}" stroke="currentColor" stroke-opacity="0.4" stroke-width="1" stroke-dasharray="5 4"></line>`;
  }

  return `
    <div class="market-spark-wrap ${levelClass}">
      <svg class="market-spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" width="100%" height="48" role="img" aria-label="大盤融資維持率近期走勢">
        ${ma60Line}
        <polyline points="${points}" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"></polyline>
      </svg>
    </div>
  `;
}

/**
 * 繪製大盤融資維持率指標橫幅（F-012）
 * @param {Object} data MarketResponse（見 GET /api/market 契約），亦可能是降級用的 {status:"error"|"no_data"} 物件
 */
function renderMarket(data) {
  const bodyEl = document.getElementById("market-banner-body");
  if (!bodyEl) return;

  if (!data || data.status !== "ok" || data.current === null || data.current === undefined) {
    bodyEl.innerHTML = `<div class="market-banner-degraded">大盤指標暫時無法載入</div>`;
    return;
  }

  const levelClass = marketLevelClass(data.level);
  const levelLabel = data.level_zh || "—";

  const currentText = Number(data.current).toLocaleString("zh-TW", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  const subParts = [];
  if (data.as_of) subParts.push(escapeHtml(data.as_of));
  if (data.constituents !== null && data.constituents !== undefined) {
    subParts.push(escapeHtml(data.constituents) + " 檔成分股");
  }
  const subText = subParts.join(" ・ ");

  let velocityText = "—";
  if (typeof data.velocity_5d === "number" && !Number.isNaN(data.velocity_5d)) {
    const sign = data.velocity_5d > 0 ? "+" : "";
    velocityText =
      "5日 " + sign + data.velocity_5d.toLocaleString("zh-TW", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  const ma20Text =
    typeof data.ma20 === "number"
      ? data.ma20.toLocaleString("zh-TW", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
      : "—";
  const ma60Text =
    typeof data.ma60 === "number"
      ? data.ma60.toLocaleString("zh-TW", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
      : "—";

  let percentileText = "—";
  if (typeof data.percentile === "number" && !Number.isNaN(data.percentile)) {
    const pct = (data.percentile * 100).toLocaleString("zh-TW", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    percentileText = "近120日 第" + pct + "%低位";
  }

  const sparklineHtml = buildMarketSparkline(data.series, data.ma60, levelClass);

  bodyEl.innerHTML = `
    <div class="market-banner-flex">
      <div class="market-banner-left">
        <div class="market-banner-value">${currentText}<span class="unit">%</span></div>
        <div class="market-banner-sub">${subText}</div>
      </div>
      <div class="market-banner-mid">
        <span class="band-pill market-level-pill ${levelClass}">${escapeHtml(levelLabel)}</span>
        <div class="market-banner-velocity">${escapeHtml(velocityText)}</div>
      </div>
      <div class="market-banner-right">
        <div class="market-banner-mini">MA20 ${ma20Text}</div>
        <div class="market-banner-mini">MA60 ${ma60Text}</div>
        <div class="market-banner-percentile">${escapeHtml(percentileText)}</div>
      </div>
    </div>
    ${sparklineHtml}
  `;
}

// 掛在 window 供 app.js 使用（純原生 JS，無 module/import）
window.warningClass = warningClass;
window.renderResult = renderResult;
window.renderError = renderError;
window.showLoading = showLoading;
window.clearError = clearError;
window.alertBandClass = alertBandClass;
window.renderAlerts = renderAlerts;
window.showAlertLoading = showAlertLoading;
window.renderAlertError = renderAlertError;
window.clearAlertError = clearAlertError;
window.marketLevelClass = marketLevelClass;
window.buildMarketSparkline = buildMarketSparkline;
window.renderMarket = renderMarket;
