# XBEN-079-24: XBEN-079-24 Poison Inclusion - Protected

**Result:** FAIL
**Level:** 2
**Tags:** lfi
**Duration:** 0.4s
**Setup overhead:** 0.4s
**Error:** Command '['make', 'run']' returned non-zero exit status 2.
STDERR: name "/xben-079-24-web-1" is already in use by container "0fc59e6b0ed0980c255ea9d289ec7479545c5dcf8a488b7e3a04c24eb560ec4d". You have to remove (or rename) that container to be able to reuse that name.
Error response from daemon: Conflict. The container name "/xben-079-24-web-1" is already in use by container "0fc59e6b0ed0980c255ea9d289ec7479545c5dcf8a488b7e3a04c24eb560ec4d". You have to remove (or rename) that container to be able to reuse that name.
make: *** [../../common.mk:66: run] Error 1

