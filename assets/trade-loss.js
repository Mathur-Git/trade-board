/* Step the Trade page's max loss by 500 from its ▼ ▲ buttons and the arrow keys.
 *
 * Written into the box the way typing is -- the native value setter plus an `input`
 * event, as ladder-drag.js does -- so React hears it and the box's half-second debounce
 * re-arms: a run of clicks commits once, when you stop, and a number typed a moment
 * before is stepped from rather than overwriting the step when its debounce fires.
 *
 * Off-step amounts go to the next step in the direction pressed (4,750 -> 5,000 or
 * 4,500); a blank box goes up to one step and not down; nothing goes below one step.
 */
(function () {
    const STEP = 500;       // LOSS_STEP in structure_board.py
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;

    function step(dir) {
        const el = document.getElementById("tr-loss");
        if (!el) return;
        const raw = String(el.value || "").replace(/[,$\s]/g, "");
        const v = raw === "" ? null : Number(raw);
        let n;
        if (dir > 0) {
            n = (v === null || isNaN(v)) ? STEP : Math.floor(v / STEP) * STEP + STEP;
        } else {
            if (v === null || isNaN(v) || v <= STEP) return;
            n = Math.max(STEP, Math.ceil(v / STEP) * STEP - STEP);
        }
        setter.call(el, String(n));
        el.dispatchEvent(new Event("input", { bubbles: true }));
        // Grey the ▼ now rather than half a second later, when the committed value
        // reaches its callback -- which then sets it the same way.
        const dn = document.getElementById("tr-loss-dn");
        if (dn) dn.disabled = !(n > STEP);
    }

    document.addEventListener("click", function (e) {
        const b = e.target && e.target.closest && e.target.closest("#tr-loss-up, #tr-loss-dn");
        if (!b || b.disabled) return;
        step(b.id === "tr-loss-up" ? 1 : -1);
    });

    document.addEventListener("keydown", function (e) {
        if (!e.target || e.target.id !== "tr-loss") return;
        if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return;
        if (e.altKey || e.ctrlKey || e.metaKey) return;
        e.preventDefault();         // not the caret jump to the start / end of the box
        step(e.key === "ArrowUp" ? 1 : -1);
    });
})();
