/* static/ai.js — Shared AI Assistant & Explain features */
(function () {
  'use strict';

  function escapeHtml(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function inlineFormat(text) {
    // inline code `code`
    text = text.replace(/`([^`]+)`/g, '<code>$1</code>');
    // bold **bold**
    text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    // italic *italic*
    text = text.replace(/\*([^*]+)\*/g, '<em>$1</em>');
    return text;
  }

  function renderMarkdown(rawText) {
    if (!rawText) return '';
    const escaped = escapeHtml(rawText);
    const lines = escaped.split(/\r?\n/);
    const out = [];
    let inUl = false;
    let inOl = false;
    let inTable = false;
    let tableHasHeader = false;

    function closeLists() {
      if (inUl) { out.push('</ul>'); inUl = false; }
      if (inOl) { out.push('</ol>'); inOl = false; }
    }

    function closeTable() {
      if (inTable) { out.push('</tbody></table></div>'); inTable = false; tableHasHeader = false; }
    }

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();
      if (!line) {
        closeLists();
        closeTable();
        continue;
      }

      // Table row detection (| col | col |)
      if (line.startsWith('|') && line.endsWith('|')) {
        closeLists();
        // Check if it is a separator row like |---|---|
        if (/^\|(\s*:?-+:?\s*\|)+$/.test(line)) {
          continue; // skip delimiter row
        }
        const cells = line.slice(1, -1).split('|').map(c => c.trim());
        if (!inTable) {
          inTable = true;
          tableHasHeader = true;
          out.push('<div class="table-wrap" style="margin:8px 0"><table class="tight"><thead><tr>');
          cells.forEach(c => out.push('<th>' + inlineFormat(c) + '</th>'));
          out.push('</tr></thead><tbody>');
        } else {
          out.push('<tr>');
          cells.forEach(c => out.push('<td>' + inlineFormat(c) + '</td>'));
          out.push('</tr>');
        }
        continue;
      } else {
        closeTable();
      }

      // Headings
      if (line.startsWith('### ')) {
        closeLists();
        out.push('<h5>' + inlineFormat(line.slice(4)) + '</h5>');
        continue;
      }
      if (line.startsWith('## ')) {
        closeLists();
        out.push('<h4>' + inlineFormat(line.slice(3)) + '</h4>');
        continue;
      }
      if (line.startsWith('# ')) {
        closeLists();
        out.push('<h3>' + inlineFormat(line.slice(2)) + '</h3>');
        continue;
      }

      // Unordered list
      const ulMatch = line.match(/^[-*]\s+(.*)$/);
      if (ulMatch) {
        if (inOl) { out.push('</ol>'); inOl = false; }
        if (!inUl) { out.push('<ul>'); inUl = true; }
        out.push('<li>' + inlineFormat(ulMatch[1]) + '</li>');
        continue;
      }

      // Ordered list
      const olMatch = line.match(/^(\d+)\.\s+(.*)$/);
      if (olMatch) {
        if (inUl) { out.push('</ul>'); inUl = false; }
        if (!inOl) { out.push('<ol>'); inOl = true; }
        out.push('<li>' + inlineFormat(olMatch[2]) + '</li>');
        continue;
      }

      // Regular paragraph
      closeLists();
      out.push('<p>' + inlineFormat(line) + '</p>');
    }
    closeLists();
    closeTable();
    return out.join('');
  }

  async function postJson(url, data) {
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      body: JSON.stringify(data || {})
    });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) {
      const err = new Error(json.error || `HTTP ${res.status}: Failed request`);
      err.code = json.code;
      err.status = res.status;
      throw err;
    }
    return json;
  }

  function showInlineBox(container, title, contentHtml, isError) {
    if (typeof container === 'string') {
      container = document.getElementById(container);
    }
    if (!container) return;
    container.style.display = 'block';
    container.innerHTML = `
      <div class="ai-inline-panel ${isError ? 'error' : ''}">
        <div class="ai-inline-header">
          <span class="ai-inline-title">
            <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8z"/></svg>
            ${escapeHtml(title)}
          </span>
          <button type="button" class="ai-inline-close" onclick="this.closest('.ai-inline-panel').parentElement.style.display='none'">&times;</button>
        </div>
        <div class="ai-inline-body">${contentHtml}</div>
      </div>
    `;
    container.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function showLoadingBox(container, title) {
    showInlineBox(container, title, '<div class="ai-loading-spinner"><span class="dot-flashing"></span> Analyzing business data with AI...</div>', false);
  }

  window.AI = {
    escapeHtml: escapeHtml,
    renderMarkdown: renderMarkdown,
    postJson: postJson,

    explainAnomaly: async function (expenseId, btn) {
      const tr = btn.closest('tr');
      if (!tr) return;
      const nextRow = tr.nextElementSibling;
      if (nextRow && nextRow.classList.contains('ai-explain-row')) {
        nextRow.remove();
        return;
      }
      // Create new tr
      const colCount = tr.children.length;
      const newTr = document.createElement('tr');
      newTr.className = 'ai-explain-row';
      newTr.innerHTML = `
        <td colspan="${colCount}" style="padding:10px 14px;background:#f8faff;border-left:3px solid var(--brand);">
          <div class="ai-anomaly-box">
            <div class="ai-loading-spinner"><span class="dot-flashing"></span> Explaining anomaly with AI...</div>
          </div>
        </td>
      `;
      tr.after(newTr);
      const box = newTr.querySelector('.ai-anomaly-box');

      try {
        btn.disabled = true;
        const res = await postJson(`/ai/explain/anomaly/${expenseId}`, {});
        const html = renderMarkdown(res.answer);
        box.innerHTML = `
          <div class="ai-explain-header">
            <strong>AI Anomaly Analysis</strong>
            <button type="button" class="btn ghost sm" onclick="this.closest('tr').remove()">Close</button>
          </div>
          <div class="ai-markdown-content">${html}</div>
        `;
      } catch (err) {
        box.innerHTML = `
          <div class="ai-explain-header">
            <strong style="color:var(--bad)">Analysis Error</strong>
            <button type="button" class="btn ghost sm" onclick="this.closest('tr').remove()">Close</button>
          </div>
          <div class="ai-error-msg">${escapeHtml(err.message)}</div>
        `;
      } finally {
        btn.disabled = false;
      }
    },

    explainForecast: async function (productId, containerId) {
      const container = document.getElementById(containerId);
      if (!container) return;
      showLoadingBox(container, 'Demand Forecast AI Explanation');
      try {
        const res = await postJson(`/ai/explain/forecast/${productId}`, {});
        showInlineBox(container, 'Demand Forecast AI Explanation', `<div class="ai-markdown-content">${renderMarkdown(res.answer)}</div>`);
      } catch (err) {
        showInlineBox(container, 'Demand Forecast AI Explanation', `<div class="ai-error-msg">${escapeHtml(err.message)}</div>`, true);
      }
    },

    explainHealth: async function (containerId) {
      const container = document.getElementById(containerId);
      if (!container) return;
      showLoadingBox(container, 'Financial Health Score AI Explanation');
      try {
        const res = await postJson('/ai/explain/health', {});
        showInlineBox(container, 'Financial Health Score AI Explanation', `<div class="ai-markdown-content">${renderMarkdown(res.answer)}</div>`);
      } catch (err) {
        showInlineBox(container, 'Financial Health Score AI Explanation', `<div class="ai-error-msg">${escapeHtml(err.message)}</div>`, true);
      }
    },

    getSummary: async function (containerId) {
      const container = document.getElementById(containerId);
      if (!container) return;
      showLoadingBox(container, 'AI Executive Business Summary');
      try {
        const res = await postJson('/ai/summary', {});
        showInlineBox(container, 'AI Executive Business Summary', `<div class="ai-markdown-content">${renderMarkdown(res.answer)}</div>`);
      } catch (err) {
        showInlineBox(container, 'AI Executive Business Summary', `<div class="ai-error-msg">${escapeHtml(err.message)}</div>`, true);
      }
    },

    getRecommendations: async function (containerId) {
      const container = document.getElementById(containerId);
      if (!container) return;
      showLoadingBox(container, 'AI Strategic Recommendations');
      try {
        const res = await postJson('/ai/recommendations', {});
        showInlineBox(container, 'AI Strategic Recommendations', `<div class="ai-markdown-content">${renderMarkdown(res.answer)}</div>`);
      } catch (err) {
        showInlineBox(container, 'AI Strategic Recommendations', `<div class="ai-error-msg">${escapeHtml(err.message)}</div>`, true);
      }
    }
  };
})();
