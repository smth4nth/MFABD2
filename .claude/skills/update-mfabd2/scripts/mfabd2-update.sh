#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="/Users/jimmychen/github/MFABD2"
UPSTREAM_REPO="sunyink/MFABD2"
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PATCHES_FILE="$SKILL_DIR/references/colormatch-patches.json"
LAUNCH_SCRIPT="$REPO_ROOT/MFAAvalonia-beta.command"

# --- Functions ---

list_releases() {
    gh release list --repo "$UPSTREAM_REPO" --limit "${1:-5}"
}

get_current_dir() {
    grep '^cd ' "$LAUNCH_SCRIPT" 2>/dev/null | sed 's/^cd "//;s/"$//' || echo ""
}

download_and_extract() {
    local tag="$1"
    local tmp_dir="/tmp/mfabd2-update"

    mkdir -p "$tmp_dir"
    echo "Downloading $tag..."
    gh release download "$tag" --repo "$UPSTREAM_REPO" --pattern "*macos-aarch64.zip" --dir "$tmp_dir" --clobber

    local zip_file
    zip_file=$(ls "$tmp_dir"/*macos-aarch64.zip 2>/dev/null | head -1)
    if [ -z "$zip_file" ]; then
        echo "ERROR: No macos-aarch64.zip found" >&2
        return 1
    fi

    local dirname
    dirname=$(basename "$zip_file" .zip)
    local target="$REPO_ROOT/$dirname"

    echo "Extracting to $target..."
    mkdir -p "$target"
    unzip -q -o "$zip_file" -d "$target"
    rm -f "$zip_file"

    echo "$target"
}

fix_macos_issues() {
    local new_dir="$1"

    echo "Fixing permissions..."
    chmod +x "$new_dir/MFAAvalonia"
    chmod +x "$new_dir"/python/bin/python3* 2>/dev/null || true

    echo "Removing quarantine..."
    xattr -r -d com.apple.quarantine "$new_dir/" 2>/dev/null || true

    echo "Reinstalling numpy & pillow..."
    local site
    site=$(echo "$new_dir"/python/lib/python3.*/site-packages)

    rm -rf "$site/numpy" "$site"/numpy-*.dist-info
    rm -rf "$site/PIL" "$site"/Pillow-*.dist-info "$site"/pillow-*.dist-info

    "$new_dir/python/bin/python3" -m pip install --quiet numpy==1.26.4 pillow --target "$site" 2>&1 | tail -3

    # Verify
    if "$new_dir/python/bin/python3" -c "import numpy; import PIL; print('OK: numpy', numpy.__version__, '| Pillow', PIL.__version__)" 2>&1; then
        echo "macOS fixes applied successfully."
    else
        echo "WARNING: numpy/Pillow import failed" >&2
    fi
}

check_conflicts() {
    local new_dir="$1"
    local pipeline_dir="$new_dir/resource/base/pipeline"

    PATCHES_FILE="$PATCHES_FILE" PIPELINE_DIR="$pipeline_dir" python3 << 'PYEOF'
import json, os, re

patches_file = os.environ["PATCHES_FILE"]
pipeline_dir = os.environ["PIPELINE_DIR"]

with open(patches_file) as f:
    config = json.load(f)

results = {"apply": [], "skip": [], "conflict": []}

for patch in config["patches"]:
    filepath = os.path.join(pipeline_dir, patch["file"])
    if not os.path.exists(filepath):
        patch["error"] = "file not found"
        results["conflict"].append(patch)
        continue

    with open(filepath) as f:
        data = json.load(f)

    if patch["node"] not in data:
        patch["error"] = "node not found"
        results["conflict"].append(patch)
        continue

    node = data[patch["node"]]
    if "path" in patch:
        for part in re.split(r'\.', patch["path"]):
            m = re.match(r'(\w+)\[(\d+)\]', part)
            if m:
                node = node[m.group(1)][int(m.group(2))]
            else:
                node = node[part]

    current = node.get(patch["field"])

    if current == patch["upstream_original"]:
        results["apply"].append(patch)
    elif current == patch["patched"]:
        results["skip"].append(patch)
    else:
        patch["current_value"] = current
        results["conflict"].append(patch)

print(json.dumps(results, indent=2, ensure_ascii=False))
PYEOF
}

