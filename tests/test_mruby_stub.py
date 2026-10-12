"""mruby/c device-API stub: spec parsing, codegen, and brief wiring."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from sim import mrubyc
from sim.brief import MrubycSection
from sim.mruby_stub import (
    MrubyApiStubSpec,
    render_stub,
    stub_problems,
)


def _spec() -> dict[str, object]:
    return {
        "artifact_kind": "mruby_api",
        "schema_version": 1,
        "product": "demo",
        "symbols": [
            {"name": "led1", "const": "kLed1"},
            {"name": "led2", "const": "kLed2"},
        ],
        "system_task": {"vm_id": 2},
        "expert_define": "FW_DEBUG_API",
        "classes": [
            {
                "name": "LED",
                "doc": "onboard LEDs",
                "constants": [{"name": "OFF", "value": 0}],
                "methods": [
                    {
                        "name": "set",
                        "doc": "set one LED",
                        "kwargs": [
                            {
                                "name": "part",
                                "type": "symbol",
                                "required": True,
                                "enum": ["led1", "led2"],
                            },
                            {"name": "state", "type": "bool", "required": False},
                        ],
                        "returns": {"type": "bool"},
                        "handler": "hw_led_set",
                    },
                    {
                        "name": "toggle",
                        "params": [{"name": "part", "type": "symbol"}],
                        "returns": {"type": "symbol"},
                        "handler": "hw_led_toggle",
                    },
                    {
                        "name": "dump",
                        "access": "system_task",
                        "returns": {"type": "string", "cap": 64},
                        "handler": "hw_led_dump",
                    },
                    {
                        "name": "raw",
                        "access": "expert",
                        "params": [
                            {"name": "idx", "type": "int"},
                            {"name": "level", "type": "float"},
                        ],
                        "handler": "hw_led_raw",
                    },
                    {
                        "name": "on_change",
                        "rest_kwargs": True,
                        "block": "optional",
                        "arg_errors": "silent",
                        "returns": {"type": "nil"},
                        "handler": "hw_led_on_change",
                    },
                ],
            },
            {
                "name": "Board",
                "kind": "module",
                "methods": [],
            },
            {
                "name": "LedBank",
                "outer": "Board",
                "methods": [{"name": "count", "handler": "hw_bank_count"}],
            },
            {
                "name": "Sample",
                "instance": {
                    "data_size": 16,
                    "constructor": "hw_sample_open",
                    "destructor": "hw_sample_close",
                },
                "methods": [
                    {
                        "name": "read",
                        "params": [{"name": "ch", "type": "int"}],
                        "returns": {"type": "array<float>", "cap": 8},
                        "handler": "hw_sample_read",
                    }
                ],
            },
        ],
    }


def _write_spec(tmp_path: Path, spec: dict[str, object]) -> Path:
    api = tmp_path / "api"
    api.mkdir(exist_ok=True)
    path = api / "demo.mruby-api.json"
    path.write_text(json.dumps(spec), encoding="utf-8")
    return Path("api/demo.mruby-api.json")


class TestSpec:
    def test_minimal_spec(self) -> None:
        spec = MrubyApiStubSpec.model_validate({"schema_version": 1, "product": "x"})
        assert spec.classes == [] and spec.symbols == []

    def test_extra_fields_ignored(self) -> None:
        raw = _spec()
        raw["extra_field"] = "ignored by lenient stub schema"
        spec = MrubyApiStubSpec.model_validate(raw)
        assert spec.classes[0].name == "LED"

    def test_full_spec_round_trip(self) -> None:
        spec = MrubyApiStubSpec.model_validate(_spec())
        led = spec.classes[0]
        assert led.methods[0].kwargs[0].name == "part"
        assert led.methods[2].access == "system_task"
        assert spec.classes[3].instance is not None
        assert spec.system_task is not None and spec.system_task.vm_id == 2


class TestRender:
    def _render(self, spec: dict[str, object] | None = None) -> str:
        model = MrubyApiStubSpec.model_validate(spec or _spec())
        return render_stub(model, "api/demo.mruby-api.json")["sim_api_stub.c"]

    def test_transcript_printf(self) -> None:
        src = self._render()
        assert 'printf("API LED.set(part=%s, state=%s)' in src
        assert "mrbc_symid_to_str(part.sym_id)" in src

    def test_system_task_guard(self) -> None:
        src = self._render()
        assert "if (vm->vm_id != 2u) {" in src
        assert "SET_NIL_RETURN();" in src

    def test_kw_block_and_rest(self) -> None:
        src = self._render()
        assert "MRBC_KW_ARG(part, state);" in src
        assert "if (!MRBC_KW_MANDATORY(part)) break;" in src
        assert "if (!MRBC_KW_END()) break;" in src
        assert "MRBC_KW_DELETE(part, state);" in src
        assert "MRBC_KW_DICT(rest);" in src

    def test_block_arg(self) -> None:
        src = self._render()
        assert "blk = &v[argc + 1];" in src

    def test_arg_errors_silent(self) -> None:
        src = self._render()
        # default arg_errors=raise emits ArgumentError on decode failure
        assert "mrbc_raise(vm, MRBC_CLASS(ArgumentError)" in src
        assert "mrbc_class_ArgumentError" in src

    def test_instance_class(self) -> None:
        src = self._render()
        assert "mrbc_instance_new(vm, v[0].cls, 16u);" in src
        assert "memset(v->instance->data, 0, 16u);" in src
        assert "mrbc_define_destructor(Sample_cls, sim_api_Sample_dtor);" in src

    def test_constants(self) -> None:
        src = self._render()
        assert 'mrbc_set_class_const(LED_cls, mrbc_str_to_symid("OFF"), &k_OFF);' in src

    def test_define_order_nested(self) -> None:
        src = self._render()
        board = src.index('Board_cls = mrbc_define_module(0, "Board");')
        bank = src.index("mrbc_define_class_under(0, Board_cls")
        assert board < bank

    def test_expert_guard(self) -> None:
        src = self._render()
        assert "#if defined(FW_DEBUG_API)" in src

    def test_symbol_return(self) -> None:
        src = self._render()
        assert 'mrbc_symbol_value(mrbc_str_to_symid("led1"))' in src

    def test_header_preamble(self) -> None:
        model = MrubyApiStubSpec.model_validate(_spec())
        header = render_stub(model, "api/demo.mruby-api.json")["sim_api_stub.h"]
        assert "int sim_api_define(void);" in header
        assert "api/demo.mruby-api.json" in header


class TestProblems:
    def test_missing_spec(self, tmp_path: Path) -> None:
        problems = stub_problems(Path("api/none.json"), tmp_path)
        assert problems and "missing" in problems[0]

    def test_invalid_spec(self, tmp_path: Path) -> None:
        api = tmp_path / "api"
        api.mkdir()
        (api / "bad.mruby-api.json").write_text("{not json", encoding="utf-8")
        problems = stub_problems(Path("api/bad.mruby-api.json"), tmp_path)
        assert problems and "invalid" in problems[0]


class TestBriefWiring:
    def test_api_spec_field(self) -> None:
        section = MrubycSection(sources=["ux/app.rb"], api_spec="api/demo.mruby-api.json")
        assert section.api_spec == "api/demo.mruby-api.json"

    def test_bad_spec_fails_api_check(self, tmp_path: Path) -> None:
        ux = tmp_path / "ux"
        ux.mkdir()
        (ux / "app.rb").write_text("puts 'x'\n", encoding="utf-8")
        _write_spec(tmp_path, {"schema_version": 2})
        section = MrubycSection(sources=["ux/app.rb"], api_spec="api/demo.mruby-api.json")
        checks = mrubyc.run_mrubyc(section, tmp_path, tmp_path / "out")
        assert checks[0].id == "mrubyc.api" and checks[0].verdict == "fail"

    def test_stub_written_before_compile(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ux = tmp_path / "ux"
        ux.mkdir()
        (ux / "app.rb").write_text("puts 'x'\n", encoding="utf-8")
        _write_spec(tmp_path, _spec())

        mrubyc_dir = tmp_path / "mrubyc"
        (mrubyc_dir / "src").mkdir(parents=True)
        (mrubyc_dir / "src/alloc.c").write_text("int a;\n", encoding="utf-8")
        hal = mrubyc_dir / "hal/emscripten"
        hal.mkdir(parents=True)
        (hal / "hal.c").write_text("int h;\n", encoding="utf-8")
        monkeypatch.setenv(mrubyc.MRUBYC_DIR_ENV, str(mrubyc_dir))

        for name, body in {
            "mrbc": "#!/bin/sh\n"
            'out=""\nsym=""\n'
            "while [ $# -gt 0 ]; do\n"
            '  case "$1" in -B) sym="$2"; shift 2;; -o) out="$2"; shift 2;; *) shift;; esac\n'
            "done\n"
            'echo "const unsigned char ${sym}[] = {0};" > "$out"\n',
            "emcc": "#!/bin/sh\nfor last; do :; done\n"
            'mkdir -p "$(dirname "$last")" && touch "$last"\n',
            "node": "#!/bin/sh\necho 'API LED.set(part=led1, state=true)'\nexit 0\n",
        }.items():
            stub = tmp_path / name
            stub.write_text(body, encoding="utf-8")
            stub.chmod(stub.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")

        section = MrubycSection(
            sources=["ux/app.rb"],
            api_spec="api/demo.mruby-api.json",
            expect=["API LED.set(part=led1, state=true)"],
        )
        checks = mrubyc.run_mrubyc(section, tmp_path, tmp_path / "out")
        verdicts = {check.id: check.verdict for check in checks}
        assert "mrubyc.api" not in verdicts
        assert verdicts["mrubyc.vm"] == "pass"
        assert verdicts["mrubyc.transcript[API LED.set(part=led1, state=true)]"] == "pass"

        stub_c = tmp_path / "out/mrubyc/api/sim_api_stub.c"
        assert stub_c.is_file()
        shim = (tmp_path / "out/mrubyc/mruby_ux_main.c").read_text(encoding="utf-8")
        assert '#include "api/sim_api_stub.h"' in shim
        assert "sim_api_define();" in shim
