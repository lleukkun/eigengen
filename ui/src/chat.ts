interface ChatMessage {
  role: string;
  content: string;
}

// Render chat messages using the markdown engine
export function renderChatHistory(messages: ChatMessage[]): void {
  const chatHistory = document.getElementById("chat-history");
  if (chatHistory) {
    chatHistory.innerHTML = "";
    messages.forEach((msg) => {
      const msgDiv = document.createElement("div");
      msgDiv.className = `chat-message ${msg.role}`;
      // md is imported from markdownEngine; assume it is available globally or passed via DI if preferred.
      import("./markdownEngine.js").then(({ md }) => {
        msgDiv.innerHTML = `<strong>${msg.role}:</strong> ` + md.render(msg.content);
      });
      chatHistory.appendChild(msgDiv);
    });
  }
}

// Fetch chat history from the API and render it.
export async function fetchChatHistory(): Promise<void> {
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
