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
