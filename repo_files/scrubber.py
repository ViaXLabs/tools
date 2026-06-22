"""
_scanner/scrubber.py — Stage 2: rule-driven tokenisation and security report.
"""

import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import yaml
except ImportError:
    print("[ERROR] pip install pyyaml")
    sys.exit(1)

try:
    from detect_secrets import SecretsCollection
    from detect_secrets.settings import default_settings
    HAS_DS = True
except ImportError:
    HAS_DS = False

from _scanner.warnings import FILE_FOOTER, REPORT_DISCLAIMER


# ── data structures ───────────────────────────────────────────────────────────

@dataclass
class Rule:
    name:         str
    category:     str
    description:  str
    pattern:      str
    enabled:      bool   = True
    suggest_only: bool   = False
    luhn_check:   bool   = False
    keep_label:   bool   = False
    multiline:    bool   = False
    notes:        str    = ""
    compiled:     object = field(default=None, repr=False)

    def compile(self):
        flags = re.DOTALL | re.MULTILINE if self.multiline else re.MULTILINE
        self.compiled = re.compile(self.pattern, flags)


@dataclass
class Finding:
    rule_name:    str
    category:     str
    source_file:  str
    line_no:      int
    original:     str
    token:        str
    context:      str
    suggest_only: bool


class TokenRegistry:
    """
    Bidirectional map: original_value ↔ unique token  [RULENAME-NNNN].
    Same value always gets the same token (deduplication).
    """
    def __init__(self):
        self._o2t: dict[str, str] = {}
        self._t2o: dict[str, str] = {}
        self._ctr: dict[str, int] = {}

    def get_or_create(self, rule: str, value: str) -> str:
        if value in self._o2t:
            return self._o2t[value]
        n = self._ctr.get(rule, 0) + 1
        self._ctr[rule] = n
        token = f"[{rule}-{n:04d}]"
        self._o2t[value] = token
        self._t2o[token] = value
        return token

    def to_dict(self) -> dict:
        return {
            "token_to_original": self._t2o,
            "original_to_token": self._o2t,
            "summary": dict(sorted(self._ctr.items())),
        }

    @property
    def total(self) -> int:
        return len(self._t2o)


# ── helpers ───────────────────────────────────────────────────────────────────

def _luhn(number: str) -> bool:
    digits = [int(c) for c in number if c.isdigit()]
    if len(digits) < 13:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _clip(s: str, n: int = 120) -> str:
    return s[:n] + " …" if len(s) > n else s


# ── rule loader ───────────────────────────────────────────────────────────────

def load_rules(path: Path) -> list[Rule]:
    if not path.exists():
        print(f"[ERROR] Rules file not found: {path}")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    rules = []
    for e in data.get("rules", []):
        if not e.get("enabled", True):
            continue
        r = Rule(
            name         = e["name"],
            category     = e.get("category", "UNKNOWN"),
            description  = e.get("description", ""),
            pattern      = e["pattern"],
            suggest_only = e.get("suggest_only", False),
            luhn_check   = e.get("luhn_check", False),
            keep_label   = e.get("keep_label", False),
            multiline    = e.get("multiline", False),
            notes        = e.get("notes", ""),
        )
        try:
            r.compile()
            rules.append(r)
        except re.error as ex:
            print(f"  [WARN] Rule '{r.name}' bad regex — skipped ({ex})")
    return rules


# ── core scrub ────────────────────────────────────────────────────────────────

def _apply(rule: Rule, line: str, line_no: int, src: str,
           reg: TokenRegistry, findings: list) -> str:

    def record(original, token):
        findings.append(Finding(
            rule_name=rule.name, category=rule.category,
            source_file=src, line_no=line_no,
            original=_clip(original), token=token,
            context=_clip(line.strip(), 160),
            suggest_only=rule.suggest_only,
        ))

    def replacer(m: re.Match) -> str:
        full = m.group(0)
        if rule.luhn_check and not _luhn(re.sub(r"\D", "", full)):
            return full
        if rule.keep_label:
            try:
                try:
                    label, value = m.group("label"), m.group("value")
                except IndexError:
                    label, value = m.group(1), m.group(2)
                tok = reg.get_or_create(rule.name, value)
                record(value, tok)
                return label + tok if not rule.suggest_only else full
            except (IndexError, AttributeError):
                pass
        tok = reg.get_or_create(rule.name, full)
        record(full, tok)
        return tok if not rule.suggest_only else full

    return rule.compiled.sub(replacer, line)


