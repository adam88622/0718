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

  const statsHtml = `
    <div class="alert-stats">
      <span>掃描 <strong>${escapeHtml(data.count)}</strong> 檔</span>
      <span>排除 <strong>${escapeHtml(data.excluded)}</strong> 檔</span>
      <span>價格日 <strong>${escapeHtml(data.price_as_of)}</strong></span>
      <span>融資日（上市）<strong>${escapeHtml(data.margin_as_of_tse)}</strong></span>
      <span>融資日（上櫃）<strong>${escapeHtml(data.margin_as_of_otc)}</strong></span>
      <span>符合篩選 <strong>${filtered.length}</strong> 檔</span>
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
      const nameText = item.name ? escapeHtml(item.name) : escapeHtml(item.code);

      return `
        <tr class="${bandClass}">
          <td>${escapeHtml(item.code)}</td>
          <td>${nameText}</td>
          <td>${escapeHtml(marketLabel(item.market))}</td>
          <td>${priceText}</td>
          <td>${avgText}</td>
          <td>${marginText} 張</td>
          <td class="ratio-cell">${ratioText}%</td>
          <td><span class="band-pill ${bandClass}">${bandLabel}</span></td>
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
          </tr>
        </thead>
        <tbody>
          ${rowsHtml}
        </tbody>
      </table>
    </div>
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
