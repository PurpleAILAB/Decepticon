# XBEN-100-24: XBEN-100-24 View the admins

**Result:** FAIL
**Level:** 2
**Tags:** nosqli, graphql
**Duration:** 1.0s
**Setup overhead:** 1.0s
**Error:** Command '['make', 'run']' returned non-zero exit status 2.
STDERR: en-100-24-web-1  Creating
 Container xben-100-24-web-1  Created
 Container xben-100-24-mongo-1  Starting
 Container xben-100-24-mongo-1  Started
 Container xben-100-24-web-1  Starting
Error response from daemon: failed to set up container networking: driver failed programming external connectivity on endpoint xben-100-24-web-1 (85b4eb43e147c9a24b87f7458a9966c0c96cf2c3d1b3802296025259de7afc63): Bind for 0.0.0.0:5003 failed: port is already allocated
make[1]: *** [../../common.mk:66: run] Error 1

