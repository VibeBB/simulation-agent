"""mruby/c WASM leg: tool detection, compile, gate semantics."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from sim import mrubyc
from sim.brief import MrubycSection


def _stub(tmp_path: Path, name: str, body: str) -> str:
    stub = tmp_path / name
    stub.write_text(body, encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return str(stub)


@pytest.fixture()
def tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    mrubyc_dir = tmp_path / "mrubyc"
    (mrubyc_dir / "src").mkdir(parents=True)
    (mrubyc_dir / "src/alloc.c").write_text("int a;\n", encoding="utf-8")
    (mrubyc_dir / "src/hal.c").write_text("int skip;\n", encoding="utf-8")
    hal = mrubyc_dir / "hal/emscripten"
    hal.mkdir(parents=True)
    (hal / "hal.c").write_text("int h;\n", encoding="utf-8")
    monkeypatch.setenv(mrubyc.MRUBYC_DIR_ENV, str(mrubyc_dir))
    _stub(
        tmp_path,
        "mrbc",
        "#!/bin/sh\n"
        'out=""\nsym=""\n'
        "while [ $# -gt 0 ]; do\n"
        '  case "$1" in -B) sym="$2"; shift 2;; -o) out="$2"; shift 2;; *) shift;; esac\n'
        "done\n"
        'echo "const unsigned char ${sym}[] = {0};" > "$out"\n',
    )
    _stub(
        tmp_path,
        "emcc",
        '#!/bin/sh\nfor last; do :; done\nmkdir -p "$(dirname "$last")" && touch "$last"\n',
    )
    _stub(tmp_path, "node", "#!/bin/sh\necho 'kettle ready'\nexit 0\n")
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    return tmp_path


class TestTools:
    def test_missing_tools_unknown(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PATH", str(tmp_path))
        section = MrubycSection(sources=["ux/app.rb"])
        checks = mrubyc.run_mrubyc(section, tmp_path, tmp_path / "out")
        assert checks[0].id == "mrubyc.tools" and checks[0].verdict == "unknown"

    def test_missing_mrubyc_tree(
        self, tmp_path: Path, tools: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(mrubyc.MRUBYC_DIR_ENV, str(tmp_path / "absent"))
        section = MrubycSection(sources=["ux/app.rb"])
        checks = mrubyc.run_mrubyc(section, tmp_path, tmp_path / "out")
        assert checks[0].verdict == "fail" and "not found" in checks[0].detail

    def test_missing_source(self, tmp_path: Path, tools: Path) -> None:
        section = MrubycSection(sources=["ux/none.rb"])
        checks = mrubyc.run_mrubyc(section, tmp_path, tmp_path / "out")
        assert checks[0].id == "mrubyc.build" and "missing" in checks[0].detail


class TestRun:
    def test_pass_with_transcript(self, tmp_path: Path, tools: Path) -> None:
        ux = tmp_path / "ux"
        ux.mkdir()
        (ux / "app.rb").write_text("puts 'kettle ready'\n", encoding="utf-8")
        section = MrubycSection(sources=["ux/app.rb"], expect=["kettle ready"])
        checks = mrubyc.run_mrubyc(section, tmp_path, tmp_path / "out")
        verdicts = {check.id: check.verdict for check in checks}
        assert verdicts["mrubyc.vm"] == "pass"
        assert verdicts["mrubyc.transcript[kettle ready]"] == "pass"

    def test_transcript_miss_fails(self, tmp_path: Path, tools: Path) -> None:
        ux = tmp_path / "ux"
        ux.mkdir()
        (ux / "app.rb").write_text("puts 'x'\n", encoding="utf-8")
        section = MrubycSection(sources=["ux/app.rb"], expect=["boiling"])
        checks = mrubyc.run_mrubyc(section, tmp_path, tmp_path / "out")
        miss = [check for check in checks if "boiling" in check.id]
        assert miss[0].verdict == "fail"

    def test_node_failure_fails(self, tmp_path: Path, tools: Path) -> None:
        ux = tmp_path / "ux"
        ux.mkdir()
        (ux / "app.rb").write_text("puts 'x'\n", encoding="utf-8")
        node = tmp_path / "node"
        node.write_text("#!/bin/sh\necho vm crash 1>&2; exit 1\n", encoding="utf-8")
        node.chmod(node.stat().st_mode | stat.S_IXUSR)
        section = MrubycSection(sources=["ux/app.rb"])
        checks = mrubyc.run_mrubyc(section, tmp_path, tmp_path / "out")
        assert checks[0].id == "mrubyc.vm" and checks[0].verdict == "fail"
