# PR Agent

PR Agent is a small toolkit that generates Word (.docx) reports from GitHub pull requests and recorded merge events. It includes a Streamlit UI for interactive report generation and two document generators:

- A PR report generator (doc_generator.py) that turns a list of PR metadata + AI analysis into a nicely formatted .docx report.
- A merge-events generator (merge_agent/doc_generator.py) that rewrites a complete merge history document from the stored merge log (merge_agent/logs/merge-log.json).

This README was previously a placeholder. The repository now contains the code listed below — use the examples to generate reports.

## Components

- app.py
  - Streamlit UI. Start the interactive app with:
    
    streamlit run app.py

- doc_generator.py
  - Generates a PR report document from a list of PR dicts and an AI analysis dict.
  - Public API: generate(pr_data_list, analysis, repo, output_path)
  - Requires: python-docx
    
    pip install python-docx

  - Example usage from Python:

    from doc_generator import generate
    # pr_data_list : list of PR dicts (cleaned)
    # analysis : dict containing AI analysis and pr_summaries
    generate(pr_data_list, analysis, "owner/repo", "pr-report.docx")

- merge_agent/doc_generator.py
  - Builds a consolidated "Merge Events Report" from recorded merge events.
  - Public API: generate(all_events: list, repo: str, output_path: str = None)
  - By default it writes to merge_agent/logs/merge-events-report.docx
  - The generator expects data shaped like the repository's merge log (see merge_agent/logs/merge-log.json).

## Logs

- merge_agent/logs/merge-log.json
  - Stores recorded merge events used by the merge-agent doc generator. The merge-agent doc generator rewrites the full report from this log so it always reflects the current history.

## Notes

- The repository contains two separate doc generators (PR vs merge-events) so both formats can coexist.
- If you add or change the structure of PR/merge event dicts, update the corresponding generator to keep the produced documents accurate.

