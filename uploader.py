import json
import time
import os
from read_sheet import get_creds, get_rows, rows_to_json, update_fields_with_default


STATE_CONFIG_FILENAME = 'state_config.json'
SECONDS_BETWEEN_REFRESH = 60


def get_last_updated_time():
    if os.path.exists(STATE_CONFIG_FILENAME):
        with open(STATE_CONFIG_FILENAME, 'r') as f:
            state_config = json.load(f)
            return state_config['last_updated']
    return 0


def set_last_updated_time(timestamp):
    with open(STATE_CONFIG_FILENAME, 'w') as f:
        json.dump({'last_updated': timestamp}, f)


def update_if_needed(force_update=False, *args, **kwargs):
    past = get_last_updated_time()
    present = time.time()
    if present - past > SECONDS_BETWEEN_REFRESH or force_update:
        message = update_people(*args, **kwargs)
        set_last_updated_time(present)
    else:
        message = 'No update is needed as only {} seconds passed before the last one'.format(present - past)
    return message


def update_people(people_filename=None):
    with open('updater_config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
    if people_filename is None:
        people_filename = os.path.join('static', config['data_filename'])
    creds = get_creds()
    rows = get_rows(creds, config['sheet_id'], config['sheet_range'])
    parse_message, result = rows_to_json(config, rows)
    result = update_fields_with_default(result)
    with open(people_filename, 'w', encoding='utf-8') as f:
        f.write('var people = ')
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write(';\n')
    # todo: optionally, validate the sheet and print the warnings (especially in the web mode)
    message = parse_message + 'Parsed successfully!'
    return message


if __name__ == '__main__':
    # todo: make a background worker script to update the data asynchronously
    update_people()
