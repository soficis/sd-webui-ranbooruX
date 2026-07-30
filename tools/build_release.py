#!/usr/bin/env python3
import fnmatch
import os
import re
import shutil
import sys
import tempfile
import time
import zipfile

ALLOWLIST_PATTERNS = [
    ".gitignore",
    ".pre-commit-config.yaml",
    "install.py",
    "pyproject.toml",
    "README.md",
    "requirements.txt",
    # "adetailer/**/*",  # local nested extension dir (ignored by .gitignore); do not package
    "data/**/*",
    "docs/CHANGELOG.md",
    "docs/CONFIG.md",
    "docs/usage.md",
    "pics/**/*",
    "ranboorux/**/*",
    "scripts/**/*",
    "tests/**/*",
    "tools/**/*",
]

# Files/dirs that must NEVER end up in the zip archive
FORBIDDEN_PATTERNS = [
    "*/.git/*",
    "*/.venv/*",
    "*/__pycache__/*",
    "*/.mypy_cache/*",
    "*/.pytest_cache/*",
    "*/.pytest_cache_local/*",
    "*/.ruff_cache/*",
    "*.log",
    "*/logs/*",
    "*credentials.json",
    "*/credentials.json",
    "*.zip",
    "*.tar.gz",
    "*.bak",
    "*~",
    "*/tmpclaude-*",
    "*/.ranboorux_*",
    "*/docs/handoff/*",
    "*/docs/joblog.txt",
    "*/docs/ranbooru backup*.py",
    "*/docs/ranbooru_fix_bundle/*",
    "*/docs/ranboorux_planning_docs/*",
    "*/docs/ranboorux_planning_docs_v2/*",
]

TEXT_CONTENT_EXTENSIONS = {
    ".cfg",
    ".css",
    ".csv",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yml",
}
LOCAL_FILE_URI_RE = re.compile(rb"\bfile:///")
WINDOWS_ABSOLUTE_PATH_RE = re.compile(rb"\b[A-Za-z]:(?:\\[^\\\r\n\t]+)+")

def matches_any(path, patterns):
    path_norm = path.replace("\\", "/")
    for pattern in patterns:
        if fnmatch.fnmatch(path_norm, pattern) or fnmatch.fnmatch(
            os.path.basename(path_norm), pattern
        ):
            return True
        # Handle recursive glob patterns manually for simplicity
        if "**" in pattern:
            parts = pattern.split("/**/")
            if len(parts) == 2:
                prefix, suffix = parts[0], parts[1]
                if path_norm.startswith(prefix) and fnmatch.fnmatch(path_norm, f"*/{suffix}"):
                    return True
    return False


def check_archive_hygiene(zip_path):
    print(f"Verifying hygiene of archive: {zip_path}")
    violations = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in zf.namelist():
            if matches_any(name, FORBIDDEN_PATTERNS):
                violations.append(name)
                continue
            suffix = os.path.splitext(name)[1].lower()
            if suffix not in TEXT_CONTENT_EXTENSIONS:
                continue
            payload = zf.read(name)
            if LOCAL_FILE_URI_RE.search(payload):
                violations.append(f"{name}: contains local file URI")
            if WINDOWS_ABSOLUTE_PATH_RE.search(payload):
                violations.append(f"{name}: contains Windows absolute path")
    if violations:
        print("HYGIENE ERROR: Forbidden files detected in the archive:")
        for v in violations:
            print(f"  - {v}")
        raise ValueError("Archive hygiene check failed due to forbidden files.")
    print("Hygiene check passed successfully.")


def copy_by_allowlist(src_dir, dest_dir):
    os.makedirs(dest_dir, exist_ok=True)

    # We walk the source directory
    for root, dirs, files in os.walk(src_dir):
        # Calculate relative path
        rel_root = os.path.relpath(root, src_dir)
        if rel_root == ".":
            rel_root = ""

        for file in files:
            rel_file = os.path.join(rel_root, file).replace("\\", "/")

            # Check if it matches ALLOWLIST_PATTERNS
            matched = False
            for pat in ALLOWLIST_PATTERNS:
                if "**" in pat:
                    prefix = pat.split("/**")[0]
                    if rel_file.startswith(prefix):
                        matched = True
                        break
                else:
                    if fnmatch.fnmatch(rel_file, pat):
                        matched = True
                        break

            if matched:
                # Still check if it matches forbidden patterns just in case
                if matches_any(rel_file, FORBIDDEN_PATTERNS):
                    continue
                src_path = os.path.join(root, file)
                dest_path = os.path.join(dest_dir, rel_file)
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                try:
                    with open(src_path, "rb") as sf, open(dest_path, "wb") as df:
                        df.write(sf.read())
                except Exception as exc:
                    print(f"Failed to copy {src_path} -> {dest_path}: {exc}")
                    raise exc


def build_zip(staging_dir, zip_path, folder_name="sd-webui-ranbooruX"):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(staging_dir):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, staging_dir)
                archive_name = os.path.join(folder_name, rel_path).replace("\\", "/")
                zf.write(full_path, archive_name)


