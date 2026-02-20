#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Helper for adding DescriptorSpec entries to descriptor_catalog.py.

Default mode is plain CLI / prompt-driven input with no UI dependencies.
An optional Textual UI is available via ``--ui`` when installed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

try:
    from textual.app import App
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.widgets import Button, Checkbox, Footer, Header, Input, Label, Static
except ImportError:  # pragma: no cover - optional dependency
    App = None
    Horizontal = None
    Vertical = None
    VerticalScroll = None
    Button = None
    Checkbox = None
    Footer = None
    Header = None
    Input = None
    Label = None
    Static = None


_VALID_NAME_RE: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_VALID_STRATEGIES: Final = ("ctk", "other", "driver")
_FORM_FIELDS: Final = (
    "name",
    "strategy",
    "linux_sonames",
    "windows_dlls",
    "site_packages_linux",
    "site_packages_windows",
    "dependencies",
    "anchor_rel_dirs_linux",
    "anchor_rel_dirs_windows",
    "requires_add_dll_directory",
    "requires_rtld_deepbind",
)


@dataclass(frozen=True)
class DescriptorInput:
    name: str
    strategy: str
    linux_sonames: tuple[str, ...]
    windows_dlls: tuple[str, ...]
    site_packages_linux: tuple[str, ...]
    site_packages_windows: tuple[str, ...]
    dependencies: tuple[str, ...]
    anchor_rel_dirs_linux: tuple[str, ...]
    anchor_rel_dirs_windows: tuple[str, ...]
    requires_add_dll_directory: bool
    requires_rtld_deepbind: bool


def _default_catalog_path() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "cuda_pathfinder"
        / "cuda"
        / "pathfinder"
        / "_dynamic_libs"
        / "descriptor_catalog.py"
    )


def _quote(s: str) -> str:
    return json.dumps(s)


def _format_tuple(values: tuple[str, ...]) -> str:
    if not values:
        return "()"
    inner = ", ".join(_quote(v) for v in values)
    if len(values) == 1:
        inner += ","
    return f"({inner})"


def _parse_csv_tuple(raw: str) -> tuple[str, ...]:
    parts = [part.strip() for part in raw.split(",")]
    return tuple(part for part in parts if part)


def _parse_bool(raw: str) -> bool:
    lowered = raw.strip().lower()
    if lowered in ("1", "true", "yes", "y", "on"):
        return True
    if lowered in ("0", "false", "no", "n", "off"):
        return False
    raise ValueError(f"Invalid boolean value: {raw!r}")


def _all_form_fields_supplied(args: argparse.Namespace) -> bool:
    return all(getattr(args, field) is not None for field in _FORM_FIELDS)


def _extract_existing_names(catalog_text: str) -> set[str]:
    return set(re.findall(r'^\s*name="([^"]+)",\s*$', catalog_text, flags=re.MULTILINE))


def validate_descriptor_input(spec: DescriptorInput) -> None:
    if not spec.name:
        raise ValueError("Library name is required")
    if not _VALID_NAME_RE.match(spec.name):
        raise ValueError(f"Invalid library name {spec.name!r}: must be a valid Python identifier")
    if spec.strategy not in _VALID_STRATEGIES:
        raise ValueError(f"Invalid strategy {spec.strategy!r}. Expected one of {_VALID_STRATEGIES!r}")
    if not spec.linux_sonames and not spec.windows_dlls:
        raise ValueError("At least one Linux SONAME or Windows DLL is required")


def render_descriptor_block(spec: DescriptorInput) -> str:
    validate_descriptor_input(spec)
    lines = [
        "    DescriptorSpec(",
        f'        name="{spec.name}",',
        f'        strategy="{spec.strategy}",',
        f"        linux_sonames={_format_tuple(spec.linux_sonames)},",
        f"        windows_dlls={_format_tuple(spec.windows_dlls)},",
        f"        site_packages_linux={_format_tuple(spec.site_packages_linux)},",
        f"        site_packages_windows={_format_tuple(spec.site_packages_windows)},",
        f"        dependencies={_format_tuple(spec.dependencies)},",
        f"        anchor_rel_dirs_linux={_format_tuple(spec.anchor_rel_dirs_linux)},",
        f"        anchor_rel_dirs_windows={_format_tuple(spec.anchor_rel_dirs_windows)},",
        f"        requires_add_dll_directory={spec.requires_add_dll_directory},",
        f"        requires_rtld_deepbind={spec.requires_rtld_deepbind},",
        "    ),",
    ]
    return "\n".join(lines)


