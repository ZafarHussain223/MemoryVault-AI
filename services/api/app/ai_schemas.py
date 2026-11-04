"""JSON contracts for local constrained decoding; validators remain authoritative."""
def text(maximum=1000):
    return {'type': 'string', 'minLength': 1, 'maxLength': maximum}


def record(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}


def array(items, maximum, minimum=0):
    return {'type': 'array', 'items': items, 'minItems': minimum, 'maxItems': maximum}


def source(count):
    return {'type': 'integer', 'minimum': 1, 'maximum': count}


def flashcards(count):
    return array(record({'question': text(500), 'answer': text(800), 'source': source(count)}), 5, 1)


def insight(count):
    return record({'summary': text(800), 'detailed_summary': text(1600),
                   'key_points': array(text(300), 6, 1), 'categories': array(text(50), 6),
                   'entities': array(record({'name': text(100), 'type': text(50)}), 8),
                   'sources': array(source(count), min(count, 12), 1)})


def quiz(count):
    return array(record({'question': text(400), 'options': array(text(120), 4, 4),
                         'correct_answer': {'type': 'integer', 'minimum': 0, 'maximum': 3},
                         'explanation': text(400), 'source': source(count)}), 5)


def conflicts(count):
    return array(record({'source_a': source(count), 'source_b': source(count),
                         'quote_a': text(500), 'quote_b': text(500), 'explanation': text(500)}), 5)
