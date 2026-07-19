/* ==========================================================================
   台股融資維持率查詢 — api.js (FN-027)
   同源 fetch 封裝，無外部依賴
   ========================================================================== */

/**
 * 查詢單股融資維持率
 * @param {string|number} code 股票代號
 * @param {string|number} n 均價天數
 * @returns {Promise<Object>} MaintenanceResponse JSON
 * @throws {{error:string, message:string, code?:string}} non-2xx 時拋出 ErrorResponse（或等效物件）
 */
async function apiGetMaintenance(code, n) {
  const url = "/api/maintenance?code=" + encodeURIComponent(code) + "&n=" + encodeURIComponent(n);

  let response;
  try {
    response = await fetch(url, { method: "GET" });
  } catch (networkErr) {
    // fetch 本身失敗（斷線、CORS 等，理論上同源不會有 CORS 問題）
    throw {
      error: "network_error",
      message: "無法連線至伺服器，請確認網路狀態後再試一次。",
    };
  }

  let body;
  try {
    body = await response.json();
  } catch (parseErr) {
    body = null;
  }

  if (!response.ok) {
    if (body && typeof body === "object") {
      throw {
        error: body.error || "unknown_error",
        message: body.message || "查詢失敗，請稍後再試。",
        code: body.code,
      };
    }
    throw {
      error: "unknown_error",
      message: "查詢失敗（HTTP " + response.status + "），請稍後再試。",
    };
  }

  return body;
}

/**
 * 查詢產業融資維持率（選配，stub）
 * @param {string} market "tse" | "otc"
 * @param {string|number} n 均價天數
 * @returns {Promise<Object>} IndustryResponse JSON
 * @throws {{error:string, message:string, code?:string}}
 */
async function apiGetIndustry(market, n) {
  const url = "/api/industry?market=" + encodeURIComponent(market) + "&n=" + encodeURIComponent(n);

  let response;
  try {
    response = await fetch(url, { method: "GET" });
  } catch (networkErr) {
    throw {
      error: "network_error",
      message: "無法連線至伺服器，請確認網路狀態後再試一次。",
    };
  }

  let body;
  try {
    body = await response.json();
  } catch (parseErr) {
    body = null;
  }

  if (!response.ok) {
    if (body && typeof body === "object") {
      throw {
        error: body.error || "unknown_error",
        message: body.message || "查詢失敗，請稍後再試。",
        code: body.code,
      };
    }
    throw {
      error: "unknown_error",
      message: "查詢失敗（HTTP " + response.status + "），請稍後再試。",
    };
  }

  return body;
}

/**
 * 查詢全市場融資維持率警示清單（F-010）
 * @param {string|number} n 均價天數
 * @returns {Promise<Object>} AlertsResponse JSON（見 GET /api/alerts 契約）
 * @throws {{error:string, message:string, code?:string}} non-2xx 時拋出 ErrorResponse（或等效物件）
 */
async function apiGetAlerts(n) {
  const url = "/api/alerts?n=" + encodeURIComponent(n);

  let response;
  try {
    response = await fetch(url, { method: "GET" });
  } catch (networkErr) {
    throw {
      error: "network_error",
      message: "無法連線至伺服器，請確認網路狀態後再試一次。",
    };
  }

  let body;
  try {
    body = await response.json();
  } catch (parseErr) {
    body = null;
  }

  if (!response.ok) {
    if (body && typeof body === "object") {
      throw {
        error: body.error || "unknown_error",
        message: body.message || "掃描失敗，請稍後再試。",
        code: body.code,
      };
    }
    throw {
      error: "unknown_error",
      message: "掃描失敗（HTTP " + response.status + "），請稍後再試。",
    };
  }

  return body;
}

// 掛在 window 供 render.js / app.js 使用（純原生 JS，無 module/import）
window.apiGetMaintenance = apiGetMaintenance;
window.apiGetIndustry = apiGetIndustry;
window.apiGetAlerts = apiGetAlerts;