def scrub(text: str, rules: list[Rule], reg: TokenRegistry):
    findings = []
    lines = text.split("\n")

    for rule in rules:
        if rule.multiline:
            continue
        cur = "(header)"
        for i in range(len(lines)):
            if lines[i].startswith("FILE:"):
                cur = lines[i][5:].strip()
            lines[i] = _apply(rule, lines[i], i + 1, cur, reg, findings)

    text = "\n".join(lines)

    for rule in rules:
        if not rule.multiline:
            continue
        def ml_replacer(m, _r=rule):
            full = m.group(0)
            ln = text[:m.start()].count("\n") + 1
            tok = reg.get_or_create(_r.name, full)
            findings.append(Finding(
                rule_name=_r.name, category=_r.category,
                source_file="(multi-line block)", line_no=ln,
                original=_clip(full), token=tok,
                context="(spans multiple lines)",
                suggest_only=_r.suggest_only,
            ))
            return tok if not _r.suggest_only else full
        text = rule.compiled.sub(ml_replacer, text)

    return text, findings


def _detect_secrets(path: Path) -> list[dict]:
    if not HAS_DS:
        return []
    out = []
    try:
        with default_settings():
            sc = SecretsCollection()
            sc.scan_file(str(path))
        for _, sset in sc:
            for s in sset:
                out.append({
                    "rule_name": f"detect-secrets:{s.type}",
                    "category": "SECRETS",
                    "source_file": str(path),
                    "line_no": s.line_number,
                    "original": "(hidden by detect-secrets)",
                    "token": "(manual review required)",
                    "context": f"Line {s.line_number}",
                    "suggest_only": True,
                })
    except Exception as e:
        out.append({"rule_name": "detect-secrets:ERROR", "category": "ERROR",
                    "source_file": "", "line_no": 0, "original": str(e),
                    "token": "", "context": "", "suggest_only": True})
    return out


# ── report ────────────────────────────────────────────────────────────────────

