#!/usr/bin/env python3
"""Run production profile selection: ADL-P Render must preserve Display13."""
from pathlib import Path
import re, subprocess, tempfile
r=Path(__file__).resolve().parents[1]
s=(r/'WhateverXe/kern_xe.cpp').read_text()
f=re.search(r'void XE::selectProfile\(.*?\n\}',s,re.S).group()
gpuinfo=re.search(r'void XE::wrapAlderLakeNNativeGPUInfo\(.*?\n\}',s,re.S).group()
code=r'''
#include "kern_xelp_platform.hpp"
#include "kern_xelp_os.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
using mach_vm_address_t=uintptr_t;
struct IOService {};
#define FunctionCast(fn,ptr) reinterpret_cast<decltype(&fn)>(ptr)
const char *version="Darwin Kernel Version 20.6.0: Thu Jul  6 22:12:47 PDT 2023; root:xnu-7195.141.49.702.12~1/RELEASE_X86_64";
bool noaccel=false,vcs2Media=false;
bool checkKernelArgument(const char *s){
 if(!strcmp(s,"-wex-noaccel"))return noaccel;
 if(!strcmp(s,"-wex-vcs2-media"))return vcs2Media;
 return false;
}
int kextIntelTGL,kextIntelTGLFb;
bool adlnNativeRCSProfileRequested=false,display13TraceEnabled=false,display13Offline=false;
void tglObserveAccelerator(IOService *,unsigned,bool,uint64_t,uint64_t){}
struct XE {
 static XE *callbackXE;
 XELP::Profile xeProfile;
 bool tglGT2Detected=false,tglGT2Ready=false;
 bool display12SmallGTDetected=false,adlsDisplaySelected=false;
 bool adlnRequested=false,adlnDetected=false,adlnKernelReady=false,adlnNativeRequested=false;
 bool adlpDisplaySelected=false,adlpRenderRequested=false,display13FramebufferRequested=false;
 bool tglRequested=false,tglAcceleratorRequested=false,tglInactivePorts=false,tglPG1Poll=false;
 bool tglClockOrderRequested=false,tglTrainingLeaseRequested=false,tglProgramEnabled=false;
 uint32_t adlnVideoMask=0;
 mach_vm_address_t orgAlderLakeNNativeGPUInfo=0;
 int *currentFramebuffer=nullptr,*currentGraphics=nullptr;
 struct {bool available=false;}modDVMTCalcFix;
 void selectProfile(const XELP::Profile &);
 static void wrapAlderLakeNNativeGPUInfo(IOService *);
};
XE *XE::callbackXE=nullptr;
void mockNativeGPUInfo(IOService *that){
 auto a=reinterpret_cast<uint8_t *>(that);
 // Simulate donor getGPUInfo after VCS0 is cleared on VCS2-only hardware (bits 0,2,4,5 = 0x35).
 *reinterpret_cast<uint64_t *>(a+0x1300)=XE::callbackXE->adlnVideoMask==4 ? 0x35ULL : 0x3dULL;
}
FUNCTION
GPUINFO
int main(){
 const uint32_t mobile[]={0x4626,0x4628,0x462a,0x46a0,0x46a1,0x46a2,0x46b0,0x46b1,0x46b2,0x46c0,0x46c1,0x46c2,0xa720,0xa721,0x46a3,0x46a6,0x46a8,0x46aa,0x46b3,0x46c3,0xa7a0,0xa7a1,0xa7a8,0xa7a9,0xa7aa,0xa7ab,0xa7ac,0xa7ad};
 constexpr unsigned mobileSelectors=2*sizeof(mobile)/sizeof(mobile[0]);
 unsigned cases=0;
 for(unsigned which=0;which<mobileSelectors+2;++which)for(unsigned rev=0;rev<256;++rev)for(unsigned off=0;off<2;++off) {
  noaccel=off;XE x;const bool isMobile=which<mobileSelectors,isN=which==mobileSelectors;
  const auto pci=(isMobile?mobile[which/2]:isN?0x46d1:0x9a49)<<16|0x8086;
  const auto effective=isMobile && (which&1)?0x9a498086:pci;
  const auto p=XELP::identify(pci,rev,effective);x.selectProfile(p);
  assert(XELP::same(x.xeProfile,p) && p.admitted());
  assert(x.currentFramebuffer==&kextIntelTGLFb && x.currentGraphics==&kextIntelTGL);
  assert(x.display13FramebufferRequested==(isMobile || isN));
  assert(x.adlpDisplaySelected==isMobile);
  assert(x.adlpRenderRequested==(isMobile&&!off));
  assert(x.adlnDetected==(isN || (isMobile&&!off)));
  assert(x.tglAcceleratorRequested==!off);
  assert(adlnNativeRCSProfileRequested==(isN || (isMobile&&!off)));++cases;
 }
 noaccel=false;XE unknown;unknown.selectProfile(XELP::identify(0x4c8a8086,12));
 assert(!unknown.adlpRenderRequested && !unknown.adlnDetected && !unknown.tglAcceleratorRequested);
 // VCS2-only hardware (video mask 4) must strip media engines (bits 3..5) at +0x1300
 // unless -wex-vcs2-media is requested; VCS0-present profiles retain their mask.
 const uint32_t videos[]={1U,4U,5U};
 for(unsigned vi=0;vi<3;++vi)for(unsigned oi=0;oi<2;++oi){
  const uint32_t video=videos[vi];const bool optIn=oi!=0;
  XE x;XE::callbackXE=&x;x.orgAlderLakeNNativeGPUInfo=reinterpret_cast<uintptr_t>(&mockNativeGPUInfo);
  x.selectProfile(XELP::identify(0xa7a98086,4));x.adlnVideoMask=video;vcs2Media=optIn;
  alignas(8) uint8_t accel[0x1400]{};
  XE::wrapAlderLakeNNativeGPUInfo(reinterpret_cast<IOService *>(accel));
  const auto engines=*reinterpret_cast<uint64_t *>(accel+0x1300);
  assert(engines==(video==4 ? (optIn ? 0x35ULL : 0x05ULL) : 0x3dULL));
 }
 assert(cases==(mobileSelectors+2)*256*2);puts("PASS production profile selections: all mobile Display13 IDs/revisions, physical and legacy donor selectors, noaccel, VCS2-only media engine guard, ADL-N and TGL");
}
'''.replace('FUNCTION',f).replace('GPUINFO',gpuinfo)
with tempfile.TemporaryDirectory(prefix='wex-adlp-render-') as d:
 p=Path(d);(p/'test.cpp').write_text(code)
 subprocess.run(['clang++','-std=c++17','-O1','-fsanitize=address,undefined','-I'+str(r/'WhateverXe'),str(p/'test.cpp'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
