import deployment.system_tray as tray


def test_access_denied_error_is_detected():
    assert tray.is_access_denied_error("OpenService FAILED 5: Access is denied.")
    assert tray.is_access_denied_error("STOP: Access is denied")
    assert not tray.is_access_denied_error("The specified service does not exist as an installed service.")
