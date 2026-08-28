#!/usr/bin/env bash
# scripts/validate.sh
#
# Packages the offline checks used while building this scaffold, so
# whoever integrates it (human or bot) can re-run the same checks after
# merging into the real repo -- this was built and checked without
# network access or the terraform/helm binaries available, so these
# checks are a substitute for `terraform validate` / `helm template`,
# not a replacement. Run those for real once you're in an environment
# that has them.
#
# What this actually checks:
#   1. Every .tf file has balanced {}/()/[] (catches copy-paste damage,
#      not real HCL syntax errors -- it's not a parser)
#   2. Every .yaml file parses as valid YAML
#   3. Every module call in terraform/live/dev/* passes exactly its
#      module's required arguments, with no typo'd/unknown arguments
#   4. Python app(s) under apps/ compile
#   5. No leftover REPLACE_ME (delegates to check-placeholders.sh)
#
# Usage:
#   ./scripts/validate.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

FAIL=0

echo "=== 1. HCL brace/paren/bracket balance ==="
python3 -c "
import glob, sys
bad = False
for f in sorted(glob.glob('terraform/**/*.tf', recursive=True)):
    s = open(f).read()
    if not (s.count('{')==s.count('}') and s.count('(')==s.count(')') and s.count('[')==s.count(']')):
        print(f'  [FAIL] {f}')
        bad = True
if bad:
    sys.exit(1)
print('  OK')
" || FAIL=1
echo

echo "=== 2. YAML parses (Harness) + Chart.yaml/values.yaml parse ==="
python3 -c "
import yaml, glob, sys
bad = False
# Note: charts/**/templates/*.yaml are Helm templates, NOT plain YAML --
# they contain Go-template syntax ({{ }}, {{- with }}, etc.) that
# yaml.safe_load() will always reject. Only Chart.yaml and values.yaml
# (no templating) get checked this way; templates/ get a different,
# template-aware check below.
patterns = ['.harness/**/*.yaml', 'charts/*/Chart.yaml', 'charts/*/values.yaml']
for pattern in patterns:
    for f in sorted(glob.glob(pattern, recursive=True)):
        try:
            yaml.safe_load(open(f))
        except Exception as e:
            print(f'  [FAIL] {f}: {e}')
            bad = True
if bad:
    sys.exit(1)
print('  OK')
" || FAIL=1
echo

echo "=== 2b. Helm template syntax (brace balance + helper resolution) ==="
python3 -c "
import glob, re, sys
bad = False
for f in sorted(glob.glob('charts/*/templates/*.yaml') + glob.glob('charts/*/templates/*.tpl')):
    s = open(f).read()
    if s.count('{{') != s.count('}}'):
        print(f'  [FAIL] {f}: unbalanced {{{{ }}}} tags')
        bad = True

defined = set()
for f in glob.glob('charts/*/templates/_helpers.tpl'):
    defined |= set(re.findall(r'define\s+\"([^\"]+)\"', open(f).read()))
for f in sorted(glob.glob('charts/*/templates/*.yaml')):
    used = set(re.findall(r'include\s+\"([^\"]+)\"', open(f).read()))
    missing = used - defined
    if missing:
        print(f'  [FAIL] {f}: uses undefined helper(s) {sorted(missing)}')
        bad = True
if bad:
    sys.exit(1)
print('  OK')
" || FAIL=1
echo

echo "=== 3. Module wiring (required args present, no unknown args) ==="
python3 << 'PYEOF' || FAIL=1
import re, glob, os, sys

def find_declared_vars(text):
    return set(re.findall(r'variable\s+"([^"]+)"', text))

def find_var_usages(text):
    return set(re.findall(r'var\.([a-zA-Z0-9_]+)', text))

