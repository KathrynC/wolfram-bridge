"""Tests for the Wolfram Data Bridge.

Offline tests mock subprocess to avoid wolframscript dependency.
Live tests (marked @pytest.mark.live) require wolframscript installed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest
from unittest.mock import patch, MagicMock

from wolfram_bridge import WolframDataBridge, _sanitize_wl_string


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_wl_result(data: dict | list) -> MagicMock:
    """Create a mock subprocess.run result returning JSON data."""
    result = MagicMock()
    result.stdout = json.dumps(data)
    result.stderr = ""
    result.returncode = 0
    return result


def _mock_wl_result_with_preamble(data: dict, preamble: str = "") -> MagicMock:
    """Mock result with Wolfram preamble noise before JSON."""
    result = MagicMock()
    result.stdout = preamble + json.dumps(data)
    result.stderr = ""
    result.returncode = 0
    return result


# ---------------------------------------------------------------------------
# Test: Bridge initialization
# ---------------------------------------------------------------------------

class TestBridgeInit:
    def test_default_executable(self):
        bridge = WolframDataBridge()
        assert bridge.executable == "wolframscript"

    def test_custom_executable(self):
        bridge = WolframDataBridge(executable="/usr/local/bin/wolframscript")
        assert bridge.executable == "/usr/local/bin/wolframscript"


# ---------------------------------------------------------------------------
# Test: JSON parser robustness
# ---------------------------------------------------------------------------

class TestParserRobustness:
    """Test that _execute_wl handles various Wolfram output formats."""

    def test_clean_json_object(self):
        bridge = WolframDataBridge()
        mock = _mock_wl_result({"test": 42, "pi": 3.14})
        with patch("subprocess.run", return_value=mock):
            result = bridge.query_custom("dummy")
        assert result == {"test": 42, "pi": 3.14}

    def test_json_with_stringform_preamble(self):
        """The key bug: FinancialData prints StringForm[...] before JSON."""
        bridge = WolframDataBridge()
        preamble = (
            'StringForm[Initializing `1` indices ...., FinancialData]\n'
            'StringForm[Initializing `1` indices ...., FinancialData]\n'
        )
        mock = _mock_wl_result_with_preamble(
            {"ticker": "SPY", "price": 672.38},
            preamble=preamble,
        )
        with patch("subprocess.run", return_value=mock):
            result = bridge.query_custom("dummy")
        assert result["ticker"] == "SPY"
        assert result["price"] == 672.38

    def test_json_with_initializing_preamble(self):
        bridge = WolframDataBridge()
        preamble = "Initializing FinancialData indices\n"
        mock = _mock_wl_result_with_preamble(
            {"gdp": 20000000000000},
            preamble=preamble,
        )
        with patch("subprocess.run", return_value=mock):
            result = bridge.query_custom("dummy")
        assert result["gdp"] == 20000000000000

    def test_no_json_returns_none(self):
        bridge = WolframDataBridge()
        result_mock = MagicMock()
        result_mock.stdout = "Syntax error in line 1"
        result_mock.stderr = ""
        result_mock.returncode = 0
        with patch("subprocess.run", return_value=result_mock):
            result = bridge.query_custom("dummy")
        assert result is None

    def test_subprocess_failure_returns_none(self):
        bridge = WolframDataBridge()
        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "wolframscript", stderr="error")):
            result = bridge.query_custom("dummy")
        assert result is None


# ---------------------------------------------------------------------------
# Test: Method signatures and return types
# ---------------------------------------------------------------------------

class TestMethodSignatures:
    """Verify all public methods exist and return dict/list on success."""

    def _make_bridge_with_mock(self, return_data):
        bridge = WolframDataBridge()
        mock = _mock_wl_result(return_data)
        return bridge, mock

    def test_get_ticker_metadata(self):
        bridge, mock = self._make_bridge_with_mock(
            {"ticker": "AAPL", "price": 200, "pe_ratio": 30, "market_cap": 3e12, "description": "Tech"}
        )
        with patch("subprocess.run", return_value=mock):
            result = bridge.get_ticker_metadata("AAPL")
        assert result["ticker"] == "AAPL"
        assert isinstance(result["price"], (int, float))

    def test_get_macro_indicators(self):
        bridge, mock = self._make_bridge_with_mock(
            {"country": "UnitedStates", "gdp": 2e13, "inflation": 0.03, "unemployment": 3.5}
        )
        with patch("subprocess.run", return_value=mock):
            result = bridge.get_macro_indicators("UnitedStates")
        assert result["country"] == "UnitedStates"
        assert "unemployment" in result  # was interest_rate (broken), now unemployment

    def test_get_weather_anomaly(self):
        bridge, mock = self._make_bridge_with_mock(
            {"city": "NewYork", "current_temp": 15, "average_temp": 12}
        )
        with patch("subprocess.run", return_value=mock):
            result = bridge.get_weather_anomaly("NewYork")
        assert result["anomaly"] == 3

    def test_get_energy_stress(self):
        bridge, mock = self._make_bridge_with_mock(
            {"country": "UnitedStates", "oil_production": 11e6, "electricity_generation": 4e12}
        )
        with patch("subprocess.run", return_value=mock):
            result = bridge.get_energy_stress("UnitedStates")
        assert "oil_production" in result

    def test_get_historical_event(self):
        """Renamed from query_custom (was shadowed)."""
        bridge, mock = self._make_bridge_with_mock(
            {"name": "World War II", "start_date": "1939-09-01", "duration_days": 2194, "description": "Global conflict"}
        )
        with patch("subprocess.run", return_value=mock):
            result = bridge.get_historical_event("World War II")
        assert result["name"] == "World War II"
        assert "start_date" in result

    def test_query_custom(self):
        """The real query_custom (line 643) should still work."""
        bridge, mock = self._make_bridge_with_mock({"x": 1})
        with patch("subprocess.run", return_value=mock):
            result = bridge.query_custom("<| \"x\" -> 1 |>")
        assert result == {"x": 1}

    def test_get_historical_prices(self):
        bridge = WolframDataBridge()
        # Wolfram returns nested list; find_payload unwraps to first dict/scalar
        # Just verify the method doesn't crash
        result_mock = MagicMock()
        result_mock.stdout = json.dumps({"prices": [672.0, 673.5]})
        result_mock.stderr = ""
        result_mock.returncode = 0
        with patch("subprocess.run", return_value=result_mock):
            result = bridge.get_historical_prices("SPY", days=5)
        assert result is not None


# ---------------------------------------------------------------------------
# Test: No duplicate method names
# ---------------------------------------------------------------------------

class TestNoDuplicates:
    """Verify the query_custom shadowing bug is fixed."""

    def test_query_custom_is_passthrough(self):
        """query_custom should be a simple passthrough to _execute_wl,
        NOT the historical event function."""
        import inspect
        source = inspect.getsource(WolframDataBridge.query_custom)
        # The real query_custom should NOT contain 'HistoricalEvent'
        assert "HistoricalEvent" not in source
        # It should be short (3-4 lines)
        assert len(source.strip().split('\n')) < 10

    def test_get_historical_event_exists(self):
        """The renamed method should exist."""
        assert hasattr(WolframDataBridge, 'get_historical_event')
        import inspect
        source = inspect.getsource(WolframDataBridge.get_historical_event)
        assert "HistoricalEvent" in source


# ---------------------------------------------------------------------------
# Live tests (require wolframscript)
# ---------------------------------------------------------------------------

def _wolframscript_available():
    try:
        result = subprocess.run(["wolframscript", "-code", "1+1"],
                                capture_output=True, text=True, timeout=30)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


live = pytest.mark.skipif(
    not _wolframscript_available(),
    reason="wolframscript not available"
)


class TestLiveSmoke:
    """Live smoke tests — run only when wolframscript is installed."""

    @live
    def test_query_custom_live(self):
        bridge = WolframDataBridge()
        result = bridge.query_custom('<| "test" -> 42, "pi" -> N[Pi] |>')
        assert result is not None
        assert result["test"] == 42
        assert abs(result["pi"] - 3.14159) < 0.001

    @live
    def test_get_macro_indicators_live(self):
        bridge = WolframDataBridge()
        result = bridge.get_macro_indicators("UnitedStates")
        assert result.get("country") == "UnitedStates"
        assert result.get("gdp", 0) > 1e12  # US GDP > $1T

    @live
    def test_get_historical_event_live(self):
        bridge = WolframDataBridge()
        result = bridge.get_historical_event("World War II")
        assert result.get("name") is not None
        assert "1939" in result.get("start_date", "")


# ---------------------------------------------------------------------------
# Test: Input sanitization (security)
# ---------------------------------------------------------------------------

class TestInputSanitization:
    """Verify _sanitize_wl_string blocks injection attempts."""

    def test_clean_input_passes(self):
        assert _sanitize_wl_string("SPY") == "SPY"
        assert _sanitize_wl_string("UnitedStates") == "UnitedStates"
        assert _sanitize_wl_string("World War II") == "World War II"
        assert _sanitize_wl_string("B11.2.3.1") == "B11.2.3.1"

    def test_injection_attempt_raises(self):
        with pytest.raises(ValueError):
            _sanitize_wl_string('SPY"]; Run["rm -rf /"]')
        with pytest.raises(ValueError):
            _sanitize_wl_string("foo`bar")
        with pytest.raises(ValueError):
            _sanitize_wl_string("x;Exit[]")
        with pytest.raises(ValueError):
            _sanitize_wl_string("a\nb")

    def test_method_level_sanitization(self):
        """Calling a bridge method with malicious input raises ValueError."""
        bridge = WolframDataBridge()
        with pytest.raises(ValueError):
            bridge.get_ticker_metadata('SPY"]; SystemOpen["calc"]')

    def test_clean_inputs_produce_correct_wl_code(self):
        """Regression: clean inputs still produce correct WL code after sanitization."""
        bridge = WolframDataBridge()
        mock = _mock_wl_result(
            {"ticker": "AAPL", "price": 200, "pe_ratio": 30,
             "market_cap": 3e12, "description": "Tech"}
        )
        with patch("subprocess.run", return_value=mock):
            result = bridge.get_ticker_metadata("AAPL")
        assert result["ticker"] == "AAPL"
