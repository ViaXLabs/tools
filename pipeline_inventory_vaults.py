"""
pipeline_inventory_vaults.py

Script to inventory Vault usage in Jenkinsfiles in a team/repo directory structure,
extracting Vault URLs, credentials, namespaces, kv paths, keys, and Vault-related environment variables,
and generating a CSV report in the output folder.
"""

import re
from pathlib import Path
from utils import write_csv_report, iter_team_repo_files, run_inventory

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
    kv_path_pattern = re.compile(
        r"kv/([A-Za-z0-9_\-/]+)",
        re.IGNORECASE
    )
    vault_key_pattern = re.compile(
        r"['\"]([A-Za-z0-9_\-]+)['\"]"
    )

    func_blocks = re.findall(
        r"(def\s+\w+\s*\([^)]*\)\s*\{([\s\S]*?)^\s*\})",
        content,
        re.MULTILINE
    )

    def extract_environment_block(content):
        start = content.lower().find("environment {")
        if start == -1:
            return None
        stack = []
        end = None
        for i, char in enumerate(content[start:], start=start):
            if char == '{':
                stack.append(i)
            elif char == '}':
                stack.pop()
                if not stack:
                    end = i
                    break
        return content[start + len("environment {"):end].strip() if end else None

    env_block_content = extract_environment_block(content)
    env_vars = (
        re.findall(
            r"([A-Za-z0-9_]+)\s*=\s*['\"]([^'\"]+)['\"]",
            env_block_content
        ) if env_block_content else []
    )
    vault_env_vars = [
        var for var in env_vars if "vault" in var[0].lower()
    ]

    for func_def, func_body in func_blocks:
        func_name_match = re.search(r"def\s+(\w+)", func_def)
        func_name = func_name_match.group(1) if func_name_match else "unknown"
        vault_urls = ", ".join(vault_url_pattern.findall(func_body))
        vault_creds = ", ".join(vault_cred_pattern.findall(func_body))
        vault_namespaces = ", ".join(vault_ns_pattern.findall(func_body))
        kv_paths = ", ".join(kv_path_pattern.findall(func_body))
        vault_keys = ""
        vault_envs = ""

        if kv_path_pattern.findall(func_body):
            key_matches = vault_key_pattern.findall(func_body)
            vault_keys = ", ".join(sorted(set(key_matches)))
        func_env_vars = re.findall(
            r"([A-Za-z0-9_]+)\s*=\s*['\"]([^'\"]+)['\"]",
            func_body
        )
        vault_func_envs = [
            var for var in func_env_vars if "vault" in var[0].lower()
        ]
        if vault_func_envs:
            vault_envs = ", ".join([f"{k}={v}" for k, v in vault_func_envs])
        func_info = {
            "Team": team,
            "Repo": repo,
            "Jenkinsfile": jenkinsfile_path.name,
            "Function": func_name,
            "Vault URLs": vault_urls,
            "Vault Credentials": vault_creds,
            "Vault Namespaces": vault_namespaces,
            "KV Paths": kv_paths,
            "Vault Keys": vault_keys,
            "Vault Env Vars": vault_envs
        }
        results.append(func_info)

    if vault_env_vars:
        func_info = {
            "Team": team,
            "Repo": repo,
            "Jenkinsfile": jenkinsfile_path.name,
            "Function": "global_environment",
            "Vault URLs": "",
            "Vault Credentials": "",
            "Vault Namespaces": "",
            "KV Paths": "",
            "Vault Keys": "",
            "Vault Env Vars": ", ".join([f"{k}={v}" for k, v in vault_env_vars])
        }
        results.append(func_info)
    return results

HEADERS = [
    "Team",
    "Repo",
    "Jenkinsfile",
    "Function",
    "Vault URLs",
    "Vault Credentials",
    "Vault Namespaces",
    "KV Paths",
    "Vault Keys",
    "Vault Env Vars"
]

if __name__ == "__main__":
    run_inventory(
        extract_func=extract_vault_info,
        filename_pattern="*Jenkinsfile*",
        headers=HEADERS,
        output_csv="pipeline_inventory_vaults.csv",
        description="Generate pipeline_inventory_vaults.csv with Vault usage info."
    )