_CATALOG_END_SENTINEL: Final = ")  # END DESCRIPTOR_CATALOG"


def merge_descriptor_block(catalog_text: str, spec: DescriptorInput) -> str:
    existing_names = _extract_existing_names(catalog_text)
    if spec.name in existing_names:
        raise ValueError(f"Descriptor {spec.name!r} already exists in catalog")

    sentinel_pos = catalog_text.find(_CATALOG_END_SENTINEL)
    if sentinel_pos < 0:
        raise ValueError("Could not locate END DESCRIPTOR_CATALOG sentinel in catalog file")

    block = render_descriptor_block(spec)
    return catalog_text[:sentinel_pos] + block + "\n" + catalog_text[sentinel_pos:]


def apply_descriptor(catalog_path: Path, spec: DescriptorInput, *, dry_run: bool = False) -> str:
    original = catalog_path.read_text(encoding="utf-8")
    updated = merge_descriptor_block(original, spec)
    if not dry_run:
        catalog_path.write_text(updated, encoding="utf-8")
    return updated


def _build_input_from_args(args: argparse.Namespace) -> DescriptorInput:
    missing = [field for field in _FORM_FIELDS if getattr(args, field) is None]
    if missing:
        missing_joined = ", ".join(missing)
        raise ValueError(f"Missing required argument(s): {missing_joined}")

    return DescriptorInput(
        name=str(args.name),
        strategy=str(args.strategy),
        linux_sonames=_parse_csv_tuple(str(args.linux_sonames)),
        windows_dlls=_parse_csv_tuple(str(args.windows_dlls)),
        site_packages_linux=_parse_csv_tuple(str(args.site_packages_linux)),
        site_packages_windows=_parse_csv_tuple(str(args.site_packages_windows)),
        dependencies=_parse_csv_tuple(str(args.dependencies)),
        anchor_rel_dirs_linux=_parse_csv_tuple(str(args.anchor_rel_dirs_linux)),
        anchor_rel_dirs_windows=_parse_csv_tuple(str(args.anchor_rel_dirs_windows)),
        requires_add_dll_directory=_parse_bool(str(args.requires_add_dll_directory)),
        requires_rtld_deepbind=_parse_bool(str(args.requires_rtld_deepbind)),
    )


def _prompt_text(label: str, default: str = "") -> str:
    prompt = f"{label}: " if not default else f"{label} [{default}]: "
    raw = input(prompt).strip()
    if raw:
        return raw
    return default


def _prompt_bool(label: str, default: bool) -> bool:
    default_text = "true" if default else "false"
    while True:
        raw = _prompt_text(label, default_text)
        try:
            return _parse_bool(raw)
        except ValueError:
            print(f"Invalid boolean value: {raw!r}. Use true/false.", file=sys.stderr)


def _bool_arg_or_default(args: argparse.Namespace, field: str, default: bool) -> bool:
    raw = getattr(args, field)
    if raw is None:
        return default
    return _parse_bool(str(raw))