def remove_tree_best_effort(path):
    last_error = None
    for _ in range(5):
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.25)
    if last_error is not None:
        print(f"Warning: could not remove staging directory {path}: {last_error}")


def run_self_tests():
    print("Running build release self-tests...")
    temp_dir = tempfile.mkdtemp()
    try:
        # Create a mock source directory
        src = os.path.join(temp_dir, "src")
        os.makedirs(src)

        # Add allowed files
        allowed = [
            "README.md",
            "install.py",
            "scripts/ranbooru.py",
            "docs/usage.md",
        ]
        for f in allowed:
            p = os.path.join(src, f)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w") as fh:
                fh.write("allowed content")
        excluded_docs = [
            "docs/joblog.txt",
            "docs/handoff/GEMINI_HANDOFF.md",
            "docs/ranbooru backup.py",
            "docs/ranbooru_fix_bundle/ranbooru.py",
        ]
        for f in excluded_docs:
            p = os.path.join(src, f)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w") as fh:
                fh.write("excluded content")

        # 1. Test clean build
        stage = os.path.join(temp_dir, "stage")
        copy_by_allowlist(src, stage)
        for f in excluded_docs:
            if os.path.exists(os.path.join(stage, f)):
                print(f"Excluded doc {f} was copied into staging! FAIL")
                sys.exit(1)

        zip_clean = os.path.join(temp_dir, "release_clean.zip")
        build_zip(stage, zip_clean)

        # Should pass
        check_archive_hygiene(zip_clean)
        print("Clean archive verification: PASS")

        # 2. Test dirty build (add a forbidden file to staging)
        forbidden_files = [
            ".git/config",
            ".venv/bin/python",
            "__pycache__/ranbooru.cpython-310.pyc",
            "user/logs/error.log",
            "credentials.json",
            "scripts/ranbooru.py.bak",
            "release.zip",
            "docs/joblog.txt",
            "docs/handoff/GEMINI_HANDOFF.md",
            "docs/ranbooru backup.py",
            "docs/ranbooru_fix_bundle/ranbooru.py",
        ]

        for ff in forbidden_files:
            stage_dirty = os.path.join(temp_dir, "stage_dirty")
            if os.path.exists(stage_dirty):
                shutil.rmtree(stage_dirty)
            copy_by_allowlist(src, stage_dirty)

            # Manually inject the forbidden file to staging to simulate accident or packaging failure
            p = os.path.join(stage_dirty, ff)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w") as fh:
                fh.write("forbidden content")

            zip_dirty = os.path.join(temp_dir, f"release_dirty_{os.path.basename(ff)}.zip")
            build_zip(stage_dirty, zip_dirty)

            try:
                check_archive_hygiene(zip_dirty)
                print(f"Dirty archive containing {ff} was NOT caught! FAIL")
                sys.exit(1)
            except ValueError:
                print(f"Dirty archive containing {ff} correctly rejected: PASS")

        forbidden_content = {
            "docs/usage.md": "see " + "file:" + "///v:/private/handoff.md",
            "scripts/ranbooru.py": "MODEL_PATH = r'E:\\private\\models'",
        }
        for ff, content in forbidden_content.items():
            stage_dirty = os.path.join(temp_dir, "stage_dirty")
            if os.path.exists(stage_dirty):
                shutil.rmtree(stage_dirty)
            copy_by_allowlist(src, stage_dirty)
            p = os.path.join(stage_dirty, ff)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w") as fh:
                fh.write(content)

            zip_dirty = os.path.join(temp_dir, f"release_dirty_content_{os.path.basename(ff)}.zip")
            build_zip(stage_dirty, zip_dirty)

            try:
                check_archive_hygiene(zip_dirty)
                print(f"Dirty archive content in {ff} was NOT caught! FAIL")
                sys.exit(1)
            except ValueError:
                print(f"Dirty archive content in {ff} correctly rejected: PASS")

        print("All G-01 self-tests passed successfully!")
    finally:
        shutil.rmtree(temp_dir)


def main():
    if "--test" in sys.argv:
        run_self_tests()
        sys.exit(0)

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    dist_dir = os.path.join(repo_root, "dist")
    os.makedirs(dist_dir, exist_ok=True)

    stale_staging_dir = os.path.join(dist_dir, "staging")
    remove_tree_best_effort(stale_staging_dir)
    staging_dir = tempfile.mkdtemp(prefix="staging_", dir=dist_dir)

    zip_path = os.path.join(dist_dir, "ranboorux.zip")
    if os.path.exists(zip_path):
        os.remove(zip_path)

    print(f"Building release from {repo_root}...")
    copy_by_allowlist(repo_root, staging_dir)
    build_zip(staging_dir, zip_path)

    try:
        check_archive_hygiene(zip_path)
        print(f"Release built and verified successfully: {zip_path}")
        # Clean up staging dir
        remove_tree_best_effort(staging_dir)
    except ValueError as e:
        print(f"Release verification FAILED: {e}")
        # Leave staging dir for inspection
        sys.exit(1)


if __name__ == "__main__":
    main()
