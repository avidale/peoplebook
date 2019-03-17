from __future__ import print_function
import copy
import json
import pickle
import re
import os.path
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# If modifying these scopes, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

# The ID and range of a sample spreadsheet.
SAMPLE_SPREADSHEET_ID = '1srgTgCU1mhOiqV90DVb8_GVi0GBTivbhuj21jxr65Pk'
SAMPLE_RANGE_NAME = 'Ответы на форму (1)!A2:F'


def rows_to_json(config, rows):
    result = []
    for row in rows:
        person = dict()
        for field_name, field_index in config['fields'].items():
            person[field_name] = row[field_index] if len(row) > field_index else ''
        result.append(person)
    return result


def get_creds():
    creds = None
    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server()
        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    return creds


def get_rows(creds, sheet_id, range_name):
    service = build('sheets', 'v4', credentials=creds)
    # Call the Sheets API
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=sheet_id, range=range_name).execute()
    values = result.get('values', [])
    return values


def update_fields_with_default(
        people, defauld_filename='default_people_data.json', columns_to_update=None, key_columns=None
):
    if columns_to_update is None:
        columns_to_update = ['photo']
    if key_columns is None:
        key_columns = ['name']
    result = copy.deepcopy(people)
    with open(defauld_filename, 'r', encoding='utf-8') as f:
        default = json.load(f)
    dicts = {
        key_column: {
            person[key_column]: person
            for person in default
        }
        for key_column in key_columns
    }
    for person in result:
        for target_column in columns_to_update:
            # these are custom rules that invalidate some fields - specifically, photo
            if target_column == 'photo':
                if not re.match('^.*\.(jpg|jpeg|png|gif)$', person[target_column]):
                    person[target_column] = ''
            for key_column in key_columns:
                if person[target_column] != '':
                    break
                if person[key_column] not in dicts[key_column]:
                    continue
                person[target_column] = dicts[key_column][person[key_column]][target_column]
    return result


def main():
    """Shows basic usage of the Sheets API.
    Prints values from a sample spreadsheet.
    """
    creds = get_creds()

    values = get_rows(creds, SAMPLE_SPREADSHEET_ID, SAMPLE_RANGE_NAME)

    print('\n'.join(['<div>{}</div>'.format(row[1]) for row in values]))


if __name__ == '__main__':
    main()

