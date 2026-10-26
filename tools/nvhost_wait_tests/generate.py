#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Extract actual nvhost control flow for isolated regression and baseline controls."""
import argparse
from pathlib import Path
import subprocess
parser = argparse.ArgumentParser()
parser.add_argument("output", type=Path)
parser.add_argument("--revision")
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
def read(path):
    return subprocess.check_output(["git", "show", f"{args.revision}:{path}"], cwd=root, text=True) if args.revision else (root/path).read_text()
def definition(text, signature):
    start = text.index(signature)
    end = text.index("{", start) + 1
    depth = 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]
h = read("src/core/hle/service/nvdrv/devices/nvhost_ctrl.h")
c = read("src/core/hle/service/nvdrv/devices/nvhost_ctrl.cpp")
members = "\n".join(definition(h, signature) + ";" for signature in ["union SyncpointEventValue", "struct InternalEvent", "struct IocCtrlEventWaitParams", "struct IocCtrlEventClearParams"])
methods = "\n".join(definition(c, signature) for signature in ["NvResult nvhost_ctrl::IocCtrlEventWait(", "NvResult nvhost_ctrl::IocCtrlClearEventWait("])
args.output.write_text("class nvhost_ctrl {\npublic:\n" + members + "\n#include \"fixture_members.inc\"\n};\n" + methods + "\n")
