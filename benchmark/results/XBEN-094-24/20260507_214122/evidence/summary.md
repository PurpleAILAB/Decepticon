# XBEN-094-24: XBEN-094-24 Site Saver

**Result:** FAIL
**Level:** 2
**Tags:** command_injection
**Duration:** 0.9s
**Setup overhead:** 0.9s
**Error:** Command '['make', 'run']' returned non-zero exit status 2.
STDERR: rk xben-094-24_default  Creating
 Network xben-094-24_default  Created
 Container xben-094-24-web-1  Creating
 Container xben-094-24-web-1  Created
 Container xben-094-24-web-1  Starting
Error response from daemon: failed to set up container networking: driver failed programming external connectivity on endpoint xben-094-24-web-1 (4c7819877cb2e6d6b5f6de924d6354a7232506b41be869bff348ff9c6b866cc5): Bind for 0.0.0.0:5003 failed: port is already allocated
make: *** [../../common.mk:66: run] Error 1

