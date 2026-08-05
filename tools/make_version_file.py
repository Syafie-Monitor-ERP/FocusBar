"""Write the Windows VERSIONINFO resource that PyInstaller embeds in the .exe.

Without this, the built file's Properties -> Details tab is blank: no version, no
product name, no company. That matters for two reasons — a user asked "which
version are you running?" can read it off the file, and unsigned binaries with no
metadata at all draw more antivirus suspicion than ones that describe themselves.

    python tools/make_version_file.py 0.0.1 build/version_info.txt

Windows wants a four-part numeric version, so `0.0.1` is padded to `0.0.1.0`. The
original string is kept verbatim in the text fields, which is what a dev build
like `0.0.1-4-gc3dfa40` needs to survive intact.
"""

from __future__ import annotations

import os
import re
import sys

TEMPLATE = """\
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({vers}),
    prodvers=({vers}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0),
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', '{company}'),
         StringStruct('FileDescription', '{description}'),
         StringStruct('FileVersion', '{display}'),
         StringStruct('InternalName', '{name}'),
         StringStruct('OriginalFilename', '{name}.exe'),
         StringStruct('ProductName', '{name}'),
         StringStruct('ProductVersion', '{display}')])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""

NAME = "FocusBar"
COMPANY = "Muhammad Syafie"
DESCRIPTION = "A thin always-on-top strip showing your current task"


def numeric(display: str) -> tuple[int, int, int, int]:
    """The leading numeric components of `display`, padded to four parts.

    Anything git appends (`-4-gc3dfa40`, `-dirty`) is dropped: this tuple is a
    binary resource field and only accepts numbers.
    """
    found = re.findall(r"\d+", display.lstrip("v"))[:4]
    parts = [int(n) for n in found] + [0] * (4 - len(found))
    return tuple(parts)  # type: ignore[return-value]


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        print(f"usage: {argv[0]} VERSION OUTPUT_PATH", file=sys.stderr)
        return 2

    display, out_path = argv[1], argv[2]
    text = TEMPLATE.format(
        vers=", ".join(str(n) for n in numeric(display)),
        display=display,
        name=NAME,
        company=COMPANY,
        description=DESCRIPTION,
    )

    parent = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(parent, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(text)

    print(f"{out_path}: {display} -> {numeric(display)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
