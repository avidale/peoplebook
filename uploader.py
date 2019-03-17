import json
import os
from read_sheet import get_creds, get_rows, rows_to_json, update_fields_with_default


def update_people(people_filename=None):
    with open('updater_config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
    if people_filename is None:
        people_filename = os.path.join('static', config['data_filename'])
    creds = get_creds()
    rows = get_rows(creds, config['sheet_id'], config['sheet_range'])
    result = rows_to_json(config, rows)
    result = update_fields_with_default(result)
    with open(people_filename, 'w', encoding='utf-8') as f:
        f.write('var people = ')
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write(';\n')
    # todo: optionally, validate the sheet and print the warnings (especially in the web mode)
    message = 'Parsed successfully!'
    return message


if __name__ == '__main__':
    update_people(people_filename='static/data.js')