def _build_input_from_prompt(args: argparse.Namespace) -> DescriptorInput:
    print("Interactive prompt mode (no UI). Press Ctrl+C to cancel.", file=sys.stderr)
    name = _prompt_text("name", str(args.name or ""))
    strategy = _prompt_text("strategy", str(args.strategy or "ctk"))
    linux_sonames = _prompt_text("linux-sonames", str(args.linux_sonames or ""))
    windows_dlls = _prompt_text("windows-dlls", str(args.windows_dlls or ""))
    site_packages_linux = _prompt_text("site-packages-linux", str(args.site_packages_linux or ""))
    site_packages_windows = _prompt_text("site-packages-windows", str(args.site_packages_windows or ""))
    dependencies = _prompt_text("dependencies", str(args.dependencies or ""))
    anchor_rel_dirs_linux = _prompt_text("anchor-rel-dirs-linux", str(args.anchor_rel_dirs_linux or "lib64,lib"))
    anchor_rel_dirs_windows = _prompt_text("anchor-rel-dirs-windows", str(args.anchor_rel_dirs_windows or "bin/x64,bin"))

    default_add_dll = _bool_arg_or_default(args, "requires_add_dll_directory", False)
    default_deepbind = _bool_arg_or_default(args, "requires_rtld_deepbind", False)
    requires_add_dll_directory = _prompt_bool("requires-add-dll-directory", default_add_dll)
    requires_rtld_deepbind = _prompt_bool("requires-rtld-deepbind", default_deepbind)

    return DescriptorInput(
        name=name,
        strategy=strategy,
        linux_sonames=_parse_csv_tuple(linux_sonames),
        windows_dlls=_parse_csv_tuple(windows_dlls),
        site_packages_linux=_parse_csv_tuple(site_packages_linux),
        site_packages_windows=_parse_csv_tuple(site_packages_windows),
        dependencies=_parse_csv_tuple(dependencies),
        anchor_rel_dirs_linux=_parse_csv_tuple(anchor_rel_dirs_linux),
        anchor_rel_dirs_windows=_parse_csv_tuple(anchor_rel_dirs_windows),
        requires_add_dll_directory=requires_add_dll_directory,
        requires_rtld_deepbind=requires_rtld_deepbind,
    )


def _can_use_terminal_form() -> bool:
    return App is not None and sys.stdin.isatty() and sys.stdout.isatty()


