#include "inode_table.h"
#include "dir_ops.h"
#include "storage_backend.h"
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <stdio.h>
#include <pthread.h>
#include <unistd.h>
#include <sys/stat.h>

/*
 * xattr helper: add/replace an xattr entry on an inode.
 * Caller must hold the global lock.
 */
int xattr_set(inode_t *n, const char *key, const uint8_t *value, size_t valuelen)
{
    xattr_entry_t *cur = n->xattrs;
    while (cur) {
        if (strcmp(cur->key, key) == 0) {
            /* Replace existing */
            free(cur->value);
            cur->value = malloc(valuelen);
            if (!cur->value) return -ENOMEM;
            memcpy(cur->value, value, valuelen);
            cur->valuelen = valuelen;
            return 0;
        }
        cur = cur->next;
    }
    /* Insert new at head */
    xattr_entry_t *e = calloc(1, sizeof(xattr_entry_t));
    if (!e) return -ENOMEM;
    e->key = strdup(key);
    if (!e->key) { free(e); return -ENOMEM; }
    e->value = malloc(valuelen);
    if (!e->value) { free(e->key); free(e); return -ENOMEM; }
    memcpy(e->value, value, valuelen);
    e->valuelen = valuelen;
    e->next = n->xattrs;
    n->xattrs = e;
    return 0;
}

/*
 * xattr helper: get an xattr entry by key.
 * Caller must hold the global lock.
 * Returns the value length, or negative errno.
 */
int xattr_get(const inode_t *n, const char *key, uint8_t *buf, size_t bufsiz)
{
    xattr_entry_t *cur = n->xattrs;
    while (cur) {
        if (strcmp(cur->key, key) == 0) {
            if (bufsiz == 0) return (int)cur->valuelen;
            size_t copy = cur->valuelen < bufsiz ? cur->valuelen : bufsiz;
            memcpy(buf, cur->value, copy);
            return (int)cur->valuelen;
        }
        cur = cur->next;
    }
    return -ENODATA;
}

/*
 * xattr helper: list all xattr keys.
 * Caller must hold the global lock.
 * Returns total bytes needed, writes to buf (may be NULL to just query size).
 */
int xattr_list(const inode_t *n, char *buf, size_t bufsiz)
{
    size_t needed = 0;
    xattr_entry_t *cur = n->xattrs;
    while (cur) {
        size_t len = strlen(cur->key) + 1;
        if (buf && needed + len <= bufsiz)
            memcpy(buf + needed, cur->key, len);
        needed += len;
        cur = cur->next;
    }
    if (buf && bufsiz > 0 && needed < bufsiz)
        buf[needed] = '\0';
    return (int)needed;
}

/*
 * xattr helper: remove an xattr entry by key.
 * Caller must hold the global lock.
 * Returns 0 on success, negative errno.
 */
int xattr_remove(inode_t *n, const char *key)
{
    xattr_entry_t *prev = NULL;
    xattr_entry_t *cur = n->xattrs;
    while (cur) {
        if (strcmp(cur->key, key) == 0) {
            if (prev)
                prev->next = cur->next;
            else
                n->xattrs = cur->next;
            free(cur->key);
            free(cur->value);
            free(cur);
            return 0;
        }
        prev = cur;
        cur = cur->next;
    }
    return -ENODATA;
}

/*
 * xattr helper: free all xattrs on an inode.
 * Caller must hold the global lock.
 */
void xattr_free_all(inode_t *n)
{
    xattr_entry_t *cur = n->xattrs;
    while (cur) {
        xattr_entry_t *next = cur->next;
        free(cur->key);
        free(cur->value);
        free(cur);
        cur = next;
    }
    n->xattrs = NULL;
}

/* ---- external global state (defined in main.c) ---- */
extern pthread_mutex_t g_lock;

/* ---- internal state ---- */
#define MAX_INODES 8192

static inode_t g_inode_pool[MAX_INODES];
static int    g_inode_used[MAX_INODES];
static uint64_t g_next_ino = 2;   /* 1 is reserved for root */
static uint64_t g_root_ino = 1;

