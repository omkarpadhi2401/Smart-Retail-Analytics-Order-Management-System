/* Chart helpers — one consistent look for every chart (Chart.js, bundled locally) */
(function () {
  const C = { blue: '#2a78d6', orange: '#eb6834', aqua: '#1baf7a', yellow: '#eda100', magenta: '#e87ba4',
              green: '#008300', violet: '#4a3aa7', red: '#e34948', grey: '#b7bdc9', good: '#0ca30c', bad: '#d03b3b' };
  const ORDER = [C.blue, C.orange, C.aqua, C.yellow, C.magenta, C.green, C.violet, C.red];

  Chart.defaults.font.family = '"Inter","Segoe UI",system-ui,Arial,sans-serif';
  Chart.defaults.font.size = 12;
  Chart.defaults.color = '#667085';
  Chart.defaults.plugins.legend.position = 'bottom';
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.plugins.legend.labels.boxWidth = 8;
  Chart.defaults.plugins.legend.labels.boxHeight = 8;
  Chart.defaults.plugins.tooltip.backgroundColor = '#101828';
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.plugins.tooltip.cornerRadius = 8;
  Chart.defaults.maintainAspectRatio = false;
  Chart.defaults.animation.duration = 350;

  function rupee(v) {
    const a = Math.abs(v), s = v < 0 ? '-' : '';
    if (a >= 1e7) return s + '₹' + (a / 1e7).toFixed(2) + ' Cr';
    if (a >= 1e5) return s + '₹' + (a / 1e5).toFixed(2) + ' L';
    if (a >= 1e3) return s + '₹' + (a / 1e3).toFixed(1) + 'K';
    return s + '₹' + Math.round(a);
  }
  function fmt(kind) {
    return function (v) {
      if (v === null || v === undefined) return '';
      if (kind === 'money') return rupee(v);
      if (kind === 'pct') return (+v).toFixed(1) + '%';
      return (+v).toLocaleString('en-IN');
    };
  }
  function scales(kind, horizontal, stacked) {
    const val = { beginAtZero: true, stacked: !!stacked, grid: { color: '#eef0f4' }, border: { display: false },
                  ticks: { callback: fmt(kind), maxTicksLimit: 6 } };
    const cat = { stacked: !!stacked, grid: { display: false }, border: { color: '#e4e7ec' } };
    return horizontal ? { x: val, y: cat } : { x: cat, y: val };
  }
  function tooltip(kind) {
    return { callbacks: { label: function (c) {
      const v = c.chart.options.indexAxis === 'y' ? c.parsed.x : c.parsed.y;
      return ' ' + (c.dataset.label ? c.dataset.label + ': ' : '') + fmt(kind)(v);
    } } };
  }
  function el(id) { return document.getElementById(id); }

  const EXP = ['Rent', 'Salaries', 'Utilities', 'Marketing', 'Inventory Purchase', 'Transportation', 'Operations', 'Miscellaneous'];
  window.BI = {
    C: C,
    /* fixed colour per expense category, so a category looks the same on every chart */
    expColor: function (name) { const i = EXP.indexOf(name); return i < 0 ? C.grey : ORDER[i]; },
    /* series: [{label, data, color, dash}] */
    line: function (id, labels, series, kind) {
      if (!el(id)) return;
      return new Chart(el(id), { type: 'line',
        data: { labels: labels, datasets: series.map(function (s, i) {
          const col = s.color || ORDER[i];
          return { label: s.label, data: s.data, borderColor: col, backgroundColor: col, borderWidth: 2,
                   borderDash: s.dash ? [6, 4] : [], pointRadius: s.dash ? 2.5 : 3, pointHoverRadius: 5,
                   pointBackgroundColor: '#fff', pointBorderWidth: 2, tension: 0.25, spanGaps: false };
        }) },
        options: { interaction: { mode: 'index', intersect: false }, scales: scales(kind),
                   plugins: { legend: { display: series.length > 1 }, tooltip: tooltip(kind) } } });
    },
    /* opts: {kind, horizontal, stacked, signed} */
    bar: function (id, labels, series, opts) {
      if (!el(id)) return;
      opts = opts || {};
      return new Chart(el(id), { type: 'bar',
        data: { labels: labels, datasets: series.map(function (s, i) {
          const col = s.color || ORDER[i];
          return { label: s.label, data: s.data, borderRadius: 4, maxBarThickness: 34,
                   borderWidth: opts.stacked ? 1 : 0, borderColor: '#fff',
                   backgroundColor: opts.signed ? s.data.map(function (v) { return v < 0 ? C.orange : col; }) : col };
        }) },
        options: { indexAxis: opts.horizontal ? 'y' : 'x', interaction: { mode: 'index', intersect: false },
                   scales: scales(opts.kind, opts.horizontal, opts.stacked),
                   plugins: { legend: { display: series.length > 1 }, tooltip: tooltip(opts.kind) } } });
    },
    donut: function (id, labels, data, kind, colors) {
      if (!el(id)) return;
      const total = data.reduce(function (a, b) { return a + b; }, 0);
      return new Chart(el(id), { type: 'doughnut',
        data: { labels: labels, datasets: [{ data: data, backgroundColor: colors || ORDER, borderColor: '#fff', borderWidth: 2 }] },
        options: { cutout: '62%', plugins: { legend: { position: 'right' },
          tooltip: { callbacks: { label: function (c) {
            return ' ' + c.label + ': ' + fmt(kind)(c.parsed) + ' (' + (c.parsed / total * 100).toFixed(1) + '%)';
          } } } } } });
    }
  };
})();
