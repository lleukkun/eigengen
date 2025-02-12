let selectedFiles: Set<string> = new Set();

export function updateSelectedFilesUI(): void {
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

export function buildTreeData(filePaths: string[]): any {
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

export function createTreeElement(tree: any, basePath: string = ""): HTMLElement {
  const ul = document.createElement("ul");
  Object.keys(tree).sort().forEach((key) => {
    const li = document.createElement("li");
    if (tree[key] === null) {
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
      const span = document.createElement("span");
      span.innerText = "[+] " + key;
      span.style.cursor = "pointer";
      const childUl = createTreeElement(tree[key], basePath + key + "/");
      childUl.style.display = "none";
      span.addEventListener("click", () => {
        if (childUl.style.display === "none") {
          childUl.style.display = "block";
          span.innerText = "[-] " + key;
        } else {
          childUl.style.display = "none";
          span.innerText = "[+] " + key;
        }
      });
      li.appendChild(span);
      li.appendChild(childUl);
    }
    ul.appendChild(li);
  });
  return ul;
}

export async function fetchProjectContext(): Promise<void> {
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
