#define _GNU_SOURCE

#include "fuse_ops.h"
#include "inode_table.h"
#include "dir_ops.h"
#include "storage_backend.h"
#include "path_utils.h"
#include "permissions.h"

#include <stdio.h>
#include <fuse.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <time.h>
#include <pthread.h>

/* xattr helpers declared in inode_table.c */
extern int  xattr_set(inode_t *n, const char *key, const uint8_t *value, size_t valuelen);
extern int  xattr_get(const inode_t *n, const char *key, uint8_t *buf, size_t bufsiz);
extern int  xattr_list(const inode_t *n, char *buf, size_t bufsiz);
extern int  xattr_remove(inode_t *n, const char *key);
extern void xattr_free_all(inode_t *n);

/* ---- external global lock from main.c ---- */
extern pthread_mutex_t g_lock;

/* ---- per-open file handle ---- */
typedef struct {
    uint64_t ino;
    int      flags;
} file_handle_t;

static void update_times(inode_t *n, int update_atime, int update_mtime,
                         int update_ctime)
{
    struct timespec now;
    clock_gettime(CLOCK_REALTIME, &now);
    if (update_atime) n->atime = now;
    if (update_mtime) n->mtime = now;
    if (update_ctime) n->ctime = now;
}

/* ---- init ---- */
static void *agentfs_init(struct fuse_conn_info *conn, struct fuse_config *cfg)
{
    (void)conn;
    cfg->kernel_cache = 0;
    cfg->entry_timeout = 0;
    cfg->attr_timeout = 0;
    return NULL;
}

/* ---- destroy ---- */
static void agentfs_destroy(void *private_data)
{
    (void)private_data;
    /* No new FUSE calls will arrive; safe to destroy without lock */
    inode_table_destroy();
}

/* ---- getattr ---- */
static int agentfs_getattr(const char *path, struct stat *stbuf,
                           struct fuse_file_info *fi)
{
    (void)fi;
    int res = 0;
    pthread_mutex_lock(&g_lock);

    uint64_t ino;
    res = path_resolve(path, &ino);
    if (res != 0) goto out;

    inode_t *n = inode_lookup(ino);
    if (!n) { res = -ENOENT; goto out; }

    memset(stbuf, 0, sizeof(*stbuf));
    stbuf->st_mode   = n->mode;
    stbuf->st_nlink  = n->nlink;
    stbuf->st_size   = (off_t)n->size;
    stbuf->st_uid    = n->uid;
    stbuf->st_gid    = n->gid;
    stbuf->st_atime  = n->atime.tv_sec;
    stbuf->st_mtime  = n->mtime.tv_sec;
    stbuf->st_ctime  = n->ctime.tv_sec;
    stbuf->st_blksize = STORAGE_BLOCK_SIZE;
    stbuf->st_blocks  = (n->size + 511) / 512;

out:
    pthread_mutex_unlock(&g_lock);
    return res;
}

/* ---- readdir ---- */
static int agentfs_readdir(const char *path, void *buf, fuse_fill_dir_t filler,
                           off_t offset, struct fuse_file_info *fi,
                           enum fuse_readdir_flags flags)
{
    (void)offset;
    (void)fi;
    (void)flags;

    int res = 0;
    pthread_mutex_lock(&g_lock);

    uint64_t ino;
    res = path_resolve(path, &ino);
    if (res != 0) goto out;

    inode_t *dir = inode_lookup(ino);
    if (!dir || dir->type != INODE_DIR) {
        res = dir ? -ENOTDIR : -ENOENT;
        goto out;
    }

    filler(buf, ".", NULL, 0, 0);
    filler(buf, "..", NULL, 0, 0);

    {
        dirent_t *de = dir->content.dir.entries->head;
        while (de) {
            filler(buf, de->name, NULL, 0, 0);
            de = de->next;
        }
    }

    update_times(dir, 1, 0, 0);

out:
    pthread_mutex_unlock(&g_lock);
    return res;
}

