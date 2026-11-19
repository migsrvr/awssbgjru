const test = require("node:test");
const assert = require("node:assert/strict");

const availability = require("../frontend/js/division-availability.js");

test("only full metadata is treated as unavailable", () => {
  assert.equal(availability.isFullPill({ dataset: { availability: "full" } }), true);
  assert.equal(availability.isFullPill({ dataset: { availability: "open" } }), false);
  assert.equal(availability.isFullPill({ dataset: {} }), false);
});

test("full-pill click prevents the page selection handler", () => {
  const listeners = {};
  const pill = {
    dataset: { availability: "full" },
    addEventListener(type, handler) {
      listeners[type] = handler;
    },
  };
  const errorText = { textContent: "default" };
  const error = {
    dataset: {},
    querySelector() {
      return errorText;
    },
    classList: {
      add(name) {
        this[name] = true;
      },
      remove(name) {
        delete this[name];
      },
    },
  };

  availability.bindPill(pill, error);

  let prevented = false;
  let stopped = false;
  listeners.click({
    preventDefault() {
      prevented = true;
    },
    stopImmediatePropagation() {
      stopped = true;
    },
  });

  assert.equal(prevented, true);
  assert.equal(stopped, true);
  assert.equal(errorText.textContent, availability.FULL_MESSAGE);
  assert.equal(error.classList.visible, true);
});

test("Skill Builder full-pill click shows the message below the department name", () => {
  const listeners = {};
  const pillClasses = new Set();
  const noteClasses = new Set();
  const note = {
    classList: {
      add(name) {
        noteClasses.add(name);
      },
      remove(name) {
        noteClasses.delete(name);
      },
    },
  };
  const pill = {
    dataset: { availability: "full" },
    parentElement: {
      querySelectorAll() {
        return [pill];
      },
    },
    addEventListener(type, handler) {
      listeners[type] = handler;
    },
    querySelector(selector) {
      return selector === ".division-unavailable-note" ? note : null;
    },
    classList: {
      add(name) {
        pillClasses.add(name);
      },
      remove(name) {
        pillClasses.delete(name);
      },
      contains(name) {
        return pillClasses.has(name);
      },
    },
  };
  const errorText = { textContent: "default" };
  const error = {
    dataset: {},
    querySelector() {
      return errorText;
    },
    classList: {
      add(name) {
        this[name] = true;
      },
      remove(name) {
        delete this[name];
      },
    },
  };

  availability.bindPill(pill, error);
  listeners.click({
    preventDefault() {},
    stopImmediatePropagation() {},
  });

  assert.equal(pillClasses.has("unavailable-message-visible"), true);
  assert.equal(noteClasses.has("visible"), true);
  assert.equal(error.classList.visible, undefined);
});

test("Office full-pill click shows the message below the department name", () => {
  const listeners = {};
  const pillClasses = new Set();
  const noteClasses = new Set();
  const note = {
    classList: {
      add(name) {
        noteClasses.add(name);
      },
      remove(name) {
        noteClasses.delete(name);
      },
    },
  };
  const pill = {
    dataset: { availability: "full" },
    parentElement: {
      querySelectorAll() {
        return [pill];
      },
    },
    addEventListener(type, handler) {
      listeners[type] = handler;
    },
    querySelector(selector) {
      return selector === ".division-unavailable-note" ? note : null;
    },
    classList: {
      add(name) {
        pillClasses.add(name);
      },
      remove(name) {
        pillClasses.delete(name);
      },
    },
  };
  const error = {
    dataset: {},
    querySelector() {
      return { textContent: "default" };
    },
    classList: {
      add() {},
      remove() {},
    },
  };

  availability.bindPill(pill, error);
  listeners.click({
    preventDefault() {},
    stopImmediatePropagation() {},
  });

  assert.equal(pillClasses.has("unavailable-message-visible"), true);
  assert.equal(noteClasses.has("visible"), true);
});

