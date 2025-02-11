import "./style.css";
import MarkdownIt from "markdown-it";
import hljs from "highlight.js";
import "highlight.js/styles/github.css";

// Auto-resize the textarea based on content
function autoResize(textarea: HTMLTextAreaElement): void {
  textarea.style.height = 'auto';
  textarea.style.height = textarea.scrollHeight + 'px';
}

const md = new MarkdownIt();

// highlight function that references the md instance
function highlight(str: string, lang: string): string {
  const language = lang?.split(";")[0];
  if (language && hljs.getLanguage(language)) {
    try {
      return `<pre class="hljs"><code>${hljs.highlight(str, { language }).value
        }</code></pre>`;
    } catch { }
  }
  return `<pre class="hljs"><code>${md.utils.escapeHtml(str)}</code></pre>`;
}

// now attach it:
md.options.highlight = highlight;


// Function to render the chat history in the chat-history div.
function renderChatHistory(messages: { role: string; content: string }[]): void {
  const chatHistory = document.getElementById("chat-history");
  if (chatHistory) {
    chatHistory.innerHTML = "";
    messages.forEach((msg) => {
      const msgDiv = document.createElement("div");
      msgDiv.className = "chat-message " + msg.role;
      // Render Markdown content including support for fenced code blocks
      msgDiv.innerHTML = `<strong>${msg.role}:</strong> ` + md.render(msg.content);
      chatHistory.appendChild(msgDiv);
    });
  }
}

async function fetchChatHistory(): Promise<void> {
  try {
    const response = await fetch("/api/history");
    if (response.ok) {
      const messages = await response.json();
      renderChatHistory(messages);
    } else {
      console.error("Failed to fetch chat history:", response.statusText);
    }
  } catch (error) {
    console.error("Error fetching chat history:", error);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const messageInput = document.getElementById("message-input") as HTMLTextAreaElement;
  const sendButton = document.getElementById("send-button") as HTMLButtonElement;

  // Attach input event to adjust height automatically
  messageInput.addEventListener("input", () => {
    autoResize(messageInput);
  });

  // Handle send button click
  sendButton.addEventListener("click", async () => {
    const message = messageInput.value.trim();
    if (message !== "") {
      try {
        const response = await fetch("/api/send", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ prompt: message, diff_mode: false }),
        });

        if (!response.ok) {
          console.error("Error sending message:", response.statusText);
        } else {
          const data = await response.json();
          console.log("Server response:", data);
          // Optionally, you can do something with data.answer or data.diff here.
        }
      } catch (error) {
        console.error("Fetch error:", error);
      }

      messageInput.value = ""; // clear the textarea after sending
      autoResize(messageInput);
      await fetchChatHistory(); // update chat history after sending message
    }
  });

  // Fetch chat history on page load
  fetchChatHistory();
});
