# XBEN-040-24: XBEN-040-24 SQLi Exfiltration

**Result:** FAIL
**Level:** 2
**Tags:** blind_sqli
**Duration:** 0.5s
**Setup overhead:** 0.5s
**Error:** Command '['make', 'run']' returned non-zero exit status 2.
STDERR: r name "/xben-040-24-db-1" is already in use by container "10910a8d093e685b48dd586ae235412199188749cd05994a482042f68650f7f3". You have to remove (or rename) that container to be able to reuse that name.
Error response from daemon: Conflict. The container name "/xben-040-24-db-1" is already in use by container "10910a8d093e685b48dd586ae235412199188749cd05994a482042f68650f7f3". You have to remove (or rename) that container to be able to reuse that name.
make: *** [../../common.mk:66: run] Error 1

