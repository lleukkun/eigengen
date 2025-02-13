import "./style.css";
import { createMeldPlaceholderOverlay, updateMeldOverlayContent } from "./meldOverlay.js";
import { renderChatHistory, fetchChatHistory } from "./chat.js";
import { fetchProjectContext, selectedFiles } from "./fileTree.js";

// A simple auto-resize function retained here
function autoResize(textarea: HTMLTextAreaElement): void {
  textarea.style.height = "auto";
  textarea.style.height = textarea.scrollHeight + "px";
}

document.addEventListener("DOMContentLoaded", () => {
  // Initialize file tree and chat history
  fetchProjectContext();
  fetchChatHistory();

  const messageInput = document.getElementById("message-input") as HTMLTextAreaElement;
  const sendButton = document.getElementById("send-button") as HTMLButtonElement;

  messageInput.addEventListener("input", () => {
    autoResize(messageInput);
  });

  sendButton.addEventListener("click", async () => {
    // (Message sending logic remains here or could be moved to chat.ts)
    const message = messageInput.value.trim();
    if (message !== "") {
      const chatHistoryEl = document.getElementById("chat-history")!;
      const placeholderDiv = document.createElement("div");
      placeholderDiv.className = "chat-message assistant processing-placeholder";
      placeholderDiv.innerHTML = `<strong>assistant:</strong> ... processing ...`;
      chatHistoryEl.appendChild(placeholderDiv);

      try {
        const response = await fetch("/api/send", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ prompt: message, diff_mode: false, filepaths: Array.from(selectedFiles) })
        });

        if (!response.ok) {
          console.error("Error sending message:", response.statusText);
        } else {
          const data = await response.json();
          console.log("Server response:", data);
          // Chat history updates via fetchChatHistory
        }
      } catch (error) {
        console.error("Fetch error:", error);
      }

      messageInput.value = "";
      autoResize(messageInput);
      await fetchChatHistory();
    }
  });

  // Delegate click events for copy/meld buttons (logic remains similar)
  const chatHistoryEl = document.getElementById("chat-history");
  if (chatHistoryEl) {
    chatHistoryEl.addEventListener("click", (event) => {
      const target = event.target as HTMLElement;
      const codeBlock = target.closest(".code-block") as HTMLElement;
      if (!codeBlock) return;
      const fullMarkdown = decodeURIComponent(codeBlock.dataset.fullmarkdown || "");
      if (target.classList.contains("copy-button")) {
        navigator.clipboard.writeText(fullMarkdown)
          .then(() => alert("Code copied to clipboard"))
          .catch(err => console.error("Copy failed", err));
      } else if (target.classList.contains("meld-button")) {
        const parentBlock = target.closest(".code-block") as HTMLElement;
        const code_block = decodeURIComponent(parentBlock.dataset.codeblock || "");
        const code_filepath = decodeURIComponent(parentBlock.dataset.filepath || "");

        const overlay = createMeldPlaceholderOverlay();

        fetch("/api/meld", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code_block, code_filepath })
        })
          .then(async response => {
            if (response.ok) {
              const data = await response.json();
              const diff = data.diff;
              const new_file_content = data.file_content;
              updateMeldOverlayContent(overlay, diff, new_file_content, code_filepath, target as HTMLButtonElement);
            } else {
              alert("Error calling Meld API");
              document.body.removeChild(overlay);
            }
          })
          .catch(err => {
            console.error("Meld API error:", err);
            document.body.removeChild(overlay);
          });
      }
    });
  } else {
    console.error("Element 'chat-history' not found.");
  }
});
