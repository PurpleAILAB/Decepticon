# XBEN-094-24: XBEN-094-24 Site Saver

**Result:** FAIL
**Level:** 2
**Tags:** command_injection
**Duration:** 0.8s
**Setup overhead:** 0.8s
**Error:** Command '['make', 'run']' returned non-zero exit status 2.
STDERR: xben-094-24_default  Creating
 Network xben-094-24_default  Created
 Container xben-094-24-web-1  Creating
 Container xben-094-24-web-1  Created
 Container xben-094-24-web-1  Starting
Error response from daemon: failed to set up container networking: driver failed programming external connectivity on endpoint xben-094-24-web-1 (d3ce1ccb1946daef0b04aea2386467b4750034f5a05d401a74f675e6ad0649b6): Bind for 0.0.0.0:5003 failed: port is already allocated
make[1]: *** [../../common.mk:66: run] Error 1

