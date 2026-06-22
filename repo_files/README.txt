REPO SECURITY SCANNER
=====================

ONE COMMAND TO SCAN A REPO:

  python repo_scan.py  <repo_folder>  <tag>

EXAMPLES:
  python repo_scan.py /path/to/myrepo          myproject
  python repo_scan.py .                         current_repo
  python repo_scan.py ~/work/api-service        api_v2

REVERT TOKENS IN BOT RESPONSES:
  python security_revert.py --tag myproject --response-file bot_answer.txt
  python security_revert.py --tag myproject --response "bot said [SSN-0001]…"

─────────────────────────────────────────────────────────

FILES IN THIS FOLDER
  repo_scan.py          ← the one command you run
  security_revert.py    ← restore real values from bot responses
  security_rules.yaml   ← your editable rule book (open and tweak)
  _scanner/             ← internal modules (don't need to touch)
  .gitignore            ← protects scan outputs from being committed

─────────────────────────────────────────────────────────

INSTALL
  pip install pyyaml pathspec detect-secrets

─────────────────────────────────────────────────────────

FULL WORKFLOW

  1.  python repo_scan.py /your/repo  my_tag

  2.  Look in repo_scans/my_tag/
      Read  my_tag_report.txt  before uploading anything

  3.  Upload chunk files to your gov chatbot:
        repo_scans/my_tag/chunks/my_tag_chunk_01_of_N.txt
        repo_scans/my_tag/chunks/my_tag_chunk_02_of_N.txt
        ...

  4.  Get the bot's response.  Save it to a file.

  5.  python security_revert.py --tag my_tag --response-file bot_answer.txt

  ⚠  NEVER upload  my_tag_map.json  to anything.
     It contains all original sensitive values.

─────────────────────────────────────────────────────────

OPTIONS (repo_scan.py)
  --limit       Max chars per chunk        default: 90000
  --rules       security_rules.yaml path  default: ./security_rules.yaml
  --mode        redact (default) | report  report = dry-run, no files changed
  --no-split    Stop after scan, skip chunking
  --max-file-kb Skip files larger than N KB  default: 500

─────────────────────────────────────────────────────────

OUTPUT FILES
  repo_scans/<tag>/
    <tag>_flat.txt          Raw flattened repo  (pre-scan)
    <tag>_clean.txt         Tokenised clean file
    <tag>_report.txt        Security report  ← READ THIS
    <tag>_map.json          Token map  ⚠ NEVER UPLOAD
    .gitignore              Protects sensitive files
    chunks/
      <tag>_chunk_01_of_N.txt   ← upload these
      <tag>_chunk_02_of_N.txt

─────────────────────────────────────────────────────────

EDITING security_rules.yaml
  enabled: false        disable a rule entirely
  suggest_only: true    flag in report, do NOT auto-substitute
  suggest_only: false   auto-substitute with a reversible token
  keep_label: true      for key=value, keep "key=" and token the value
  Add custom rules at the bottom using the template block.

─────────────────────────────────────────────────────────

⚠  USE AT YOUR OWN RISK
   Regex scanning WILL miss things.  Always review the report.
   Never paste raw secrets into any AI chat — gov or commercial.
   Never use on classified or CUI material.
