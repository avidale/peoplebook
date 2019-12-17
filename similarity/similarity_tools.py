

def deduplicate(facts, max_number=3, threshold=0.5):
    lhs = set()
    rhs = set()
    facts = sorted(facts, key=lambda x: x['score'], reverse=True)
    result = []
    for fact in facts:
        if fact['first'] not in lhs and fact['second'] not in rhs and fact['score'] >= threshold:
            result.append(fact)
        lhs.add(fact['first'])
        rhs.add(fact['second'])
    return result[:max_number]
