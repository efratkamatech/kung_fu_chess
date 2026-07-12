from pathlib import Path

import pytest

from runner import program_output

FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURE_INPUTS = sorted(FIXTURES_DIR.glob("*.in"))


@pytest.mark.parametrize("in_path", FIXTURE_INPUTS, ids=lambda p: p.stem)
def test_fixture_output_matches_expected(in_path):
    expected = in_path.with_suffix(".out").read_text()
    assert program_output(in_path.read_text()) == expected