/* ---- mkdir ---- */
static int agentfs_mkdir(const char *path, mode_t mode)
{
    int res = 0;
    pthread_mutex_lock(&g_lock);

    /* Resolve parent and check permissions */
    uint64_t parent_ino;
    const char *name;
    res = path_parent_resolve(path, &parent_ino, &name);
    if (res != 0) goto out;

    inode_t *parent = inode_lookup(parent_ino);
    if (!parent) { res = -ENOENT; goto out; }

    res = perm_check(parent, PERM_WRITE | PERM_EXEC);
    if (res != 0) goto out;

    /* Check if name already exists in parent */
    if (dir_lookup(parent->content.dir.entries, name)) {
        res = -EEXIST;
        goto out;
    }

    /* Allocate new directory inode */
    inode_t *child = inode_alloc(INODE_DIR, S_IFDIR | (mode & 07777));
    if (!child) { res = -ENOSPC; goto out; }

    /* Add entry to parent */
    res = dir_add(parent->content.dir.entries, name, child->ino);
    if (res != 0) {
        inode_free(child->ino);
        goto out;
    }

    update_times(parent, 0, 1, 1);

out:
    pthread_mutex_unlock(&g_lock);
    return res;
}

/* ---- rmdir ---- */
static int agentfs_rmdir(const char *path)
{
    int res = 0;
    pthread_mutex_lock(&g_lock);

    uint64_t parent_ino;
    const char *name;
    res = path_parent_resolve(path, &parent_ino, &name);
    if (res != 0) goto out;

    inode_t *parent = inode_lookup(parent_ino);
    if (!parent) { res = -ENOENT; goto out; }

    res = perm_check(parent, PERM_WRITE | PERM_EXEC);
    if (res != 0) goto out;

    dirent_t *entry = dir_lookup(parent->content.dir.entries, name);
    if (!entry) { res = -ENOENT; goto out; }

    inode_t *child = inode_lookup(entry->ino);
    if (!child) { res = -ENOENT; goto out; }

    if (child->type != INODE_DIR) { res = -ENOTDIR; goto out; }

    /* Check that the child directory is empty */
    if (dir_count(child->content.dir.entries) > 0) {
        res = -ENOTEMPTY;
        goto out;
    }

    /* Remove entry from parent */
    dir_remove(parent->content.dir.entries, name);

    /* Free the child inode */
    inode_free(child->ino);

    update_times(parent, 0, 1, 1);

out:
    pthread_mutex_unlock(&g_lock);
    return res;
}

/* ---- create ---- */
static int agentfs_create(const char *path, mode_t mode,
                          struct fuse_file_info *fi)
{
    int res = 0;
    pthread_mutex_lock(&g_lock);

    uint64_t parent_ino;
    const char *name;
    res = path_parent_resolve(path, &parent_ino, &name);
    if (res != 0) goto out;

    inode_t *parent = inode_lookup(parent_ino);
    if (!parent) { res = -ENOENT; goto out; }

    res = perm_check(parent, PERM_WRITE | PERM_EXEC);
    if (res != 0) goto out;

    /* Check if name already exists */
    if (dir_lookup(parent->content.dir.entries, name)) {
        res = -EEXIST;
        goto out;
    }

    /* Allocate new file inode */
    inode_t *child = inode_alloc(INODE_FILE, S_IFREG | (mode & 07777));
    if (!child) { res = -ENOSPC; goto out; }

    /* Add entry to parent */
    res = dir_add(parent->content.dir.entries, name, child->ino);
    if (res != 0) {
        inode_free(child->ino);
        goto out;
    }

    update_times(parent, 0, 1, 1);

    /* Allocate file handle */
    file_handle_t *fh = calloc(1, sizeof(file_handle_t));
    if (!fh) {
        dir_remove(parent->content.dir.entries, name);
        inode_free(child->ino);
        res = -ENOMEM;
        goto out;
    }
    fh->ino = child->ino;
    fh->flags = fi->flags;
    fi->fh = (uint64_t)(uintptr_t)fh;

out:
    pthread_mutex_unlock(&g_lock);
    return res;
}

