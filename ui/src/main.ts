import "./style.css";
import MarkdownIt from "markdown-it";
import hljs from "highlight.js";
import "highlight.js/styles/atom-one-dark.css";

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

// Custom renderer for fenced code blocks with a header and control buttons
md.renderer.rules.fence = function (tokens, idx, options, env, self) {
  const token = tokens[idx];
  const info = token.info ? token.info.trim() : "";
  const parts = info.split(";");
  const filePathProvided = parts[1] && parts[1].trim().length > 0;
  const fileName = filePathProvided ? parts[1].trim() : "code";
  // If a language is provided after a semicolon use it, otherwise infer from the file extension
  const language = parts.length > 1
    ? parts[0].trim()
    : (fileName.includes(".") ? fileName.split(".").pop() || "" : "");
  const fullBlock = "```" + token.info + "\n" + token.content + "\n```";

  let highlighted = "";
  if (language && hljs.getLanguage(language)) {
    try {
      highlighted = hljs.highlight(token.content, { language }).value;
    } catch (e) { }
  }
  if (!highlighted) {
    highlighted = md.utils.escapeHtml(token.content);
  }
  const codeHtml = `<pre class="hljs"><code>${highlighted}</code></pre>`;

  return `
    <div class="code-block"
         data-fullmarkdown="${encodeURIComponent(fullBlock)}"
         data-codeblock="${encodeURIComponent(token.content)}"
         data-filepath="${encodeURIComponent(fileName)}">
      <div class="code-header">
        <span class="code-filename">${fileName}</span>
        <span class="code-language">${language ? language.toUpperCase() : ""}</span>
        <div class="code-header-buttons">
          <button class="copy-button">Copy</button>
          ${filePathProvided ? '<button class="meld-button">Meld</button>' : '<button class="meld-button" disabled>Meld</button>'}
        </div>
      </div>
      ${codeHtml}
    </div>
  `;
};

// Helper function to show the diff overlay and handle user confirmation.
function showMeldOverlay(diff: string, file_content: string,
                         file_path: string, meldButton: HTMLButtonElement): void {
  // Create overlay container
  const overlay = document.createElement("div");
  overlay.id = "meld-overlay";
  overlay.style.position = "fixed";
  overlay.style.top = "0";
  overlay.style.left = "0";
  overlay.style.width = "100vw";
  overlay.style.height = "100vh";
  overlay.style.backgroundColor = "rgba(0, 0, 0, 0.8)";
  overlay.style.display = "flex";
  overlay.style.alignItems = "center";
  overlay.style.justifyContent = "center";
  overlay.style.zIndex = "1000";

  // Create container for the diff content and buttons
  const container = document.createElement("div");
  container.style.backgroundColor = "#1e1e1e";
  container.style.padding = "20px";
  container.style.borderRadius = "5px";
  container.style.maxWidth = "80vw";
  container.style.maxHeight = "80vh";
  container.style.overflowY = "auto";

  // Diff display with basic formatting and syntax highlighting using hljs (if available)
  const diffPre = document.createElement("pre");
  diffPre.style.backgroundColor = "#2d2d2d";
  diffPre.style.padding = "10px";
  diffPre.style.borderRadius = "3px";
  diffPre.style.overflowX = "auto";
  diffPre.className = "hljs";
  const diffCode = document.createElement("code");
  diffCode.className = "diff";
  diffCode.innerText = diff;
  diffPre.appendChild(diffCode);

  // Create buttons container
  const buttonsDiv = document.createElement("div");
  buttonsDiv.style.marginTop = "10px";
  buttonsDiv.style.textAlign = "right";

  // Accept button
  const acceptButton = document.createElement("button");
  acceptButton.innerText = "Accept";
  acceptButton.style.marginRight = "10px";

  // Reject button
  const rejectButton = document.createElement("button");
  rejectButton.innerText = "Reject";

  buttonsDiv.appendChild(acceptButton);
  buttonsDiv.appendChild(rejectButton);

  container.appendChild(diffPre);
  container.appendChild(buttonsDiv);
  overlay.appendChild(container);
  document.body.appendChild(overlay);

  // Accept handler: call /api/apply and disable button on success
  acceptButton.addEventListener("click", async () => {
    try {
      const response = await fetch("/api/apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ "file_content": file_content, "file_path": file_path })
      });
      if (response.ok) {
        alert("Changes applied successfully.");
        meldButton.disabled = true;
      } else {
        const data = await response.json();
        alert("Error applying changes: " + (data.error || response.statusText));
      }
    } catch (err) {
      console.error("Apply API error:", err);
      alert("Error applying changes.");
    }
    document.body.removeChild(overlay);
  });

  // Reject handler: simply remove the overlay.
  rejectButton.addEventListener("click", () => {
    document.body.removeChild(overlay);
  });
}