void inode_table_init(void)
{
    memset(g_inode_pool, 0, sizeof(g_inode_pool));
    memset(g_inode_used, 0, sizeof(g_inode_used));
    g_next_ino = 2;
    g_root_ino = 1;

    /* Allocate root directory inode */
    inode_t *root = inode_alloc(INODE_DIR, 0755);
    if (!root) {
        fprintf(stderr, "FATAL: cannot allocate root inode\n");
        abort();
    }
    /* Fix up: allocate returns ino = 2 by default; we force 1 for root */
    /* So free the auto-allocated one and manually set slot 0 */
    inode_free(root->ino);

    /* Manually seed root at index 0 */
    memset(&g_inode_pool[0], 0, sizeof(inode_t));
    g_inode_used[0] = 1;
    g_inode_pool[0].ino = 1;
    g_inode_pool[0].mode = S_IFDIR | 0755;
    g_inode_pool[0].uid = getuid();
    g_inode_pool[0].gid = getgid();
    g_inode_pool[0].nlink = 2;
    g_inode_pool[0].type = INODE_DIR;
    g_inode_pool[0].content.dir.entries = dir_list_alloc();
    clock_gettime(CLOCK_REALTIME, &g_inode_pool[0].atime);
    g_inode_pool[0].mtime = g_inode_pool[0].atime;
    g_inode_pool[0].ctime = g_inode_pool[0].atime;
    g_next_ino = 2;
}

uint64_t inode_get_root(void)
{
    return g_root_ino;
}

inode_t *inode_alloc(int type, mode_t mode)
{
    for (int i = 0; i < MAX_INODES; i++) {
        if (!g_inode_used[i]) {
            memset(&g_inode_pool[i], 0, sizeof(inode_t));
            g_inode_used[i] = 1;
            inode_t *n = &g_inode_pool[i];
            n->ino = g_next_ino++;
            n->mode = mode;
            n->uid = getuid();
            n->gid = getgid();
            n->nlink = (type == INODE_DIR) ? 2 : 1;
            n->type = type;
            n->size = 0;
            clock_gettime(CLOCK_REALTIME, &n->atime);
            n->mtime = n->atime;
            n->ctime = n->atime;
            if (type == INODE_DIR) {
                n->content.dir.entries = dir_list_alloc();
            } else if (type == INODE_SYMLINK) {
                n->content.symlink.target = NULL;
            } else {
                n->content.file.data = NULL;
                n->content.file.capacity = 0;
            }
            return n;
        }
    }
    return NULL;
}

inode_t *inode_lookup(uint64_t ino)
{
    for (int i = 0; i < MAX_INODES; i++) {
        if (g_inode_used[i] && g_inode_pool[i].ino == ino)
            return &g_inode_pool[i];
    }
    return NULL;
}

void inode_free(uint64_t ino)
{
    for (int i = 0; i < MAX_INODES; i++) {
        if (g_inode_used[i] && g_inode_pool[i].ino == ino) {
            inode_t *n = &g_inode_pool[i];
            xattr_free_all(n);
            if (n->type == INODE_DIR) {
                dir_list_free(n->content.dir.entries);
            } else if (n->type == INODE_SYMLINK) {
                free(n->content.symlink.target);
            } else {
                storage_free_buffer(n->content.file.data);
            }
            memset(n, 0, sizeof(inode_t));
            g_inode_used[i] = 0;
            return;
        }
    }
}

inode_t *inode_iter(uint64_t prev_ino)
{
    inode_t *best = NULL;
    for (int i = 0; i < MAX_INODES; i++) {
        if (g_inode_used[i] && g_inode_pool[i].ino > prev_ino) {
            if (!best || g_inode_pool[i].ino < best->ino)
                best = &g_inode_pool[i];
        }
    }
    return best;
}

void inode_table_destroy(void)
{
    for (int i = 0; i < MAX_INODES; i++) {
        if (g_inode_used[i]) {
            inode_t *n = &g_inode_pool[i];
            xattr_free_all(n);
            if (n->type == INODE_DIR) {
                dir_list_free(n->content.dir.entries);
            } else if (n->type == INODE_SYMLINK) {
                free(n->content.symlink.target);
            } else {
                storage_free_buffer(n->content.file.data);
            }
            memset(n, 0, sizeof(inode_t));
            g_inode_used[i] = 0;
        }
    }
}
