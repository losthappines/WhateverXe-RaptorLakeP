#!/usr/bin/env python3
"""Compile actual runtime clock adapters with mock PCI/MMIO, never real hardware."""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--zig', type=Path, help='Optional portable Zig compiler for Windows CPU tests')
a = p.parse_args()
root = Path(__file__).resolve().parents[1]
source = (root / 'WhateverXe/kern_xe.cpp').read_text()
start = source.index('struct Display13FBClockIO {')
adapter = source[start:source.index('// Owner IOLock', start)]
early_start = source.index('Display13Clock::Readout XE::adlnClockReadout(')
early_end = source.index('void XE::wrapAlderLakeNClockInit(', early_start)
early = source[early_start:early_end]
start = early.index('struct IO {')
early_adapter = early[start:early.index('} io {', start)] + '};'
early_adapter = early_adapter.replace('struct IO {', 'struct EarlyClockIO {', 1)
assert 'profileForDevice(pci->configRead32(0),checkKernelArgument("-wex-rplu-clock"))' in early
assert 'Display13Clock::select(clock.refKHz,minimumHz,external,io.clockProfile())' in source
code = r'''
#include <cassert>
#include <cstdio>
#include <cstring>
#include <vector>
#include "kern_display13_clock.hpp"
struct IOMemoryMap {
    std::vector<uint32_t> data = std::vector<uint32_t>(0x1000000/4);
    size_t getLength() const {return 0x1000000;}
    uintptr_t getVirtualAddress() {return reinterpret_cast<uintptr_t>(data.data());}
};
struct {uint32_t identity=0xA7A98086;} xelpSelectedProfile;
static int gpu;
static int *xelpSelectedGPU=&gpu;
static bool qualified=true, enabled=false;
bool xelpSelectedDevice(int *p) {return qualified && p==&gpu;}
bool checkKernelArgument(const char *s) {assert(!strcmp(s,"-wex-rplu-clock"));return enabled;}
void IODelay(unsigned) {}
void IOSleep(unsigned) {}
// ADAPTERS
int main() {
    using namespace Display13Clock;
    IOMemoryMap map;
    map.data[DSSM/4]=2U<<29;map.data[PLL/4]=0xC0000019;map.data[Control/4]=0x3803BE;
    Display13FBClockIO runtime{&map};
    assert(runtime.clockProfile()==Profile::Unsupported);
    assert(read(runtime).status==Status::NotReady);
    // Disabled experimentation must not issue any MMIO write.
    auto before=map.data;
    assert(set(runtime,960000000,{true,true,0}).status==ChangeStatus::NotReady);
    assert(map.data==before);
    enabled=true;
    assert(runtime.clockProfile()==Profile::RPLU && read(runtime).cdclkKHz==480000);
    assert(select(38400,614400000,false,runtime.clockProfile())==960000000);
    EarlyClockIO early{map.getVirtualAddress(),profileForDevice(0xA7A98086,enabled)};
    assert(read(early).nativeHz()==read(runtime).nativeHz());
    qualified=false;assert(runtime.clockProfile()==Profile::Unsupported);
    assert(read(runtime).status==Status::NotReady);
    qualified=true;xelpSelectedProfile.identity=0xA7A88086;
    assert(runtime.clockProfile()==Profile::ADLP && read(runtime).status==Status::UnsupportedFrequency);
    xelpSelectedProfile.identity=0x46D08086;
    assert(runtime.clockProfile()==Profile::ADLP);
    xelpSelectedProfile.identity=0xA7A910DE;
    assert(runtime.clockProfile()==Profile::Unsupported);
    puts("PASS actual clock adapters: physical identity/opt-in gating, early/runtime agreement and no writes when disabled. Mock MMIO only.");
}
'''.replace('// ADAPTERS', adapter + '\n' + early_adapter)
with tempfile.TemporaryDirectory(prefix='rplu-clock-') as temp:
    directory = Path(temp)
    cpp = directory / 'test.cpp'
    exe = directory / ('test.exe' if sys.platform == 'win32' else 'test')
    cpp.write_text(code)
    compiler = [str(a.zig.resolve()), 'c++'] if a.zig else ['clang++']
    flags = ['-fsanitize=address,undefined'] if sys.platform != 'win32' else []
    subprocess.run(compiler + ['-std=c++17','-Wall','-Wextra','-Werror',*flags,
        '-I'+str(root/'WhateverXe'),str(cpp),'-o',str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
