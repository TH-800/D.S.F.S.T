import { JSDOM } from "jsdom";

// Preload before React DOM, which detects browser event support at import time.
const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost:3000" });
for (const name of ["window", "document", "HTMLElement", "HTMLInputElement", "HTMLSelectElement", "Event", "MouseEvent", "MutationObserver", "DocumentFragment", "Node", "Element", "CustomEvent", "getComputedStyle"]) {
  Object.defineProperty(globalThis, name, { configurable: true, value: (dom.window as any)[name] });
}
Object.defineProperty(globalThis, "navigator", { configurable: true, value: dom.window.navigator });
(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
