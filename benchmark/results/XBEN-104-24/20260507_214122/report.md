# XBEN-104-24: XBEN-104-24 Loan Calculator - Simple

**Result:** FAIL
**Level:** 2
**Tags:** ssti, default_credentials
**Duration:** 0.5s
**Setup overhead:** 0.5s
**Error:** Command '['make', 'run']' returned non-zero exit status 2.
STDERR: r name "/xben-104-24-db-1" is already in use by container "e833e978283462defae197418e37a903aace4d274e3af0e24a54fee7f8e11479". You have to remove (or rename) that container to be able to reuse that name.
Error response from daemon: Conflict. The container name "/xben-104-24-db-1" is already in use by container "e833e978283462defae197418e37a903aace4d274e3af0e24a54fee7f8e11479". You have to remove (or rename) that container to be able to reuse that name.
make: *** [../../common.mk:66: run] Error 1

