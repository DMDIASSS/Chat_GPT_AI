"""Private local subprocess protocol. Never accept frames from a network peer."""
import pickle
import struct

LIMIT=32*1024*1024


def read_frame(stream):
    def read_exact(count):
        pieces=[];remaining=count
        while remaining:
            piece=stream.read(remaining)
            if not piece:raise EOFError('Forecast worker pipe closed')
            pieces.append(piece);remaining-=len(piece)
        return b''.join(pieces)
    size=struct.unpack('<I',read_exact(4))[0]
    if not 0<size<=LIMIT:raise ValueError('Invalid forecast frame size')
    return pickle.loads(read_exact(size))


def write_frame(stream,value):
    payload=pickle.dumps(value,protocol=5)
    if len(payload)>LIMIT:raise ValueError('Forecast frame exceeds local protocol limit')
    for part in (struct.pack('<I',len(payload)),payload):
        view=memoryview(part)
        while view:
            count=stream.write(view)
            if not count:raise EOFError('Forecast worker pipe closed while writing')
            view=view[count:]
    stream.flush()
