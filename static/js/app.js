/* ==========================================================================
   台股融資維持率查詢 — app.js (FN-032)
   綁定表單事件、前端驗證、串接 api.js / render.js
   ========================================================================== */

(function () {
  var isSubmitting = false;

  /** 驗證股票代號：需為 4 碼數字 */
  function isValidCode(code) {
    return /^[0-9]{4}$/.test(code);
  }

  /** 驗證 N 值：需介於 1~250 的整數 */
  function isValidN(n) {
    var num = Number(n);
    return Number.isInteger(num) && num >= 1 && num <= 250;
  }

  async function handleSubmit(event) {
    event.preventDefault();

    if (isSubmitting) {
      // 防重複送出
      return;
    }

    var codeInput = document.getElementById("code-input");
    var nInput = document.getElementById("n-input");

    var code = codeInput ? codeInput.value.trim() : "";
    var n = nInput ? nInput.value.trim() : "20";

    if (!isValidCode(code)) {
      renderError("股票代號需為 4 碼數字，請重新輸入（例如 2330）。");
      return;
    }

    if (!isValidN(n)) {
      renderError("均價天數需為 1 ~ 250 之間的整數。");
      return;
    }

    var submitBtn = document.getElementById("submit-btn");

    isSubmitting = true;
    showLoading(true);
    if (submitBtn) submitBtn.disabled = true;

    try {
      var data = await apiGetMaintenance(code, n);
      renderResult(data);
    } catch (err) {
      var message =
        (err && err.message) ||
        "查詢失敗，請確認股票代號是否正確，或稍後再試。";
      renderError(message);
    } finally {
      showLoading(false);
      if (submitBtn) submitBtn.disabled = false;
      isSubmitting = false;
    }
  }

  function handleNChange() {
    var nInput = document.getElementById("n-input");
    if (!nInput) return;

    var value = Number(nInput.value);
    if (Number.isNaN(value)) return;

    if (value < 1) {
      nInput.value = "1";
    } else if (value > 250) {
      nInput.value = "250";
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var form = document.getElementById("query-form");
    var nInput = document.getElementById("n-input");

    if (form) {
      form.addEventListener("submit", handleSubmit);
    }
    if (nInput) {
      nInput.addEventListener("change", handleNChange);
    }
  });

  /* ------------------------------------------------------------------
     大盤融資維持率指標橫幅（F-012）
     頁面載入即呼叫，失敗靜默降級，不阻塞其他功能
     ------------------------------------------------------------------ */
  document.addEventListener("DOMContentLoaded", function () {
    try {
      apiGetMarket()
        .then(function (data) {
          renderMarket(data);
        })
        .catch(function () {
          renderMarket(null);
        });
    } catch (e) {
      // 靜默失敗，不影響單股查詢 / 警示清單功能
    }
  });

  /* ------------------------------------------------------------------
     融資維持率警示清單（F-010）
     ------------------------------------------------------------------ */

  var isAlertScanning = false;
  var lastAlertsData = null; // 暫存上次掃描結果，供 filter change 就地重篩用

  /** 讀取目前篩選門檻：回傳數字（130/150/200）或 "all" */
  function getAlertFilterValue() {
    var filterEl = document.getElementById("alert-filter");
    if (!filterEl) return 200;
    var value = filterEl.value;
    if (value === "all") return "all";
    var num = Number(value);
    return Number.isNaN(num) ? 200 : num;
  }

  /** 驗證警示清單均價天數：需為 1~250 的整數 */
  function isValidAlertN(n) {
    var num = Number(n);
    return Number.isInteger(num) && num >= 1 && num <= 250;
  }

  async function handleAlertScan() {
    if (isAlertScanning) {
      // 防重複掃描
      return;
    }

    var nInput = document.getElementById("alert-n");
    var scanBtn = document.getElementById("alert-scan-btn");
    var n = nInput ? nInput.value.trim() : "20";

    if (!isValidAlertN(n)) {
      renderAlertError("均價天數需為 1 ~ 250 之間的整數。");
      return;
    }

    isAlertScanning = true;
    showAlertLoading(true);
    if (scanBtn) scanBtn.disabled = true;

    try {
      var data = await apiGetAlerts(n);
      lastAlertsData = data;
      renderAlerts(data, getAlertFilterValue());
    } catch (err) {
      lastAlertsData = null;
      var message =
        (err && err.message) || "掃描失敗，請稍後再試。";
      renderAlertError(message);
    } finally {
      showAlertLoading(false);
      if (scanBtn) scanBtn.disabled = false;
      isAlertScanning = false;
    }
  }

  /** 篩選門檻變更時：若已有資料則就地重篩，不重打 API */
  function handleAlertFilterChange() {
    if (!lastAlertsData) return;
    renderAlerts(lastAlertsData, getAlertFilterValue());
  }

  document.addEventListener("DOMContentLoaded", function () {
    var scanBtn = document.getElementById("alert-scan-btn");
    var filterEl = document.getElementById("alert-filter");

    if (scanBtn) {
      scanBtn.addEventListener("click", handleAlertScan);
    }
    if (filterEl) {
      filterEl.addEventListener("change", handleAlertFilterChange);
    }
  });
})();
