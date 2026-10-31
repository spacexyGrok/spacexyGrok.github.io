/* Deals and Finds: search and sort for Forumotion HTML pages */
(function () {
  "use strict";

  var CATALOG_URL = "https://spacexygrok.github.io/data/catalog.json";

  function qs(sel, root) {
    return (root || document).querySelector(sel);
  }
  function qsa(sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }

  function money(n) {
    if (n == null || isNaN(n)) return "";
    if (Math.abs(n - Math.round(n)) < 1e-9) return "$" + Math.round(n);
    return "$" + Number(n).toFixed(2);
  }

  function fetchCatalog() {
    return fetch(CATALOG_URL, { credentials: "omit", mode: "cors" }).then(function (r) {
      if (!r.ok) throw new Error("catalog " + r.status);
      return r.json();
    });
  }

  function initHome(catalog) {
    var listEl = qs("[data-df-topics]");
    var searchEl = qs("[data-df-search]");
    var sortEl = qs("[data-df-sort]");
    var resultsEl = qs("[data-df-search-results]");
    if (!listEl) return;

    var pages = (catalog.pages || []).slice();

    function renderTopics(list) {
      listEl.innerHTML = "";
      if (!list.length) {
        listEl.innerHTML = '<p class="df-empty">No topic lists match.</p>';
        return;
      }
      list.forEach(function (p) {
        var a = document.createElement("a");
        a.className = "df-card";
        a.href = p.forum_path || "#";
        a.setAttribute("data-title", p.title || "");
        a.setAttribute("data-items", String(p.item_count || 0));
        a.setAttribute("data-saving", String(p.biggest_saving_dollars || 0));
        a.setAttribute("data-date", p.date || "");
        var saveLine =
          p.biggest_saving_dollars != null
            ? "Biggest listed saving: " + money(p.biggest_saving_dollars)
            : "Savings vary by item";
        a.innerHTML =
          "<h3>" +
          escapeHtml(p.title) +
          "</h3>" +
          '<div class="df-meta">' +
          escapeHtml(p.category || "") +
          " · " +
          (p.item_count || 0) +
          " items · Updated " +
          escapeHtml(p.date || "") +
          "</div>" +
          '<div class="df-summary">' +
          escapeHtml((p.description || "").replace(/#ad/g, "").trim()) +
          "</div>" +
          '<div class="df-meta">' +
          escapeHtml(saveLine) +
          "</div>" +
          '<span class="df-cta">Open list</span>';
        listEl.appendChild(a);
      });
    }

    function sortPages(mode) {
      var list = pages.slice();
      if (mode === "items") {
        list.sort(function (a, b) {
          return (b.item_count || 0) - (a.item_count || 0);
        });
      } else if (mode === "saving") {
        list.sort(function (a, b) {
          return (b.biggest_saving_dollars || 0) - (a.biggest_saving_dollars || 0);
        });
      } else if (mode === "az") {
        list.sort(function (a, b) {
          return (a.title || "").localeCompare(b.title || "");
        });
      } else {
        list.sort(function (a, b) {
          return (b.date || "").localeCompare(a.date || "");
        });
      }
      return list;
    }

    function apply() {
      var mode = sortEl ? sortEl.value : "newest";
      var q = searchEl ? searchEl.value.trim().toLowerCase() : "";
      var list = sortPages(mode);
      if (q) {
        list = list.filter(function (p) {
          var hay =
            (p.title || "") +
            " " +
            (p.category || "") +
            " " +
            (p.description || "");
          return hay.toLowerCase().indexOf(q) !== -1;
        });
      }
      renderTopics(list);

      if (resultsEl) {
        if (!q) {
          resultsEl.className = "df-hidden";
          resultsEl.innerHTML = "";
          return;
        }
        var hits = (catalog.items || []).filter(function (it) {
          var hay =
            (it.name || "") +
            " " +
            (it.store || "") +
            " " +
            (it.category || "") +
            " " +
            (it.page_title || "");
          return hay.toLowerCase().indexOf(q) !== -1;
        }).slice(0, 12);
        resultsEl.className = "df-product-grid";
        resultsEl.innerHTML = hits
          .map(function (it) {
            var price = formatPrice(it);
            var href = (it.page_slug && pageForumPath(it.page_slug, catalog)) || it.link || "#";
            return (
              '<article class="df-product">' +
              (it.image
                ? '<img src="' +
                  escapeAttr(it.image) +
                  '" alt="' +
                  escapeAttr(it.image_alt || it.name) +
                  '" loading="lazy" />'
                : "") +
              "<h3>" +
              escapeHtml(it.name) +
              "</h3>" +
              '<div class="df-prices">' +
              price +
              "</div>" +
              '<div class="df-meta">' +
              escapeHtml(it.page_title || "") +
              "</div>" +
              '<a class="df-cta" href="' +
              escapeAttr(href) +
              '">View on list</a>' +
              "</article>"
            );
          })
          .join("");
        if (!hits.length) {
          resultsEl.innerHTML = '<p class="df-empty">No items match that search.</p>';
        }
      }
    }

    if (sortEl) sortEl.addEventListener("change", apply);
    if (searchEl) searchEl.addEventListener("input", apply);
    apply();
  }

  function pageForumPath(slug, catalog) {
    var pages = catalog.pages || [];
    for (var i = 0; i < pages.length; i++) {
      if (pages[i].slug === slug) return pages[i].forum_path;
    }
    return null;
  }

  function formatPrice(it) {
    if (it.is_range && it.now_price != null && it.now_price_high != null) {
      return (
        '<span class="df-now">From ' +
        money(it.now_price) +
        " to " +
        money(it.now_price_high) +
        "</span>"
      );
    }
    var html = "";
    if (it.now_price != null) {
      html += '<span class="df-now">Now ' + money(it.now_price) + "</span>";
    } else if (it.price_raw) {
      html += '<span class="df-now">' + escapeHtml(it.price_raw) + "</span>";
    }
    if (it.old_price != null) {
      html += '<span class="df-old">' + money(it.old_price) + "</span>";
    }
    if (it.savings_dollars != null) {
      html +=
        '<span class="df-save">Save ' +
        money(it.savings_dollars) +
        (it.savings_percent != null ? " (" + it.savings_percent + "%)" : "") +
        "</span>";
    }
    return html;
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
  function escapeAttr(s) {
    return escapeHtml(s).replace(/'/g, "&#39;");
  }

  function initListSort() {
    var grid = qs("[data-df-products]");
    var sortEl = qs("[data-df-list-sort]");
    if (!grid || !sortEl) return;
    sortEl.addEventListener("change", function () {
      var cards = qsa(".df-product", grid);
      var mode = sortEl.value;
      cards.sort(function (a, b) {
        if (mode === "saving") {
          return (
            parseFloat(b.getAttribute("data-saving") || "0") -
            parseFloat(a.getAttribute("data-saving") || "0")
          );
        }
        if (mode === "price") {
          return (
            parseFloat(a.getAttribute("data-price") || "0") -
            parseFloat(b.getAttribute("data-price") || "0")
          );
        }
        if (mode === "az") {
          return (a.getAttribute("data-name") || "").localeCompare(
            b.getAttribute("data-name") || ""
          );
        }
        return 0;
      });
      cards.forEach(function (c) {
        grid.appendChild(c);
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initListSort();
    if (!qs("[data-df-topics]")) return;
    fetchCatalog()
      .then(initHome)
      .catch(function (err) {
        var listEl = qs("[data-df-topics]");
        if (listEl) {
          listEl.innerHTML =
            '<p class="df-empty">Topic lists are embedded below. Live catalog search needs a network fetch of catalog.json.</p>';
        }
        console.warn("DF catalog fetch failed", err);
      });
  });

  window.DF = { fetchCatalog: fetchCatalog, formatPrice: formatPrice };
})();
