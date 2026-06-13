#ifndef STORAGE_BACKEND_H
#define STORAGE_BACKEND_H

#include "inode_table.h"
#include <stddef.h>
#include <stdint.h>

#define STORAGE_BLOCK_SIZE 4096
#define STORAGE_MAX_SIZE   (1024ULL * 1024 * 1024)  /* 1 GB */

/*
 * Read up to 'size' bytes from the file inode's data buffer starting at
 * 'offset'. Returns the number of bytes actually read (may be less if
 * offset >= file size). Caller must hold the global lock.
 */
int storage_read(inode_t *inode, char *buf, size_t size, off_t offset);

/*
 * Write 'size' bytes from 'buf' to the file inode's data buffer at
 * 'offset'. Grows the buffer as needed. Returns the number of bytes
 * written on success, or a negative errno on failure.
 * Caller must hold the global lock.
 */
int storage_write(inode_t *inode, const char *buf, size_t size, off_t offset);

/*
 * Truncate the file inode's data to 'new_size' bytes. Grows or shrinks
 * the buffer as needed. Zero-fills expanded regions. Returns 0 on success
 * or negative errno.
 * Caller must hold the global lock.
 */
int storage_truncate(inode_t *inode, off_t new_size);

/*
 * Free a file data buffer. Safe to call with NULL.
 */
void storage_free_buffer(uint8_t *data);

#endif /* STORAGE_BACKEND_H */
