/* PELEC Bank ATM: keypad.
   This file only types into the input. Money and PIN rules stay in Python. */

(function () {
  "use strict";

  const PIN_LENGTH = 6;
  const MAX_AMOUNT_CHARS = 10;

  const monitor = document.getElementById("monitor");
  const entryForm = document.getElementById("entry-form");
  const keypad = document.getElementById("keypad");
  if (!monitor || !keypad) return; // the keypad markup is not on the page

  const mode = monitor.dataset.input; // "none", "pin", "amount" or "change_pin"

  // The fields on the monitor. The CSRF token is also an input.
  // It is hidden, and it must stay untouched.
  const fields = entryForm
    ? Array.from(entryForm.querySelectorAll('input:not([type="hidden"])'))
    : [];
  const buffers = fields.map(function () { return ""; }); // what was typed, per field

  let step = 0;          // which field is being typed (Change PIN has three)
  let locked = false;    // true once a form is on its way: all input is ignored

  // ------------------------------------------------------------------
  // Typing
  // ------------------------------------------------------------------

  function acceptsInput() {
    return mode !== "none" && !locked;
  }

  function current() {
    return buffers[step];
  }

  function setCurrent(value) {
    buffers[step] = value;
    render();
  }

  function pressDigit(digit) {
    if (!acceptsInput()) return;
    const value = current();
    if (mode === "amount") {
      setCurrent(nextAmount(value, digit));
    } else if (value.length < PIN_LENGTH) {
      setCurrent(value + digit);
    }
  }

  // Amount typing rules: at most 2 decimals, no leading zeros, limited length.
  function nextAmount(value, digit) {
    if (value.length >= MAX_AMOUNT_CHARS) return value;
    if (value.includes(".") && value.split(".")[1].length >= 2) return value;
    if (value === "0") return digit === "0" ? value : digit;
    return value + digit;
  }

  function pressDecimal() {
    if (!acceptsInput() || mode !== "amount") return;
    const value = current();
    if (value.includes(".")) return;
    setCurrent(value === "" ? "0." : value + ".");
  }

  function pressDoubleZero() {
    if (!acceptsInput() || mode !== "amount") return;
    pressDigit("0");
    pressDigit("0");
  }

  // The Clear key is added in the next commit, so it is ignored for now.
  function pressKey(key) {
    if (key === ".") pressDecimal();
    else if (key === "00") pressDoubleZero();
    else if (key !== "clear") pressDigit(key);
  }

  // ------------------------------------------------------------------
  // Showing things
  // ------------------------------------------------------------------

  function render() {
    fields.forEach(function (input, i) {
      input.value = buffers[i];
    });
    updateKeys();
  }

  function updateKeys() {
    keypad.querySelectorAll("[data-key]").forEach(function (button) {
      const key = button.dataset.key;
      let enabled = acceptsInput();
      if (key === "." || key === "00") enabled = enabled && mode === "amount";
      button.disabled = !enabled;
    });
  }

  // ------------------------------------------------------------------
  // Wiring
  // ------------------------------------------------------------------

  // Keypad (mouse). mousedown is stopped so a key never keeps keyboard focus.
  keypad.addEventListener("mousedown", function (event) { event.preventDefault(); });
  keypad.addEventListener("click", function (event) {
    const button = event.target.closest("[data-key]");
    if (button && !button.disabled) pressKey(button.dataset.key);
  });

  // ------------------------------------------------------------------
  // Start
  // ------------------------------------------------------------------

  fields.forEach(function (input, i) {
    input.readOnly = true;   // the keypad types, not the browser
    input.tabIndex = -1;
    input.placeholder = mode === "amount" ? "0.00" : "------";
    input.addEventListener("focus", function () { step = i; });
  });
  render();
})();