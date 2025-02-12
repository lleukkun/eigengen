import MarkdownIt from "markdown-it";
import hljs from "highlight.js";
import "highlight.js/styles/atom-one-dark.css";

const md = new MarkdownIt();

function highlight(str: string, lang: string): string {
  const language = lang?.split(";")[0];
  if (language && hljs.getLanguage(language)) {
    try {
      return `<pre class="hljs"><code>${hljs.highlight(str, { language }).value}</code></pre>`;
    } catch { }
  }
  return `<pre class="hljs"><code>${md.utils.escapeHtml(str)}</code></pre>`;
}

md.options.highlight = highlight;

md.renderer.rules.fence = function (tokens, idx, options, env, self) {
  const token = tokens[idx];
  const info = token.info ? token.info.trim() : "";
  const parts = info.split(";");
  const filePathProvided = parts[1] && parts[1].trim().length > 0;
  const fileName = filePathProvided ? parts[1].trim() : "code";
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

export { md };
