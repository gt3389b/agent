# End-to-End Tests

Comprehensive E2E tests for USP agent with full MTP integration.

## Test Files

### `test_websocket_mtp.py`
Tests WebSocket MTP end-to-end:
- Boot! and Periodic! notifications
- All USP request types (Get, Set, GetSupportedDM, GetInstances, Operate)
- Concurrent requests
- Error handling
- Connection recovery

### `test_multi_mtp.py`
Tests multi-MTP agent architecture:
- Multiple controllers simultaneously
- Request routing across MTPs
- MTP isolation (no cross-talk)
- Failure isolation
- Stress testing

### `test_usp_operations.py`
Comprehensive USP operation testing:
- Each USP message type individually
- Operation sequences
- Error responses
- Notification types

## Running Tests

```bash
# Run all E2E tests
pytest tests/e2e/ -v

# Run specific test file
pytest tests/e2e/test_websocket_mtp.py -v

# Run with coverage
pytest tests/e2e/ --cov=agent --cov=mtp --cov-report=html

# Run specific test
pytest tests/e2e/test_websocket_mtp.py::test_boot_notification -v -s
```

## Requirements

- pytest
- pytest-asyncio
- websockets
- Running controller (or mock controller in fixtures)

## Test Strategy

1. **Mock controllers** - Tests use pytest fixtures to create mock WebSocket controllers
2. **Agent lifecycle** - Each test starts agent, runs for duration, cancels
3. **Message verification** - Validate protobuf messages received
4. **Timing** - Adequate sleep() calls for async operations
5. **Cleanup** - Fixtures handle server shutdown

## Coverage Goals

- **Line Coverage**: 85%+ overall
- **MTP bindings**: 80%+
- **BaseAgent**: 95%+
- **MultiMTPAgent**: 90%+

## Notes

- Tests require `database/test-dm.json` and `database/test-db.json`
- Mock controllers auto-respond to keep tests fast
- Long-running tests (periodic) use extended timeouts
- Tests are isolated - no shared state between tests
