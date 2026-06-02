CC = gcc
CFLAGS = -g -Wall -D_FILE_OFFSET_BITS=64 $(shell pkg-config --cflags fuse3)
LDLIBS = $(shell pkg-config --libs fuse3)

TARGET = passthrough_ll
SRC = passthrough_ll.c
OBJ = $(SRC:.c=.o)

all: $(TARGET)

$(TARGET): $(OBJ)
	$(CC) $(OBJ) -o $@ $(LDLIBS)

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f $(OBJ) $(TARGET)

.PHONY: all clean