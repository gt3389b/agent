# Database Directory Structure

## Overview

The database directory uses a 3-tier architecture to separate factory defaults from runtime state:

```
database/
├── defaults/           # Factory defaults (version controlled)
│   ├── test-defaults.json
│   ├── camera-defaults.json
│   └── motion-defaults.json
│
├── runtime/            # Working databases (.gitignored)
│   ├── test-db.json
│   ├── camera-db.json
│   └── motion-db.json
│
├── backups/            # Timestamped backups (.gitignored)
│   └── test-db.2026-01-15T10-30-00.json
│
└── *-dm.json           # Data models (schemas, version controlled)
    ├── test-dm.json       # Multi-MTP agent (WebSocket, CoAP, UDS)
    ├── camera-dm.json
    └── motion-dm.json
```

## File Types

### Data Models (`*-dm.json`)
- **Purpose**: Define the USP data model schema
- **Location**: Root of `database/` directory
- **Version Control**: ✅ Tracked in git
- **Modified**: Rarely (only when adding new parameters/objects)
- **Example**: `test-dm.json` defines which parameters exist and their access rights

### Factory Defaults (`defaults/*-defaults.json`)
- **Purpose**: Clean factory state for factory reset
- **Location**: `database/defaults/` directory
- **Version Control**: ✅ Tracked in git
- **Modified**: When default configuration should change
- **Usage**: Source for factory reset and initial setup

### Runtime Databases (`runtime/*-db.json`)
- **Purpose**: Working database modified during agent operation
- **Location**: `database/runtime/` directory
- **Version Control**: ❌ Gitignored
- **Modified**: Continuously by agent and controller
- **Usage**: Active database used by running agent

### Backups (`backups/*.json`)
- **Purpose**: Timestamped snapshots before factory reset
- **Location**: `database/backups/` directory
- **Version Control**: ❌ Gitignored
- **Modified**: Created automatically before factory reset
- **Usage**: Recovery if factory reset was unintended

## Usage

### Starting the Agent

Agent automatically uses runtime databases:

```bash
python -m agent.multi_mtp_agent database/test-dm.json database/runtime/test-db.json
```

If runtime database doesn't exist, it will be created from defaults automatically.

### Factory Reset

The `Device.FactoryReset()` USP command will:
1. Create backup of current runtime database in `backups/`
2. Copy factory defaults to runtime database
3. Reload the database
4. Send Boot! notification with Cause="RemoteFactoryReset"

### Manual Reset

To manually reset a database to factory defaults:

```bash
cp database/defaults/test-defaults.json database/runtime/test-db.json
```

### Changing Default Configuration

1. Edit the file in `database/defaults/`
2. Commit the change to git
3. Existing runtime databases are unaffected
4. New installations or factory resets will use the new defaults

## Git Tracking

**Tracked (committed to git):**
- `defaults/*.json` - Factory defaults
- `*-dm.json` - Data model schemas
- `README.md` - This file

**Ignored (.gitignore):**
- `runtime/` - Working databases
- `backups/` - Backup snapshots
- `*.backup` - Ad-hoc backup files

## Migration from Old Structure

Old structure had all databases in root:
```
database/
├── test-db.json      # Was both default AND runtime
├── test-dm.json
└── ...
```

New structure separates concerns:
```
database/
├── defaults/test-defaults.json   # Factory default
├── runtime/test-db.json          # Working copy
└── test-dm.json                  # Schema (unchanged)
```

**Migration steps:**
1. ✅ Created `defaults/`, `runtime/`, `backups/` directories
2. ✅ Copied existing `*-db.json` to `defaults/*-defaults.json`
3. ✅ Moved existing `*-db.json` to `runtime/`
4. ✅ Updated `.gitignore` to exclude `runtime/` and `backups/`
5. ⏳ Update `agent_db.py` to support new paths (next step)
6. ⏳ Update all agent startup scripts to use `runtime/` paths
7. ⏳ Implement `Device.FactoryReset()` operation
