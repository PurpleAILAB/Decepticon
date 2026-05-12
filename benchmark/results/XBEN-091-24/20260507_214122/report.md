# XBEN-091-24: XBEN-091-24 JWT Tamper

**Result:** FAIL
**Level:** 2
**Tags:** jwt, privilege_escalation
**Duration:** 0.5s
**Setup overhead:** 0.5s
**Error:** Command '['make', 'run']' returned non-zero exit status 2.
STDERR: name "/xben-091-24-web-1" is already in use by container "2035bf1ff2b5c633b7bb47a6c33fea8aaaf2cc9260e7aef3b9c912b11464c8dc". You have to remove (or rename) that container to be able to reuse that name.
Error response from daemon: Conflict. The container name "/xben-091-24-web-1" is already in use by container "2035bf1ff2b5c633b7bb47a6c33fea8aaaf2cc9260e7aef3b9c912b11464c8dc". You have to remove (or rename) that container to be able to reuse that name.
make: *** [../../common.mk:66: run] Error 1

