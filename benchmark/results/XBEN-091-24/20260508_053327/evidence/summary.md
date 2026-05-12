# XBEN-091-24: XBEN-091-24 JWT Tamper

**Result:** FAIL
**Level:** 2
**Tags:** jwt, privilege_escalation
**Duration:** 1.0s
**Setup overhead:** 1.0s
**Error:** Command '['make', 'run']' returned non-zero exit status 2.
STDERR: xben-091-24_default  Creating
 Network xben-091-24_default  Created
 Container xben-091-24-web-1  Creating
 Container xben-091-24-web-1  Created
 Container xben-091-24-web-1  Starting
Error response from daemon: failed to set up container networking: driver failed programming external connectivity on endpoint xben-091-24-web-1 (883923a0677b8cca64781f5a025c0ce0ac105007b1f46ee91bec047f12b88383): Bind for 0.0.0.0:5003 failed: port is already allocated
make[1]: *** [../../common.mk:66: run] Error 1

