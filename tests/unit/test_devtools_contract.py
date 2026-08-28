from omnibot import devtools
from omnibot import actions


def test_normalize_console_entry_keeps_level_text_and_url():
    entry = devtools.normalize_console_entry({"level": "error", "text": "Boom", "url": "https://example.com/app.js", "lineNumber": 12})
    assert entry == {"level": "error", "text": "Boom", "url": "https://example.com/app.js", "line": 12}


def test_network_summary_counts_status_codes():
    summary = devtools.network_summary([{"status": 200}, {"status": 404}, {"status": 500}])
    assert summary["total"] == 3
    assert summary["errors"] == 2


def test_console_text_from_error_object_keeps_message_and_stack():
    text = devtools.console_arg_text({
        "type": "object",
        "subtype": "error",
        "description": "Error: console-error-object-test\n    at app.js:10:5",
    })
    assert "console-error-object-test" in text
    assert text.startswith("Error:")


def test_console_text_from_plain_object_uses_json_preview():
    text = devtools.console_arg_text({
        "type": "object",
        "value": {"code": 123, "message": "complex-object"},
    })
    assert "complex-object" in text
    assert "123" in text


def test_normalize_runtime_console_api_called_event():
    entry = devtools.normalize_cdp_console_event({
        "method": "Runtime.consoleAPICalled",
        "params": {
            "type": "error",
            "args": [{"type": "string", "value": "boom"}],
            "timestamp": 1781699387000,
            "stackTrace": {"callFrames": [{"url": "https://example.com/app.js", "lineNumber": 41}]},
        },
    })
    assert entry == {
        "level": "error",
        "text": "boom",
        "url": "https://example.com/app.js",
        "line": 42,
        "timestamp": 1781699387000,
        "source": "cdp:Runtime.consoleAPICalled",
    }


def test_normalize_runtime_exception_thrown_event():
    entry = devtools.normalize_cdp_console_event({
        "method": "Runtime.exceptionThrown",
        "params": {
            "timestamp": 1781699388000,
            "exceptionDetails": {
                "text": "Uncaught",
                "url": "https://example.com/app.js",
                "lineNumber": 9,
                "exception": {"description": "Error: uncaught-exception-test"},
            },
        },
    })
    assert entry["level"] == "error"
    assert "uncaught-exception-test" in entry["text"]
    assert entry["url"] == "https://example.com/app.js"
    assert entry["line"] == 10
    assert entry["source"] == "cdp:Runtime.exceptionThrown"


def test_normalize_log_entry_added_event():
    entry = devtools.normalize_cdp_console_event({
        "method": "Log.entryAdded",
        "params": {
            "entry": {
                "level": "error",
                "text": "Failed to load resource: net::ERR_FAILED",
                "url": "https://example.com/api/login",
                "lineNumber": 0,
                "timestamp": 1781699389000,
            }
        },
    })
    assert entry["level"] == "error"
    assert "Failed to load resource" in entry["text"]
    assert entry["url"] == "https://example.com/api/login"
    assert entry["source"] == "cdp:Log.entryAdded"


def test_normalize_network_request_event():
    entry = devtools.normalize_network_event({
        "method": "Network.requestWillBeSent",
        "params": {
            "requestId": "123.1",
            "type": "XHR",
            "documentURL": "https://shop.example/item",
            "request": {
                "url": "https://api.example/order/confirm",
                "method": "POST",
                "headers": {"content-type": "application/json"},
                "postData": "{\"sku\":\"100067675226\"}",
            },
            "timestamp": 10.5,
        },
        "timestamp": 1710000000000,
    })

    assert entry["event"] == "request"
    assert entry["request_id"] == "123.1"
    assert entry["method"] == "POST"
    assert entry["url"] == "https://api.example/order/confirm"
    assert entry["host"] == "api.example"
    assert entry["resource_type"] == "XHR"
    assert entry["post_data"] == "{\"sku\":\"100067675226\"}"


def test_normalize_network_response_event():
    entry = devtools.normalize_network_event({
        "method": "Network.responseReceived",
        "params": {
            "requestId": "123.1",
            "type": "Fetch",
            "response": {
                "url": "https://api.example/order/confirm",
                "status": 200,
                "mimeType": "application/json",
            },
        },
        "timestamp": 1710000001000,
    })

    assert entry["event"] == "response"
    assert entry["status"] == 200
    assert entry["mime_type"] == "application/json"
    assert entry["host"] == "api.example"


def test_normalize_network_loading_failed_event():
    entry = devtools.normalize_network_event({
        "method": "Network.loadingFailed",
        "params": {
            "requestId": "456.2",
            "url": "https://cdn.example/app.js",
            "errorText": "net::ERR_ABORTED",
            "blockedReason": "csp",
        },
        "timestamp": 1710000002000,
    })

    assert entry["event"] == "loadingFailed"
    assert entry["url"] == "https://cdn.example/app.js"
    assert entry["host"] == "cdn.example"
    assert entry["error_text"] == "net::ERR_ABORTED"
    assert entry["blocked_reason"] == "csp"


def test_network_summary_groups_api_hosts_and_failures():
    summary = devtools.network_summary([
        {"event": "request", "method": "POST", "url": "https://api.example/order", "host": "api.example", "resource_type": "XHR"},
        {"event": "response", "status": 200, "url": "https://api.example/order", "host": "api.example", "resource_type": "XHR"},
        {"event": "loadingFailed", "url": "https://cdn.example/a.js", "host": "cdn.example", "error_text": "net::ERR_ABORTED"},
    ])

    assert summary["total"] == 3
    assert summary["status_counts"] == {"200": 1}
    assert summary["hosts"]["api.example"] == 2
    assert summary["methods"]["POST"] == 1
    assert summary["resource_types"]["XHR"] == 2
    assert summary["failures"] == 1
    assert summary["api_candidates"] == ["https://api.example/order"]


def test_console_clear_script_calls_page_console_clear():
    script = actions._console_hook_script(clear=True)

    assert "console.clear()" in script
