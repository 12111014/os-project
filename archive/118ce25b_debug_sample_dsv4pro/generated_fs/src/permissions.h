#ifndef PERMISSIONS_H
#define PERMISSIONS_H

#include "inode_table.h"

/* Access mode flags for perm_check */
#define PERM_READ    4
#define PERM_WRITE   2
#define PERM_EXEC    1

/*
 * Check whether the calling user (from fuse_get_context()) has the
 * requested access to the given inode.
 * Returns 0 if access is granted, -EACCES if denied.
 * Caller must hold the global lock (though this function doesn't
 * directly touch global state, it accesses inode fields).
 */
int perm_check(const inode_t *inode, int access_mode);

#endif /* PERMISSIONS_H */