/* ---- open ---- */
static int agentfs_open(const char *path, struct fuse_file_info *fi)
{
    int res = 0;
    pthread_mutex_lock(&g_lock);

    uint64_t ino;
    res = path_resolve(path, &ino);
    if (res != 0) goto out;

    inode_t *n = inode_lookup(ino);
    if (!n) { res = -ENOENT; goto out; }

    if (n->type == INODE_DIR) { res = -EISDIR; goto out; }

    /* Check permissions based on open flags */
    int accmode = fi->flags & O_ACCMODE;
    if (accmode == O_RDONLY || accmode == O_RDWR)
        res = perm_check(n, PERM_READ);
    if (res == 0 && (accmode == O_WRONLY || accmode == O_RDWR))
        res = perm_check(n, PERM_WRITE);
    if (res != 0) goto out;

    /* Allocate file handle */
    file_handle_t *fh = calloc(1, sizeof(file_handle_t));
    if (!fh) { res = -ENOMEM; goto out; }
    fh->ino = ino;
    fh->flags = fi->flags;
    fi->fh = (uint64_t)(uintptr_t)fh;

out:
    pthread_mutex_unlock(&g_lock);
    return res;
}

/* ---- read ---- */
static int agentfs_read(const char *path, char *buf, size_t size, off_t offset,
                        struct fuse_file_info *fi)
{
    (void)path;
    int res;
    pthread_mutex_lock(&g_lock);

    uint64_t ino;
    if (fi && fi->fh) {
        file_handle_t *fh = (file_handle_t *)(uintptr_t)fi->fh;
        ino = fh->ino;
    } else {
        res = path_resolve(path, &ino);
        if (res != 0) goto out;
    }

    inode_t *n = inode_lookup(ino);
    if (!n || n->type != INODE_FILE) {
        res = n ? -EISDIR : -ENOENT;
        goto out;
    }

    res = perm_check(n, PERM_READ);
    if (res != 0) goto out;

    res = storage_read(n, buf, size, offset);
    update_times(n, 1, 0, 0);

out:
    pthread_mutex_unlock(&g_lock);
    return res;
}

/* ---- write ---- */
static int agentfs_write(const char *path, const char *buf, size_t size,
                         off_t offset, struct fuse_file_info *fi)
{
    (void)path;
    int res;
    pthread_mutex_lock(&g_lock);

    uint64_t ino;
    if (fi && fi->fh) {
        file_handle_t *fh = (file_handle_t *)(uintptr_t)fi->fh;
        ino = fh->ino;
    } else {
        res = path_resolve(path, &ino);
        if (res != 0) goto out;
    }

    inode_t *n = inode_lookup(ino);
    if (!n || n->type != INODE_FILE) {
        res = n ? -EISDIR : -ENOENT;
        goto out;
    }

    res = perm_check(n, PERM_WRITE);
    if (res != 0) goto out;

    res = storage_write(n, buf, size, offset);
    update_times(n, 0, 1, 1);

out:
    pthread_mutex_unlock(&g_lock);
    return res;
}

/* ---- unlink ---- */
static int agentfs_unlink(const char *path)
{
    int res = 0;
    pthread_mutex_lock(&g_lock);

    uint64_t parent_ino;
    const char *name;
    res = path_parent_resolve(path, &parent_ino, &name);
    if (res != 0) goto out;

    inode_t *parent = inode_lookup(parent_ino);
    if (!parent) { res = -ENOENT; goto out; }

    res = perm_check(parent, PERM_WRITE | PERM_EXEC);
    if (res != 0) goto out;

    dirent_t *entry = dir_lookup(parent->content.dir.entries, name);
    if (!entry) { res = -ENOENT; goto out; }

    inode_t *child = inode_lookup(entry->ino);
    if (!child) { res = -ENOENT; goto out; }

    if (child->type == INODE_DIR) { res = -EISDIR; goto out; }

    dir_remove(parent->content.dir.entries, name);
    inode_free(child->ino);

    update_times(parent, 0, 1, 1);

out:
    pthread_mutex_unlock(&g_lock);
    return res;
}

