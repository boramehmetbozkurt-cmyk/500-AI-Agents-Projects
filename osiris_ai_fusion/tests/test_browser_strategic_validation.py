from run_browser_strategic_validation import (
    BUDGET_ERROR_CODE,
    PLATFORM_UNAVAILABLE_CODE,
    _platform_block_reason,
)


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