// Creates a Meld overlay with a placeholder processing message.
function createMeldPlaceholderOverlay(): HTMLElement {
  const overlay = document.createElement("div");
  overlay.id = "meld-overlay";
  overlay.style.position = "fixed";
  overlay.style.top = "0";
  overlay.style.left = "0";
  overlay.style.width = "100vw";
  overlay.style.height = "100vh";
  overlay.style.backgroundColor = "rgba(0, 0, 0, 0.8)";
  overlay.style.display = "flex";
  overlay.style.alignItems = "center";
  overlay.style.justifyContent = "center";
  overlay.style.zIndex = "1000";

  const container = document.createElement("div");
  container.id = "meld-container";
  container.style.backgroundColor = "#1e1e1e";
  container.style.padding = "20px";
  container.style.borderRadius = "5px";
  container.style.maxWidth = "80vw";
  container.style.maxHeight = "80vh";
  container.style.overflowY = "auto";

  const placeholder = document.createElement("div");
  placeholder.className = "processing-placeholder";
  placeholder.style.fontSize = "18px";
  placeholder.style.textAlign = "center";
  placeholder.innerText = "... processing ...";

  container.appendChild(placeholder);
  overlay.appendChild(container);
  document.body.appendChild(overlay);

  return overlay;
}

// Updates the existing Meld overlay with the diff result and confirmation buttons.
function updateMeldOverlayContent(overlay: HTMLElement, diff: string, file_content: string, file_path: string, meldButton: HTMLButtonElement): void {
  const container = overlay.querySelector("#meld-container") as HTMLElement;
  container.innerHTML = ""; // clear placeholder

  // Diff display with basic formatting and syntax highlighting using hljs (if available)
  const diffPre = document.createElement("pre");
  diffPre.style.backgroundColor = "#2d2d2d";
  diffPre.style.padding = "10px";
  diffPre.style.borderRadius = "3px";
  diffPre.style.overflowX = "auto";
  diffPre.className = "hljs";
  const diffCode = document.createElement("code");
  diffCode.className = "diff";
  diffCode.innerText = diff;
  diffPre.appendChild(diffCode);

  // Create buttons container
  const buttonsDiv = document.createElement("div");
  buttonsDiv.style.marginTop = "10px";
  buttonsDiv.style.textAlign = "right";

  // Accept button
  const acceptButton = document.createElement("button");
  acceptButton.innerText = "Accept";
  acceptButton.style.marginRight = "10px";

  // Reject button
  const rejectButton = document.createElement("button");
  rejectButton.innerText = "Reject";

  buttonsDiv.appendChild(acceptButton);
  buttonsDiv.appendChild(rejectButton);

  container.appendChild(diffPre);
  container.appendChild(buttonsDiv);

  // Accept handler: call /api/apply and disable button on success
  acceptButton.addEventListener("click", async () => {
    try {
      const response = await fetch("/api/apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ "file_content": file_content, "file_path": file_path })
      });
      if (response.ok) {
        alert("Changes applied successfully.");
        meldButton.disabled = true;
      } else {
        const data = await response.json();
        alert("Error applying changes: " + (data.error || response.statusText));
      }
    } catch (err) {
      console.error("Apply API error:", err);
      alert("Error applying changes.");
    }
    document.body.removeChild(overlay);
  });

  // Reject handler: simply remove the overlay.
  rejectButton.addEventListener("click", () => {
    document.body.removeChild(overlay);
  });
}

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

// New code for file selection and tree structure
let selectedFiles: Set<string> = new Set();

function updateSelectedFilesUI(): void {
  const selectedFilesList = document.getElementById("selected-files");
  if (selectedFilesList) {
    selectedFilesList.innerHTML = "";
    selectedFiles.forEach((filePath) => {
      const li = document.createElement("li");
      li.innerText = filePath;
      const removeButton = document.createElement("button");
      removeButton.innerText = "[x]";
      removeButton.style.marginLeft = "10px";
      removeButton.addEventListener("click", () => {
        selectedFiles.delete(filePath);
        const checkbox = document.querySelector(`input[type="checkbox"][data-filepath="${filePath}"]`) as HTMLInputElement;
        if (checkbox) {
          checkbox.checked = false;
        }
        updateSelectedFilesUI();
      });
      li.appendChild(removeButton);
      selectedFilesList.appendChild(li);
    });
  }
}

