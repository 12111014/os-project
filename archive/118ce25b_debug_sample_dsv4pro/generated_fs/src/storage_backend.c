#include "storage_backend.h"
#include <stdlib.h>
#include <string.h>
#include <errno.h>

static int ensure_capacity(inode_t *inode, size_t need)
{
    if (need <= inode->content.file.capacity)
        return 0;

    if (need > STORAGE_MAX_SIZE)
        return -ENOSPC;

    /* Align to 4KB boundaries, doubling strategy */
    size_t newcap = inode->content.file.capacity;
    if (newcap == 0)
        newcap = STORAGE_BLOCK_SIZE;
    while (newcap < need) {
        if (newcap > STORAGE_MAX_SIZE / 2)
            newcap = STORAGE_MAX_SIZE;
        else
            newcap *= 2;
        if (newcap >= STORAGE_MAX_SIZE) {
            newcap = STORAGE_MAX_SIZE;
            break;
        }
    }

    uint8_t *p = realloc(inode->content.file.data, newcap);
    if (!p)
        return -ENOMEM;

    /* Zero the newly allocated region */
    memset(p + inode->content.file.capacity, 0,
           newcap - inode->content.file.capacity);

    inode->content.file.data = p;
    inode->content.file.capacity = newcap;
    return 0;
}

int storage_read(inode_t *inode, char *buf, size_t size, off_t offset)
{
    if (offset < 0) return -EINVAL;
    if ((size_t)offset >= inode->size)
        return 0;

    size_t avail = inode->size - (size_t)offset;
    if (size > avail)
        size = avail;
    memcpy(buf, inode->content.file.data + offset, size);
    return (int)size;
}

int storage_write(inode_t *inode, const char *buf, size_t size, off_t offset)
{
    if (offset < 0) return -EINVAL;

    size_t end = (size_t)offset + size;
    int rc = ensure_capacity(inode, end);
    if (rc != 0)
        return rc;

    memcpy(inode->content.file.data + offset, buf, size);
    if (end > inode->size)
        inode->size = end;
    return (int)size;
}

int storage_truncate(inode_t *inode, off_t new_size)
{
    if (new_size < 0) return -EINVAL;

    size_t ns = (size_t)new_size;
    int rc = ensure_capacity(inode, ns);
    if (rc != 0)
        return rc;

    if (ns > inode->size)
        memset(inode->content.file.data + inode->size, 0, ns - inode->size);
    inode->size = ns;
    return 0;
}

void storage_free_buffer(uint8_t *data)
{
    free(data);
}
