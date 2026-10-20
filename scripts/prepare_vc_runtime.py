"""Prepare matching app-local VC runtime DLLs from the supplied Microsoft bundle.

Only expands cabinets into the workspace. Does not run an installer or modify
the system. The extracted Microsoft components retain their original license.
Copyright (C) 2026 PaperRoute contributors. AGPL-3.0-only.
"""

import hashlib
import json
import shutil
import struct
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def expand(source, target):
    target.mkdir(parents=True, exist_ok=True)
    subprocess.run(["expand.exe", str(source), "-F:*", str(target)], check=True,
                   stdout=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)


def main():
    source = ROOT / "VC_redist.x64.exe"
    content = source.read_bytes()
    verification = ROOT / ".verification"
    verification.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="vc-", dir=verification) as temporary:
        work = Path(temporary)
        cabinets = []
        start = 0
        while True:
            start = content.find(b"MSCF", start)
            if start < 0:
                break
            length = struct.unpack_from("<I", content, start + 8)[0]
            if 32 < length <= len(content) - start and content[start + 24:start + 26] == b"\x03\x01":
                cabinet = work / f"container-{len(cabinets)}.cab"
                cabinet.write_bytes(content[start:start + length])
                cabinets.append(cabinet)
            start += 4
        if len(cabinets) != 2:
            raise RuntimeError("Unsupported Microsoft bundle layout; do not guess its payloads")
        expand(cabinets[0], work / "ux")
        expand(cabinets[1], work / "payload")
        manifest = ET.parse(work / "ux" / "0")
        payloads = [node for node in manifest.iter() if node.tag.rsplit("}", 1)[-1] == "Payload"]
        minimum = next(node for node in payloads if node.get("FilePath", "").lower().endswith("vcruntimeminimum_amd64\\cab1.cab"))
        license_node = next(node for node in payloads if node.get("FilePath") == "license.rtf")
        expand(work / "payload" / minimum.attrib["SourcePath"], work / "dlls")
        target = ROOT / "core" / "redist"
        target.mkdir(parents=True, exist_ok=True)
        copied = []
        for file in sorted((work / "dlls").glob("*.dll_amd64")):
            name = file.name.removesuffix("_amd64")
            output = target / name
            shutil.copy2(file, output)
            copied.append({"name": name, "sha256": hashlib.sha256(output.read_bytes()).hexdigest()})
        if not any(item["name"] == "msvcp140.dll" for item in copied):
            raise RuntimeError("The Microsoft C++ runtime was not found in the supplied bundle")
        shutil.copy2(work / "ux" / license_node.attrib["SourcePath"], ROOT / "licenses" / "Microsoft-VC-Runtime.rtf")
        (target / "ORIGIN.json").write_text(json.dumps({"source": source.name, "source_sha256": hashlib.sha256(content).hexdigest(),
            "component": "Microsoft Visual C++ 2015-2022 runtime, AMD64", "files": copied}, indent=2), encoding="utf-8")
        print(f"Prepared {len(copied)} Microsoft app-local runtime DLLs; no system installation performed")


if __name__ == "__main__":
    main()
