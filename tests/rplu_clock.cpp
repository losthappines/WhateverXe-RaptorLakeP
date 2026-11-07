// Synthetic register/firmware tests, not hardware qualification.
#include <cassert>
#include <cstdio>
#include <map>
#include <vector>
#include "kern_display13_clock.hpp"
using namespace Display13Clock;
struct IO {
    uint32_t physical=0xA7A98086;
    bool enabled=true, deny=false, timeout=false, badControl=false, change=false;
    unsigned reads=0;
    std::map<uint32_t,uint32_t> regs {{DSSM,2U<<29},{PLL,0xC0000022},{Control,0x380518},{Squash,0},
        {Mailbox,0},{Data,0},{Data1,0}};
    std::vector<std::pair<uint32_t,uint32_t>> writes;
    Profile clockProfile() const {return profileForDevice(physical,enabled);}
    bool readable(uint32_t reg) const {return regs.count(reg);}
    uint32_t read(uint32_t reg) {++reads;return regs.at(reg);}
    void delayUs(unsigned) {}
    void write(uint32_t reg,uint32_t value) {
        writes.emplace_back(reg,value);regs[reg]=value;
        if(reg==Mailbox) {
            assert(value==0x80000007 && regs[Data1]==0);
            regs[Mailbox]=0;
            if(regs[Data]==3)regs[Data]=deny ? 0:1;
            if(change)regs[PLL]^=1;
        }
        if(reg==PLL && (value&(1U<<31))) {
            regs[PLL]|=1U<<30;
            if((value&(1U<<23)) && !timeout)regs[PLL]|=1U<<22;
        }
        if(reg==PLL && !(value&(1U<<31)))regs[PLL]&=~(1U<<30);
        if(reg==Control && badControl)regs[Control]^=1;
    }
    unsigned count(uint32_t reg) const {unsigned n=0;for(auto w:writes)n+=w.first==reg;return n;}
};
int main() {
    {
        IO io;io.enabled=false;
        assert(observe(io,0xA7A98086).status==Status::Complete);
        assert(io.reads && io.writes.empty());
        io.reads=0;
        assert(observe(io,0xA7A910DE).status==Status::NotReady && !io.reads);
    }
    // A721 is absent from this older fork's PCI catalogue; do not admit it here.
    assert(profileForDevice(0xA7218086,true)==Profile::Unsupported);
    for(auto id:{0xA7A1U,0xA7A9U,0xA7ACU,0xA7ADU}) {
        assert(profileForDevice((id<<16)|0x8086,false)==Profile::Unsupported);
        assert(profileForDevice((id<<16)|0x8086,true)==Profile::RPLU);
    }
    assert(profileForDevice(0xA7A88086,true)==Profile::ADLP);
    assert(profileForDevice(0x46D08086,false)==Profile::ADLP);
    assert(profileForDevice(0xA7A910DE,true)==Profile::Unsupported);
    assert(profileForDevice(0xFFFF8086,true)==Profile::Unsupported);
    // Independent Linux v6.12 rplu_cdclk_table fixtures, DSSM order.
    const uint32_t freq[3][6]={{176000,192000,312000,480000,552000,648000},
        {172800,192000,307200,480000,556800,652800},
        {179200,192000,307200,480000,556800,652800}};
    const uint32_t ratio[3][6]={{22,16,26,40,46,54},{27,20,32,50,58,68},{14,10,16,25,29,34}};
    for(unsigned ref=0;ref<3;++ref)for(unsigned from=0;from<6;++from) {
        const auto control=0x380000|(from==0 ? 1U<<22:0U)|((2*freq[ref][from]+500)/1000-2);
        auto r=decode(ref<<29,0xC0000000|ratio[ref][from],control,0,Profile::RPLU);
        assert(r.status==Status::Complete && r.cdclkKHz==freq[ref][from]);
        assert(decode(ref<<29,0xC0000000|ratio[ref][from],control,0).status==
            (from==3 ? Status::UnsupportedFrequency:Status::Complete));
        // Every pair, both active and quiesced: divider changes stay blocked
        // with an active pipe; same-divider changes use the existing crawl.
        for(unsigned to=0;to<6;++to)for(unsigned active:{0U,1U}) {
            IO io;io.regs[DSSM]=ref<<29;io.regs[PLL]=0xC0000000|ratio[ref][from];io.regs[Control]=control;
            const auto hz=uint64_t(freq[ref][to])*2000;
            auto c=set(io,hz,{true,true,active});
            if(active && ((from==0)!=(to==0))) {
                assert(c.status==ChangeStatus::ActiveDividerChange && io.writes.empty());continue;
            }
            assert(c.status==ChangeStatus::Complete && c.after.nativeHz()==hz);
            if(from==to)assert(io.writes.empty());
            else {
                std::vector<uint32_t> messages;
                for(auto w:io.writes)if(w.first==Data)messages.push_back(w.second);
                const auto f=freq[ref][to];
                const auto expected=f<=312000 ? 0U:f<=480000 ? 1U:f<=556800 ? 2U:3U;
                assert(messages.size()==2 && messages[0]==3 && messages[1]==expected);
            }
        }
    }
    assert(select(38400,614400000,false,Profile::RPLU)==960000000);
    assert(select(38400,960000000,false,Profile::RPLU)==1113600000);
    assert(select(38400,614400000,false)==1113600000);
    assert(select(38400,0,true,Profile::RPLU)==1305600000);
    assert(select(38400,0,true,Profile::Unsupported)==0);
    assert(voltage(480000,Profile::RPLU)==1 && voltage(480001,Profile::RPLU)==2);
    assert(voltage(480000)==2);
    {IO io;io.enabled=false;auto r=set(io,960000000,{true,true,0});assert(r.status==ChangeStatus::NotReady && !io.reads && io.writes.empty());}
    {IO io;io.physical=0xA7A910DE;assert(read(io).status==Status::NotReady && !io.reads);}
    {IO io;auto r=set(io,960000000,{false,true,0});assert(r.status==ChangeStatus::OwnershipRequired && io.writes.empty());}
    {IO io;auto r=set(io,960000000,{true,false,0});assert(r.status==ChangeStatus::WatermarksRequired && io.writes.empty());}
    {IO io;io.deny=true;auto r=set(io,960000000,{true,true,0});assert(r.status==ChangeStatus::PrepareTimeout && io.count(PLL)==0);}
    {IO io;io.timeout=true;auto r=set(io,960000000,{true,true,1});assert(r.status==ChangeStatus::PllTimeout && io.count(Data)==1 && io.count(Control)==0);}
    {IO io;io.badControl=true;auto r=set(io,960000000,{true,true,1});assert(r.status==ChangeStatus::ReadbackMismatch && io.count(Data)==1);}
    {IO io;io.change=true;auto r=set(io,960000000,{true,true,0});assert(r.status==ChangeStatus::ReadbackMismatch && io.count(PLL)==0);}
    {IO io;io.regs[Squash]=1U<<31;auto r=set(io,960000000,{true,true,0});assert(r.status==ChangeStatus::NotReady && io.writes.empty());}
    {IO io;assert(set(io,960000000,{true,true,0}).status==ChangeStatus::Complete);
        assert(stop(io,{true,false,0}).status==ChangeStatus::Complete);
        assert(set(io,960000000,{true,true,0}).status==ChangeStatus::Complete);
        assert(read(io).cdclkKHz==480000);}
    puts("PASS RPL-U: 18 readouts, 216 transition cases, firmware voltage messages, opt-in identity guards, faults and stop/resume. Synthetic IO only.");
}
