---
name: update-mfabd2
description: >
  Update MFABD2 (Brown Dust 2 automation assistant) to a new upstream release on macOS.
  Handles downloading from sunyink/MFABD2, fixing macOS issues (permissions, quarantine,
  broken numpy/pillow .dylibs), applying ColorMatch RGB patches for BlueStacks Air
  emulator compatibility, migrating config, and updating the launch script.
  TRIGGER when: user says "update MFABD2", "download latest beta", "new MFABD2 release",
  "update MFA", "升級 MFABD2", "更新 MFABD2", or similar.
---

# MFABD2 macOS Update Skill

## Constants

- Repo root: `/Users/jimmychen/github/MFABD2`
- Upstream: `sunyink/MFABD2`
- Launch script: `/Users/jimmychen/github/MFABD2/MFAAvalonia-beta.command`
- Update script: `/Users/jimmychen/github/MFABD2/.claude/skills/update-mfabd2/scripts/mfabd2-update.sh`
- Patches config: `/Users/jimmychen/github/MFABD2/.claude/skills/update-mfabd2/references/colormatch-patches.json`

## Workflow

### Step 1: List releases and pick version

```bash
bash /Users/jimmychen/github/MFABD2/.claude/skills/update-mfabd2/scripts/mfabd2-update.sh list 5
```

Show releases in a table. Ask user which to install (default: latest beta).
Also show current installed version:

```bash
bash /Users/jimmychen/github/MFABD2/.claude/skills/update-mfabd2/scripts/mfabd2-update.sh current
```

If same version, warn and confirm before reinstalling.

### Step 2: Run full update

```bash
bash /Users/jimmychen/github/MFABD2/.claude/skills/update-mfabd2/scripts/mfabd2-update.sh full "<tag>"
```

This executes all steps automatically:
1. Download `*macos-aarch64.zip` from GitHub release
2. Extract to repo root directory
3. Fix `chmod +x` on MFAAvalonia and python3
4. Remove Gatekeeper quarantine
5. Reinstall numpy 1.26.4 and pillow with native .dylibs
6. Check for ColorMatch patch conflicts
7. Apply ColorMatch patches (only where upstream hasn't changed)
8. Migrate config from previous version
9. Update `MFAAvalonia-beta.command` to point to new directory

### Step 3: Handle conflict output

Parse the JSON from the conflict check. Three categories:

- **apply**: Safe to patch. Report count.
- **skip**: Already patched (upstream adopted our fix or re-run). Report as info.
- **conflict**: Upstream changed values. For each:
  - Show file, node, field, expected vs actual vs our patch
  - Ask user: (a) apply our patch, (b) keep upstream value, (c) skip

For manual conflict resolution, use python3 to modify individual nodes.

### Step 4: Verify

```bash
cat /Users/jimmychen/github/MFABD2/MFAAvalonia-beta.command
ls -la <new_dir>/config/instances/default.json
<new_dir>/python/bin/python3 -c "import numpy, PIL; print('OK')"
python3 -c "import json; d=json.load(open('<new_dir>/resource/base/pipeline/Mail.json')); print('Mail_GetAll lower:', d['Mail_GetAll']['lower'])"
```

### Step 5: Cleanup (ask user)

Ask if they want to delete the old release directory:

```bash
bash /Users/jimmychen/github/MFABD2/.claude/skills/update-mfabd2/scripts/mfabd2-update.sh cleanup "<old_dir>"
```

## Individual Commands

The script supports running steps individually:

| Command | Usage |
|---------|-------|
| `list [N]` | List latest N releases |
| `current` | Show current install path |
| `download <tag>` | Download and extract |
| `fix <dir>` | Fix macOS issues only |
| `check-conflicts <dir>` | Check patches only |
| `patch <dir>` | Apply patches only |
| `migrate <old> <new>` | Copy config only |
| `update-script <dir>` | Update launch script only |
| `cleanup <dir>` | Delete old directory |
| `full <tag>` | All of the above |

## Edge Cases

- **gh not authenticated**: Tell user to run `gh auth login`
- **No old config**: First install, skip migration, tell user to configure manually
- **Python version change**: Script uses glob `python3.*/site-packages`
- **Network failure**: Retry download once, then abort with message
- **App running during update**: Warn user to close MFAAvalonia first
