export function createMeldPlaceholderOverlay(): HTMLElement {
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

export function updateMeldOverlayContent(
  overlay: HTMLElement,
  diff: string,
  file_content: string,
  file_path: string,
  meldButton: HTMLButtonElement
): void {
  const container = overlay.querySelector("#meld-container") as HTMLElement;
  container.innerHTML = "";

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

  const buttonsDiv = document.createElement("div");
  buttonsDiv.style.marginTop = "10px";
  buttonsDiv.style.textAlign = "right";

  const acceptButton = document.createElement("button");
  acceptButton.innerText = "Accept";
  acceptButton.style.marginRight = "10px";

  const rejectButton = document.createElement("button");
  rejectButton.innerText = "Reject";

  buttonsDiv.appendChild(acceptButton);
  buttonsDiv.appendChild(rejectButton);

  container.appendChild(diffPre);
  container.appendChild(buttonsDiv);

  acceptButton.addEventListener("click", async () => {
    try {
      const response = await fetch("/api/apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file_content, file_path })
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

  rejectButton.addEventListener("click", () => {
    document.body.removeChild(overlay);
  });
}