apply_patches() {
    local new_dir="$1"
    local pipeline_dir="$new_dir/resource/base/pipeline"

    PATCHES_FILE="$PATCHES_FILE" PIPELINE_DIR="$pipeline_dir" python3 << 'PYEOF'
import json, os, re

patches_file = os.environ["PATCHES_FILE"]
pipeline_dir = os.environ["PIPELINE_DIR"]

with open(patches_file) as f:
    config = json.load(f)

by_file = {}
for patch in config["patches"]:
    by_file.setdefault(patch["file"], []).append(patch)

for filename, patches in by_file.items():
    filepath = os.path.join(pipeline_dir, filename)
    with open(filepath) as f:
        data = json.load(f)

    applied = 0
    for patch in patches:
        node = data[patch["node"]]
        if "path" in patch:
            for part in re.split(r'\.', patch["path"]):
                m = re.match(r'(\w+)\[(\d+)\]', part)
                if m:
                    node = node[m.group(1)][int(m.group(2))]
                else:
                    node = node[part]

        current = node.get(patch["field"])
        if current == patch["upstream_original"]:
            node[patch["field"]] = patch["patched"]
            applied += 1

    with open(filepath, 'w') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
        f.write('\n')

    print(f"  {filename}: {applied}/{len(patches)} patches applied")
PYEOF
}

migrate_config() {
    local old_dir="$1"
    local new_dir="$2"

    if [ -z "$old_dir" ] || [ ! -d "$old_dir" ]; then
        echo "No old directory found, skipping config migration."
        return 0
    fi

    mkdir -p "$new_dir/config/instances"

    local migrated=0
    for f in config/config.json config/maa_option.json config/instances/default.json; do
        if [ -f "$old_dir/$f" ]; then
            cp "$old_dir/$f" "$new_dir/$f"
            echo "  Migrated: $f"
            migrated=$((migrated + 1))
        fi
    done
    echo "Config migration: $migrated files."
}

update_launch_script() {
    local new_dir="$1"

    if [ ! -f "$LAUNCH_SCRIPT" ]; then
        cat > "$LAUNCH_SCRIPT" << SCRIPT
#!/bin/bash
cd "$new_dir"
export DOTNET_ROOT="\$HOME/.dotnet"
export PATH="\$PATH:\$DOTNET_ROOT"
./MFAAvalonia
osascript -e 'tell application "Terminal" to close front window' &
SCRIPT
        chmod +x "$LAUNCH_SCRIPT"
        echo "Launch script created."
    else
        sed -i '' "s|^cd .*|cd \"$new_dir\"|" "$LAUNCH_SCRIPT"
        echo "Launch script updated to: $new_dir"
    fi
}

cleanup_old() {
    local old_dir="$1"
    if [ -d "$old_dir" ]; then
        local size
        size=$(du -sh "$old_dir" | cut -f1)
        rm -rf "$old_dir"
        echo "Removed: $old_dir ($size freed)"
    else
        echo "Directory not found: $old_dir"
    fi
}

# --- Main dispatcher ---
case "${1:-help}" in
    list)
        list_releases "${2:-5}"
        ;;
    current)
        get_current_dir
        ;;
    download)
        download_and_extract "$2"
        ;;
    fix)
        fix_macos_issues "$2"
        ;;
    check-conflicts)
        check_conflicts "$2"
        ;;
    patch)
        apply_patches "$2"
        ;;
    migrate)
        migrate_config "$2" "$3"
        ;;
    update-script)
        update_launch_script "$2"
        ;;
    cleanup)
        cleanup_old "$2"
        ;;
    full)
        tag="$2"
        old_dir=$(get_current_dir)

        echo "=== Step 1: Download & Extract ==="
        new_dir=$(download_and_extract "$tag" | tail -1)
        echo "Extracted to: $new_dir"
        echo ""

        echo "=== Step 2: Fix macOS Issues ==="
        fix_macos_issues "$new_dir"
        echo ""

        echo "=== Step 3: Check Conflicts ==="
        check_conflicts "$new_dir"
        echo ""

        echo "=== Step 4: Apply Patches ==="
        apply_patches "$new_dir"
        echo ""

        echo "=== Step 5: Migrate Config ==="
        migrate_config "$old_dir" "$new_dir"
        echo ""

        echo "=== Step 6: Update Launch Script ==="
        update_launch_script "$new_dir"
        echo ""

        echo "=== DONE ==="
        echo "New: $new_dir"
        echo "Old (not deleted): $old_dir"
        ;;
    help)
        echo "MFABD2 macOS Update Tool"
        echo ""
        echo "Usage: $(basename "$0") <command> [args...]"
        echo ""
        echo "Commands:"
        echo "  list [N]              List latest N releases (default 5)"
        echo "  current               Show current install directory"
        echo "  download <tag>        Download and extract a release"
        echo "  fix <dir>             Fix macOS issues (permissions, dylibs)"
        echo "  check-conflicts <dir> Check ColorMatch patch conflicts"
        echo "  patch <dir>           Apply ColorMatch patches"
        echo "  migrate <old> <new>   Copy config from old to new"
        echo "  update-script <dir>   Update launch script to point to dir"
        echo "  cleanup <dir>         Delete old release directory"
        echo "  full <tag>            Run all steps for a given release tag"
        ;;
esac