/* ---- rename ---- */
static int agentfs_rename(const char *from, const char *to,
                          unsigned int flags)
{
    int res = 0;
    pthread_mutex_lock(&g_lock);

    /* Resolve source */
    uint64_t src_parent_ino;
    const char *src_name;
    res = path_parent_resolve(from, &src_parent_ino, &src_name);
    if (res != 0) goto out;

    dirent_t *src_entry = dir_lookup(
        inode_lookup(src_parent_ino)->content.dir.entries, src_name);
    if (!src_entry) { res = -ENOENT; goto out; }

    uint64_t src_ino = src_entry->ino;

    /* Resolve destination parent */
    uint64_t dst_parent_ino;
    const char *dst_name;
    res = path_parent_resolve(to, &dst_parent_ino, &dst_name);
    if (res != 0) goto out;

    inode_t *dst_parent = inode_lookup(dst_parent_ino);
    if (!dst_parent) { res = -ENOENT; goto out; }

    /* Check write+exec on both parents */
    inode_t *src_parent = inode_lookup(src_parent_ino);
    res = perm_check(src_parent, PERM_WRITE | PERM_EXEC);
    if (res != 0) goto out;
    if (src_parent_ino != dst_parent_ino) {
        res = perm_check(dst_parent, PERM_WRITE | PERM_EXEC);
        if (res != 0) goto out;
    }

    /* Check destination */
    dirent_t *dst_entry = dir_lookup(dst_parent->content.dir.entries,
                                     dst_name);

    if (dst_entry) {
        if (flags & RENAME_NOREPLACE) {
            res = -EEXIST;
            goto out;
        }
        /* If target is a non-empty directory, fail */
        inode_t *dst_inode = inode_lookup(dst_entry->ino);
        if (dst_inode && dst_inode->type == INODE_DIR &&
            dir_count(dst_inode->content.dir.entries) > 0) {
            res = -ENOTEMPTY;
            goto out;
        }
        /* If source is dir and target is file, or vice versa */
        inode_t *src_inode = inode_lookup(src_ino);
        if (src_inode && dst_inode) {
            if (src_inode->type != dst_inode->type) {
                if (src_inode->type == INODE_DIR) {
                    res = -ENOTDIR;
                    goto out;
                } else {
                    res = -EISDIR;
                    goto out;
                }
            }
        }
        /* Remove destination */
        dir_remove(dst_parent->content.dir.entries, dst_name);
        if (dst_inode) inode_free(dst_entry->ino);
    }

    /* Perform the rename: add entry in dst dir, remove from src dir */
    res = dir_add(dst_parent->content.dir.entries, dst_name, src_ino);
    if (res != 0) goto out;

    dir_remove(src_parent->content.dir.entries, src_name);

    update_times(src_parent, 0, 1, 1);
    if (src_parent_ino != dst_parent_ino)
        update_times(dst_parent, 0, 1, 1);

    /* Update ctime on the renamed inode */
    {
        inode_t *moved = inode_lookup(src_ino);
        if (moved) update_times(moved, 0, 0, 1);
    }

out:
    pthread_mutex_unlock(&g_lock);
    return res;
}

/* ---- truncate ---- */
static int agentfs_truncate(const char *path, off_t size,
                            struct fuse_file_info *fi)
{
    (void)fi;
    int res = 0;
    pthread_mutex_lock(&g_lock);

    uint64_t ino;
    res = path_resolve(path, &ino);
    if (res != 0) goto out;

    inode_t *n = inode_lookup(ino);
    if (!n) { res = -ENOENT; goto out; }
    if (n->type == INODE_DIR) { res = -EISDIR; goto out; }

    res = perm_check(n, PERM_WRITE);
    if (res != 0) goto out;

    res = storage_truncate(n, size);
    update_times(n, 0, 1, 1);

out:
    pthread_mutex_unlock(&g_lock);
    return res;
}

/* ---- chmod ---- */
static int agentfs_chmod(const char *path, mode_t mode,
                         struct fuse_file_info *fi)
{
    (void)fi;
    int res = 0;
    pthread_mutex_lock(&g_lock);

    uint64_t ino;
    res = path_resolve(path, &ino);
    if (res != 0) goto out;

    inode_t *n = inode_lookup(ino);
    if (!n) { res = -ENOENT; goto out; }

    /* Only the owner or root can chmod */
    {
        struct fuse_context *ctx = fuse_get_context();
        if (ctx && ctx->uid != 0 && ctx->uid != n->uid) {
            res = -EPERM;
            goto out;
        }
    }

