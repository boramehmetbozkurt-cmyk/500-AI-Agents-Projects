import importlib
import sys
import types

# The helper under test is pure. Stub Playwright so the standard unit-test job
# does not need to install a browser-only benchmark dependency just to import it.
async_api = types.ModuleType("playwright.async_api")
async_api.async_playwright = None
sys.modules.setdefault("playwright", types.ModuleType("playwright"))
sys.modules.setdefault("playwright.async_api", async_api)

validation = importlib.import_module("run_browser_strategic_validation")
BUDGET_ERROR_CODE = validation.BUDGET_ERROR_CODE
PLATFORM_UNAVAILABLE_CODE = validation.PLATFORM_UNAVAILABLE_CODE
_platform_block_reason = validation._platform_block_reason


def test_daily_budget_error_is_a_platform_block():
    assert _platform_block_reason("AI daily token budget exceeded") == BUDGET_ERROR_CODE


def test_appdeploy_402_unavailable_is_a_platform_block():
    message = (
        'Request failed with status code 402 | {"code":"APP_TEMPORARILY_UNAVAILABLE",'
        '"message":"This app is temporarily unavailable."}'
    )
    assert _platform_block_reason(message) == PLATFORM_UNAVAILABLE_CODE


def test_ordinary_execution_error_is_not_a_platform_block():
    assert _platform_block_reason("invalid benchmark payload") is None
