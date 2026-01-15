# Device.FactoryReset() Implementation

## Overview

This implementation provides full support for the USP `Device.FactoryReset()` operation with a robust 3-tier database architecture (defaults/runtime/backups).

## Architecture

### 3-Tier Database Structure

```
database/
├── defaults/              # Factory defaults (version controlled)
│   ├── test-defaults.json
│   ├── camera-defaults.json
│   └── motion-defaults.json
│
├── runtime/               # Working databases (gitignored)
│   ├── test-db.json
│   ├── camera-db.json
│   └── motion-db.json
│
├── backups/               # Timestamped backups (gitignored)
│   └── 20260115_185333_test-db.json
│
└── *.dm.json             # Data models (version controlled)
```

### Benefits

- **Factory defaults**: Version controlled, immutable reference state
- **Runtime databases**: Working state, gitignored, can be reset
- **Timestamped backups**: Audit trail before factory reset
- **Auto-restore**: First startup automatically restores from defaults

## Implementation Details

### Database Class (agent/agent_db.py)

#### New Methods

1. **`_get_defaults_path(runtime_path)`**
   - Converts runtime path to defaults path
   - Example: `database/runtime/test-db.json` → `database/defaults/test-defaults.json`

2. **`_restore_from_defaults(runtime_path)`**
   - Copies factory defaults to runtime location
   - Creates runtime directory if needed
   - Used during startup and factory reset

3. **`_create_backup()`**
   - Creates timestamped backup in `database/backups/`
   - Format: `YYYYMMDD_HHMMSS_<filename>.json`
   - Returns backup path for logging

4. **`factory_reset()`**
   - Public method to reset database to factory defaults
   - Creates backup before reset
   - Restores from defaults
   - Reloads database in memory
   - Resets uptime counter

#### Updated Methods

1. **`__init__(dm_filename, db_filename, net_intf)`**
   - Auto-restores from defaults if runtime DB doesn't exist
   - Enables clean first-startup experience

### BaseAgent Class (agent/base_agent.py)

#### Device.FactoryReset() Handler

```python
async def on_operate_request(self, request):
    """Handle Operate request - supports Device.FactoryReset()"""
    
    if request.command == "Device.FactoryReset()":
        # Perform factory reset on database
        self._db.factory_reset()
        
        # Success response
        response = OperateResponse(
            msg_id=request.msg_id,
            command=request.command,
            output_args={"Status": "Success"}
        )
        
        # Schedule delayed reboot (allows response to be sent first)
        async def delayed_reboot():
            await asyncio.sleep(1)
            # Agent would restart here in production
        
        asyncio.create_task(delayed_reboot())
        return response
```

## Testing

### Test Suite (tests/e2e/test_factory_reset.py)

**4 passing tests:**

1. **`test_factory_reset_restores_defaults`**
   - Modifies parameters
   - Executes factory reset
   - Verifies restoration to defaults

2. **`test_factory_reset_creates_backup`**
   - Verifies timestamped backup creation
   - Checks backup filename format
   - Confirms backup count increases

3. **`test_factory_reset_reloads_database`**
   - Modifies in-memory values
   - Executes factory reset
   - Verifies memory reloaded from defaults

4. **`test_auto_restore_on_missing_runtime_db`**
   - Removes runtime database
   - Initializes Database class
   - Verifies auto-restore from defaults

### Demo Script (demo_factory_reset.py)

Interactive demonstration showing:
- Loading agent database
- Modifying parameters (simulating runtime changes)
- Executing factory reset
- Verifying restoration to defaults
- Checking backup creation

Run with:
```bash
python demo_factory_reset.py
```

## Usage Examples

### Manual Factory Reset (Python)

```python
from agent.agent_db import Database

# Load database
db = Database('database/test-dm.json', 'database/runtime/test-db.json', 'eth0')

# Perform factory reset
db.factory_reset()
# → Creates backup at database/backups/20260115_185333_test-db.json
# → Restores from database/defaults/test-defaults.json
# → Reloads database in memory
```

