(function () {
  var RESET_MS = 1500;

  var NAV_ICONS = {
    "Главная": "home",
    "Быстрый старт": "rocket",
    "Руководства": "book-open",
    "Примеры": "clipboard",
    "Блог": "pen-tool",
    "Справочник": "library",
    "Журнал изменений": "history",
    "Команды": "message-circle",
    "Аргументы": "target",
    "Cog-модули": "settings",
    "Package-модули": "package",
    "Клавиатуры и View": "grid",
    "FSM (диалоги)": "refresh",
    "FSM": "refresh",
    "Проверки и cooldown": "shield",
    "Префиксы": "hash",
    "Аддоны": "puzzle",
    "Эксперименты": "activity",
    "App и Bot": "bot",
    "API": "radio",
    "Контекст": "theater",
    "Модели": "user",
    "UI": "grid",
    "События": "zap",
    "Утилиты": "wrench"
  };

  var CL_TYPES = {
    "Добавлено": "added",
    "Изменено": "changed",
    "Устаревшее": "deprecated",
    "Удалено": "removed",
    "Исправлено": "fixed",
    "Безопасность": "security",
    "Производительность": "performance"
  };

  function headingText(el) {
    var clone = el.cloneNode(true);
    var link = clone.querySelector(".headerlink");
    if (link) link.remove();
    return clone.textContent.trim();
  }

  function showCopied(el, iconEl) {
    var originalIcon = iconEl ? iconEl.innerHTML : null;
    if (iconEl) {
      iconEl.innerHTML =
        '<polyline points="20 6 9 17 4 12" stroke="currentColor" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>';
    }
    var timer = setTimeout(reset, RESET_MS);
    el.addEventListener("mouseleave", function () {
      clearTimeout(timer);
      reset();
    }, { once: true });

    function reset() {
      el.classList.remove("vf-copied", "vf-pip-copied");
      if (iconEl && originalIcon) iconEl.innerHTML = originalIcon;
    }
  }

  document.addEventListener("click", function (e) {
    var btn = e.target.closest(".md-clipboard");
    if (!btn) return;
    btn.classList.add("vf-copied");
    showCopied(btn, btn.querySelector("svg"));
  });

  document.addEventListener("click", function (e) {
    var el = e.target.closest("#vf-pip-copy");
    if (!el) return;
    var text = el.getAttribute("data-copy");
    if (!text) return;
    navigator.clipboard.writeText(text).then(function () {
      el.classList.add("vf-pip-copied");
      showCopied(el, el.querySelector(".vf-hero__copy-icon"));
    });
  });

  function initNavIcons() {
    document.querySelectorAll("a.md-nav__link, label.md-nav__link").forEach(function (link) {
      if (link.hasAttribute("data-vf-icon")) return;
      var el = link.querySelector(".md-ellipsis");
      if (!el) return;
      var icon = NAV_ICONS[el.textContent.trim()];
      if (icon) link.setAttribute("data-vf-icon", icon);
    });

    document.querySelectorAll(".md-tabs__link").forEach(function (link) {
      if (link.hasAttribute("data-vf-icon")) return;
      var text = link.textContent.trim();
      var icon = NAV_ICONS[text];
      if (icon) link.setAttribute("data-vf-icon", icon);
    });
  }

  function initChangelog() {
    var content = document.querySelector(".md-content__inner");
    if (!content) return;
    var h1 = content.querySelector("h1");
    if (!h1 || headingText(h1) !== "Журнал изменений") return;

    content.classList.add("vf-cl");
    document.body.classList.add("vf-cl-page");

    content.querySelectorAll("h3").forEach(function (h3) {
      var type = CL_TYPES[headingText(h3)];
      if (type) h3.setAttribute("data-vf-cl", type);
    });

    var versions = [];
    var cur = null;
    content.querySelectorAll("h2, h3").forEach(function (el) {
      if (el.tagName === "H2") {
        cur = { title: headingText(el), id: el.id, cats: [] };
        versions.push(cur);
      } else if (el.tagName === "H3" && cur) {
        var t = headingText(el);
        var type = CL_TYPES[t];
        if (type) cur.cats.push({ title: t, id: el.id, type: type });
      }
    });

    if (!versions.length) return;

    var nav = document.querySelector(".md-sidebar--primary .md-nav--primary");
    if (nav) nav.classList.remove("md-nav--lifted");

    var sidebar = nav ? nav.querySelector(":scope > .md-nav__list") : null;
    if (!sidebar) return;

    sidebar.innerHTML = "";

    versions.forEach(function (ver, i) {
      var li = document.createElement("li");
      li.className = "md-nav__item";

      var details = document.createElement("details");
      if (i === 0) details.setAttribute("open", "");
      details.className = "vf-cl-nav-version";

      var summary = document.createElement("summary");
      summary.innerHTML = '<span class="md-ellipsis">' + ver.title.replace(/\s*\(.*\)/, "") + "</span>";
      details.appendChild(summary);

      if (ver.cats.length) {
        var ul = document.createElement("ul");
        ul.className = "md-nav__list";
        ver.cats.forEach(function (cat) {
          var catLi = document.createElement("li");
          catLi.className = "md-nav__item";
          var a = document.createElement("a");
          a.className = "md-nav__link vf-cl-cat-link";
          a.href = "#" + cat.id;
          a.setAttribute("data-vf-cl-type", cat.type);
          a.innerHTML = '<span class="vf-cl-dot"></span><span class="md-ellipsis">' + cat.title + "</span>";
          catLi.appendChild(a);
          ul.appendChild(catLi);
        });
        details.appendChild(ul);
      }

      li.appendChild(details);
      sidebar.appendChild(li);
    });
  }

  function initBlogSearch() {
    if (document.querySelector(".vf-blog-header")) return;
    var posts = document.querySelectorAll(".md-post--excerpt");
    if (!posts.length) return;
    var content = document.querySelector(".md-content__inner");
    if (!content) return;
    var h1 = content.querySelector("h1");
    if (!h1) return;

    content.closest(".md-content").classList.add("vf-blog-page");

    var header = document.createElement("div");
    header.className = "vf-blog-header";
    h1.parentNode.insertBefore(header, h1);
    header.appendChild(h1);

    var bar = document.createElement("div");
    bar.className = "vf-blog-search";

    var field = document.createElement("div");
    field.className = "vf-blog-search__field";

    var iconSvg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    iconSvg.setAttribute("class", "vf-blog-search__icon");
    iconSvg.setAttribute("viewBox", "0 0 24 24");
    iconSvg.setAttribute("fill", "none");
    iconSvg.setAttribute("stroke", "currentColor");
    iconSvg.setAttribute("stroke-width", "2");
    iconSvg.setAttribute("stroke-linecap", "round");
    iconSvg.setAttribute("stroke-linejoin", "round");
    iconSvg.innerHTML = '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>';

    var input = document.createElement("input");
    input.type = "text";
    input.className = "vf-blog-search__input";
    input.placeholder = "Поиск...";

    field.appendChild(iconSvg);
    field.appendChild(input);

    var clearBtn = document.createElement("button");
    clearBtn.className = "vf-blog-search__clear";
    clearBtn.textContent = "Сбросить";
    clearBtn.type = "button";

    var count = document.createElement("span");
    count.className = "vf-blog-search__count";

    bar.appendChild(field);
    bar.appendChild(clearBtn);
    bar.appendChild(count);
    header.appendChild(bar);

    var grid = document.createElement("div");
    grid.className = "vf-blog-grid";
    posts[0].parentNode.insertBefore(grid, posts[0]);
    posts.forEach(function (post) { grid.appendChild(post); });

    var postData = [];
    posts.forEach(function (post) {
      var titleEl = post.querySelector("h2");
      var contentEl = post.querySelector(".md-post__content");
      postData.push({
        el: post,
        title: titleEl ? titleEl.textContent.toLowerCase() : "",
        text: contentEl ? contentEl.textContent.toLowerCase() : ""
      });
    });

    function filter() {
      var q = input.value.trim().toLowerCase();
      if (!q) {
        postData.forEach(function (p) { p.el.classList.remove("vf-blog-hidden"); });
        clearBtn.classList.remove("vf-visible");
        count.textContent = "";
        return;
      }
      var visible = 0;
      var terms = q.split(/\s+/);
      postData.forEach(function (p) {
        var matches = terms.every(function (term) {
          return p.title.indexOf(term) !== -1 || p.text.indexOf(term) !== -1;
        });
        if (matches) {
          p.el.classList.remove("vf-blog-hidden");
          visible++;
        } else {
          p.el.classList.add("vf-blog-hidden");
        }
      });
      clearBtn.classList.add("vf-visible");
      count.textContent = visible + " из " + postData.length;
    }

    input.addEventListener("input", filter);
    clearBtn.addEventListener("click", function () {
      input.value = "";
      filter();
      input.focus();
    });
  }

  function initProgressAndBreadcrumbs() {
    var old = document.querySelector(".vf-progress");
    if (old) old.remove();
    var oldBc = document.querySelector(".vf-breadcrumbs");
    if (oldBc) oldBc.remove();

    var path = location.pathname;
    if (path.indexOf("/guides/") === -1) return;

    var bar = document.createElement("div");
    bar.className = "vf-progress";
    document.body.appendChild(bar);

    function updateProgress() {
      var docHeight = document.documentElement.scrollHeight - window.innerHeight;
      bar.style.width = docHeight <= 0 ? "100%" : (window.scrollY / docHeight * 100) + "%";
    }

    window.addEventListener("scroll", updateProgress, { passive: true });
    updateProgress();

    var content = document.querySelector(".md-content__inner");
    if (!content) return;
    var h1 = content.querySelector("h1");
    if (!h1) return;

    var bc = document.createElement("nav");
    bc.className = "vf-breadcrumbs";
    bc.setAttribute("aria-label", "Breadcrumbs");
    bc.innerHTML =
      '<a href="/">Главная</a>' +
      '<span class="vf-breadcrumbs__sep">\u203A</span>' +
      '<a href="' + path.replace(/\/[^/]+\/$/, "/") + '">Руководства</a>' +
      '<span class="vf-breadcrumbs__sep">\u203A</span>' +
      '<span class="vf-breadcrumbs__current">' + headingText(h1) + "</span>";

    h1.parentNode.insertBefore(bc, h1);
  }

  function runInit() {
    initNavIcons();
    initBlogSearch();
    initProgressAndBreadcrumbs();
    initChangelog();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", runInit);
  } else {
    runInit();
  }

  if (typeof document$ !== "undefined") {
    document$.subscribe(runInit);
  }

  if ("IntersectionObserver" in window) {
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add("vf-visible");
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.15 });

    document.addEventListener("DOMContentLoaded", function () {
      document.querySelectorAll(".vf-reveal").forEach(function (el) {
        observer.observe(el);
      });
    });
  }
})();