def _report(findings, ds_findings, rules, reg, in_p, out_p, map_p,
            mode, cb, ca, tag, run_time):
    W = 72
    D = "=" * W

    auto_f    = [f for f in findings if not f.suggest_only]
    suggest_f = [f for f in findings if f.suggest_only]

    def hdr(n, t):
        return [D, f"  {n}. {t}", D, ""]

    L = []

    # cover
    L += [
        D,
        f"  SECURITY SCAN REPORT  —  {tag}",
        D,
        f"  Generated      : {run_time}",
        f"  Mode           : {mode}",
        f"  Input          : {in_p}",
        f"  Clean file     : {out_p or '(report mode — not written)'}",
        f"  Subst. map     : {map_p}  ⚠ NEVER UPLOAD THIS FILE",
        f"  Chars in       : {cb:,}",
        f"  Chars out      : {ca:,}  (delta: {cb-ca:,})",
        f"  Unique tokens  : {reg.total}",
        D, "",
    ]

    # 1. executive summary
    L += hdr(1, "EXECUTIVE SUMMARY")
    total_a = len(auto_f)
    total_s = len(suggest_f) + len(ds_findings)
    L += [
        f"  Total findings             : {total_a + total_s}",
        f"  Auto-substituted (tokens)  : {total_a}",
        f"  Flagged for manual review  : {total_s}",
        f"  Unique secret values       : {reg.total}",
        f"  (duplicates share the same token — only counted once)",
        "",
    ]
    cat_a: dict = defaultdict(int)
    cat_s: dict = defaultdict(int)
    for f in auto_f:    cat_a[f.category] += 1
    for f in suggest_f: cat_s[f.category] += 1
    for d in ds_findings: cat_s[d["category"]] += 1
    cats = sorted(set(list(cat_a) + list(cat_s)))
    L.append(f"  {'CATEGORY':<20}  {'AUTO-SUBST':>10}  {'REVIEW':>10}")
    L.append(f"  {'-'*20}  {'-'*10}  {'-'*10}")
    for c in cats:
        L.append(f"  {c:<20}  {cat_a.get(c,0):>10}  {cat_s.get(c,0):>10}")
    L += ["", ""]

    # 2. by source file
    L += hdr(2, "FINDINGS BY SOURCE FILE")
    fc: dict = defaultdict(int)
    for f in findings:   fc[f.source_file] += 1
    for d in ds_findings: fc[d.get("source_file", "")] += 1
    if fc:
        L.append(f"  {'SOURCE FILE':<58}  {'HITS':>4}")
        L.append(f"  {'-'*58}  {'-'*4}")
        for src, cnt in sorted(fc.items(), key=lambda x: -x[1]):
            disp = src if len(src) <= 58 else "…" + src[-57:]
            L.append(f"  {disp:<58}  {cnt:>4}")
    else:
        L.append("  No findings.")
    L += ["", ""]

    # 3. auto-substituted detail
    L += hdr(3, "AUTO-SUBSTITUTED FINDINGS  (applied to clean file)")
    L += [
        "  ORIGINAL = the actual value found",
        "  TOKEN    = what replaced it (search for this in bot output to revert)",
        "",
    ]
    if auto_f:
        by_rule: dict = defaultdict(list)
        for f in auto_f:
            by_rule[f.rule_name].append(f)
        for rname in sorted(by_rule):
            items = by_rule[rname]
            rdesc = next((r.description for r in rules if r.name == rname), "")
            L += [f"  ┌─ [{rname}]  ({len(items)} occurrence(s))",
                  f"  │  {rdesc}", "  │"]
            for i, f in enumerate(items):
                conn = "└" if i == len(items)-1 else "├"
                L += [
                    f"  │  {conn}─ Line {f.line_no:<6}  {f.source_file}",
                    f"  │     ORIGINAL : {f.original}",
                    f"  │     TOKEN    : {f.token}",
                    f"  │     CONTEXT  : {f.context}",
                ]
                if i < len(items)-1:
                    L.append("  │")
            L += ["", ""]
    else:
        L += ["  None.", ""]

    # 4. substitution map preview
    L += hdr(4, "SUBSTITUTION MAP PREVIEW  (full map in *_map.json)")
    L += ["  TOKEN                ORIGINAL VALUE", "  " + "-"*65]
    for tok, orig in sorted(reg.to_dict()["token_to_original"].items()):
        L.append(f"  {tok:<22}  {orig[:55] + '…' if len(orig)>55 else orig}")
    L += ["", ""]

    # 5. manual review
    L += hdr(5, "FLAGGED FOR MANUAL REVIEW  (NOT auto-substituted)")
    L += ["  These matched a suggest_only rule or were flagged by detect-secrets.",
          "  They were NOT tokenised — review each one before uploading.", ""]
    all_s = list(suggest_f) + [
        Finding(d["rule_name"], d["category"], d.get("source_file",""),
                d["line_no"], d["original"], d["token"], d["context"], True)
        for d in ds_findings
    ]
    if all_s:
        for i, f in enumerate(all_s, 1):
            L += [f"  [{i:04d}]  Rule     : {f.rule_name}",
                  f"          Category : {f.category}",
                  f"          File     : {f.source_file}",
                  f"          Line     : {f.line_no}",
                  f"          Original : {f.original}",
                  f"          Context  : {f.context}", ""]
    else:
        L += ["  None.", ""]

    # 6. change summary
    L += hdr(6, "CHANGE SUMMARY BY RULE")
    L.append(f"  {'RULE':<30}  {'CATEGORY':<10}  {'HITS':>5}  {'UNIQUE':>6}  {'TYPE'}")
    L.append(f"  {'-'*30}  {'-'*10}  {'-'*5}  {'-'*6}  {'-'*12}")
    rs: dict = defaultdict(lambda: {"cat":"","hits":0,"uniq":set(),"sug":False})
    for f in findings:
        rs[f.rule_name]["cat"]   = f.category
        rs[f.rule_name]["hits"] += 1
        rs[f.rule_name]["uniq"].add(f.token)
        rs[f.rule_name]["sug"]   = f.suggest_only
    for d in ds_findings:
        rs[d["rule_name"]]["cat"]   = d["category"]
        rs[d["rule_name"]]["hits"] += 1
        rs[d["rule_name"]]["sug"]   = True
    for rn, info in sorted(rs.items(), key=lambda x: -x[1]["hits"]):
        rtype = "suggest-only" if info["sug"] else "auto-token"
        uniq  = len(info["uniq"]) if info["uniq"] else "-"
        L.append(f"  {rn:<30}  {info['cat']:<10}  {info['hits']:>5}  {str(uniq):>6}  {rtype}")
    L += ["", ""]

    # 7. all rules loaded
    L += hdr(7, "ALL RULES LOADED THIS RUN")
    L.append(f"  {'RULE':<30}  {'CAT':<10}  {'HITS':>5}  {'MODE':<14}  DESCRIPTION")
    L.append(f"  {'-'*30}  {'-'*10}  {'-'*5}  {'-'*14}  {'-'*30}")
    for r in sorted(rules, key=lambda x: (x.category, x.name)):
        hits = rs.get(r.name, {}).get("hits", 0)
        mode = "suggest-only" if r.suggest_only else "auto-token"
        desc = r.description[:35] + "…" if len(r.description) > 35 else r.description
        L.append(f"  {r.name:<30}  {r.category:<10}  {hits:>5}  {mode:<14}  {desc}")
    L += ["", ""]

    # 8. suggestions
    L += hdr(8, "SUGGESTIONS & NOTES")
    sug = []
    if total_s:
        sug.append(f"  • {total_s} item(s) need manual review (section 5). "
                   "Promote rules to auto-token in security_rules.yaml when confident.")
    if not HAS_DS:
        sug.append("  • pip install detect-secrets for deeper secret detection.")
    for r in rules:
        if r.notes and rs.get(r.name, {}).get("hits", 0) > 0:
            sug.append(f"  • [{r.name}] {r.notes}")
    total_hits = len(auto_f)
    if total_hits > reg.total:
        sug.append(f"  • {total_hits - reg.total} duplicate values found — "
                   "they share a token, revert handles them all.")
    if not sug:
        sug.append("  • No additional suggestions.")
    L += sug + ["", ""]

    # 9. revert instructions
    L += hdr(9, "HOW TO REVERT TOKENS IN GOV CHATBOT RESPONSES")
    L += [
        "  WORKFLOW:",
        "    1. Upload chunk files from the chunks/ folder to your gov chatbot.",
        "    2. Receive the bot's response.",
        "    3. Run:",
        "",
        f"       python security_revert.py --response-file bot_answer.txt",
        f"       python security_revert.py --response \"the [SSN-0001] field…\"",
        f"       python security_revert.py --response-file bot_answer.txt --out reverted.txt",
        "",
        "  The revert script swaps every token back to its original value.",
        "",
        "  ⚠  The *_map.json file contains ALL original sensitive values.",
        "     Keep it local.  Never upload it.  Never share it.",
        "",
        D, "  END OF REPORT", f"  {run_time}", D,
    ]

    L.append(REPORT_DISCLAIMER)
    return "\n".join(L)


