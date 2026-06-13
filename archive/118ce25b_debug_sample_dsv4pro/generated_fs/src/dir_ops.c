#include "dir_ops.h"
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <stdio.h>

dirent_list_t *dir_list_alloc(void)
{
    dirent_list_t *list = calloc(1, sizeof(dirent_list_t));
    if (!list) {
        fprintf(stderr, "FATAL: out of memory allocating dirent_list\n");
        abort();
    }
    return list;
}

void dir_list_free(dirent_list_t *list)
{
    if (!list) return;
    dirent_t *cur = list->head;
    while (cur) {
        dirent_t *next = cur->next;
        free(cur->name);
        free(cur);
        cur = next;
    }
    free(list);
}

dirent_t *dir_lookup(dirent_list_t *list, const char *name)
{
    dirent_t *cur = list->head;
    while (cur) {
        if (strcmp(cur->name, name) == 0)
            return cur;
        cur = cur->next;
    }
    return NULL;
}

int dir_add(dirent_list_t *list, const char *name, uint64_t ino)
{
    /* Check for duplicate */
    if (dir_lookup(list, name))
        return -EEXIST;

    dirent_t *entry = calloc(1, sizeof(dirent_t));
    if (!entry)
        return -ENOMEM;

    entry->name = strdup(name);
    if (!entry->name) {
        free(entry);
        return -ENOMEM;
    }
    entry->ino = ino;

    /* Insert in sorted order (by name) */
    if (!list->head) {
        list->head = list->tail = entry;
    } else {
        dirent_t *cur = list->head;
        dirent_t *prev = NULL;
        while (cur && strcmp(cur->name, name) < 0) {
            prev = cur;
            cur = cur->next;
        }
        if (!prev) {
            /* Insert at head */
            entry->next = list->head;
            list->head->prev = entry;
            list->head = entry;
        } else if (!cur) {
            /* Insert at tail */
            prev->next = entry;
            entry->prev = prev;
            list->tail = entry;
        } else {
            /* Insert between prev and cur */
            prev->next = entry;
            entry->prev = prev;
            entry->next = cur;
            cur->prev = entry;
        }
    }
    return 0;
}

int dir_remove(dirent_list_t *list, const char *name)
{
    dirent_t *entry = dir_lookup(list, name);
    if (!entry)
        return -ENOENT;

    if (entry->prev)
        entry->prev->next = entry->next;
    else
        list->head = entry->next;

    if (entry->next)
        entry->next->prev = entry->prev;
    else
        list->tail = entry->prev;

    free(entry->name);
    free(entry);
    return 0;
}

int dir_count(dirent_list_t *list)
{
    int count = 0;
    dirent_t *cur = list->head;
    while (cur) {
        count++;
        cur = cur->next;
    }
    return count;
}
