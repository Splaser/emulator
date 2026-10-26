#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Extract production display selection and image preparation for controlled tests."""
import argparse
from pathlib import Path
import subprocess
parser = argparse.ArgumentParser()
parser.add_argument("output", type=Path)
parser.add_argument("--revision")
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
def read(path):
    if args.revision:
        return subprocess.check_output(["git", "show", f"{args.revision}:{path}"], cwd=root, text=True)
    return (root / path).read_text()
def definition(text, signature):
    start = text.index(signature)
    end = text.index("{", start) + 1
    depth = 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]
source = read("src/video_core/texture_cache/texture_cache.h")
methods = []
for signature in ["std::pair<typename P::ImageView*, bool> TextureCache<P>::TryFindFramebufferImageView(", "void TextureCache<P>::SynchronizeAliases(", "void TextureCache<P>::PrepareImage("]:
    methods.append("template <class P>\n" + definition(source, signature))
args.output.write_text("\n\n".join(methods) + "\n")

args.output.with_name("framebuffer_present_config.inc").write_text(
    "#define FRAMEBUFFER_PRESENT_HAS_SHADOW " + str(int("ShadowKind shadow_kind" in methods[-1])) + "\n")
