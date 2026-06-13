#ifndef INODE_TABLE_H
#define INODE_TABLE_H

#include <stdint.h>
#include <sys/types.h>
#include <time.h>

/* inode types */
#define INODE_FILE    0
#define INODE_DIR     1
#define INODE_SYMLINK 2

/* forward declarations */
struct dirent_list;
struct xattr_entry;

typedef struct xattr_entry {
    char                *key;
    uint8_t             *value;
    size_t               valuelen;
    struct xattr_entry  *next;
} xattr_entry_t;

typedef struct {
    uint64_t ino;
    mode_t   mode;
    uid_t    uid;
    gid_t    gid;
    struct timespec atime, mtime, ctime;
    nlink_t  nlink;
    size_t   size;

    int type;  /* INODE_FILE, INODE_DIR, or INODE_SYMLINK */

    /* xattr linked list (NULL if none) */
    xattr_entry_t *xattrs;

    union {
        struct {
            uint8_t *data;
            size_t   capacity;
        } file;
        struct {
            struct dirent_list *entries;
        } dir;
        struct {
            char *target;  /* symlink target path */
        } symlink;
    } content;
} inode_t;

/*
 * Allocate a new inode of the given type and mode.
 * Increments the global next_ino counter.
 * Caller must hold the global lock.
 * Returns NULL if the inode table is full (ENOSPC).
 */
inode_t *inode_alloc(int type, mode_t mode);

/*
 * Look up an inode by number. Returns NULL if not found.
 * Caller must hold the global lock.
 */
inode_t *inode_lookup(uint64_t ino);

/*
 * Free an inode and remove it from the table.
 * Does NOT clean up directory entries pointing to this inode.
 * Caller must hold the global lock.
 */
void inode_free(uint64_t ino);

/*
 * Simple iteration: returns the first inode for which ino > prev_ino.
 * To iterate all inodes, start with prev_ino = 0 and repeat until
 * NULL is returned.
 * Caller must hold the global lock.
 */
inode_t *inode_iter(uint64_t prev_ino);

/*
 * Initialize the inode table and create the root inode.
 * Must be called once at startup (lock need not be held yet).
 */
void inode_table_init(void);

/*
 * Destroy the entire inode table and free all memory.
 * Must be called at shutdown (lock need not be held, but no other
 * threads may be active).
 */
void inode_table_destroy(void);

/*
 * Get the root inode number.
 */
uint64_t inode_get_root(void);

#endif /* INODE_TABLE_H */
