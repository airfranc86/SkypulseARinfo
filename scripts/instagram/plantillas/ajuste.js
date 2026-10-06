/* Safety net: if a plate ever carries more than the safe area holds, shrink the body until it fits
   instead of cutting it. The scale is written on the content box (data-fit-scale) so the layout
   probe reports it; the templates are sized so real plates never need it. */
(function () {
  var MIN_SCALE = 0.6;
  var TOLERANCE_PX = 4;

  function fit() {
    var content = document.querySelector('.content');
    var body = content && content.querySelector('.body');
    if (!body) {
      return;
    }
    // Measured on the content box, which is never zoomed, so every number is in page px.
    var scale = 1;
    var excess = content.scrollHeight - content.clientHeight;
    if (excess > TOLERANCE_PX) {
      var available = content.clientHeight - body.offsetTop;
      scale = Math.max(MIN_SCALE, available / (available + excess));
      body.style.zoom = String(scale);
      for (var step = 0; step < 10 && scale > MIN_SCALE; step += 1) {
        if (content.scrollHeight <= content.clientHeight + TOLERANCE_PX) {
          break;
        }
        scale = Math.max(MIN_SCALE, scale - 0.02);
        body.style.zoom = String(scale);
      }
    }
    content.setAttribute('data-fit-scale', scale.toFixed(3));
  }

  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(fit);
  } else {
    fit();
  }
})();
