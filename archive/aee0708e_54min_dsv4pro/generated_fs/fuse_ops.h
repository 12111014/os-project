/*
 * fuse_ops.h — shared types, inode and dirent structures, and module API
 * declarations for simplefs.
 *
 * All internal modules and the FUSE callbacks reference these definitions.
 */

#ifndef FUSE_OPS_H
#define FUSE_OPS_H

#define FUSE_USE_VERSION 31

#include <fuse.h>
#include <time.h>
#include <sys/stat.h>
#include <stddef.h>
#include <stdint.h>

/* ------------------------------------------------------------------------ */
/*  Limits                                                                  */
/* ------------------------------------------------------------------------ */

#define SYMLOOP_MAX  40          /* max symlink resolution depth */
#define PATH_MAX_SZ  4096        /* internal max path length */

/* ------------------------------------------------------------------------ */
/*  Xattr linked-list node                                                  */
/* ------------------------------------------------------------------------ */

struct xattr_node {
	char              *name;       /* heap-allocated, null-terminated */
	uint8_t           *value;      /* heap-allocated raw buffer       */
	size_t             value_len;  /* length of value buffer          */
	struct xattr_node *next;       /* next xattr in list              */
};

/* ------------------------------------------------------------------------ */
/*  Directory entry (sorted singly-linked list)                              */
/* ------------------------------------------------------------------------ */

struct dirent {
	char         *name;      /* heap-allocated entry name */
	uint64_t      ino;       /* inode number of child     */
	struct dirent *next;     /* next sibling (sorted)     */
};

/* ------------------------------------------------------------------------ */
/*  Inode                                                                    */
/* ------------------------------------------------------------------------ */

struct inode {
	uint64_t          ino;       /* unique inode number (monotonic) */
	mode_t            mode;      /* file type + permission bits    */
	nlink_t           nlink;     /* hard-link count (always 1)     */
	uid_t             uid;       /* owner user id                  */
	gid_t             gid;       /* owner group id                 */
	off_t             size;      /* logical file size in bytes     */
	struct timespec   atime;     /* access time                    */
	struct timespec   mtime;     /* modify time                    */
	struct timespec   ctime;     /* change time                    */

	uint8_t          *data;      /* byte buffer (S_IFREG)          */
	size_t            cap;       /* allocated capacity of data     */
	char             *target;    /* symlink target (S_IFLNK)       */

	struct dirent    *children;  /* directory entries (S_IFDIR)     */
	struct xattr_node *xattrs;   /* extended attributes             */

	int               refcount;  /* open/lookup reference count    */
};

/* ------------------------------------------------------------------------ */
/*  Module API — inode_table                                                 */
/* ------------------------------------------------------------------------ */

struct inode *inode_alloc(mode_t mode, uid_t uid, gid_t gid);
struct inode *inode_lookup(uint64_t ino);
struct inode *inode_lookup_by_path(const char *path);
void          inode_put(struct inode *ino);
void          inode_unlink(struct inode *ino);

/* ------------------------------------------------------------------------ */
/*  Module API — dir_ops                                                     */
/* ------------------------------------------------------------------------ */

int dir_add(uint64_t parent_ino, const char *name, uint64_t child_ino);
int dir_remove(uint64_t parent_ino, const char *name);
int dir_lookup(uint64_t parent_ino, const char *name, uint64_t *child_out);
int dir_readdir(uint64_t parent_ino, off_t offset,
                void *buf, fuse_fill_dir_t filler);

/* ------------------------------------------------------------------------ */
/*  Module API — storage_backend                                             */
/* ------------------------------------------------------------------------ */

int storage_read(uint64_t ino, off_t offset, char *buf, size_t size);
int storage_write(uint64_t ino, off_t offset, const char *buf, size_t size);
int storage_truncate(uint64_t ino, off_t new_size);

/* ------------------------------------------------------------------------ */
/*  Module API — path_utils                                                  */
/* ------------------------------------------------------------------------ */

int  path_normalize(const char *in, char *out, size_t outsz);
int  path_parent(const char *path, char *parent, size_t parent_sz,
                 const char **basename);
int  path_resolve_symlink(const char *path, char *resolved, size_t res_sz);

/* ------------------------------------------------------------------------ */
/*  Global lock (single mutex for all operations)                            */
/* ------------------------------------------------------------------------ */

#include <pthread.h>
extern pthread_mutex_t g_lock;

#endif /* FUSE_OPS_H */
