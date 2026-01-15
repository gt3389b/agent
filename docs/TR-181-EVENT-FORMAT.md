# TR-181 Event Definition Format

## Overview

This document describes the correct format for defining events in TR-181/TR-369 USP data models, based on the official BBF specification at https://usp-data-models.broadband-forum.org/tr-181-2-18-0-usp.html

## Event Definition Structure

Events in TR-181 are defined as **flat data model paths** (not nested under a special section), with their event arguments defined as sub-elements.

### Specification Format (from TR-181)

In the TR-181 specification, events are shown with this notation:

```
Boot! | event | - | Boot event indicating that the Device was rebooted. | - | 2.12 |
⇒ CommandKey | string | R | The command_key supplied when requesting the boot... | - | 2.12 |
⇒ Cause | string | R | The cause of the boot. Enumeration of: LocalReboot... | - | 2.12 |
⇒ Reason | string | R | The reason of the boot (e.g. power on reset...) | - | 2.12 |
⇒ FirmwareUpdated | boolean | R | true if the firmware was updated... | - | 2.12 |
⇒ ParameterMap | string | R | Boot parameters configured... | - | 2.12 |
```

The `⇒` symbol indicates **event arguments** (output parameters of the event).

## JSON Data Model Format

### Correct Format (TR-181 Compliant)

Events should be defined as top-level data model entries with this structure:

```json
{
  "Device.Boot!": {
    "type": "event",
    "description": "Boot event indicating that the Device was rebooted",
    "arguments": {
      "CommandKey": {
        "type": "string",
        "access": "R",
        "description": "The command_key supplied when requesting the boot, or an empty string if the boot was not requested via a USP operation"
      },
      "Cause": {
        "type": "string",
        "access": "R",
        "description": "The cause of the boot",
        "enum": ["LocalReboot", "RemoteReboot", "FactoryReset", "LocalFactoryReset", "RemoteFactoryReset"]
      },
      "Reason": {
        "type": "string",
        "access": "R",
        "description": "The reason of the boot (e.g. power on reset, watchdog, overheat, FAN fault, web userinterface, ...)"
      },
      "FirmwareUpdated": {
        "type": "boolean",
        "access": "R",
        "description": "true if the firmware was updated as a result of the boot that caused this Event Notification; otherwise false"
      },
      "ParameterMap": {
        "type": "string",
        "access": "R",
        "description": "Boot parameters configured via the recipient Controller's LocalAgent.Controller.{i}.BootParameter table. Formatted as a JSON Object"
      }
    },
    "notify_params": [
      "Device.DeviceInfo.ManufacturerOUI",
      "Device.DeviceInfo.ProductClass",
      "Device.DeviceInfo.SerialNumber"
    ]
  }
}
```

### Incorrect Format (Do Not Use)

❌ **WRONG**: Events nested under a special `__EVENTS__` section:

```json
{
  "__EVENTS__": {
    "Device.Boot!": {
      "parameters": ["Device.DeviceInfo.ManufacturerOUI", ...]
    }
  }
}
```

This was a custom format that doesn't match the TR-181 specification.

## TR-181 Standard Events

### Device.Boot!

**Object Path**: `Device.LocalAgent.`  
**Event Name**: `Boot!`

**Arguments** (sent with every Boot! notification):
- `CommandKey` (string): Command key that initiated the boot, or empty string
- `Cause` (string enum): LocalReboot | RemoteReboot | FactoryReset | LocalFactoryReset | RemoteFactoryReset
- `Reason` (string): Human-readable boot reason (e.g., "power on reset", "watchdog")
- `FirmwareUpdated` (boolean): Whether firmware was updated during boot
- `ParameterMap` (string): JSON object containing boot parameters

**Additional Parameters** (optional, included via subscription ReferenceList):
- Typically includes device identification parameters like ManufacturerOUI, ProductClass, SerialNumber

### Device.LocalAgent.Periodic!

**Object Path**: `Device.LocalAgent.`  
**Event Name**: `Periodic!`

**Arguments**: None (periodic event typically has no event-specific arguments)

**Additional Parameters**: Included based on subscription ReferenceList

## USP Protobuf Wire Format

Events are transmitted in USP messages using this structure (from usp-msg-1-4.proto):

```protobuf
message Event {
  string obj_path = 1;      // e.g., "Device.LocalAgent."
  string event_name = 2;    // e.g., "Boot!"
  map<string, string> params = 3;  // Event arguments + subscribed parameters
}
```

The `params` map contains:
1. **Event arguments** (defined in the data model's `arguments` section)
2. **Subscribed parameters** (from subscription's ReferenceList or data model's `notify_params`)

## Implementation Notes

### notify_params vs arguments

- **`arguments`**: TR-181 defined event arguments that are ALWAYS sent with the event (CommandKey, Cause, Reason, etc.)
- **`notify_params`**: Additional device-specific parameters to include in the notification (ManufacturerOUI, ProductClass, etc.)

Both are merged into the USP Event message's `params` map.

### Reading Events from Data Model

```python
# Correct way to read event definition
boot_event = data_model.get("Device.Boot!", {})
if boot_event.get("type") == "event":
    arguments = boot_event.get("arguments", {})
    notify_params = boot_event.get("notify_params", [])
```

### GetSupportedDM Response

When reporting supported events in a GetSupportedDM response, events are reported as:

```
Device.Boot! (event)
  CommandKey (string)
  Cause (string)
  Reason (string)
  FirmwareUpdated (boolean)
  ParameterMap (string)
```

## References

- **TR-181**: Device Data Model - https://usp-data-models.broadband-forum.org/tr-181-2-18-0-usp.html
- **TR-369**: User Services Platform (USP) - https://www.broadband-forum.org/technical/download/TR-369.pdf
- **RFC 7159**: JSON Data Interchange Format
- **Device.Boot! Definition**: TR-181 Section "Device:2.18 Data Model"

## Version History

- **2026-01-15**: Initial documentation based on TR-181 Amendment 18 (2.18)
- Format corrected from custom `__EVENTS__` nested structure to flat TR-181 compliant format
