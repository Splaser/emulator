#!/usr/bin/env python3
"""Validate native DMA shader and execute its integer functions as C++ against production CPU packing.
This is a shader-algorithm check, not Vulkan device execution or barrier validation.
"""
import argparse
from pathlib import Path
import subprocess
import re
import tempfile

PREFIX = r"""
#include <cstdint>
#include <vector>
#include <stdexcept>
#include <iostream>
#include <cstring>
#include "video_core/texture_cache/depth_stencil.h"
using uint=std::uint32_t;
struct Buffer { std::vector<uint> words; } packed,planes;
struct Params { uint width,height,layers,row_pitch,layer_pitch,packed_offset,depth_offset,stencil_offset,guest_layout,pack_mode,output_first,output_end; } p;
uint invocation;
"""
TESTS = r"""int main(){
 namespace DS=VideoCommon::DepthStencil;
 for(uint guest=0;guest<3;++guest) for(uint width=1;width<33;++width) {
  const uint bpp=guest==2?8:4, pitch=width*bpp+13, slice=pitch*5;
  const uint size=((7+slice*2+3)/4)*4;
  std::vector<uint8_t> source(size),baseline(size),reference(size),cpu_planes;
  for(uint i=0;i<size;++i){ source[i]=uint8_t(i*37+11); baseline[i]=uint8_t(i*71+19); }
  const auto host=guest==2?DS::DepthFormat::Float32:DS::DepthFormat::Unorm24;
  auto t=DS::PlanTransfer(static_cast<DS::GuestLayout>(guest),host,{width,3,2},{7,pitch,slice},size,0);
  if(!t)throw std::runtime_error("planning failed");
  cpu_planes.resize(t->end,0);
  if(!DS::UnpackTransfer(static_cast<DS::GuestLayout>(guest),host,*t,source,cpu_planes))throw std::runtime_error("reference unpack failed");
  packed.words.resize(size/4);std::memcpy(packed.words.data(),source.data(),size);
  planes.words.assign(t->end/4,0);
  p={width,3,2,pitch,slice,7,uint(t->depth.offset),uint(t->stencil.offset),guest,0,uint(t->depth.offset),uint(t->end)};
  for(invocation=0;invocation<((p.output_end-p.output_first+255)/256)*64;++invocation)kernel();
  if(std::memcmp(planes.words.data(),cpu_planes.data(),t->end))throw std::runtime_error("GPU algorithm disagrees with CPU planes");
  // Simulate arbitrary D24 X bits from image readback.
  if(guest!=2)for(uint i=0;i<width*3*2;++i){
   reinterpret_cast<uint8_t*>(planes.words.data())[t->depth.offset+i*4+3]=0xfa;
   cpu_planes[t->depth.offset+i*4+3]=0xfa;
  }
  reference=baseline;
  if(!DS::PackTransfer(static_cast<DS::GuestLayout>(guest),host,*t,cpu_planes,reference))throw std::runtime_error("reference pack failed");
  p.pack_mode=1;p.output_first=0;p.output_end=size;
  for(uint order=0;order<2;++order) {
   std::memcpy(packed.words.data(),baseline.data(),size);
   const uint work=((size+255)/256)*64;
   for(uint i=0;i<work;++i){ invocation=order?work-1-i:i;kernel(); }
   if(std::memcmp(packed.words.data(),reference.data(),size))throw std::runtime_error("GPU algorithm disagrees with CPU packed baseline");
  }
 }
 std::cout<<"96 native shader algorithm cases match production CPU helper; X bits, odd pitches, layers and baseline bytes checked. No GPU execution.\n";
}
"""

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--glslang', default='glslangValidator')
    parser.add_argument('--spirv-val', default='spirv-val')
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    shader = repo / 'src/video_core/host_shaders/vulkan_depth_stencil_dma.comp'
    with tempfile.TemporaryDirectory(prefix='depth-stencil-dma-') as directory:
        temp = Path(directory)
        spv = temp / 'shader.spv'
        subprocess.run([args.glslang, '-V', '--target-env', 'spirv1.3', str(shader), '-o', str(spv)], check=True)
        subprocess.run([args.spirv_val, '--target-env', 'vulkan1.1', str(spv)], check=True)
        # The current kernel is deliberately uint-only. Keep the tested functions
        # verbatim; replace only the entrypoint name and invocation built-in.
        functions = shader.read_text(encoding='utf-8').split('uint packed_byte', 1)[1]
        functions = 'uint packed_byte' + functions
        functions = functions.replace('void main()', 'void kernel()').replace('gl_GlobalInvocationID.x', 'invocation')
        source = temp / 'algorithms.cpp'
        fields = shader.read_text(encoding='utf-8').split('uniform Parameters {', 1)[1].split('} p;', 1)[0]
        prefix, substitutions = re.subn(r'struct Params \{[^}]+\} p;', 'struct Params {' + fields + '} p;', PREFIX)
        if substitutions != 1:
            raise RuntimeError('Cannot bind the actual shader parameter layout')
        source.write_text(prefix + functions + TESTS, encoding='utf-8')
        for optimization in ('-O2', '-O0'):
            exe = temp / 'algorithms.exe'
            subprocess.run([args.cxx, '-std=c++20', optimization, '-D_GLIBCXX_ASSERTIONS',
                '-Wall', '-Wextra', '-Werror', '-I' + str(repo / 'src'), str(source),
                str(repo / 'src/video_core/texture_cache/depth_stencil.cpp'), '-o', str(exe)], check=True)
            subprocess.run([str(exe)], check=True)

if __name__ == '__main__':
    main()
