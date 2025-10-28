# STACK (lifo)
class Stack:
    def __init__(self):
        self.items = []
    
    def push(self, item):
        self.items.append(item)
    
    def pop(self):
        if self.is_empty():
            return None
        return self.items.pop()
        
    def peek(self):
        if self.is_empty():
            return None
        return self.items[-1]
    
    def is_empty(self):
        return len(self.items) == 0
    
    def size(self):
        return len(self.items)
    
    def clear(self):
        self.items.clear()
    
    def show_stack(self):
        return self.items
    
# QUEUE (FIFO)
class Queue:
    def __init__(self):
        self.items = []
    
    def enqueue(self, item):
        self.items.append(item)

    def dequeue(self):
        if self.is_empty():
            return None
        return self.items.pop(0)
    
    def front(self):
        if self.is_empty():
            return None
        return self.items[0]
    
    def is_empty(self):
        return len(self.items) == 0
    
    def size(self):
        return len(self.items)
    
    def clear(self):
        self.items.clear()
    
    def show_queue(self):
        return self.items
    
# ORDER
class OrderedTable:
    def __init__(self):
        self.pairs = []
    
    def set(self, key, value):
        for index, (existing_key, _) in enumerate(self.pairs):
            if existing_key == key:
                self.pairs[index] = (key, value)
                return
        self.pairs.append((key, value))

    def get(self, key):
        for existing_key, existing_value in self.pairs:
            if existing_key == key:
                return existing_value
        return None
    
    def has(self, key):
        return any(existing_key == key for existing_key, _ in self.pairs)
    
    def delete(self, key):
        for index, (existing_key, _) in enumerate(self.pairs):
            if existing_key == key:
                del self.pairs[index]
                return True
        return False
    
    def keys(self):
        return [key for key, _ in self.pairs]
    
    def values(self):
        return [value for _, value in self.pairs]
    
    def items(self):
        return self.pairs
    
    def size(self):
        return len(self.pairs)
    
    def clear(self):
        self.pairs.clear()