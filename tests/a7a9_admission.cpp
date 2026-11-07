#include <cassert>
#include <cstdio>
#include <cstring>
#include <initializer_list>
#include "kern_raptorlake_p.hpp"
#include "kern_display13_clock.hpp"
int main() {
    using namespace XELP;
    for (unsigned rev=0;rev<256;++rev) {
        auto p=identify(0xA7A98086,rev);
        assert(p.admitted()==(rev==4));
        assert(p.gt==GT::RPLPMedium && p.display==Display::XeLPD);
        assert(!identify(0xA7A910DE,rev).admitted());
        assert(!identify(0x12348086,rev,0xA7A98086).admitted());
        assert(!identify(0xA7A98086,rev,0xA7A88086).admitted());
        assert(!identify(0xA7A98086,rev,0x9A498086).admitted());
        assert(!identify(0xA7A98086,rev,0x46D08086).admitted());
        assert(!identify(0xA7A88086,rev,0xA7A98086).admitted());
    }
    for (uint32_t id : {0xA7A88086U,0xA7A98086U}) {
        using namespace RaptorLakeP::CapsReply;
        for (auto presented : {Presented,PresentedADLN}) {
            uint8_t reply[Size],before[Size];
            for (unsigned i=0;i<Size;++i)reply[i]=uint8_t(i);
            memcpy(reply+8,&id,4);memcpy(before,reply,Size);
            assert(adapt(reply,Size,0,false,presented)==Status::Disabled);
            assert(!memcmp(reply,before,Size));
            assert(adapt(reply,Size-1,0,true,presented)==Status::BadSize);
            assert(adapt(reply,Size,1,true,presented)==Status::Error);
            assert(!memcmp(reply,before,Size));
            assert(adapt(reply,Size,0,true,presented)==Status::Rewritten);
            assert(identity(reply)==presented);
            for(unsigned i=0;i<Size;++i)if(i!=10 && i!=11)assert(reply[i]==before[i]);
        }
    }
    AlderLakeN::Resources resources;
    assert(RaptorLakeP::qualifiedGT(1,15,0,0x88,0xE00FE,resources));
    assert(resources.eus==64 && resources.l3Banks==6 && resources.urbKiB==384);
    assert(!RaptorLakeP::qualifiedGT(1,15,0,0x80,0xE00FE,resources));
    assert(!RaptorLakeP::qualifiedGT(1,15,0,0x88,0xE00FA,resources));
    puts("PASS A7A9: exact physical identity/revision, bounded caps rewrite and unchanged fuse qualification");
}