test("applyAvailability dynamically flips Office pills between open and full", () => {
  function makeMockPill(division, initialAvailability, extraClasses = []) {
    const attrs = {};
    const classes = new Set(extraClasses);
    let noteEl = null;
    const ribbonEl = { innerHTML: "" };
    const copyEl = {
      appendChild(el) {
        noteEl = el;
      },
    };
    return {
      dataset: { division, availability: initialAvailability },
      attrs,
      classes,
      ribbonEl,
      getNote: () => noteEl,
      setAttribute(k, v) {
        attrs[k] = v;
      },
      removeAttribute(k) {
        delete attrs[k];
      },
      classList: {
        add(name) { classes.add(name); },
        remove(name) { classes.delete(name); },
        contains(name) { return classes.has(name); },
      },
      querySelector(selector) {
        if (selector === ".availability-ribbon") return ribbonEl;
        if (selector === ".division-copy") return copyEl;
        if (selector === ".division-unavailable-note") return noteEl;
        return null;
      },
    };
  }

  const origDoc = global.document;
  global.document = {
    createElement(tag) {
      const attrs = {};
      return {
        tagName: tag.toUpperCase(),
        className: "",
        textContent: "",
        attrs,
        setAttribute(k, v) { attrs[k] = v; },
        classList: { add() {}, remove() {} },
      };
    },
  };

  try {
    const opsPill = makeMockPill("Operations", "open", ["selected"]);
    const mktPill = makeMockPill("Marketing", "full");
    const relPill = makeMockPill("Relations", "full", ["year-ineligible"]);
    relPill.setAttribute("aria-disabled", "true");

    availability.applyAvailability(
      "office",
      { Operations: "full", Marketing: "open", Relations: "open" },
      [opsPill, mktPill, relPill],
    );

    assert.equal(opsPill.dataset.availability, "full");
    assert.equal(opsPill.attrs["aria-disabled"], "true");
    assert.equal(opsPill.classes.has("selected"), false);
    assert.match(opsPill.ribbonEl.innerHTML, /ribbons\/full\.svg/);
    assert.ok(opsPill.getNote());
    assert.equal(opsPill.getNote().textContent, availability.FULL_MESSAGE);

    assert.equal(mktPill.dataset.availability, "open");
    assert.equal(mktPill.attrs["aria-disabled"], undefined);
    assert.match(mktPill.ribbonEl.innerHTML, /ribbons\/open\.svg/);
    assert.match(mktPill.ribbonEl.innerHTML, /ribbons\/open-selected\.svg/);

    // Year-ineligible pill keeps aria-disabled="true" even when opened
    assert.equal(relPill.dataset.availability, "open");
    assert.equal(relPill.attrs["aria-disabled"], "true");
  } finally {
    global.document = origDoc;
  }
});

test("applyAvailability dynamically updates Skill Builder ribbons", () => {
  const attrs = {};
  const ribbonEl = { innerHTML: "" };
  const copyEl = { appendChild() {} };
  const sbPill = {
    dataset: { division: "Web Development", availability: "full" },
    setAttribute(k, v) { attrs[k] = v; },
    removeAttribute(k) { delete attrs[k]; },
    classList: { add() {}, remove() {}, contains() { return false; } },
    querySelector(selector) {
      if (selector === ".availability-ribbon") return ribbonEl;
      if (selector === ".division-copy") return copyEl;
      return null;
    },
  };

  availability.applyAvailability("skillbuilder", { "Web Development": "open" }, [sbPill]);
  assert.equal(sbPill.dataset.availability, "open");
  assert.match(ribbonEl.innerHTML, /ribbons\/skillbuilder-open\.svg/);

  availability.applyAvailability("skillbuilder", { "Web Development": "full" }, [sbPill]);
  assert.equal(sbPill.dataset.availability, "full");
  assert.equal(attrs["aria-disabled"], "true");
  assert.match(ribbonEl.innerHTML, /ribbons\/skillbuilder-full\.svg/);
});
