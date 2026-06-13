#include "path_utils.h"
#include "inode_table.h"
#include "dir_ops.h"
#include <string.h>
#include <errno.h>
#include <stdlib.h>

int path_resolve(const char *path, uint64_t *target_ino)
{
    if (!path || path[0] != '/') return -EINVAL;

    /* Root directory */
    if (strcmp(path, "/") == 0) {
        *target_ino = inode_get_root();
        return 0;
    }

    uint64_t current = inode_get_root();

    /* Make a mutable copy we can tokenize */
    char *copy = strdup(path);
    if (!copy) return -ENOMEM;

    char *saveptr;
    char *token = strtok_r(copy, "/", &saveptr);
    while (token) {
        inode_t *dir = inode_lookup(current);
        if (!dir || dir->type != INODE_DIR) {
            free(copy);
            return -ENOTDIR;
        }

        dirent_t *entry = dir_lookup(dir->content.dir.entries, token);
        if (!entry) {
            free(copy);
            return -ENOENT;
        }

        current = entry->ino;
        token = strtok_r(NULL, "/", &saveptr);
    }

    free(copy);
    *target_ino = current;
    return 0;
}

int path_parent_resolve(const char *path, uint64_t *parent_ino,
                        const char **name)
{
    if (!path || path[0] != '/') return -EINVAL;

    /* Root has no parent */
    if (strcmp(path, "/") == 0)
        return -EINVAL;

    /* Find the last slash */
    const char *last_slash = strrchr(path, '/');
    if (!last_slash) return -EINVAL;

    /* Extract parent path */
    size_t parent_len;
    if (last_slash == path) {
        /* Parent is root */
        *parent_ino = inode_get_root();
    } else {
        parent_len = (size_t)(last_slash - path);
        char *parent_path = strndup(path, parent_len);
        if (!parent_path) return -ENOMEM;
        int rc = path_resolve(parent_path, parent_ino);
        free(parent_path);
        if (rc != 0) return rc;
    }

    /* Check that parent exists and is a directory */
    inode_t *parent = inode_lookup(*parent_ino);
    if (!parent || parent->type != INODE_DIR)
        return -ENOTDIR;

    *name = last_slash + 1;
    if (**name == '\0')
        return -EINVAL;

    return 0;
}
