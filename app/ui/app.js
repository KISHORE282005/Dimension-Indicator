/* AI Engineering Drawing Analysis - interface logic */
(function () {
  "use strict";

  var API = "/api/part-report";

  var state = {
    documentId: null,
    fileName: null,
    pageCount: 0,
    jobId: null,
    result: null,
    polling: null,
    findingFilter: "all",
    busy: false
  };

  /* Placeholders are format hints only - the report never restricts a field
     to a fixed vocabulary. Whatever the drawing states is what gets reported. */
  var FIELDS = [
    { key: "s_no",        placeholder: "1" },
    { key: "part_no",     placeholder: "part number" },
    { key: "description", placeholder: "part name" },
    { key: "dwg_no",      placeholder: "drawing number" },
    { key: "weight_kg",   placeholder: "kg" },
    { key: "thickness",   placeholder: "mm or NA" },
    { key: "process",     placeholder: "how it is made" },
    { key: "length",      placeholder: "mm" },
    { key: "width",       placeholder: "mm" },
    { key: "height",      placeholder: "mm" }
  ];

  function $(id) { return document.getElementById(id); }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }

  function banner(container, kind, title, message) {
    var box = el("div", "banner " + kind);
    if (title) box.appendChild(el("strong", null, title));
    box.appendChild(document.createTextNode(message));
    container.appendChild(box);
    return box;
  }

  function formatBytes(bytes) {
    if (!bytes) return "0 B";
    var units = ["B", "KB", "MB", "GB"];
    var i = Math.floor(Math.log(bytes) / Math.log(1024));
    return (bytes / Math.pow(1024, i)).toFixed(i ? 1 : 0) + " " + units[i];
  }

  /* ------------------------------------------------------------------
   * HTTP
   * ---------------------------------------------------------------- */

  function request(url, options) {
    return fetch(url, options).then(function (response) {
      var isJson = (response.headers.get("content-type") || "").indexOf("json") !== -1;
      return (isJson ? response.json() : response.text()).then(function (body) {
        if (!response.ok) {
          var detail = body && body.detail ? body.detail : body;
          throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
        }
        return body;
      });
    });
  }

  /* ------------------------------------------------------------------
   * 1. Upload
   * ---------------------------------------------------------------- */

  function initUpload() {
    var zone = $("dropzone");
    var input = $("fileInput");

    zone.addEventListener("click", function () { input.click(); });
    zone.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); }
    });

    ["dragenter", "dragover"].forEach(function (name) {
      zone.addEventListener(name, function (e) {
        e.preventDefault(); zone.classList.add("dragover");
      });
    });
    ["dragleave", "drop"].forEach(function (name) {
      zone.addEventListener(name, function (e) {
        e.preventDefault(); zone.classList.remove("dragover");
      });
    });

    zone.addEventListener("drop", function (e) {
      if (e.dataTransfer.files && e.dataTransfer.files.length) {
        upload(e.dataTransfer.files[0]);
      }
    });

    input.addEventListener("change", function () {
      if (input.files && input.files.length) upload(input.files[0]);
      input.value = "";
    });

    $("clearFile").addEventListener("click", function () {
      state.documentId = null;
      state.fileName = null;
      state.pageCount = 0;
      $("fileInfo").classList.add("hidden");
      $("dropzone").classList.remove("hidden");
      refreshAnalyzeButton();
    });
  }

  function upload(file) {
    var zone = $("dropzone");
    zone.querySelector(".primary").textContent = "Uploading " + file.name + "…";

    var form = new FormData();
    form.append("file", file);

    request(API + "/upload", { method: "POST", body: form })
      .then(function (data) {
        state.documentId = data.document_id;
        state.fileName = data.filename;
        state.pageCount = data.page_count;

        $("fileName").textContent = data.filename;
        $("fileMeta").textContent = formatBytes(data.size_bytes) +
          (data.page_count ? " · " + data.page_count + " page" +
            (data.page_count === 1 ? "" : "s") + " — all will be analysed"
            : " · page count unavailable");

        $("fileInfo").classList.remove("hidden");
        zone.classList.add("hidden");
        refreshAnalyzeButton();
      })
      .catch(function (error) {
        clear($("analyzeError"));
        banner($("analyzeError"), "err", "Upload failed", error.message);
      })
      .then(function () {
        zone.querySelector(".primary").textContent =
          "Drop your drawing here, or click to browse";
      });
  }

  /* ------------------------------------------------------------------
   * 2. Input grid
   * ---------------------------------------------------------------- */

  function addRow(values) {
    var tbody = $("partRows");
    var tr = el("tr");

    tr.appendChild(el("td", "rownum"));

    FIELDS.forEach(function (field) {
      var td = el("td");
      var input = el("input");
      input.type = "text";
      input.dataset.field = field.key;
      input.placeholder = field.placeholder;
      input.value = (values && values[field.key]) || "";
      input.addEventListener("input", refreshAnalyzeButton);
      td.appendChild(input);
      tr.appendChild(td);
    });

    var actions = el("td", "actions");
    var remove = el("button", "btn-icon", "×");
    remove.type = "button";
    remove.title = "Remove this part";
    remove.addEventListener("click", function () {
      tr.remove();
      if (!tbody.children.length) addRow();
      renumber();
      refreshAnalyzeButton();
    });
    actions.appendChild(remove);
    tr.appendChild(actions);

    tbody.appendChild(tr);
    renumber();
    return tr;
  }

  function renumber() {
    var rows = $("partRows").children;
    for (var i = 0; i < rows.length; i++) {
      rows[i].querySelector("td.rownum").textContent = String(i + 1);
    }
    $("rowCount").textContent = rows.length + " part row" + (rows.length === 1 ? "" : "s");
  }

  function collectParts() {
    var parts = [];
    var rows = $("partRows").children;
    for (var i = 0; i < rows.length; i++) {
      var part = {};
      var filled = false;
      rows[i].querySelectorAll("input[data-field]").forEach(function (input) {
        var value = input.value.trim();
        part[input.dataset.field] = value;
        if (value) filled = true;
      });
      if (filled) parts.push(part);
    }
    return parts;
  }

  function refreshAnalyzeButton() {
    var parts = collectParts();
    var withPartNo = parts.filter(function (p) { return p.part_no; });
    var button = $("analyzeBtn");
    var hint = $("analyzeHint");

    if (state.busy) {
      button.disabled = true;
      return;
    }

    var problems = [];
    if (!state.documentId) problems.push("upload a drawing");

    if (parts.length && withPartNo.length < parts.length) {
      problems.push("every row you fill in needs a PART NO");
    }

    var duplicates = findDuplicatePartNumbers(withPartNo);
    if (duplicates.length) {
      problems.push("PART NO " + duplicates.join(", ") + " is repeated");
    }

    button.disabled = problems.length > 0;

    var pages = (state.pageCount || "all") + " page" +
      (state.pageCount === 1 ? "" : "s");

    if (problems.length) {
      hint.textContent = "To continue: " + problems.join("; ") + ".";
    } else if (!withPartNo.length) {
      hint.textContent = "Grid is empty — the parts list will be read from the " +
        "drawing itself across " + pages + ". Fill rows in only if you want to " +
        "override what the drawing says.";
    } else {
      hint.textContent = "Ready — " + withPartNo.length + " part" +
        (withPartNo.length === 1 ? "" : "s") + " against " + pages + ".";
    }
  }

  function findDuplicatePartNumbers(parts) {
    var seen = {}, duplicates = [];
    parts.forEach(function (p) {
      var key = p.part_no.replace(/[^a-z0-9]/gi, "").toUpperCase();
      if (!key) return;
      if (seen[key]) {
        if (duplicates.indexOf(p.part_no) === -1) duplicates.push(p.part_no);
      }
      seen[key] = true;
    });
    return duplicates;
  }

  /* ------------------------------------------------------------------
   * 3 & 4. Analyze + progress
   * ---------------------------------------------------------------- */

  function initAnalyze() {
    $("analyzeBtn").addEventListener("click", startAnalysis);
    $("addRow").addEventListener("click", function () { addRow(); refreshAnalyzeButton(); });
  }

  function startAnalysis() {
    clear($("analyzeError"));
    $("results").classList.add("hidden");
    state.busy = true;
    state.result = null;

    var button = $("analyzeBtn");
    button.disabled = true;
    clear(button);
    button.appendChild(el("span", "spinner"));
    button.appendChild(document.createTextNode("Analyzing…"));

    $("progressCard").classList.remove("hidden");
    setProgress("starting", 0, "Queued");

    request(API + "/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        document_id: state.documentId,
        parts: collectParts(),
        use_vlm: $("useVlm").checked,
        use_ocr: $("useOcr").checked
      })
    })
      .then(function (data) {
        state.jobId = data.job_id;
        poll();
      })
      .catch(function (error) {
        finishAnalysis();
        banner($("analyzeError"), "err", "Could not start the analysis", error.message);
        $("progressCard").classList.add("hidden");
      });
  }

  function poll() {
    if (state.polling) clearInterval(state.polling);
    state.polling = setInterval(function () {
      request(API + "/progress/" + state.jobId)
        .then(function (data) {
          setProgress(data.stage, data.progress, data.detail);
          if (data.status === "complete") {
            clearInterval(state.polling);
            loadResult();
            autoDownloadExcel();
          } else if (data.status === "error") {
            clearInterval(state.polling);
            finishAnalysis();
            banner($("analyzeError"), "err", "Analysis failed",
              data.error || data.detail || "Unknown error.");
          }
        })
        .catch(function (error) {
          clearInterval(state.polling);
          finishAnalysis();
          banner($("analyzeError"), "err", "Lost contact with the server", error.message);
        });
    }, 1200);
  }

  function setProgress(stage, fraction, detail) {
    var pct = Math.round((fraction || 0) * 100);
    $("progressFill").style.width = pct + "%";
    $("progressPct").textContent = pct + "%";
    $("progressStage").textContent = (stage || "working").replace(/_/g, " ");
    $("progressDetail").textContent = detail || "";
  }

  function autoDownloadExcel() {
    if (!state.jobId) return;
    fetch(API + "/excel/" + state.jobId)
      .then(function (response) {
        if (!response.ok) throw new Error("Excel generation failed.");
        return response.blob();
      })
      .then(function (blob) {
        var name = (state.fileName || "drawing").replace(/\.[^.]+$/, "");
        var url = URL.createObjectURL(blob);
        var link = document.createElement("a");
        link.href = url;
        link.download = name + "_analysis_report.xlsx";
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
        banner($("resultBanners"), "ok", "Report ready",
          "Excel report downloaded automatically. Use the button below to download again.");
      })
      .catch(function () {
        banner($("resultBanners"), "warn", "Auto-download failed",
          "The report was generated but could not be downloaded automatically. Use the button below.");
      });
  }

  function finishAnalysis() {
    state.busy = false;
    var button = $("analyzeBtn");
    clear(button);
    button.appendChild(document.createTextNode("Analyze Drawing"));
    refreshAnalyzeButton();
  }

  function loadResult() {
    request(API + "/result/" + state.jobId)
      .then(function (data) {
        state.result = data;
        finishAnalysis();
        renderResult(data);
        $("results").classList.remove("hidden");
        $("results").scrollIntoView({ behavior: "smooth", block: "start" });
      })
      .catch(function (error) {
        finishAnalysis();
        banner($("analyzeError"), "err", "Could not load the result", error.message);
      });
  }

  /* ------------------------------------------------------------------
   * 5. Extracted drawing information
   * ---------------------------------------------------------------- */

  function renderResult(data) {
    renderResultBanners(data);
    renderStats(data);
    renderFindings(data);
    renderReport(data);
  }

  function renderResultBanners(data) {
    var box = $("resultBanners");
    clear(box);

    (data.errors || []).forEach(function (message) {
      banner(box, "err", null, message);
    });
    (data.warnings || []).forEach(function (message) {
      banner(box, "warn", null, message);
    });

    if (data.discovery_mode && data.table.rows.length) {
      banner(box, "info", "Parts read from the drawing",
        data.table.rows.length + " part(s) were taken from the drawing's " +
        "parts-list table because the input grid was empty. Every value below " +
        "came from the drawing — check them before relying on the report.");
    }

    if (!data.errors.length && !data.warnings.length) {
      banner(box, "ok", null,
        "All " + data.pages_analyzed + " page(s) analysed with no warnings.");
    }
  }

  function renderStats(data) {
    var box = $("runStats");
    clear(box);

    var stats = [
      { num: data.pages_analyzed + " / " + data.total_pages, lbl: "Pages analysed", kind: "" },
      { num: data.table.rows.length, lbl: "Part rows", kind: "" },
      { num: (data.findings || []).length + (data.unmatched_findings || []).length,
        lbl: "Items read", kind: "" },
      { num: data.stats.filled_from_drawing, lbl: "Filled from drawing", kind: "ok" },
      { num: data.stats.conflicts, lbl: "Conflicts", kind: data.stats.conflicts ? "warn" : "" },
      { num: data.stats.not_detected, lbl: "Not detected", kind: data.stats.not_detected ? "err" : "" },
      { num: data.processing_time_seconds + "s", lbl: "Processing time", kind: "" }
    ];

    stats.forEach(function (stat) {
      var card = el("div", "stat " + stat.kind);
      card.appendChild(el("div", "num", stat.num));
      card.appendChild(el("div", "lbl", stat.lbl));
      box.appendChild(card);
    });
  }

  function allFindings(data) {
    var combined = (data.findings || []).slice();
    (data.unmatched_findings || []).forEach(function (f) {
      var copy = {};
      for (var k in f) copy[k] = f[k];
      copy.attributed_to = null;
      combined.push(copy);
    });
    combined.sort(function (a, b) {
      return a.page_number - b.page_number ||
        String(a.category).localeCompare(String(b.category));
    });
    return combined;
  }

  function renderFindings(data) {
    var findings = allFindings(data);
    $("findingsSummary").textContent =
      findings.length + " item" + (findings.length === 1 ? "" : "s") +
      " read across " + data.pages_analyzed + " page" +
      (data.pages_analyzed === 1 ? "" : "s");

    var counts = { all: findings.length };
    findings.forEach(function (f) {
      counts[f.category] = (counts[f.category] || 0) + 1;
    });

    var filters = $("findingFilters");
    clear(filters);

    Object.keys(counts).sort(function (a, b) {
      if (a === "all") return -1;
      if (b === "all") return 1;
      return counts[b] - counts[a];
    }).forEach(function (category) {
      var chip = el("button", "filter" + (state.findingFilter === category ? " active" : ""));
      chip.type = "button";
      chip.appendChild(document.createTextNode(
        category === "all" ? "All" : category.replace(/_/g, " ")));
      chip.appendChild(el("span", "n", counts[category]));
      chip.addEventListener("click", function () {
        state.findingFilter = category;
        renderFindings(data);
      });
      filters.appendChild(chip);
    });

    var body = $("findingsBody");
    clear(body);

    var visible = findings.filter(function (f) {
      return state.findingFilter === "all" || f.category === state.findingFilter;
    });

    if (!visible.length) {
      var row = el("tr");
      var cell = el("td", "empty", findings.length
        ? "No items in this category."
        : "Nothing was read from the drawing. Check that the vision model is " +
          "configured and that the PDF contains a readable drawing.");
      cell.colSpan = 7;
      row.appendChild(cell);
      body.appendChild(row);
      return;
    }

    visible.forEach(function (f) {
      var tr = el("tr");

      var pageCell = el("td");
      pageCell.appendChild(el("span", "tag page", "p." + f.page_number));
      tr.appendChild(pageCell);

      tr.appendChild(el("td", null, String(f.category).replace(/_/g, " ")));
      tr.appendChild(el("td", null, f.attributed_to || f.part_no || "—"));

      var valueCell = el("td", "val", f.value);
      tr.appendChild(valueCell);

      tr.appendChild(el("td", null, f.detail || ""));

      var confCell = el("td");
      var pct = Math.round((f.confidence || 0) * 100);
      confCell.appendChild(el("span", "tag" + (pct < 50 ? " low" : ""), pct + "%"));
      tr.appendChild(confCell);

      tr.appendChild(el("td", null, f.source || ""));
      body.appendChild(tr);
    });
  }

  /* ------------------------------------------------------------------
   * 6. Report preview
   * ---------------------------------------------------------------- */

  var NUMERIC = {
    "WEIGHT (IN KG)": 1, "THICKNESS": 1,
    "LENGTH (mm)": 1, "WIDTH (mm)": 1, "HEIGHT (mm)": 1
  };
  var CENTERED = { "S No": 1, "PART NO": 1, "DWG NO": 1 };

  var STATUS_CLASS = {
    conflict: "st-conflict",
    missing: "st-missing",
    filled: "st-filled",
    confirmed: "st-confirmed"
  };

  var STATUS_MARK = {
    conflict: "⚠",
    filled: "✓",
    confirmed: "✓"
  };

  function renderReport(data) {
    var columns = data.table.columns;

    var head = $("reportHead");
    clear(head);
    columns.forEach(function (column) {
      head.appendChild(el("th", null, column));
    });

    var body = $("reportBody");
    clear(body);

    if (!data.table.rows.length) {
      var tr = el("tr");
      var td = el("td", "empty", "No parts in the report.");
      td.colSpan = columns.length;
      tr.appendChild(td);
      body.appendChild(tr);
      return;
    }

    data.table.rows.forEach(function (row) {
      var tr = el("tr");
      columns.forEach(function (column, index) {
        var cell = row.cells[column] || {};
        var td = el("td", null, row.values[index]);

        if (NUMERIC[column]) td.className = "num";
        else if (CENTERED[column]) td.className = "mid";

        var statusClass = STATUS_CLASS[cell.status];
        if (statusClass) td.className = (td.className + " " + statusClass).trim();

        var mark = STATUS_MARK[cell.status];
        if (mark) {
          td.appendChild(el("span", "cellmark", mark));
        }

        if (cell.note) td.title = buildTooltip(cell);
        tr.appendChild(td);
      });
      body.appendChild(tr);
    });

    var warnBox = $("rowWarnings");
    clear(warnBox);
    Object.keys(data.row_warnings || {}).forEach(function (partNo) {
      (data.row_warnings[partNo] || []).forEach(function (message) {
        warnBox.appendChild(el("div", "row-warn", partNo + " — " + message));
      });
    });
  }

  function buildTooltip(cell) {
    var lines = [];
    if (cell.user_value) lines.push("You entered: " + cell.user_value);
    if (cell.drawing_value) lines.push("Drawing shows: " + cell.drawing_value);
    if (cell.page_references && cell.page_references.length) {
      lines.push("Page(s): " + cell.page_references.join(", "));
    }
    if (cell.confidence) {
      lines.push("Confidence: " + Math.round(cell.confidence * 100) + "%");
    }
    if (cell.note) lines.push("", cell.note);
    return lines.join("\n");
  }

  /* ------------------------------------------------------------------
   * 7. Download
   * ---------------------------------------------------------------- */

  function initDownload() {
    $("downloadBtn").addEventListener("click", function () {
      if (!state.jobId) return;
      clear($("downloadError"));

      var button = $("downloadBtn");
      button.disabled = true;
      var original = button.textContent;
      button.textContent = "Generating…";

      fetch(API + "/excel/" + state.jobId)
        .then(function (response) {
          if (!response.ok) {
            return response.json().then(function (body) {
              throw new Error(body.detail || "Excel generation failed.");
            });
          }
          return response.blob();
        })
        .then(function (blob) {
          var name = (state.fileName || "drawing").replace(/\.[^.]+$/, "");
          var url = URL.createObjectURL(blob);
          var link = document.createElement("a");
          link.href = url;
          link.download = name + "_analysis_report.xlsx";
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
          setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
        })
        .catch(function (error) {
          banner($("downloadError"), "err", "Download failed", error.message);
        })
        .then(function () {
          button.disabled = false;
          button.textContent = original;
        });
    });
  }

  /* ------------------------------------------------------------------
   * Boot
   * ---------------------------------------------------------------- */

  document.addEventListener("DOMContentLoaded", function () {
    initUpload();
    initAnalyze();
    initDownload();
    addRow();
    refreshAnalyzeButton();
  });
})();
