"""
pipeline_inventory_vaults.py

Script to inventory Vault usage in Jenkinsfiles in a team/repo directory structure,
extracting Vault URLs, credentials, namespaces, kv paths, keys, and Vault-related environment variables,
and generating a CSV report in the output folder.
"""

import re
import shutil
from pathlib import Path
from tools.utils import write_csv_report, iter_team_repo_files, run_inventory

def extract_vault_info(jenkinsfile_path: Path, team: str, repo: str):
    results = []
    try:
        content = jenkinsfile_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            content = jenkinsfile_path.read_text(encoding="latin-1")
            print(f"Warning: Unable to decode {jenkinsfile_path} using 'utf-8'. Falling back to 'latin-1'.")
        except Exception as e:
            print(f"Encoding error in {jenkinsfile_path}: {e}.")
            return results
    except OSError as e:
        print(f"Error reading {jenkinsfile_path}: {e}")
        return results

    vault_url_pattern = re.compile(
        r"(?:https?://)?[a-zA-Z0-9.-]+\.vault\.?[a-zA-Z0-9.-]*/?[a-zA-Z0-9._~:/?#\[\]@!$&'()*+,;=%]*",
        re.IGNORECASE
    )
    vault_cred_pattern = re.compile(
        r"vault.*?(?:cred|token|secret)[^\s\"'=]*",
        re.IGNORECASE
    )
    vault_ns_pattern = re.compile(
        r"namespace\s*=\s*['\"]([^'\"]+)['\"]",
        re.IGNORECASE
    )

    func_blocks = re.findall(
        r"(def\s+\w+\s*\([^)]*\)\s*\{([\s\S]*?)^\s*\})",
        content,
        re.MULTILINE
    )

    results.extend([
        {
            "Team": team,
            "Repo": repo,
            "Jenkinsfile": jenkinsfile_path.name,
            "Function": func_name,
            "Vault URLs": ", ".join(vault_url_pattern.findall(func_body)),
            "Vault Credentials": ", ".join(vault_cred_pattern.findall(func_body)),
            "Vault Namespaces": ", ".join(vault_ns_pattern.findall(func_body))
        }
        for func_def, func_body in func_blocks
        if (func_name := re.search(r"def\s+(\w+)", func_def).group(1)) is not None
    ])

    return results

HEADERS = [
    "Team",
    "Repo",
    "Jenkinsfile",
    "Function",
    "Vault URLs",
    "Vault Credentials",
    "Vault Namespaces"
]

if __name__ == "__main__":
    run_inventory(
        extract_func=extract_vault_info,
        filename_pattern="*Jenkinsfile*",
        headers=HEADERS,
        output_csv="pipeline_inventory_vaults.csv",
        description="Generate pipeline_inventory_vaults.csv with Vault usage info."
    )

    # Cleanup __pycache__ folder
    pycache_path = Path("__pycache__")
    if pycache_path.exists():
        shutil.rmtree(pycache_path)

    print("✅ Cleanup complete: __pycache__ folder removed.")