def _build_input_from_textual_form(args: argparse.Namespace) -> tuple[DescriptorInput | None, bool]:
    if not _can_use_terminal_form():
        return None, False

    # Narrow types after the guard above confirms imports succeeded.
    assert App is not None and Input is not None and Static is not None  # type: narrow

    class DescriptorFormApp(App[DescriptorInput | None]):
        TITLE = "Add NVIDIA Library Descriptor"

        CSS = """
        Screen {
            align: center middle;
        }

        #form-container {
            width: 140;
            height: auto;
            max-height: 95%;
            padding: 0 2;
            border: round $panel;
        }

        .field-row {
            height: auto;
        }

        .field-label-col {
            width: 56;
            height: auto;
            padding: 0 1 0 0;
        }

        .field-label-col Label {
            text-style: bold;
        }

        .field-label-col .hint {
            color: $text-muted;
            text-style: italic;
        }

        .field-input-col {
            width: 1fr;
            height: auto;
        }

        .field-input-col Input {
            width: 1fr;
        }

        .field-error {
            color: $error;
            height: auto;
            margin: 0 0 1 1;
        }

        .bool-group {
            height: auto;
        }

        .bool-group Checkbox {
            text-style: bold;
        }

        .bool-group .hint {
            color: $text-muted;
            text-style: italic;
            padding: 0 0 0 4;
        }

        #status {
            color: $error;
            height: auto;
        }

        #actions {
            margin: 1 0 0 0;
            height: auto;
        }

        #actions Button {
            margin: 0 1 0 0;
        }
        """

        BINDINGS = [("ctrl+c", "quit", "Cancel")]

        # Fields whose values/placeholders are derived from the library name.
        _SEEDABLE_FIELDS: Final = frozenset(
            {
                "linux_sonames",
                "windows_dlls",
                "site_packages_linux",
                "site_packages_windows",
            }
        )

        def __init__(self, initial_args: argparse.Namespace):
            super().__init__()
            self._initial_args = initial_args
            self._user_touched: set[str] = set()

        def _seed_text(self, key: str, default: str) -> str:
            value = getattr(self._initial_args, key)
            if value is None:
                return default
            return str(value)

        def _seed_bool(self, key: str, default: bool) -> bool:
            raw = getattr(self._initial_args, key)
            if raw is None:
                return default
            try:
                return _parse_bool(str(raw))
            except ValueError:
                return default

        def _input_value(self, field_id: str, *, use_placeholder: bool = False) -> str:
            widget = self.query_one(f"#{field_id}", Input)
            val = widget.value.strip()
            if not val and use_placeholder:
                val = widget.placeholder.strip()
            return val

        def _collect_input(self) -> DescriptorInput:
            return DescriptorInput(
                name=self._input_value("name"),
                strategy=self._input_value("strategy") or "ctk",
                linux_sonames=_parse_csv_tuple(self._input_value("linux_sonames")),
                windows_dlls=_parse_csv_tuple(self._input_value("windows_dlls")),
                site_packages_linux=_parse_csv_tuple(self._input_value("site_packages_linux", use_placeholder=True)),
                site_packages_windows=_parse_csv_tuple(
                    self._input_value("site_packages_windows", use_placeholder=True)
                ),
                dependencies=_parse_csv_tuple(self._input_value("dependencies")),
                anchor_rel_dirs_linux=_parse_csv_tuple(self._input_value("anchor_rel_dirs_linux") or "lib64,lib"),
                anchor_rel_dirs_windows=_parse_csv_tuple(self._input_value("anchor_rel_dirs_windows") or "bin/x64,bin"),
                requires_add_dll_directory=self.query_one("#requires_add_dll_directory", Checkbox).value,
                requires_rtld_deepbind=self.query_one("#requires_rtld_deepbind", Checkbox).value,
            )

        _TEXT_FIELDS: Final = (
            ("name", "Library name", "Short identifier, e.g. cudart, cublas, nvvm.", "", "e.g. cudart"),
            (
                "strategy",
                "Strategy",
                "ctk = CUDA Toolkit, other = separate package, driver = display driver.",
                "ctk",
                "",
            ),
            (
                "linux_sonames",
                "Linux SONAMEs",
                "Versioned .so names, e.g. libcudart.so.12",
                "",
                "libfoo.so.1,libfoo.so.2",
            ),
            ("windows_dlls", "Windows DLLs", "DLL filenames, e.g. cudart64_12.dll", "", "foo64_12.dll"),
            (
                "site_packages_linux",
                "site-packages linux dirs",
                "Paths under site-packages for .so, e.g. nvidia/cublas/lib",
                "",
                "nvidia/foo/lib",
            ),
            (
                "site_packages_windows",
                "site-packages windows dirs",
                "Paths under site-packages for .dll, e.g. nvidia/cublas/bin",
                "",
                "nvidia/foo/bin",
            ),
            (
                "dependencies",
                "Dependencies",
                "Other library names loaded first (comma-separated).",
                "",
                "cudart,cublasLt",
            ),
            (
                "anchor_rel_dirs_linux",
                "Anchor linux dirs",
                "Subdirs under CTK root on Linux. Most libs use lib64,lib.",
                "lib64,lib",
                "",
            ),
            (
                "anchor_rel_dirs_windows",
                "Anchor windows dirs",
                "Subdirs under CTK root on Windows. Most libs use bin/x64,bin.",
                "bin/x64,bin",
                "",
            ),
        )

        _BOOL_FIELDS: Final = (
            (
                "requires_add_dll_directory",
                "Requires AddDllDirectory",
                "Enable if Windows needs AddDllDirectory() for transitive DLL deps.",
            ),
            (
                "requires_rtld_deepbind",
                "Requires RTLD_DEEPBIND",
                "Enable if the library needs RTLD_DEEPBIND on Linux to isolate symbols.",
            ),
        )

        def on_mount(self) -> None:
            self.query_one("#form-container", VerticalScroll).can_focus = False
            self.query_one("#name", Input).focus()

        def compose(self):
            yield Header(show_clock=False)
            with VerticalScroll(id="form-container"):
                for fid, label, hint, default, placeholder in self._TEXT_FIELDS:
                    with Horizontal(classes="field-row"):
                        with Vertical(classes="field-label-col"):
                            yield Label(label)
                            yield Static(hint, classes="hint")
                        with Vertical(classes="field-input-col"):
                            yield Input(value=self._seed_text(fid, default), placeholder=placeholder, id=fid)
                            yield Static("", id=f"{fid}_error", classes="field-error")
                for fid, label, hint in self._BOOL_FIELDS:
                    with Vertical(classes="bool-group"):
                        yield Checkbox(label, value=self._seed_bool(fid, False), id=fid)
                        yield Static(hint, classes="hint")
                yield Static("", id="status")
                with Horizontal(id="actions"):
                    yield Button("Apply", id="apply", variant="success")
                    yield Button("Cancel", id="cancel")
            yield Footer()

        def _reseed_from_name(self, name: str) -> None:
            """Update untouched fields with convention-based defaults."""
            name = name.strip()
            name_lower = name.lower()

            # All seedable fields use placeholder (ghost) text so the
            # user sees the convention without committing to a value.
            seeds: dict[str, str] = {}
            if name:
                seeds = {
                    "linux_sonames": f"lib{name}.so.XX,lib{name}.so.YY",
                    "windows_dlls": f"{name}64_XX.dll,{name}64_YY.dll",
                    "site_packages_linux": f"nvidia/{name_lower}/lib",
                    "site_packages_windows": f"nvidia/{name_lower}/bin",
                }

            for field_id in self._SEEDABLE_FIELDS:
                if field_id in self._user_touched:
                    continue
                widget = self.query_one(f"#{field_id}", Input)
                widget.placeholder = seeds.get(field_id, "")

        def on_input_changed(self, event: Input.Changed) -> None:
            field_id = event.input.id
            if field_id == "name":
                self._reseed_from_name(event.value)
            elif field_id in self._SEEDABLE_FIELDS:
                self._user_touched.add(field_id)

        def _clear_errors(self) -> None:
            for fid, *_ in self._TEXT_FIELDS:
                self.query_one(f"#{fid}_error", Static).update("")
            self.query_one("#status", Static).update("")

        def _set_field_error(self, field_id: str, msg: str) -> None:
            self.query_one(f"#{field_id}_error", Static).update(msg)

        def on_button_pressed(self, event) -> None:
            if event.button.id == "cancel":
                self.exit(None)
                return
            if event.button.id != "apply":
                return

            self._clear_errors()
            spec = self._collect_input()
            has_error = False

            if not spec.name:
                self._set_field_error("name", "Required")
                has_error = True
            elif not _VALID_NAME_RE.match(spec.name):
                self._set_field_error("name", "Must be a valid Python identifier")
                has_error = True

            if spec.strategy not in _VALID_STRATEGIES:
                self._set_field_error("strategy", f"Must be one of: {', '.join(_VALID_STRATEGIES)}")
                has_error = True

            if not spec.linux_sonames and not spec.windows_dlls:
                self._set_field_error("linux_sonames", "At least one SONAME or DLL required")
                self._set_field_error("windows_dlls", "At least one SONAME or DLL required")
                has_error = True

            if has_error:
                return

            self.exit(spec)

    spec = DescriptorFormApp(args).run()
    return spec, True


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Add descriptor_catalog entries (CLI or optional UI)")
    parser.add_argument("--catalog", type=Path, default=_default_catalog_path())
    parser.add_argument("--ui", action="store_true", help="Use optional Textual UI form")
    parser.add_argument("--name")
    parser.add_argument("--strategy", choices=_VALID_STRATEGIES)
    parser.add_argument("--linux-sonames")
    parser.add_argument("--windows-dlls")
    parser.add_argument("--site-packages-linux")
    parser.add_argument("--site-packages-windows")
    parser.add_argument("--dependencies")
    parser.add_argument("--anchor-rel-dirs-linux")
    parser.add_argument("--anchor-rel-dirs-windows")
    parser.add_argument("--requires-add-dll-directory")
    parser.add_argument("--requires-rtld-deepbind")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def run(argv: list[str]) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    if not args.catalog.is_file():
        parser.error(f"Catalog file not found: {args.catalog}")

    if _all_form_fields_supplied(args):
        spec = _build_input_from_args(args)
    elif args.ui:
        spec, used_form = _build_input_from_textual_form(args)
        if spec is None and not used_form:
            parser.error("--ui requires textual and an interactive terminal")
        if spec is None:
            return 1
    else:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            parser.error("Pass all --fields on the CLI (or run interactively, optionally with --ui)")
        try:
            spec = _build_input_from_prompt(args)
        except (EOFError, KeyboardInterrupt):
            return 1

    validate_descriptor_input(spec)
    apply_descriptor(args.catalog, spec, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