### USP Operation (Controller → Agent)

```
Request:
  msg_id: "reset-001"
  command: "Device.FactoryReset()"
  input_args: {}

Response:
  msg_id: "reset-001"
  command: "Device.FactoryReset()"
  output_args: {"Status": "Success"}
  error: null

Agent Actions:
  1. Create backup: database/backups/20260115_185333_test-db.json
  2. Restore from: database/defaults/test-defaults.json
  3. Reload database in memory
  4. Send success response
  5. Schedule reboot (delayed 1 second)
```

### First Startup (Auto-Restore)

```python
# Runtime database doesn't exist
# → Database.__init__ detects missing runtime DB
# → Automatically restores from database/defaults/test-defaults.json
# → Creates database/runtime/test-db.json
# → Agent starts normally with factory defaults
```

## Migration from Legacy

### Old Structure
```
database/
├── test-db.json        # Working database (version controlled)
├── camera-db.json
└── motion-db.json
```

### New Structure
```
database/
├── defaults/           # Factory state (version controlled)
│   ├── test-defaults.json
│   ├── camera-defaults.json
│   └── motion-defaults.json
├── runtime/            # Working state (gitignored)
│   ├── test-db.json
│   ├── camera-db.json
│   └── motion-db.json
└── backups/            # Audit trail (gitignored)
```

### Updated References

1. **Agent startup** (agent/main.py):
   ```python
   # Old
   db_file_name = "database/{}-db.json".format(client_type)
   
   # New
   db_file_name = "database/runtime/{}-db.json".format(client_type)
   ```

2. **E2E tests** (tests/e2e/):
   ```python
   # Old
   agent = MultiMTPAgent('database/test-dm.json', 'database/test-db.json')
   
   # New
   agent = MultiMTPAgent('database/test-dm.json', 'database/runtime/test-db.json')
   ```

## File Changes

### Modified Files
- `agent/agent_db.py` (+80 lines): Factory reset methods
- `agent/base_agent.py` (+44 lines): Device.FactoryReset() handler
- `agent/main.py` (1 line): Use runtime/ path
- `tests/e2e/test_*.py` (3 files): Use runtime/ paths

### New Files
- `tests/e2e/test_factory_reset.py` (184 lines): Comprehensive test suite
- `demo_factory_reset.py` (133 lines): Interactive demonstration

### Database Files
- `database/defaults/*.json`: Factory defaults (version controlled)
- `database/runtime/*.json`: Working databases (gitignored)
- `database/backups/*.json`: Timestamped backups (gitignored)

## Error Handling

### Missing Defaults File
```python
FileNotFoundError: Factory defaults not found at database/defaults/test-defaults.json
```
**Resolution**: Ensure defaults file exists and is version controlled

### JSON Parse Error
```python
ValueError: Persisted Database is NOT properly formatted JSON
```
**Resolution**: Database loads but with empty dict, logged as error

### File Write Permission
```python
PermissionError: [Errno 13] Permission denied: 'database/runtime/test-db.json'
```
**Resolution**: Check file/directory permissions, ensure writable

## Future Enhancements

1. **Agent Restart**: Implement actual agent restart after factory reset
2. **Selective Reset**: Support partial reset (e.g., only network settings)
3. **Backup Management**: Auto-cleanup old backups (retention policy)
4. **Boot! Notification**: Send Boot! with Cause="RemoteFactoryReset"
5. **Subscription Cleanup**: Clear all subscriptions on factory reset
6. **Concurrent Reset**: Add locking to prevent concurrent reset operations

## References

- USP Specification: [TR-369 Device.FactoryReset()](https://usp.technology/)
- Database README: `database/README.md`
- Test Suite: `tests/e2e/test_factory_reset.py`
- Demo Script: `demo_factory_reset.py`

## Commits

- `286e3f7`: Implement Device.FactoryReset() with 3-tier database architecture
- `7151402`: Add factory reset demonstration script
