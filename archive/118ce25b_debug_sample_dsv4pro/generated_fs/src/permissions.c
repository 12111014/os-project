#include "permissions.h"
#include <fuse.h>
#include <errno.h>
#include <unistd.h>

int perm_check(const inode_t *inode, int access_mode)
{
    struct fuse_context *ctx = fuse_get_context();
    if (!ctx) return -EACCES;

    uid_t uid = ctx->uid;
    gid_t gid = ctx->gid;

    /* Root (uid 0) always has access */
    if (uid == 0)
        return 0;

    mode_t mode = inode->mode;
    int granted;

    if (uid == inode->uid) {
        /* Owner */
        granted = (mode & S_IRWXU) >> 6;
    } else if (gid == inode->gid) {
        /* Group */
        granted = (mode & S_IRWXG) >> 3;
    } else {
        /* Other */
        granted = (mode & S_IRWXO);
    }

    if ((granted & access_mode) == access_mode)
        return 0;

    return -EACCES;
}
