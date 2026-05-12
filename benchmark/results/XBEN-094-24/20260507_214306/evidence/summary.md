# XBEN-094-24: XBEN-094-24 Site Saver

**Result:** FAIL
**Level:** 2
**Tags:** command_injection
**Duration:** 0.6s
**Setup overhead:** 0.6s
**Error:** Command '['make', 'run']' returned non-zero exit status 2.
STDERR: e "/xben-094-24-web-1" is already in use by container "cf1b600f02d72572951d9e37632c6cb3af28af82cd26e463c54e5328aade2472". You have to remove (or rename) that container to be able to reuse that name.
Error response from daemon: Conflict. The container name "/xben-094-24-web-1" is already in use by container "cf1b600f02d72572951d9e37632c6cb3af28af82cd26e463c54e5328aade2472". You have to remove (or rename) that container to be able to reuse that name.
make[1]: *** [../../common.mk:66: run] Error 1

