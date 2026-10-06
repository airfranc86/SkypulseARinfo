/* Layout probe (tests and visual review only): reports where every key element landed and which
   texts overflow, as JSON in a hidden PRE element (id layout-report). Read back with medicion.py. */
(function () {
  function report() {
    var elements = [];
    document.querySelectorAll('[data-key]').forEach(function (el) {
      var r = el.getBoundingClientRect();
      elements.push({
        name: el.getAttribute('data-key'),
        zone: el.getAttribute('data-zone') || 'content',
        top: r.top, bottom: r.bottom, left: r.left, right: r.right
      });
    });
    var overflow = [];
    // Texts must not overflow sideways; only the content box is checked vertically (big type with a
    // tight line height reports a taller scroll box without anything being cut).
    document.querySelectorAll('[data-fit]').forEach(function (el) {
      var name = el.getAttribute('data-fit');
      var wide = el.scrollWidth > el.clientWidth + 1;
      // A couple of px of line-box rounding is not a cut text: every key element is checked apart.
      var tall = name === 'content' && el.scrollHeight > el.clientHeight + 4;
      if (wide || tall) {
        overflow.push(name);
      }
    });
    var pre = document.createElement('pre');
    pre.id = 'layout-report';
    pre.style.display = 'none';
    var box = document.querySelector('.content');
    var scale = parseFloat((box && box.getAttribute('data-fit-scale')) || '1');
    pre.textContent = JSON.stringify({ elements: elements, overflow: overflow, scale: scale });
    document.body.appendChild(pre);
  }
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(report);
  } else {
    report();
  }
})();
