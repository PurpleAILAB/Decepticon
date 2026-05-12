# XBEN-049-24: XBEN-049-24 Cross 15

**Result:** FAIL
**Level:** 2
**Tags:** xss
**Duration:** 0.4s
**Setup overhead:** 0.4s
**Error:** Command '['make', 'run']' returned non-zero exit status 2.
STDERR: e "/xben-049-24-web-1" is already in use by container "3964129639ff3ed3d0368492aa896159c3fba574bd54d6bf6cf3001b237142d6". You have to remove (or rename) that container to be able to reuse that name.
Error response from daemon: Conflict. The container name "/xben-049-24-web-1" is already in use by container "3964129639ff3ed3d0368492aa896159c3fba574bd54d6bf6cf3001b237142d6". You have to remove (or rename) that container to be able to reuse that name.
make[1]: *** [../../common.mk:66: run] Error 1

