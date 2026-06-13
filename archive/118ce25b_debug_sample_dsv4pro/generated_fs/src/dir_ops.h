#ifndef DIR_OPS_H
#define DIR_OPS_H

#include <stdint.h>

/*
 * Directory entry in a doubly-linked list.
 */
typedef struct dirent {
    char          *name;
    uint64_t       ino;
    struct dirent *prev;
    struct dirent *next;
} dirent_t;

/*
 * Container for a directory's entry list.
 */
typedef struct dirent_list {
    dirent_t *head;
    dirent_t *tail;
} dirent_list_t;

/* Allocate an empty directory entry list. */
dirent_list_t *dir_list_alloc(void);

/* Free the entire entry list and all entries. */
void dir_list_free(dirent_list_t *list);

/*
 * Look up a child entry by name in the directory list.
 * Returns the dirent pointer or NULL if not found.
 */
dirent_t *dir_lookup(dirent_list_t *list, const char *name);

/*
 * Add a new entry (name, ino) to the directory.
 * Returns 0 on success, -EEXIST if name already present, -ENOMEM on error.
 * Entries are inserted in sorted order (by name).
 */
int dir_add(dirent_list_t *list, const char *name, uint64_t ino);

/*
 * Remove an entry by name. Returns 0 on success, -ENOENT if not found.
 */
int dir_remove(dirent_list_t *list, const char *name);

/*
 * Count entries in the directory (not including . and ..).
 */
int dir_count(dirent_list_t *list);

#endif /* DIR_OPS_H */
