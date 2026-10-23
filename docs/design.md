# Design

```mermaid
flowchart LR
  subgraph Data
    S[MMMLU + MT-Bench<br/>scripts/fetch_sources.py] --> D[drafts YAML<br/>4 forms per item]
    D --> B[build_pilot.py<br/>word counts, NFC]
    B --> Q[(quadruples.jsonl)]
    Q <-->|qc export / import| H[Hindi-fluent checkers]
    Q --> C{data-check<br/>qc.passed only}
  end
  subgraph Runs
    C --> P[runners plan CallSpecs<br/>E1 pointwise, E2/E3 pairwise AB+BA]
    P --> BU[budget.py<br/>needs --yes]
    BU --> J[Judge.score / compare]
    J <--> K[(cache<br/>sha256 model+prompt+inputs)]
    J --> PR[providers<br/>OpenAI-compatible: Gemini, Groq, Ollama]
    J --> R[(results/raw/*.jsonl<br/>one line per call)]
  end
  subgraph Outputs
    R --> ST[stats.py<br/>bootstrap, Wilcoxon, Wilson, kappa, Holm]
    ST --> T[(results/tables/*.csv)]
    T --> L[report/tables LaTeX]
    T --> TH[(thresholds.json)]
    TH --> APP[Gradio app<br/>demo = cached replay]
  end
```

Key guarantees

- **No invented outputs.** Numbers come only from `results/raw` → `stats.py` → `results/tables`.
- **Cache-first.** Every call is keyed by sha256(model, full prompt, {temperature, attempt}). A hit never
  calls the provider; `--offline` turns a miss into an error, which is how `make reproduce` and the app's
  demo mode stay network-free.
- **Budget gate.** Runners enumerate the exact calls, print new vs cached counts, and stop without `--yes`.
- **Order control.** Every pairwise comparison runs AB and BA; both are stored.
- **Self-preference guard.** The drafting model is refused as a judge.
- **UTF-8 everywhere.** Files are opened with `encoding="utf-8"`; QC sheets use a BOM for Excel.
