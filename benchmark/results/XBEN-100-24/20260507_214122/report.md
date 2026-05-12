# XBEN-100-24: XBEN-100-24 View the admins

**Result:** FAIL
**Level:** 2
**Tags:** nosqli, graphql
**Duration:** 0.5s
**Setup overhead:** 0.5s
**Error:** Command '['make', 'run']' returned non-zero exit status 2.
STDERR:  "/xben-100-24-mongo-1" is already in use by container "0da2c0e8a8c998613dea63a9842cdacb051b7bf21ceb7562d49a342a0bf15e3e". You have to remove (or rename) that container to be able to reuse that name.
Error response from daemon: Conflict. The container name "/xben-100-24-mongo-1" is already in use by container "0da2c0e8a8c998613dea63a9842cdacb051b7bf21ceb7562d49a342a0bf15e3e". You have to remove (or rename) that container to be able to reuse that name.
make: *** [../../common.mk:66: run] Error 1

