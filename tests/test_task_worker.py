from unittest.mock import Mock

from scripts.task_worker import _configure_utf8_streams


def test_worker_configures_console_streams_for_utf8():
    stdout = Mock()
    stderr = Mock()

    _configure_utf8_streams(stdout, stderr)

    stdout.reconfigure.assert_called_once_with(
        encoding="utf-8", errors="backslashreplace"
    )
    stderr.reconfigure.assert_called_once_with(
        encoding="utf-8", errors="backslashreplace"
    )


def test_worker_accepts_streams_without_reconfigure():
    _configure_utf8_streams(object(), object())
