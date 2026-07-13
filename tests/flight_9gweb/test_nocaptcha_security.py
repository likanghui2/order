from pathlib import Path


def test_nocaptcha_utility_has_no_debug_output_or_embedded_credentials():
    source = (Path(__file__).parents[2] / "common/utils/nocaptcha_util.py").read_text()

    assert "print(" not in source
    assert "if __name__ ==" not in source
    assert "http://api.nocaptcha" not in source
