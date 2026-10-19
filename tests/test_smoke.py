from typer.testing import CliRunner

import jtw
from jtw.cli import app


def test_package_imports() -> None:
    assert jtw.__version__


def test_version_flag() -> None:
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip() == f"jtw {jtw.__version__}"