# ── public entry point ────────────────────────────────────────────────────────

def run(in_path: Path, out_path: Path, report_path: Path, map_path: Path,
        rules_path: Path, tag: str, mode: str = "redact") -> dict:

    run_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rules    = load_rules(rules_path)
    text     = in_path.read_text(encoding="utf-8", errors="replace")
    cb       = len(text)
    reg      = TokenRegistry()

    clean, findings = scrub(text, rules, reg)
    ds = _detect_secrets(in_path)
    ca = len(clean)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    map_path.parent.mkdir(parents=True, exist_ok=True)

    if mode == "redact":
        out_path.write_text(clean + FILE_FOOTER, encoding="utf-8")
        map_path.write_text(json.dumps(reg.to_dict(), indent=2), encoding="utf-8")

    report_text = _report(
        findings, ds, rules, reg,
        in_path, out_path if mode == "redact" else None,
        map_path, mode, cb, ca, tag, run_time,
    )
    report_path.write_text(report_text, encoding="utf-8")

    json_p = report_path.with_suffix(".json")
    all_j = [
        {k: getattr(f, k) for k in
         ("rule_name","category","source_file","line_no","original","token","context","suggest_only")}
        for f in findings
    ] + ds
    json_p.write_text(json.dumps(all_j, indent=2), encoding="utf-8")

    return {
        "rules_loaded": len(rules),
        "auto": sum(1 for f in findings if not f.suggest_only),
        "suggest": sum(1 for f in findings if f.suggest_only) + len(ds),
        "unique_tokens": reg.total,
        "char_before": cb,
        "char_after": ca,
        "map": reg.to_dict(),
    }
