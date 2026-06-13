#ifndef FUSE_OPS_H
#define FUSE_OPS_H

/* Forward declaration: struct fuse_operations is defined in <fuse.h>.
   Callers must include <fuse.h> before including this header. */
struct fuse_operations;

/* Returns the fully populated fuse_operations struct */
struct fuse_operations *agentfs_get_operations(void);

#endif /* FUSE_OPS_H */