def find_module_blocks(text):
    blocks = []
    for m in re.finditer(r'module\s+"([^"]+)"\s*\{', text):
        start = m.end()
        depth = 1
        i = start
        while depth > 0 and i < len(text):
            if text[i] == '{': depth += 1
            elif text[i] == '}': depth -= 1
            i += 1
        body = text[start:i-1]
        src_m = re.search(r'source\s*=\s*"([^"]+)"', body)
        blocks.append((m.group(1), src_m.group(1) if src_m else None, body))
    return blocks

def top_level_keys(body):
    keys = []
    depth = 0
    buf = ""
    for ch in body:
        if ch == '\n':
            stripped = buf.strip()
            m = re.match(r'^([a-zA-Z0-9_]+)\s*=', stripped)
            if m and depth == 0:
                keys.append(m.group(1))
            buf = ""
            continue
        buf += ch
        if ch == '{': depth += 1
        elif ch == '}': depth -= 1
    stripped = buf.strip()
    m = re.match(r'^([a-zA-Z0-9_]+)\s*=', stripped)
    if m and depth == 0:
        keys.append(m.group(1))
    return set(keys) - {"source"}

def find_module_required_vars(module_dir):
    text = ""
    for f in glob.glob(os.path.join(module_dir, "*.tf")):
        text += open(f).read() + "\n"
    required, optional = [], []
    for m in re.finditer(r'variable\s+"([^"]+)"\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}', text, re.S):
        name, body = m.group(1), m.group(2)
        (optional if 'default' in body else required).append(name)
    return required, optional

bad = False
for root in sorted(glob.glob("terraform/live/*/*/")):
    root = root.rstrip("/")
    text = ""
    for f in glob.glob(os.path.join(root, "*.tf")):
        text += open(f).read() + "\n"
    if not text:
        continue

    declared = find_declared_vars(text)
    used = find_var_usages(text)
    undeclared = used - declared
    if undeclared:
        print(f"  [FAIL] {root}: variables used but never declared: {sorted(undeclared)}")
        bad = True

    for name, source, body in find_module_blocks(text):
        if source is None:
            continue
        module_dir = os.path.normpath(os.path.join(root, source))
        if not os.path.isdir(module_dir):
            print(f"  [FAIL] {root}: module \"{name}\" source '{source}' does not resolve to a real directory")
            bad = True
            continue
        required, optional = find_module_required_vars(module_dir)
        passed = top_level_keys(body)
        missing = set(required) - passed
        extra = passed - set(required) - set(optional)
        if missing:
            print(f"  [FAIL] {root}: module \"{name}\" missing required args: {sorted(missing)}")
            bad = True
        if extra:
            print(f"  [FAIL] {root}: module \"{name}\" passes unknown args: {sorted(extra)}")
            bad = True

if bad:
    sys.exit(1)
print("  OK")
PYEOF
echo

echo "=== 4. App source compiles/parses ==="
for f in $(find apps -name "*.py" 2>/dev/null); do
  python3 -m py_compile "$f" && echo "  OK: $f" || FAIL=1
done
echo "  (Java apps: no javac assumed available here -- build with your"
echo "   actual Gradle/Docker toolchain to verify those.)"
echo

echo "=== 5. Leftover placeholders ==="
if [ -x "$SCRIPT_DIR/check-placeholders.sh" ]; then
  "$SCRIPT_DIR/check-placeholders.sh" > /tmp/placeholder_check.txt 2>&1 || true
  cat /tmp/placeholder_check.txt
  grep -q "No REPLACE_ME placeholders found" /tmp/placeholder_check.txt || echo "  (expected to fail until you've filled in real values -- not a validate.sh bug)"
else
  echo "  [SKIP] check-placeholders.sh not found or not executable"
fi
echo

if [ "$FAIL" -eq 1 ]; then
  echo "=== RESULT: one or more checks FAILED above ==="
  exit 1
else
  echo "=== RESULT: all structural checks passed ==="
  echo "(Still run real 'terraform validate' / 'terraform plan' / 'helm template'"
  echo " once you're in an environment with those tools -- this script cannot"
  echo " substitute for them, it only catches what's checkable without them.)"
fi
