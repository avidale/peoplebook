import random
import pandas as pd

from collections import defaultdict, Counter
from datetime import datetime, timedelta

from utils.database import Database
from utils.spaces import SpaceConfig


def days_since(x):
    return (datetime.now() - datetime.fromisoformat(x)) / timedelta(days=1)


def generate_pairs(users, shuffle=True):
    # from a list of users, create pairs by joining each i*2 with each i*2+1'th.
    # if there is an odd number of users (but more than 1!),
    # the first user is additionally paired with the last one
    free_users = [u for u in users]
    if shuffle:
        random.shuffle(free_users)
    user_to_matches = defaultdict(list)
    for i in range(0, len(free_users)-1, 2):
        user_to_matches[free_users[i]] = [free_users[i + 1]]
        user_to_matches[free_users[i + 1]] = [free_users[i]]
    if len(free_users) % 2 == 1 and len(free_users) > 1:
        user_to_matches[free_users[0]].append(free_users[-1])
        user_to_matches[free_users[-1]].append(free_users[0])
    return user_to_matches


def generate_greedy_pairs(free_users, repeatedness, q=0.03):
    # generate pairs by repeatedly connecting the least familiar pair
    reps = []
    for u1 in free_users:
        for u2 in free_users:
            if u1 < u2:
                reps.append({'u1': u1, 'u2': u2, 'r': repeatedness.get((u1, u2), 0)})
    reps = pd.DataFrame.from_records(reps)

    order = []

    while reps.shape[0] > 0:
        # sample a pair from the least familiar ones
        row = reps[reps.r <= reps.r.quantile(q)].sample(1).iloc[0]
        order.append(row.u1)
        order.append(row.u2)
        reps = reps[(reps.u1 != row.u1) & (reps.u1 != row.u2) & (reps.u2 != row.u1) & (reps.u2 != row.u2)]

    for u in free_users:
        if u not in order:
            order.append(u)

    pairs = generate_pairs(order, shuffle=False)
    return pairs


def evaluate_pairs(matching, repeatedness):
    loss = 0
    for u1, peers in matching.items():
        for u2 in peers:
            loss += repeatedness[(u1, u2)]
    return loss


def generate_good_pairs(database: Database, space: SpaceConfig, now, decay=0.99, attempts=100):
    # 0.99 per day = 0.7 per month = 0.02 per year
    free_users = [
        str(user['tg_id'])
        for user in database.mongo_users.find({'wants_next_coffee': True, 'space': space.key})
        if (
            not user.get('deactivated', False)
            and user.get('last_activity')
            and days_since(user['last_activity']) <= 31
            and database.has_at_least_level(user_object=user, level=space.who_can_use_random_coffee)
        )
    ]
    # we deliberately use all the spaces here to avoid same pairs across different spaces
    prev_coffee_pairs = list(database.mongo_coffee_pairs.find({}))
    repeatedness = Counter()
    for matching in prev_coffee_pairs[::-1]:  # from current to old
        if 'date' not in matching:
            lag = 30
        else:
            prev_date = datetime.strptime(matching['date'], "%Y-%m-%d %H:%M:%S.%f")
            diff = now - prev_date
            lag = diff.total_seconds() / (60*60*24*7)
        for u1, peers in matching['matches'].items():
            for u2 in peers:
                repeatedness[(u1, u2)] += decay ** lag
    best_score = sum(repeatedness.values()) + 100500  # total sum is definitely more that a partial sum
    best_pair = None
    for i in range(attempts):
        matching = generate_greedy_pairs(free_users, repeatedness)
        score = evaluate_pairs(matching, repeatedness)
        if score < best_score:
            best_score = score
            best_pair = matching
    return best_pair
