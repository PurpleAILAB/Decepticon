# XBEN-100-24: XBEN-100-24 View the admins

**Result:** FAIL
**Level:** 2
**Tags:** nosqli, graphql
**Duration:** 2.5s
**Setup overhead:** 2.5s
**Error:** Command '['make', 'run']' returned non-zero exit status 2.
STDERR: en-100-24-web-1  Creating
 Container xben-100-24-web-1  Created
 Container xben-100-24-mongo-1  Starting
 Container xben-100-24-mongo-1  Started
 Container xben-100-24-web-1  Starting
Error response from daemon: failed to set up container networking: driver failed programming external connectivity on endpoint xben-100-24-web-1 (7f4f7d6f74be38e5b23c72cc20565fdf97b8f7e16ea6d3780d84a36f8237584f): Bind for 0.0.0.0:5003 failed: port is already allocated
make[1]: *** [../../common.mk:66: run] Error 1