    n->mode = (n->mode & S_IFMT) | (mode & 07777);
    update_times(n, 0, 0, 1);

out:
    pthread_mutex_unlock(&g_lock);
    return res;
}

/* ---- fsync ---- */
static int agentfs_fsync(const char *path, int isdatasync,
                         struct fuse_file_info *fi)
{
    (void)path;
    (void)isdatasync;
    (void)fi;
    /* In-memory filesystem: no-op */
    return 0;
}

/* ---- release (called on close) ---- */
static int agentfs_release(const char *path, struct fuse_file_info *fi)
{
    (void)path;
    pthread_mutex_lock(&g_lock);
    if (fi && fi->fh) {
        file_handle_t *fh = (file_handle_t *)(uintptr_t)fi->fh;
        free(fh);
        fi->fh = 0;
    }
    pthread_mutex_unlock(&g_lock);
    return 0;
}

/* ---- utimens ---- */
static int agentfs_utimens(const char *path, const struct timespec ts[2],
                           struct fuse_file_info *fi)
{
    (void)fi;
    int res = 0;
    pthread_mutex_lock(&g_lock);

    uint64_t ino;
    res = path_resolve(path, &ino);
    if (res != 0) goto out;

    inode_t *n = inode_lookup(ino);
    if (!n) { res = -ENOENT; goto out; }

    n->atime = ts[0];
    n->mtime = ts[1];

out:
    pthread_mutex_unlock(&g_lock);
    return res;
}

/* ---- symlink ---- */
static int agentfs_symlink(const char *target, const char *linkpath)
{
    int res = 0;
    pthread_mutex_lock(&g_lock);

    uint64_t parent_ino;
    const char *name;
    res = path_parent_resolve(linkpath, &parent_ino, &name);
    if (res != 0) goto out;

    inode_t *parent = inode_lookup(parent_ino);
    if (!parent) { res = -ENOENT; goto out; }

    res = perm_check(parent, PERM_WRITE | PERM_EXEC);
    if (res != 0) goto out;

    if (dir_lookup(parent->content.dir.entries, name)) {
        res = -EEXIST;
        goto out;
    }

    /* Allocate new symlink inode */
    inode_t *child = inode_alloc(INODE_SYMLINK, S_IFLNK | 0777);
    if (!child) { res = -ENOSPC; goto out; }

    child->content.symlink.target = strdup(target);
    if (!child->content.symlink.target) {
        inode_free(child->ino);
        res = -ENOMEM;
        goto out;
    }

    child->size = strlen(target);

    res = dir_add(parent->content.dir.entries, name, child->ino);
    if (res != 0) {
        inode_free(child->ino);
        goto out;
    }

    update_times(parent, 0, 1, 1);

out:
    pthread_mutex_unlock(&g_lock);
    return res;
}

/* ---- readlink ---- */
static int agentfs_readlink(const char *path, char *buf, size_t bufsiz)
{
    int res = 0;
    pthread_mutex_lock(&g_lock);

    uint64_t ino;
    res = path_resolve(path, &ino);
    if (res != 0) goto out;

    inode_t *n = inode_lookup(ino);
    if (!n) { res = -ENOENT; goto out; }
    if (n->type != INODE_SYMLINK) { res = -EINVAL; goto out; }

    size_t len = strlen(n->content.symlink.target);
    if (len >= bufsiz) len = bufsiz - 1;
    memcpy(buf, n->content.symlink.target, len);
    buf[len] = '\0';

    update_times(n, 1, 0, 0);

out:
    pthread_mutex_unlock(&g_lock);
    return res;
}

/* ---- setxattr ---- */
static int agentfs_setxattr(const char *path, const char *key,
                            const char *value, size_t size, int flags)
{
    (void)flags;
    int res = 0;
    pthread_mutex_lock(&g_lock);

    /* Only user.* xattrs are supported */
    if (strncmp(key, "user.", 5) != 0 && strncmp(key, "trusted.", 8) != 0) {
        res = -EOPNOTSUPP;
        goto out;
    }

    uint64_t ino;
    res = path_resolve(path, &ino);
    if (res != 0) goto out;

    inode_t *n = inode_lookup(ino);
    if (!n) { res = -ENOENT; goto out; }

    /* Check write permission */
    res = perm_check(n, PERM_WRITE);
    if (res != 0) goto out;

    res = xattr_set(n, key, (const uint8_t *)value, size);
    if (res != 0) goto out;

    update_times(n, 0, 0, 1);

out:
    pthread_mutex_unlock(&g_lock);
    return res;
}

