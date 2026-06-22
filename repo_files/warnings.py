"""
_scanner/warnings.py — Security disclaimers shared across all modules.
Never run directly.
"""

import os
import sys


def _colour():
    if os.name == "nt":
        return False
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


C      = _colour()
RED    = "\033[91m" if C else ""
YELLOW = "\033[93m" if C else ""
BOLD   = "\033[1m"  if C else ""
RESET  = "\033[0m"  if C else ""


STARTUP_BANNER = f"""{RED}{BOLD}
╔══════════════════════════════════════════════════════════════════════════╗
║            ⚠   REPO SECURITY SCANNER — READ BEFORE PROCEEDING   ⚠       ║
╠══════════════════════════════════════════════════════════════════════════╣
║                                                                          ║
║  USE AT YOUR OWN RISK.                                                   ║
║                                                                          ║
║  This tool attempts to find and substitute sensitive data before you     ║
║  share code with an AI assistant.  It is NOT a guarantee that all        ║
║  sensitive data will be detected or removed.  Regex-based scanning       ║
║  WILL miss things.                                                       ║
║                                                                          ║
║  YOUR RESPONSIBILITIES:                                                  ║
║    • Review the security report BEFORE uploading any chunk files.        ║
║    • Never upload the substitution map (_map.json) to any AI tool.       ║
║    • Never copy/paste raw secrets, passwords, keys, SSNs, or any         ║
║      sensitive data directly into ANY AI chat — gov or otherwise.        ║
║    • You are responsible for what you upload.                            ║
║                                                                          ║
║  THIS TOOL DOES NOT PROVIDE:                                             ║
║    • Compliance with HIPAA, PCI-DSS, FISMA, FedRAMP, or any framework.  ║
║    • A guarantee of complete PII or secret removal.                      ║
║    • Authorisation to share data with any specific system.               ║
║                                                                          ║
║  CLASSIFIED / CUI MATERIAL:                                              ║
║    NEVER run this tool on classified or Controlled Unclassified          ║
║    Information (CUI).  No scrubber makes classified data safe to share.  ║
║                                                                          ║
╚══════════════════════════════════════════════════════════════════════════╝
{RESET}"""


COMPLETION_BANNER = f"""{YELLOW}{BOLD}
┌──────────────────────────────────────────────────────────────────────────┐
│  ⚠  BEFORE YOU UPLOAD — FINAL CHECKLIST                                  │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  □  Open *_report.txt and read it fully — especially section 5.          │
│  □  Spot-check *_clean.txt for anything the scanner may have missed.     │
│  □  Confirm *_map.json is NOT in your upload set.                        │
│  □  Confirm you are not uploading classified or CUI material.            │
│  □  Confirm the target system is approved for this data classification.  │
│                                                                           │
│  NEVER paste raw secrets into any AI chat — government or commercial.    │
│  IF IN DOUBT — DON'T UPLOAD.  Ask your security officer first.           │
│                                                                           │
│  USE AT YOUR OWN RISK.  Provided as-is with no warranty.                 │
└──────────────────────────────────────────────────────────────────────────┘
{RESET}"""


REVERT_BANNER = f"""{YELLOW}{BOLD}
╔══════════════════════════════════════════════════════════════════════════╗
║  ⚠  REVERT TOOL — OUTPUT CONTAINS REAL SENSITIVE DATA                   ║
╠══════════════════════════════════════════════════════════════════════════╣
║  • The output of this script restores ORIGINAL sensitive values.         ║
║  • Do NOT paste the reverted output into any AI chat system.             ║
║  • Handle reverted output with the same care as the original repo.       ║
║  • Never share *_map.json with anyone or any system.                     ║
║  • USE AT YOUR OWN RISK.                                                 ║
╚══════════════════════════════════════════════════════════════════════════╝
{RESET}"""


FILE_FOOTER = """

================================================================================
  SECURITY DISCLAIMER — READ BEFORE SHARING OR UPLOADING
================================================================================
  This file was produced by an automated security scrubbing tool.
  USE AT YOUR OWN RISK.

  • The tool attempts to detect and substitute PII, keys, secrets, and
    credentials using regex patterns.  It does NOT guarantee complete removal.
  • Review the *_report.txt for items flagged for manual review.
  • Manually inspect this file for anything the scanner may have missed.
  • NEVER paste raw passwords, API keys, SSNs, or any sensitive data
    directly into any AI chat system — government or commercial.
  • NEVER upload the *_map.json substitution file to any AI tool or chat.
  • This tool does not provide regulatory or legal compliance.
  • NEVER use on classified or Controlled Unclassified Information (CUI).

  The person who ran this scan is responsible for what they upload.
================================================================================
"""


REPORT_DISCLAIMER = """
================================================================================
  DISCLAIMER & LIMITATIONS
================================================================================
  Generated by an automated tool.  USE AT YOUR OWN RISK.

  WHAT THIS TOOL DOES:
    Applies regex and heuristic patterns to find and replace common forms of
    PII, secrets, keys, and credentials with reversible numbered tokens.

  WHAT THIS TOOL DOES NOT DO:
    - Guarantee complete removal of all sensitive data.
    - Understand context — a test fixture value gets treated the same as a
      real secret.
    - Detect novel, obfuscated, or encoded credential formats.
    - Provide compliance with HIPAA, PCI-DSS, FISMA, FedRAMP, or any other
      regulatory or security framework.
    - Authorise you to share any data with any particular system.
    - Make classified or CUI data safe to share.  Ever.

  YOUR OBLIGATIONS:
    - Read section 5 (Manual Review Flags) carefully before uploading.
    - Manually inspect the clean file before uploading.
    - Confirm the target system is approved for your data classification.
    - Never paste raw sensitive data into any AI chat.
    - Keep *_map.json secure and local — never upload it.
    - You are responsible for what you upload.

  NEVER run this tool on classified or Controlled Unclassified Information.
================================================================================
"""


def print_startup():
    print(STARTUP_BANNER)


def print_stage(label: str):
    print(f"\n{YELLOW}{BOLD}[{label}]{RESET}{YELLOW}  "
          f"Never paste raw secrets into any AI chat.{RESET}\n")


def print_completion():
    print(COMPLETION_BANNER)
