

def serialize(data):
    if hasattr(data, '__dict__'):
        return {k: serialize(v) for k, v in data.__dict__.items()}
    return data