/* ---- getxattr ---- */
static int agentfs_getxattr(const char *path, const char *key,
                            char *value, size_t size)
{
    int res = 0;
    pthread_mutex_lock(&g_lock);

    uint64_t ino;
    res = path_resolve(path, &ino);
    if (res != 0) goto out;

    inode_t *n = inode_lookup(ino);
    if (!n) { res = -ENOENT; goto out; }

    res = xattr_get(n, key, (uint8_t *)value, size);

out:
    pthread_mutex_unlock(&g_lock);
    return res;
}

/* ---- listxattr ---- */
static int agentfs_listxattr(const char *path, char *list, size_t size)
{
    int res = 0;
    pthread_mutex_lock(&g_lock);

    uint64_t ino;
    res = path_resolve(path, &ino);
    if (res != 0) goto out;

    inode_t *n = inode_lookup(ino);
    if (!n) { res = -ENOENT; goto out; }

    res = xattr_list(n, list, size);

out:
    pthread_mutex_unlock(&g_lock);
    return res;
}

/* ---- removexattr ---- */
static int agentfs_removexattr(const char *path, const char *key)
{
    int res = 0;
    pthread_mutex_lock(&g_lock);

    uint64_t ino;
    res = path_resolve(path, &ino);
    if (res != 0) goto out;

    inode_t *n = inode_lookup(ino);
    if (!n) { res = -ENOENT; goto out; }

    /* Check write permission */
    res = perm_check(n, PERM_WRITE);
    if (res != 0) goto out;

    res = xattr_remove(n, key);
    if (res != 0) goto out;

    update_times(n, 0, 0, 1);

out:
    pthread_mutex_unlock(&g_lock);
    return res;
}

/* ---- statfs ---- */
static int agentfs_statfs(const char *path, struct statvfs *stbuf)
{
    (void)path;
    memset(stbuf, 0, sizeof(*stbuf));
    stbuf->f_bsize   = STORAGE_BLOCK_SIZE;
    stbuf->f_frsize  = STORAGE_BLOCK_SIZE;
    stbuf->f_blocks  = STORAGE_MAX_SIZE / STORAGE_BLOCK_SIZE;
    stbuf->f_bfree   = STORAGE_MAX_SIZE / STORAGE_BLOCK_SIZE;
    stbuf->f_bavail  = STORAGE_MAX_SIZE / STORAGE_BLOCK_SIZE;
    stbuf->f_namemax = 255;
    return 0;
}

/* ---- operations struct ---- */
static const struct fuse_operations agentfs_oper = {
    .init     = agentfs_init,
    .destroy  = agentfs_destroy,
    .getattr  = agentfs_getattr,
    .readdir  = agentfs_readdir,
    .mkdir    = agentfs_mkdir,
    .rmdir    = agentfs_rmdir,
    .create   = agentfs_create,
    .open     = agentfs_open,
    .read     = agentfs_read,
    .write    = agentfs_write,
    .unlink   = agentfs_unlink,
    .rename   = agentfs_rename,
    .truncate = agentfs_truncate,
    .chmod    = agentfs_chmod,
    .fsync    = agentfs_fsync,
    .release  = agentfs_release,
    .utimens  = agentfs_utimens,
    .symlink  = agentfs_symlink,
    .readlink = agentfs_readlink,
    .setxattr    = agentfs_setxattr,
    .getxattr    = agentfs_getxattr,
    .listxattr   = agentfs_listxattr,
    .removexattr = agentfs_removexattr,
    .statfs   = agentfs_statfs,
};

struct fuse_operations *agentfs_get_operations(void)
{
    /* Return a non-const pointer by casting (safe: FUSE doesn't modify it) */
    return (struct fuse_operations *)&agentfs_oper;
}
