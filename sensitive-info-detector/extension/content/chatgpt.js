(function () {
  const extension = window.AISecurityExtension;
  if (!extension) {
    return;
  }

  extension.installInterception({
    platform: "chatgpt",
    composeSelectors: [
      "form textarea",
      "textarea[placeholder]",
      "div[contenteditable='true'][data-testid*='composer']",
      "div[contenteditable='true'][role='textbox']"
    ],
    sendButtonSelectors: [
      "form button[data-testid*='send']",
      "button[data-testid='send-button']",
      "button[aria-label*='Send']",
      "button[aria-label*='send']"
    ]
  });
})();
