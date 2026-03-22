(function () {
  const extension = window.AISecurityExtension;
  if (!extension) {
    return;
  }

  extension.installInterception({
    platform: "gemini",
    composeSelectors: [
      "rich-textarea div[contenteditable='true']",
      "div[contenteditable='true'][role='textbox']",
      "textarea",
      "div.ql-editor[contenteditable='true']"
    ],
    sendButtonSelectors: [
      "button[aria-label*='Send']",
      "button[aria-label*='send']",
      "button[data-test-id*='send']",
      "button[mattooltip*='Send']"
    ]
  });
})();