function buildTreeData(filePaths: string[]): any {
  const tree: any = {};
  filePaths.forEach((filePath) => {
    const parts = filePath.split("/");
    let current = tree;
    parts.forEach((part, index) => {
      if (index === parts.length - 1) {
        current[part] = null;
      } else {
        if (!current[part]) {
          current[part] = {};
        }
        current = current[part];
      }
    });
  });
  return tree;
}

function createTreeElement(tree: any, basePath: string = ""): HTMLElement {
  const ul = document.createElement("ul");
  Object.keys(tree).sort().forEach((key) => {
    const li = document.createElement("li");
    if (tree[key] === null) {
      // Leaf file: add a checkbox and label.
      const fullPath = basePath + key;
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.setAttribute("data-filepath", fullPath);
      checkbox.addEventListener("change", function () {
        if (this.checked) {
          selectedFiles.add(fullPath);
        } else {
          selectedFiles.delete(fullPath);
        }
        updateSelectedFilesUI();
      });
      const label = document.createElement("label");
      label.innerText = key;
      li.appendChild(checkbox);
      li.appendChild(label);
    } else {
      // Folder: show the folder name and recursively build child list.
      const span = document.createElement("span");
      span.innerText = key;
      li.appendChild(span);
      const childUl = createTreeElement(tree[key], basePath + key + "/");
      li.appendChild(childUl);
    }
    ul.appendChild(li);
  });
  return ul;
}

async function fetchProjectContext(): Promise<void> {
  try {
    const response = await fetch("/api/project_context");
    if (response.ok) {
      const data = await response.json();
      const filePaths: string[] = data.file_paths;
      const treeData = buildTreeData(filePaths);
      const treeElement = createTreeElement(treeData);
      const fileBrowser = document.getElementById("file-browser");
      if (fileBrowser) {
        fileBrowser.innerHTML = "";
        fileBrowser.appendChild(treeElement);
      }
    } else {
      console.error("Failed to fetch project context:", response.statusText);
    }
  } catch (error) {
    console.error("Error fetching project context:", error);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  // Load project context tree on page load.
  fetchProjectContext();
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
      // Append a placeholder chat message to indicate processing.
      const chatHistory = document.getElementById("chat-history")!;
      const placeholderDiv = document.createElement("div");
      placeholderDiv.className = "chat-message assistant processing-placeholder";
      placeholderDiv.innerHTML = `<strong>assistant:</strong> ... processing ...`;
      chatHistory.appendChild(placeholderDiv);
  
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
          // The chat placeholder will be replaced via fetchChatHistory.
        }
      } catch (error) {
        console.error("Fetch error:", error);
      }
  
      messageInput.value = ""; // clear the textarea after sending
      autoResize(messageInput);
      await fetchChatHistory(); // update chat history after sending message
    }
  });
  
  // Delegate click events for copy/meld buttons within rendered markdown
  const chatHistory = document.getElementById("chat-history");
  if (chatHistory) {
    chatHistory.addEventListener("click", (event) => {
      const target = event.target as HTMLElement;
      const codeBlock = target.closest(".code-block") as HTMLElement;
      if (!codeBlock) return;
      const fullMarkdown = decodeURIComponent(codeBlock.dataset.fullmarkdown || "");
      if (target.classList.contains("copy-button")) {
        navigator.clipboard.writeText(fullMarkdown)
          .then(() => { alert("Code copied to clipboard"); })
          .catch(err => console.error("Copy failed", err));
      } else if (target.classList.contains("meld-button")) {
        // Retrieve the code block and file path from data attributes.
        const parentBlock = target.closest(".code-block") as HTMLElement;
        const code_block = decodeURIComponent(parentBlock.dataset.codeblock || "");
        const code_filepath = decodeURIComponent(parentBlock.dataset.filepath || "");
  
        // Create the Meld overlay with a placeholder indicator.
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
            console.log("file name: ", code_filepath);
            // Update the existing Meld overlay with the diff and confirmation buttons.
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
  
  // Fetch chat history on page load
  fetchChatHistory();
});
