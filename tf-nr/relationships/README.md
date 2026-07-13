<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<title>{{ title }}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/vis-network/9.1.9/vis-network.min.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #0D1117;
    --panel: #161B22;
    --panel-border: #262C36;
    --text: #E6EDF3;
    --muted: #8B949E;
    --accent: #E3A008;
    --accent-soft: #4A3B14;
    --edge: #2DD4BF;
    --danger: #F0625A;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: "IBM Plex Sans", sans-serif;
    font-size: 14px;
    line-height: 1.5;
  }
  header {
    padding: 40px 48px 28px;
    border-bottom: 1px solid var(--panel-border);
  }
  .eyebrow {
    font-family: "IBM Plex Mono", monospace;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--accent);
    font-size: 12px;
    margin-bottom: 10px;
  }
  h1 {
    font-family: "Space Grotesk", sans-serif;
    font-weight: 700;
    font-size: 30px;
    margin: 0 0 6px;
  }
  .meta {
    color: var(--muted);
    font-family: "IBM Plex Mono", monospace;
    font-size: 12.5px;
  }
  .stat-row {
    display: flex;
    gap: 28px;
    margin-top: 22px;
    flex-wrap: wrap;
  }
  .stat {
    border-left: 2px solid var(--accent);
    padding-left: 12px;
  }
  .stat .num {
    font-family: "Space Grotesk", sans-serif;
    font-size: 24px;
    font-weight: 700;
    display: block;
  }
  .stat .label {
    color: var(--muted);
    font-size: 11.5px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }
  main { padding: 32px 48px 64px; }
  section { margin-bottom: 44px; }
  .section-title {
    font-family: "Space Grotesk", sans-serif;
    font-size: 15px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text);
    margin: 0 0 4px;
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .section-title::before {
    content: "";
    width: 8px; height: 8px;
    background: var(--accent);
    display: inline-block;
  }
  .section-sub { color: var(--muted); font-size: 12.5px; margin-bottom: 16px; }

  #graph {
    height: 620px;
    background: var(--panel);
    border: 1px solid var(--panel-border);
    border-radius: 2px;
  }
  .legend {
    display: flex;
    gap: 18px;
    margin-top: 10px;
    flex-wrap: wrap;
    font-family: "IBM Plex Mono", monospace;
    font-size: 11.5px;
    color: var(--muted);
  }
  .legend span.swatch {
    display: inline-block;
    width: 10px; height: 10px;
    border-radius: 50%;
    margin-right: 5px;
    vertical-align: middle;
  }

  table {
    width: 100%;
    border-collapse: collapse;
    background: var(--panel);
    border: 1px solid var(--panel-border);
  }
  th, td {
    text-align: left;
    padding: 9px 14px;
    border-bottom: 1px solid var(--panel-border);
    font-size: 13px;
  }
  th {
    font-family: "IBM Plex Mono", monospace;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    font-size: 11px;
    color: var(--muted);
    font-weight: 500;
  }
  td.mono, code {
    font-family: "IBM Plex Mono", monospace;
    font-size: 12px;
    color: var(--muted);
  }
  tr:last-child td { border-bottom: none; }
  .badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 2px;
    font-family: "IBM Plex Mono", monospace;
    font-size: 11px;
    background: var(--accent-soft);
    color: var(--accent);
  }
  .badge.edge { background: #123A38; color: var(--edge); }
  .badge.aws { background: #2A2410; color: #F5C453; }
  .badge.confidence-exact { background: #123A2A; color: #5FD07A; }
  .badge.confidence-fuzzy { background: #2A2410; color: #F5C453; }
  .badge.confidence-none { background: #3A1616; color: var(--danger); }
  .empty-state {
    color: var(--muted);
    font-style: italic;
    padding: 18px;
    border: 1px dashed var(--panel-border);
    text-align: center;
  }
  footer {
    padding: 24px 48px 40px;
    color: var(--muted);
    font-family: "IBM Plex Mono", monospace;
    font-size: 11.5px;
    border-top: 1px solid var(--panel-border);
  }
</style>
</head>
<body>

<header>
  <div class="eyebrow">NerdGraph Relationship Report</div>
  <h1>{{ title }}</h1>
  <div class="meta">generated {{ generated_at }} &middot; query: <code>{{ query_used }}</code></div>
  <div class="stat-row">
    <div class="stat"><span class="num">{{ nodes|length }}</span><span class="label">Entities</span></div>
    <div class="stat"><span class="num">{{ edges|length }}</span><span class="label">Relationships</span></div>
    <div class="stat"><span class="num">{{ entity_types|length }}</span><span class="label">Entity types</span></div>
    <div class="stat"><span class="num">{{ rel_types|length }}</span><span class="label">Relationship types</span></div>
    {% if suggestions %}
    <div class="stat"><span class="num">{{ suggestions|length }}</span><span class="label">Suggestions</span></div>
    {% endif %}
  </div>
</header>

<main>
  <section>
    <div class="section-title">Relationship map</div>
    <div class="section-sub">Drag to rearrange, scroll to zoom, hover a node for its tags.</div>
    <div id="graph"></div>
    <div class="legend" id="legend"></div>
  </section>

  <section>
    <div class="section-title">Entities</div>
    <div class="section-sub">{{ nodes|length }} entities matched or discovered by traversal.</div>
    {% if nodes %}
    <table>
      <thead><tr><th>Name</th><th>Type</th><th>System</th><th>GUID</th><th>Tags</th></tr></thead>
      <tbody>
        {% for n in nodes %}
        <tr>
          <td>{{ n.name }}</td>
          <td><span class="badge">{{ n.entity_type }}</span></td>
          <td><span class="badge {{ 'aws' if n.system == 'aws' else '' }}">{{ n.system }}</span></td>
          <td class="mono">{{ n.guid }}</td>
          <td class="mono">{% for k, vals in n.tags.items() %}{{ k }}={{ vals|join(',') }} {% endfor %}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    {% else %}
    <div class="empty-state">No entities matched this query.</div>
    {% endif %}
  </section>

  <section>
    <div class="section-title">Relationships</div>
    <div class="section-sub">{{ edges|length }} edges across {{ rel_types|length }} relationship type(s).</div>
    {% if edges %}
    <table>
      <thead><tr><th>Type</th><th>Source</th><th>Target</th></tr></thead>
      <tbody>
        {% for e in edges %}
        <tr>
          <td><span class="badge edge">{{ e.type }}</span></td>
          <td>{{ node_names.get(e.source, e.source) }}</td>
          <td>{{ node_names.get(e.target, e.target) }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    {% else %}
    <div class="empty-state">No relationships found among these entities.</div>
    {% endif %}
  </section>

  {% if aws_matches %}
  <section>
    <div class="section-title">Cross-system matches (AWS &harr; New Relic)</div>
    <div class="section-sub">
      {{ aws_matches|selectattr('confidence', 'equalto', 'none')|list|length }} unmatched --
      review these first, since a naming mismatch here means the relationship report above is missing an edge.
    </div>
    <table>
      <thead><tr><th>Confidence</th><th>AWS kind</th><th>AWS resource</th><th>Matched New Relic entity</th><th>Score</th><th>Matched on</th></tr></thead>
      <tbody>
        {% for m in aws_matches %}
        <tr>
          <td><span class="badge confidence-{{ m.confidence }}">{{ m.confidence }}</span></td>
          <td class="mono">{{ m.aws_kind }}</td>
          <td>{{ m.aws_id }}</td>
          <td>{{ m.nr_name or '—' }}</td>
          <td class="mono">{{ m.score }}</td>
          <td class="mono">{{ m.matched_on }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </section>
  {% endif %}

  {% if suggestions %}
  <section>
    <div class="section-title">Suggested relationships</div>
    <div class="section-sub">Heuristic, tag-based suggestions -- review before turning into a change plan.</div>
    <table>
      <thead><tr><th>Confidence</th><th>Source</th><th>Target</th><th>Suggested type</th><th>Reason</th></tr></thead>
      <tbody>
        {% for s in suggestions %}
        <tr>
          <td><span class="badge">{{ s.confidence }}</span></td>
          <td>{{ s.source_name }}</td>
          <td>{{ s.target_name }}</td>
          <td class="mono">{{ s.suggested_type }}</td>
          <td>{{ s.reason }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </section>
  {% endif %}
</main>

<footer>
  Generated by nr-rel. Nothing on this page was written back to New Relic --
  this is a read-only report. Use `nr-rel plan-add` / `plan-remove` and
  `nr-rel apply` to make changes, after review.
</footer>

<script>
  const graphData = {{ graph_json|safe }};

  const typeColors = {};
  const palette = ["#E3A008", "#2DD4BF", "#F0625A", "#7C8CF8", "#B984E8", "#5FD07A", "#F2A6C1"];
  let colorIdx = 0;
  function colorFor(type) {
    if (!(type in typeColors)) {
      typeColors[type] = palette[colorIdx % palette.length];
      colorIdx += 1;
    }
    return typeColors[type];
  }

  const nodes = new vis.DataSet(graphData.nodes.map(n => ({
    id: n.guid,
    label: n.name,
    title: Object.entries(n.tags || {}).map(([k,v]) => `${k}: ${v.join(', ')}`).join('\\n') || n.entity_type,
    color: { background: colorFor(n.entity_type), border: n.system === 'aws' ? '#F5C453' : "#0D1117" },
    font: { color: "#0D1117", face: "IBM Plex Mono", size: 12 },
    shape: n.system === 'aws' ? 'box' : 'dot',
    size: 14,
  })));

  const confidenceColors = { exact: "#5FD07A", fuzzy: "#F5C453", none: "#F0625A" };
  const edges = new vis.DataSet(graphData.edges.map(e => {
    const isMatch = e.type === "AWS_MATCH";
    const conf = isMatch ? (e.metadata && e.metadata.confidence) : null;
    return {
      from: e.source, to: e.target, label: e.type,
      arrows: "to",
      color: { color: isMatch ? (confidenceColors[conf] || "#8B949E") : "#2DD4BF", opacity: 0.55 },
      dashes: isMatch,
      font: { color: "#8B949E", size: 10, face: "IBM Plex Mono", strokeWidth: 0, background: "#0D1117" },
      smooth: { type: "dynamic" },
    };
  }));

  const container = document.getElementById('graph');
  const network = new vis.Network(container, { nodes, edges }, {
    physics: { stabilization: true, barnesHut: { gravitationalConstant: -3000, springLength: 140 } },
    interaction: { hover: true },
  });

  const legend = document.getElementById('legend');
  Object.entries(typeColors).forEach(([type, color]) => {
    const el = document.createElement('span');
    el.innerHTML = `<span class="swatch" style="background:${color}"></span>${type}`;
    legend.appendChild(el);
  });
</script>

</body>
</html>
