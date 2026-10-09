/* Drag a flag up and down a ladder with the left button.
 *
 * Dash has no drag primitive, so this is a plain document-level mouse handler. It is
 * generic: everything it needs is written onto the flag itself by the renderer that
 * drew it.
 *
 *     .lad-flag            marks a draggable chip
 *     data-input="tr-stop"    the input to write the dropped price into
 *     data-lo / data-hi       the legal price range, computed server-side
 *
 * The server already knows every constraint -- a stop stays on the losing side, a target
 * on the winning side, nothing leaves the drawn window -- so it renders the legal range
 * rather than this script re-deriving rules it would then have to keep in step.
 *
 * LEFT button (desk, 2026-10-09). It was the right, the gesture on the platform the desk
 * trades on, until the desk asked for the left; the right button now gets the browser's
 * own menu back. The click that follows a drop is swallowed, so letting go over a size
 * or a dot never skips or picks anything.
 *
 * On release it writes through the native value setter plus an `input` event; assigning
 * `.value` updates the DOM and React never hears about it. That is a documented
 * workaround rather than an API, so the typed field stays the source of truth -- if a
 * Dash upgrade breaks this you lose the drag, not the ladder.
 */
(function () {
    "use strict";

    function priceOf(tr) {
        var el = tr && tr.querySelector(".lad-px");
        return el ? parseFloat(el.textContent) : NaN;
    }

    function setNative(el, v) {
        var d = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, "value");
        d.set.call(el, String(v));
        el.dispatchEvent(new Event("input", { bubbles: true }));
    }

    var drag = null;
    var suppressUntil = 0;

    // Capture phase, on the document: it runs before React's own listener, so a click
    // stopped here never reaches a Dash n_clicks.
    document.addEventListener("click", function (e) {
        if (Date.now() < suppressUntil) {
            e.stopPropagation();
            e.preventDefault();
        }
    }, true);

    document.addEventListener("mousedown", function (e) {
        if (e.button !== 0 || !e.target.closest) return;
        var flag = e.target.closest(".lad-flag");
        if (!flag) return;

        var body = flag.closest("tbody");
        var tr = flag.closest("tr");
        if (!body || !tr) return;
        var rows = Array.prototype.slice.call(body.querySelectorAll("tr"));
        var from = rows.indexOf(tr);
        if (from < 0) return;

        /* Prices run high to low down the table, so the legal rows are contiguous and
         * the range collapses to a first and last index. */
        var lo = parseFloat(flag.getAttribute("data-lo"));
        var hi = parseFloat(flag.getAttribute("data-hi"));
        var first = -1, last = -1;
        for (var i = 0; i < rows.length; i++) {
            var px = priceOf(rows[i]);
            if (isFinite(px) && px >= lo - 1e-9 && px <= hi + 1e-9) {
                if (first < 0) first = i;
                last = i;
            }
        }
        if (first < 0) return;                     // nowhere legal to put it

        e.preventDefault();
        drag = {
            flag: flag, rows: rows, from: from, to: from,
            first: first, last: last,
            input: flag.getAttribute("data-input"),
            rowH: tr.getBoundingClientRect().height || 22,
            y0: e.clientY,
        };
        flag.classList.add("dragging");
        document.body.classList.add("lad-dragging");
    });

    document.addEventListener("mousemove", function (e) {
        if (!drag) return;
        var want = drag.from + Math.round((e.clientY - drag.y0) / drag.rowH);
        var to = Math.max(drag.first, Math.min(drag.last, want));
        if (to !== drag.to) {
            drag.rows[drag.to].classList.remove("lad-drop");
            drag.to = to;
            drag.rows[to].classList.add("lad-drop");
        }
        // The flag follows the cursor in the DOM; the ladder is only rebuilt on release,
        // because a rebuild mid-drag would destroy the element being dragged.
        drag.flag.style.transform =
            "translateY(" + (drag.to - drag.from) * drag.rowH + "px)";
    });

    function finish() {
        if (!drag) return;
        var d = drag;
        drag = null;
        suppressUntil = Date.now() + 400;      // the click that would follow the drop
        d.flag.classList.remove("dragging");
        d.flag.style.transform = "";
        document.body.classList.remove("lad-dragging");
        var row = d.rows[d.to];
        if (row) row.classList.remove("lad-drop");
        if (d.to === d.from) return;

        var px = priceOf(row);
        var input = document.getElementById(d.input);
        if (input && isFinite(px)) setNative(input, Math.round(px * 2) / 2);
    }

    document.addEventListener("mouseup", finish);
    // A drag that leaves the window would otherwise stay armed forever.
    window.addEventListener("blur", finish);
})();
