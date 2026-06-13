#ifndef PATH_UTILS_H
#define PATH_UTILS_H

#include <stdint.h>

/*
 * Resolve a full path to an inode number by walking from root.
 * On success, returns 0 and sets *target_ino to the target inode number.
 * On failure, returns a negative errno:
 *   -ENOENT if any component doesn't exist
 *   -ENOTDIR if an intermediate component is not a directory
 * Caller must hold the global lock.
 */
int path_resolve(const char *path, uint64_t *target_ino);

/*
 * Resolve a path to find the parent directory and the final component name.
 * The parent directory must exist and be a directory; the final component
 * may or may not exist.
 * On success, returns 0 and sets *parent_ino and *name (points into a
 * static buffer — copy if needed).
 * On failure, returns a negative errno.
 * Caller must hold the global lock.
 */
int path_parent_resolve(const char *path, uint64_t *parent_ino,
                        const char **name);

#endif /* PATH_UTILS_H */
