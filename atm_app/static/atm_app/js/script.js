/* PELEC Bank ATM: keypad, computer keyboard and small effects.

   Rules of this file:
   - It only collects input and shows effects. Money and PIN rules stay in Python.
   - The mouse keypad and the computer keyboard call the SAME functions.
   - A typed PIN lives only in memory. It is sent in the form, then forgotten.
   - If this file does not load, the page still works with the plain fields. */

(function () {
  "use strict";

  document.documentElement.classList.add("js");

  const PIN_LENGTH = 6;
  const MAX_AMOUNT_CHARS = 10;
  const PROCESSING_MS = 900;
  const CARD_MS = 1300;

  const machineTop = document.querySelector(".machine-top");
  const monitor = document.getElementById("monitor");
  const messageEl = monitor.querySelector(".monitor-message");
  const entryForm = document.getElementById("entry-form");
  const chooseForm = document.getElementById("choose-form");
  const cancelForm = document.getElementById("cancel-form");
  const keypad = document.getElementById("keypad");

  const screenName = monitor.dataset.screen;
  const mode = monitor.dataset.input; // "none", "pin", "amount" or "change_pin"

  // The fields on the monitor. Their order matches the steps of Change PIN.
  // The CSRF token is also an input. It is hidden, and it must stay untouched.
  const fields = entryForm
    ? Array.from(entryForm.querySelectorAll('input:not([type="hidden"])'))
    : [];
  const labels = entryForm ? Array.from(entryForm.querySelectorAll("label")) : [];
  const buffers = fields.map(function () { return ""; }); // what was typed, per field

  let step = 0;          // Change PIN: which of the 3 PINs is being typed
  let locked = false;    // true once a form is on its way: all input is ignored
  let hinted = false;    // a hint is showing instead of the normal message
  let baseHTML = messageEl.innerHTML;

  // ------------------------------------------------------------------
  // Shared input functions. Mouse and keyboard both end up here.
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

  function backspace() {
    if (!acceptsInput()) return;
    setCurrent(current().slice(0, -1));
  }

  function clearEntry() {
    if (!acceptsInput()) return;
    setCurrent("");
  }

  function enter() {
    if (!acceptsInput()) return;

    if (mode === "amount") {
      if (current() === "") return hint("Please enter the amount.");
      return send({ amount: current() }, null, 0);
    }

    // PIN modes need exactly six digits. Enter never fires by itself.
    if (current().length !== PIN_LENGTH) return hint("Please enter all six digits.");

    if (mode === "pin") {
      return send({ pin: current() }, "Verifying your PIN...\nPlease wait.", PROCESSING_MS);
    }

    // Change PIN: current PIN, new PIN, confirm. All three go together at the end.
    if (step < 2) {
      step += 1;
      messageEl.textContent = labels[step].textContent;
      baseHTML = messageEl.innerHTML;
      return render();
    }
    send({
      current_pin: buffers[0],
      new_pin: buffers[1],
      confirm_pin: buffers[2],
    }, "Processing your request...\nPlease wait.", PROCESSING_MS);
  }

  function cancelKey() {
    if (locked) return;
    const picker = document.querySelector(".card-picker");
    if (picker && picker.open) {
      picker.open = false; // first close the card window
      return;
    }
    if (screenName === "welcome") return; // nothing to cancel
    if (cancelForm.requestSubmit) cancelForm.requestSubmit();
    else cancelForm.submit();
  }

  function pressKey(key) {
    if (key === "clear") clearEntry();
    else if (key === ".") pressDecimal();
    else if (key === "00") pressDoubleZero();
    else pressDigit(key);
  }

  // ------------------------------------------------------------------
  // Showing things
  // ------------------------------------------------------------------

  function render() {
    fields.forEach(function (input, i) {
      const active = i === step;
      input.hidden = !active;
      labels[i].hidden = !active;
      // A PIN is always shown as stars. Never the digits.
      input.value = mode === "amount" ? buffers[i] : "*".repeat(buffers[i].length);
    });
    if (hinted) {
      messageEl.innerHTML = baseHTML;
      hinted = false;
    }
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

  function hint(text) {
    messageEl.textContent = text;
    hinted = true;
  }

  function showProcessing(text) {
    machineTop.classList.add("is-processing");
    const box = document.createElement("div");
    box.className = "processing";
    const message = document.createElement("p");
    message.className = "monitor-message";
    text.split("\n").forEach(function (line, i) {
      if (i > 0) message.append(document.createElement("br"));
      message.append(document.createTextNode(line));
    });
    const spinner = document.createElement("div");
    spinner.className = "spinner";
    box.append(message, spinner);
    monitor.querySelector(".monitor-main").append(box);
  }

  // ------------------------------------------------------------------
  // Sending a form. Only one form is ever sent per page.
  // ------------------------------------------------------------------

  function addHidden(form, values) {
    Object.keys(values).forEach(function (name) {
      const input = document.createElement("input");
      input.type = "hidden";
      input.name = name;
      input.value = values[name];
      input.dataset.jsField = "1";
      form.append(input);
    });
  }

  function removeHidden(form) {
    form.querySelectorAll("input[data-js-field]").forEach(function (input) {
      input.remove();
    });
  }

  function wipe() {
    buffers.fill("");
    fields.forEach(function (input) { input.value = ""; });
  }

  function submitWith(form, values, processingText, delay) {
    if (locked) return; // a second Enter or click cannot send it twice
    locked = true;
    updateKeys();
    addHidden(form, values);
    if (processingText) showProcessing(processingText);
    window.setTimeout(function () {
      form.submit();      // the form data is read right here
      removeHidden(form); // so typed PINs do not stay in the page
      wipe();
    }, processingText ? delay : 0);
  }

  function send(values, processingText, delay) {
    submitWith(entryForm, values, processingText, delay);
  }

  // ------------------------------------------------------------------
  // Wiring: keypad, keyboard, side buttons, card slot
  // ------------------------------------------------------------------

  // Keypad (mouse). mousedown is stopped so a key never keeps keyboard focus.
  keypad.addEventListener("mousedown", function (event) { event.preventDefault(); });
  keypad.addEventListener("click", function (event) {
    const button = event.target.closest("[data-key]");
    if (button && !button.disabled) pressKey(button.dataset.key);
  });

  // The Enter key and any Enter button submit the entry form: use enter().
  if (entryForm) {
    entryForm.addEventListener("submit", function (event) {
      event.preventDefault();
      enter();
    });
  }

  // Cancel button (and Escape) end up here. Lock so nothing else is sent.
  cancelForm.addEventListener("submit", function (event) {
    if (locked) {
      event.preventDefault();
      return;
    }
    locked = true;
    updateKeys();
  });

  // Side buttons: show "Processing..." only for the final Yes of a transaction.
  chooseForm.addEventListener("submit", function (event) {
    event.preventDefault();
    const slot = event.submitter && event.submitter.value;
    if (!slot || locked) return;

    let text = null;
    if (screenName === "confirm" && labelFor(slot) === "Yes") {
      const deposit = messageEl.textContent.indexOf("Deposit") === 0;
      text = deposit ? "Processing your deposit...\nPlease wait."
                     : "Processing your withdrawal...\nPlease wait.";
    }
    submitWith(chooseForm, { slot: slot }, text, PROCESSING_MS);
  });

  function labelFor(slot) {
    const side = slot.charAt(0) === "L" ? ".labels-left" : ".labels-right";
    const item = monitor.querySelectorAll(side + " li")[Number(slot.charAt(1)) - 1];
    const strong = item && item.querySelector("strong");
    return strong ? strong.textContent : "";
  }

  // Card window: choosing a card slides it into the slot, then sends the form.
  document.querySelectorAll(".card-window form").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      if (locked) return;
      const cardButton = event.submitter || form.querySelector("button");
      const reader = document.getElementById("card-slot");

      const copy = document.createElement("div");
      copy.className = cardButton.className + " inserted-card";
      copy.replaceChildren.apply(copy, Array.from(cardButton.childNodes, function (node) {
        return node.cloneNode(true);
      }));
      reader.append(copy);

      const picker = reader.querySelector("details");
      if (picker) picker.open = false;
      submitWith(form, {}, "Processing your card...\nPlease wait.", CARD_MS);
    });
  });

  // A click outside the card window closes it.
  document.addEventListener("click", function (event) {
    const picker = document.querySelector(".card-picker");
    if (picker && picker.open && !picker.contains(event.target)) picker.open = false;
  });

  // Computer keyboard. It calls the same functions as the keypad.
  document.addEventListener("keydown", function (event) {
    if (event.ctrlKey || event.metaKey || event.altKey) return; // keep browser shortcuts
    const key = event.key;

    if (key === "Escape") {
      event.preventDefault();
      flash("#key-cancel");
      cancelKey();
    } else if (/^[0-9]$/.test(key)) { // top row and numpad both give "0" to "9"
      if (mode === "none") return;
      event.preventDefault();
      flash('[data-key="' + key + '"]');
      pressDigit(key);
    } else if (key === ".") {
      if (mode !== "amount") return;
      event.preventDefault();
      flash('[data-key="."]');
      pressDecimal();
    } else if (key === "Backspace") {
      if (mode === "none") return;
      event.preventDefault();
      backspace();
    } else if (key === "Delete") {
      if (mode === "none") return;
      event.preventDefault();
      flash('[data-key="clear"]');
      clearEntry();
    } else if (key === "Enter") {
      if (mode === "none") return; // leave Enter to a focused button
      const target = event.target;
      if (target.closest && target.closest("button, summary, a")) return;
      event.preventDefault();
      if (event.repeat) return; // a held Enter must not repeat
      flash("#key-enter");
      enter();
    }
  });

  function flash(selector) {
    const button = keypad.querySelector(selector);
    if (!button) return;
    button.classList.add("is-pressed");
    window.setTimeout(function () { button.classList.remove("is-pressed"); }, 120);
  }

  // ------------------------------------------------------------------
  // Start
  // ------------------------------------------------------------------

  fields.forEach(function (input) {
    input.readOnly = true;           // the keypad types, not the browser
    input.type = "text";             // stars are text, not password dots
    input.removeAttribute("name");   // the real values are sent as hidden fields
    input.tabIndex = -1;
    input.placeholder = mode === "amount" ? "0.00" : "------";
  });
  render();

  // After a transaction the receipt and cash come out.
  if (screenName === "done") {
    const printer = document.getElementById("receipt-printer");
    const dispenser = document.getElementById("cash-dispenser");
    printer.classList.add("is-printing");
    dispenser.classList.add("is-dispensing");
    const tab = printer.querySelector("summary");
    if (tab) {
      tab.addEventListener("animationend", function () {
        printer.classList.remove("is-printing");
      });
    }
  }

  // Back button: reload so the screen matches the server.
  window.addEventListener("pageshow", function (event) {
    if (event.persisted) window.location.reload();
  });
})();