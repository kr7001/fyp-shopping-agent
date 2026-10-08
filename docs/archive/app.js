/* Shared behaviour for the project's pages.
   Three jobs: show one section at a time so a page is not thirty thousand pixels
   tall, remember the theme, and let a code block be copied. Everything degrades:
   with scripting off every section stays visible and the page reads top to bottom. */

(function () {
  var root = document.documentElement;
  root.classList.add("js-on");

  /* ------------------------------------------------------------- theme */

  var themeBtn = document.getElementById("themebtn");
  function applyTheme(mode) {
    root.setAttribute("data-theme", mode);
    if (!themeBtn) return;
    themeBtn.setAttribute("aria-pressed", mode === "dark" ? "true" : "false");
    themeBtn.textContent = mode === "dark" ? "Light" : "Dark";
  }
  var storedTheme = null;
  try { storedTheme = localStorage.getItem("igr-theme"); } catch (e) {}
  applyTheme(storedTheme === "dark" ? "dark" : "light");
  if (themeBtn) {
    themeBtn.addEventListener("click", function () {
      var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      applyTheme(next);
      try { localStorage.setItem("igr-theme", next); } catch (e) {}
    });
  }

  /* --------------------------------------------- one section at a time */

  var sections = Array.prototype.slice.call(document.querySelectorAll("main > section"));
  var links = Array.prototype.slice.call(document.querySelectorAll(".navlist a[href^='#']"));
  if (!sections.length) return;

  function show(id, push) {
    var found = false;
    sections.forEach(function (s) {
      var on = s.id === id;
      s.classList.toggle("shown", on);
      if (on) found = true;
    });
    if (!found) {
      sections[0].classList.add("shown");
      id = sections[0].id;
    }
    links.forEach(function (a) {
      a.classList.toggle("on", a.getAttribute("href") === "#" + id);
    });
    if (push && window.history && window.history.replaceState) {
      window.history.replaceState(null, "", "#" + id);
    }
    return id;
  }

  /* A link may point at a heading inside a section rather than at the section
     itself, so resolve any hash to whichever section contains it. */
  function sectionFor(hash) {
    if (!hash) return null;
    var el = null;
    try { el = document.querySelector(hash); } catch (e) { return null; }
    if (!el) return null;
    var s = el.closest("main > section");
    return s ? s.id : null;
  }

  var showAllBtn = document.getElementById("showall");
  function setShowAll(on) {
    root.classList.toggle("show-all", on);
    if (showAllBtn) {
      showAllBtn.setAttribute("aria-pressed", on ? "true" : "false");
      showAllBtn.textContent = on ? "One at a time" : "Show all";
    }
    try { localStorage.setItem("igr-showall", on ? "1" : "0"); } catch (e) {}
  }
  var storedAll = null;
  try { storedAll = localStorage.getItem("igr-showall"); } catch (e) {}
  setShowAll(storedAll === "1");
  if (showAllBtn) {
    showAllBtn.addEventListener("click", function () {
      setShowAll(!root.classList.contains("show-all"));
    });
  }

  show(sectionFor(window.location.hash) || sections[0].id, false);

  links.forEach(function (a) {
    a.addEventListener("click", function (event) {
      var id = a.getAttribute("href").slice(1);
      if (!document.getElementById(id)) return;
      event.preventDefault();
      show(sectionFor("#" + id) || id, true);
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });

  /* Any in-page link, including ones inside the prose, should open the section
     it points into rather than appearing to do nothing. */
  document.addEventListener("click", function (event) {
    var a = event.target.closest("a[href^='#']");
    if (!a || a.closest(".navlist")) return;
    var id = sectionFor(a.getAttribute("href"));
    if (!id) return;
    event.preventDefault();
    show(id, true);
    var target = document.querySelector(a.getAttribute("href"));
    if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
  });

  window.addEventListener("hashchange", function () {
    var id = sectionFor(window.location.hash);
    if (id) show(id, false);
  });

  /* ---------------------------------------------------- copy a snippet */

  document.querySelectorAll("figure.code").forEach(function (fig) {
    var pre = fig.querySelector("pre");
    var btn = fig.querySelector(".copybtn");
    if (!pre || !btn) return;
    btn.addEventListener("click", function () {
      var text = Array.prototype.slice.call(pre.querySelectorAll(".src"))
        .map(function (n) { return n.textContent; }).join("\n") || pre.textContent;
      if (!navigator.clipboard) return;
      navigator.clipboard.writeText(text).then(function () {
        var was = btn.textContent;
        btn.textContent = "Copied";
        setTimeout(function () { btn.textContent = was; }, 1200);
      });
    });
  });
})();
